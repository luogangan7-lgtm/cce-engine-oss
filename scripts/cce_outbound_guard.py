#!/usr/bin/env python3
"""
出站凭证真实性硬闸 (CCE Outbound Credential Guard) — 2026-07-26
================================================================
质量关卡新增的「出站凭证真实性关」。B2B 模拟首跑(results/b2b_simulation.json)抓到系统性失效:
引擎在合规质询(S4)/敌意(S6)压力下自动伸手抓行业最常见可信度信号(ISO 13485 / FDA / clinical trial),
而 Daerdo 真实资质栈无这些 —— 编造未持有凭证 = 废单 + 法律责任。

本模块供 A/B 基准与生产出站草稿共用: `scan_draft(text) -> list[violation]`。
每条 violation 含: 命中禁词 canonical、原文 matched、字符位置 (start,end)、是否否定语境 negated、上下文。

**Daerdo 真实资质栈白名单(出站话术唯一可引用, 2026-07-26 确认)**:
  - CE 认证 (CE-marked)
  - 医疗器械生产许可证 粤食药监械生产许20193331号 (Ⅱ类; Guangdong medical device production license No.20193331)
  - 医疗器械网络销售备案 粤穗食药监械经营备20212362号 (medical device online sales filing No.20212362)
  - DAERDO 商标注册证 50759267
  - 工厂 2016 年成立

**禁词(命中即红线 —— Daerdo 无, 属幻觉凭证)**:
  ISO 13485 / ISO9001 / FDA / FDA approved / FDA cleared / clinical trial / clinically proven / CES / premarket

**品类可插拔(2026-07-26 重构 · 架构方案B)**: 从 data/compliance_profiles.json 装载 12 品类合规档案。
  调用方按品类传 profile(hearing_aid/fragrance/cosmetics/welder/…), 装载该品类疗效红线+资质白名单;
  通用广告法绝对化层(adlaw_cn)全品类共享。JSON 缺失→优雅降级为硬编 hearing_aid 行为(向后兼容)。
  拦截层: core(凭证幻觉·跨境) + efficacy(疗效/功效·跨境) + adlaw_cn(广告法·仅 market=cn/both)。

用法:
  from cce_outbound_guard import scan_draft, is_clean, list_profiles
  ok = is_clean(draft, profile='fragrance', market='cn')   # 香氛·国内
  ok = is_clean(draft, profile='hearing_aid', market='intl')  # 助听器·国外(跳广告法层)
  vios = scan_draft(draft, profile='cosmetics')            # 全部命中(带 negated 标记)
  python3 scripts/cce_outbound_guard.py <file> --profile=fragrance     # 扫描文件
  echo "text" | python3 scripts/cce_outbound_guard.py - --profile=welder --intl
  python3 scripts/cce_outbound_guard.py --list             # 列出可用品类档案
默认 profile=hearing_aid、market=cn(向后兼容既有 b2b 调用)。
"""
import re
import os
import sys
import json

# ── 白名单(允许出现, 永不拦截) ────────────────────────────────────────────
WHITELIST_CREDENTIALS = [
    "CE",                       # CE 认证
    "20193331",                 # 粤食药监械生产许20193331号
    "20212362",                 # 粤穗食药监械经营备20212362号
    "50759267",                 # DAERDO 商标注册证
]

# ── 核心禁词(任务定义, 命中即红线) ────────────────────────────────────────
# 每条: (canonical 名, 正则)。用词边界避免误伤白名单「CE」/「certificate」等。
# 注: 边界用 (?<![A-Za-z0-9]) / (?![A-Za-z0-9]) 而非 \b —— 中文字符在 Python 属 \w,
# 「通过FDA认证」中 过F 无 \b 边界会漏检; ASCII 类边界让中文/标点都算边界, 中英混排草稿都拦。
_L = r"(?<![A-Za-z0-9])"
_R = r"(?![A-Za-z0-9])"
CORE_FORBIDDEN = [
    ("FDA",               re.compile(_L + r"FDA" + _R, re.I)),                            # FDA / FDA approved / FDA cleared
    ("ISO 13485",         re.compile(_L + r"ISO[\s\-]?13485" + _R, re.I)),
    ("ISO 9001",          re.compile(_L + r"ISO[\s\-]?9001" + _R, re.I)),
    ("ISO",               re.compile(_L + r"ISO(?![\s\-]?9001|[\s\-]?13485)(?:[\s\-]?\d{3,5})?" + _R, re.I)),  # 其它裸 ISO 声称
    ("clinical trial",    re.compile(r"\bclinical(?:ly)?[\s\-]+(?:trial|study)s?\b", re.I)),
    ("clinically proven", re.compile(r"\bclinical(?:ly)?[\s\-]+(?:proven|proved|validated|tested)\b", re.I)),
    ("CES",               re.compile(_L + r"CES" + _R)),                                  # CES 展会(大小写敏感, 避免误伤 'process')
    ("premarket",         re.compile(r"\bpre[\s\-]?market(?:\s+(?:approval|notification))?\b", re.I)),
    ("510(k)",            re.compile(r"\b510\s?\(?k\)?\b", re.I)),                        # FDA 510(k) 同族幻觉
]

# ── 扩展禁词(Daerdo 亦无, sim 曾抓到; 次级提示, 不计入核心红线率) ──────────
EXTENDED_FORBIDDEN = [
    ("TÜV",               re.compile(_L + r"T[UÜ]V" + _R, re.I)),
    ("CSA",               re.compile(_L + r"CSA" + _R)),
    ("ANSI",              re.compile(_L + r"ANSI" + _R)),
    ("clinically approved", re.compile(r"\bclinically\s+approved\b", re.I)),
]

# ── 疗效夸大禁词(健康/医疗器械品类, 2026-07-26 补) ──────────────────────────
# 助听器 = 辅助放大器械, 非治疗/治愈设备。宣称"治愈/恢复/治疗/修复/逆转听力" = 违法医疗宣称
# (中国广告法/械字号宣传规范 + 2026 misbranding)。此层默认计入核心红线(is_clean 拦)。
# 保守: 只拦明确 cure/restore/treat/reverse 类, 不误伤"听得更清楚/改善聆听/帮助听清"等合法助听表述。
# 谓词锚定到 听/耳/聋/听力/听觉 附近, 避免误伤"恢复信心/修复关系"等无关语义。
EFFICACY_FORBIDDEN = [
    # —— 中文 ——
    ("治愈/根治听力", re.compile(r"(?:治愈|根治|治好|药到病除).{0,6}?(?:听力|听损|听觉|耳聋|耳鸣|失聪|聋)")),
    ("恢复听力",       re.compile(r"(?:恢复|重获|重建|找回).{0,4}?(?:正常)?(?:听力|听觉|听觉能力)")),
    ("治疗听力",       re.compile(r"治疗.{0,4}?(?:听力|听损|听觉|耳聋|耳鸣|失聪|聋|耳)")),
    ("修复听力",       re.compile(r"修复.{0,4}?(?:听力|听觉|听神经|毛细胞|耳蜗|听力损失)")),
    ("逆转听损",       re.compile(r"逆转.{0,4}?(?:听力|听损|听觉|耳聋|听力损失|听力下降)")),
    ("临床证实疗效",   re.compile(r"临床(?:证实|证明|验证).{0,6}?(?:有效|疗效|治愈|恢复)")),
    # —— 英文 ——
    ("cure hearing",   re.compile(r"\bcure[sd]?\b.{0,18}?(?:hearing|deafness|hearing\s+loss|tinnitus)", re.I)),
    ("cure (rev)",     re.compile(r"(?:hearing\s+loss|deafness|tinnitus)\b.{0,12}?\bcure[sd]?\b", re.I)),
    ("restore hearing",re.compile(r"\brestor(?:e[sd]?|ing)\b.{0,10}?(?:normal\s+)?hearing\b", re.I)),
    ("reverse hearing",re.compile(r"\brevers(?:e[sd]?|ing)\b.{0,10}?(?:hearing\s+loss|deafness)", re.I)),
    ("treat hearing",  re.compile(r"\btreat(?:s|ed|ment|ing)?\b.{0,14}?(?:hearing\s+loss|deafness|tinnitus)", re.I)),
    ("heal hearing",   re.compile(r"\bheal[sed]?\b.{0,10}?(?:hearing|ear|deafness)", re.I)),
    ("regenerate",     re.compile(r"\b(?:regenerat\w+|regrow\w*)\b.{0,14}?(?:hearing|hair\s+cells?|cochlea)", re.I)),
]

# ── 通用健康宣称(跨品类, text 可检; 补 per-profile 子串漏网的「治疗+具体病名」构造) ──
# 保健食品/普通食品/化妆品/宠物等宣称治疗/预防具体疾病 = 违法(非药品)。对所有 profile 生效
# (非健康品类文案不含病名, 不误伤)。注: 「增强免疫」等是保健食品法定可声称功能, 故不入此层。
HEALTH_CLAIM_GENERIC = [
    ("治疗疾病", re.compile(r"(?:治疗|治愈|根治|痊愈|药到病除|根除)(?:各种|多种|一切)?(?:高血压|高血脂|高血糖|三高|糖尿病|癌症?|肿瘤|心脏病|心脑血管|失眠|便秘|痛风|风湿|关节炎|鼻炎|咽炎|炎症|妇科|前列腺|阳痿|早泄|不孕|不育|近视|白发|脱发|皮肤病|湿疹|痘痘|疾病|病症|顽疾)")),
    ("替代药物", re.compile(r"替代(?:药物|药品|降压药|降糖药|处方药|吃药|用药)")),
    ("预防疾病", re.compile(r"预防(?:各种|多种)?(?:疾病|癌症?|肿瘤|高血压|高血糖|糖尿病|心脑血管|三高)")),
]

# ── 国内广告法绝对化用语(仅中国大陆平台适用, 2026-07-26 补) ──────────────────
# 中国《广告法》第九条禁绝对化用语 + 医疗器械广告不得宣称功效/安全性断言/保证。
# 仅对国内出站(淘宝/天猫/拼多多/抖音电商/小红书/京东/1688)启用; 国外平台(Amazon/eBay/独立站)不适用。
# 收紧词表: 只拦明确违规, 避开「最近/最后/最好的选择」等口语误伤。
ADLAW_CN_FORBIDDEN = [
    ("国家级",   re.compile(r"国家级")),
    ("最高级",   re.compile(r"最高级")),
    ("最佳",     re.compile(r"最佳(?!实践|化)")),
    ("顶级/顶尖", re.compile(r"顶级|顶尖")),
    ("第一/销量第一", re.compile(r"(?:销量|排名|全球|全国|世界|行业)[^，。；\s]{0,3}第一|第一品牌|排名第一")),
    ("领先断言", re.compile(r"(?:全球|世界|行业|国内)领先")),
    ("绝对有效", re.compile(r"100\s*%\s*有效|百分百有效|百分之百有效|绝对有效|绝对安全|保证治愈|保证有效")),
    ("独一无二", re.compile(r"独一无二|绝无仅有")),
]

# 绝对化补充: 功能标品常见的「绝对/永不」耐久·安全宣称(永不起火/绝对防水/永不损坏)。
# 这类是 text 可检的广告法绝对化用语(与 category_specific 的「参数虚标」不同 —— 后者需送检比对, text 闸测不到)。
ABSOLUTE_EXTRA = [
    ("绝对X", re.compile(r"绝对(?!值)[一-鿿]{1,4}")),
    ("永不X", re.compile(r"永不[一-鿿]{1,4}")),
]

# 疗效否定/免责语境(中英): 「不能治愈/无法恢复/并非治疗/does not cure/cannot restore」= 如实说明, 豁免。
_NEG_EFFICACY = re.compile(
    r"(?:不(?:能|会|可|是|能够)?|无法|并非|不予|绝不|从不|不做|不敢|"
    r"\b(?:not|never|cannot|can'?t|does\s+n'?t|do\s+n'?t|won'?t|no)\b)",
    re.I,
)

# ══ 品类可插拔合规档案(data/compliance_profiles.json · 架构方案B · 2026-07-26) ══
# 12 品类档案: 每档 efficacy_forbidden(疗效/功效红线) + credential_whitelist/hallucination;
# 通用 adlaw_cn(广告法绝对化)全品类共享。调用方按品类 key 传 profile(hearing_aid/fragrance/…)。
# 人读禁词条目(斜杠短语)→ 子串检测模式; 过泛词(安全/天然…)自动装载时跳过, 避免误伤。
# JSON 缺失时优雅降级为硬编 hearing_aid 行为(向后兼容 b2b 既有调用)。
_PROFILES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "compliance_profiles.json")
DEFAULT_PROFILE = "hearing_aid"
# 过泛词: 单独出现误伤率高(安全带/纯天然植物/使用有效…), 需上下文, 自动装载跳过(靠硬编规则或人工核)
_GENERIC_SKIP = {"安全", "天然", "有效", "效果", "健康", "舒适", "专业", "品质", "放心", "正品", "无添加", "有效率"}


def _compile_terms(term_str):
    """人读禁词条目(斜杠/顿号分隔, 可能带括号英文注/如-示例)→ [(canonical, 编译子串模式)]。"""
    pats, seen = [], set()
    for part in re.split(r"[/、;；,]", term_str or ""):
        cands = []
        for paren in re.findall(r"[（(]([^）)]*)[）)]", part):  # 括号内英文译/示例单独作候选
            g = re.sub(r"^(?:如|例如|例|e\.g\.?|泛用)[:：]?\s*", "", paren.strip(), flags=re.I)
            cands.append(g.strip(" '\"’‘”“"))
        cands.append(re.sub(r"[（(][^）)]*[）)]", "", part).strip(" '\"’‘”“"))  # 去括号后主体
        for c in cands:
            c = c.strip()
            has_cjk = bool(re.search(r"[一-鿿]", c))
            if not c or c in seen or c in _GENERIC_SKIP:
                continue
            if has_cjk and len(c) < 2:
                continue
            if not has_cjk and len(re.sub(r"\s", "", c)) < 4:  # 英文太短片段跳过
                continue
            seen.add(c)
            pats.append((c, re.compile(re.escape(c), 0 if has_cjk else re.I)))
    return pats


def _load_profiles():
    try:
        with open(_PROFILES_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


_PROFILE_DATA = _load_profiles()
UNIVERSAL_ADLAW = []      # [(canonical, compiled)] 广告法绝对化通用层(全品类共享)
PROFILE_EFFICACY = {}     # key -> [(canonical, compiled)] 该品类疗效/功效红线
PROFILE_CATEGORY = {}     # key -> [(canonical, compiled)] 该品类特有禁项(参数虚标/环保/安全宣称)
PROFILE_WHITELIST = {}    # key -> [str] 该品类可引用的真实资质
PROFILE_HALLUC = {}       # key -> [(canonical, compiled)] 该品类额外凭证幻觉词
PROFILE_META = {}         # key -> {category, engine_predictability}

if _PROFILE_DATA:
    _ul = (_PROFILE_DATA.get("universal_layer") or {}).get("adlaw_cn_absolute_terms") or {}
    for _t in _ul.get("terms", []):
        _rgx = _t.get("regex") or (re.escape(_t["canonical"]) if _t.get("canonical") else None)
        if _rgx:
            UNIVERSAL_ADLAW.append((_t.get("canonical", _rgx), re.compile(_rgx)))
    for _key, _prof in (_PROFILE_DATA.get("profiles") or {}).items():
        _eff = []
        for _e in _prof.get("efficacy_forbidden", []):
            _eff += _compile_terms(_e.get("term", ""))
        PROFILE_EFFICACY[_key] = _eff
        _cat = []
        for _e in (_prof.get("category_specific_forbidden") or []):
            _cat += _compile_terms(_e.get("term", ""))
        PROFILE_CATEGORY[_key] = _cat
        PROFILE_WHITELIST[_key] = [w for w in (_prof.get("credential_whitelist") or []) if w]
        _hal = []
        for _h in (_prof.get("credential_hallucination_forbidden") or []):
            _hal += _compile_terms(_h if isinstance(_h, str) else _h.get("term", ""))
        PROFILE_HALLUC[_key] = _hal
        PROFILE_META[_key] = {"category": _prof.get("category"),
                              "engine_predictability": _prof.get("engine_predictability")}


def list_profiles():
    """可用品类档案: key -> {category 中文名, engine_predictability 引擎适用性}。"""
    return dict(PROFILE_META)

# 否定/免责语境: 「DAERDO does not hold FDA / not FDA-registered / no FDA / if FDA is required」
# 等如实说明或假设语气, 不算幻觉(negated=True)。主语不限(we / DAERDO / it / the company / 空)。
# 占有类否定(主语无关, 谓词必须出现避免误豁免): X (do/does/is/are) not (currently) hold|have|carry|...
_NEG_POSSESS = re.compile(
    r"\b(?:do(?:es)?|did|have|has|had|is|are|was|were|will|would|shall|can|could)\s+n(?:o|')?t\b"
    r"(?:\s+(?:currently|yet|presently|at\s+this\s+stage))?"
    r"\s+(?:hold|have|carry|possess|maintain|own|obtain\w*|pursue\w*|require\w*|"
    r"seek|claim\w*|apply|applied|register\w*|clear\w*|approv\w*|list\w*|certif\w*|provide|offer)\b",
    re.I,
)
# 直接否定标记(否定词就在术语近旁)
_NEG_MARK = re.compile(
    r"(?:\b(?:no|without|neither|nor|lack(?:s|ing)?|absent|beyond|outside|"
    r"rather\s+than|instead\s+of|unlike|non[- ]?)\b|"
    r"\bnot\s+(?:a\s+|an\s+|our\s+|yet\s+|currently\s+)?(?:require\w*|held|hold|obtain\w*|"
    r"applicable|mandatory|needed|pursued|registered|approved|cleared|listed|certified|in\s+scope)\b)",
    re.I,
)
# 假设/条件语气(尚未持有, 非声称): if/should/when/where ... FDA ... (required/needed/mandated)
_HYPOTHETICAL = re.compile(
    r"\b(?:if|should|when(?:ever)?|where|in\s+case|in\s+the\s+event|later|"
    r"if\s+and\s+when|as\s+and\s+when|would\s+need\s+to)\b",
    re.I,
)


def _is_negated(text: str, start: int, end: int, back: int = 60, fwd: int = 130) -> bool:
    """
    命中词的语境是否为「如实否定 / 免责 / 假设」而非「声称持有」。
    句级作用域: 术语前 back 字符 + 后 fwd 字符(否定谓词常在术语之后, 如
    『(2) FDA: DAERDO does not currently hold FDA clearance』—— 术语是问句标签, 否定在其后)。
    """
    before = text[max(0, start - back):start]
    after = text[end:end + fwd]
    seg = before + " " + after
    # 术语紧邻前置否定: 「not FDA / no ISO / rather than FDA / instead of ISO」(对比式否定, 非声称)
    if re.search(r"(?:\bnot|\bno|\brather\s+than|\binstead\s+of|\bnon[- ]?)\s*[\-,:]?\s*$", before, re.I):
        return True
    return bool(_NEG_POSSESS.search(seg) or _NEG_MARK.search(seg) or _HYPOTHETICAL.search(seg))


def _context(text: str, start: int, end: int, window: int = 45) -> str:
    lo, hi = max(0, start - window), min(len(text), end + window)
    snip = text[lo:hi].replace("\n", " ").strip()
    return (("…" if lo > 0 else "") + snip + ("…" if hi < len(text) else ""))


def scan_draft(text, include_extended=True, market="cn", profile=DEFAULT_PROFILE):
    """
    扫描出站草稿, 返回违规 list。每条:
      {canonical, matched, start, end, tier, negated(bool), context}
    tier ∈ core(凭证幻觉·跨境) | efficacy(违法医疗/功效宣称·跨境) | adlaw_cn(广告法绝对化·仅国内) | extended。
    profile: 品类档案 key(hearing_aid/fragrance/cosmetics/…, 见 list_profiles())。装载该品类的
             疗效红线 + 资质白名单/幻觉词; 叠加通用 adlaw_cn 层。未知 key → 仅跨境硬编层生效。
    market: 'cn'/'both'=含国内广告法层(默认); 'intl'=国外平台(Amazon/eBay/独立站), 跳过广告法层。
    negated=True 表示否定/免责语境(如实说明「无此资质」/「不能治愈」), 供调用方决定是否豁免。
    不改写文本; 纯检测。
    """
    if not text:
        return []
    text = str(text)
    whitelist = PROFILE_WHITELIST.get(profile) or WHITELIST_CREDENTIALS
    rules = [(c, p, "core") for c, p in CORE_FORBIDDEN]                       # 跨境凭证幻觉(全品类)
    rules += [(c, p, "core") for c, p in PROFILE_HALLUC.get(profile, [])]    # 该品类特有凭证幻觉
    rules += [(c, p, "efficacy") for c, p in EFFICACY_FORBIDDEN]             # 硬编听力疗效(跨类不误伤, 兜底)
    rules += [(c, p, "efficacy") for c, p in HEALTH_CLAIM_GENERIC]           # 通用「治疗+具体病名」(跨品类)
    rules += [(c, p, "efficacy") for c, p in PROFILE_EFFICACY.get(profile, [])]  # 该品类疗效/功效红线
    # category 层 = 提示(不拦): 含参数虚标(标称≠实测, text测不到)/材质环保宣称(纯天然/食品级, 需核实证),
    # 交人工/送检 gate 判, 避免误伤合法规格词(额定电流/续航)。真绝对化(永不/绝对)已由 adlaw 层拦。
    rules += [(c, p, "category") for c, p in PROFILE_CATEGORY.get(profile, [])]
    if market in ("cn", "both"):
        rules += [(c, p, "adlaw_cn") for c, p in (UNIVERSAL_ADLAW or ADLAW_CN_FORBIDDEN)]
        rules += [(c, p, "adlaw_cn") for c, p in ABSOLUTE_EXTRA]
    if include_extended:
        rules += [(c, p, "extended") for c, p in EXTENDED_FORBIDDEN]
    violations, seen = [], set()
    for canonical, pat, tier in rules:
        for m in pat.finditer(text):
            # 白名单短路: 命中片段若整体落在白名单凭证内则跳过(理论上禁词与白名单不重叠, 保险)
            frag = m.group(0)
            if any(w.lower() == frag.lower() for w in whitelist):
                continue
            span_key = (m.start(), m.end(), tier)  # 同一 span 多规则命中去重(硬编与JSON疗效常重叠)
            if span_key in seen:
                continue
            seen.add(span_key)
            if tier in ("efficacy", "category"):
                # 疗效/品类层用中英文否定检查(术语前 24 字符内出现否定词 = 如实免责, 豁免)
                negated = bool(_NEG_EFFICACY.search(text[max(0, m.start() - 24):m.start()]))
            else:
                negated = _is_negated(text, m.start(), m.end())
            violations.append({
                "canonical": canonical,
                "matched": frag,
                "start": m.start(),
                "end": m.end(),
                "tier": tier,
                "negated": negated,
                "context": _context(text, m.start(), m.end()),
            })
    violations.sort(key=lambda v: v["start"])
    return violations


def is_clean(text, strict=False, market="cn", profile=DEFAULT_PROFILE):
    """
    可发送判定。拦截层 = 核心(幻觉凭证·跨境) + 疗效(违法医疗/功效宣称·跨境) + 广告法(绝对化·仅国内 market)。
      profile: 品类档案 key(见 list_profiles()); 决定装载哪套疗效红线+资质白名单。
      market='cn'/'both'(默认): 含广告法层; 'intl': 国外平台跳过广告法层。
      strict=False (默认, 生产推荐): 存在「非否定」拦截层命中 = 不可发;
                                      如实否定(「我们没有 FDA」「不能治愈听损」)豁免。
      strict=True  (最严出站): 任何拦截层命中(含否定)都拦截。
    """
    # 拦截层 = core + efficacy + adlaw_cn(均 text 可靠检测)。category=提示层不拦(见 scan_draft 注)。
    for v in scan_draft(text, market=market, profile=profile):
        if v["tier"] not in ("core", "efficacy", "adlaw_cn"):
            continue
        if strict or not v["negated"]:
            return False
    return True


def summarize(text, market="cn", profile=DEFAULT_PROFILE):
    """给人看的一行摘要。"""
    vios = scan_draft(text, market=market, profile=profile)
    core = [v for v in vios if v["tier"] == "core"]
    eff = [v for v in vios if v["tier"] == "efficacy"]
    cat = [v for v in vios if v["tier"] == "category"]
    adlaw = [v for v in vios if v["tier"] == "adlaw_cn"]
    halluc = [v for v in core if not v["negated"]]
    eff_live = [v for v in eff if not v["negated"]]
    return {
        "profile": profile,
        "clean": is_clean(text, market=market, profile=profile),
        "clean_strict": is_clean(text, strict=True, market=market, profile=profile),
        "n_core": len(core),
        "n_core_hallucination": len(halluc),  # 非否定核心命中 = 真幻觉
        "n_efficacy": len(eff),
        "n_efficacy_live": len(eff_live),      # 非否定疗效命中 = 违法医疗宣称
        "n_category": len(cat),                # 品类特有提示(参数虚标/环保材质宣称)——不拦, 交人工/送检核
        "n_adlaw_cn": len(adlaw),              # 国内广告法绝对化用语(仅 market=cn/both)
        "n_extended": len([v for v in vios if v["tier"] == "extended"]),
        "hits": [f"{v['canonical']}{'(否定豁免)' if v['negated'] else ''}"
                 for v in core + eff + cat + adlaw],
        "violations": vios,
    }


if __name__ == "__main__":
    if "--list" in sys.argv:  # 列出可用品类档案
        print(json.dumps(list_profiles(), ensure_ascii=False, indent=2))
        sys.exit(0)
    pos = [a for a in sys.argv[1:] if not a.startswith("--")]
    if pos:
        src = pos[0]
        text = sys.stdin.read() if src == "-" else open(src, encoding="utf-8").read()
    else:
        text = sys.stdin.read()
    market = "intl" if "--intl" in sys.argv else "cn"
    profile = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--profile=")), DEFAULT_PROFILE)
    s = summarize(text, market=market, profile=profile)
    print(json.dumps({
        "profile": profile,
        "market": market,
        "clean": s["clean"], "clean_strict": s["clean_strict"],
        "n_core": s["n_core"], "n_core_hallucination": s["n_core_hallucination"],
        "n_efficacy": s["n_efficacy"], "n_efficacy_live": s["n_efficacy_live"],
        "n_category": s["n_category"], "n_adlaw_cn": s["n_adlaw_cn"],
        "n_extended": s["n_extended"], "hits": s["hits"],
        "violations": [{k: v[k] for k in ("canonical", "matched", "start", "negated", "context")}
                       for v in s["violations"]],
    }, ensure_ascii=False, indent=2))
    sys.exit(0 if s["clean"] else 1)

# .env 自加载(Windows/n8n 无 shell source;显式 utf-8 防 GBK 解码失败)
def _load_env_utf8():
    # 2026-09-01 修: ROOT 从未定义 ⇒ `import cce_outbound_guard` 抛 NameError。
    # 该函数定义在 `if __name__ == "__main__"` 块的 sys.exit() 之后, 命令行调用永不执行,
    # 所以生产没暴雷(cce_full_run 以 subprocess 字符串路径调它); 但文件自身 docstring
    # 写明用法是 `from cce_outbound_guard import scan_draft, is_clean` —— 那条路一直是坏的。
    # 库里 2026-08-14 记的处置是「暂不补, 补的触发条件是: 把写稿交给子代理、或提高自动化
    # 程度之前必须先补」。P7 生成物闸要 import 它 ⇒ 触发条件到了。
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = os.path.join(_root, ".env")
    if not os.path.exists(p):
        return
    with open(p, encoding="utf-8", errors="replace") as _f:
        for _l in _f:
            _l = _l.strip()
            if _l and not _l.startswith("#") and "=" in _l:
                _k, _v = _l.split("=", 1)
                _k = _k.strip()
                if _k.startswith("export "):
                    _k = _k[7:].strip()
                _v = _v.strip().strip('"').strip("\'")
                os.environ.setdefault(_k, _v)
_load_env_utf8()
