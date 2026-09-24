# -*- coding: utf-8 -*-
"""引用证书 —— 生产模块(2026-09-24 owner「接吧」, 预注册 v3 ad5deee4 判 ADOPT_SHADOW 后接线)。

★ 验证器部分(normalize_about / _clean_kind / _parse / classify_refusal / declared_objects / _granularity / _judge 与常量)是
  probes/extractor_counterexample_run_r2.py 的**逐字复制**(由 tests/test_cce_s2b_citation_shadow.py 按 AST 切片逐字比对; 任一侧漂移即红)。
  生产不许 import 探针(module_boundary), 所以复制而不是引用; 复制的正确性由闸守, 不靠人记。
★ 采集部分(kind_menu / prompt_v3 / repair_prompt / reason_codes)是 probes/citation_certificate_protocol_v3.py 的同源实现(r2. 前缀改为本模块名)。
★ shadow_certificates(): 影子段 —— 两张证书并发, 都 UPGRADED 且见证交集非空 ⇒ CITED_UNVERIFIED; 否则候选。citable_as_confirmed 恒 False。
   产物只落 sha16 / 结局 / 原因码 / 耗时, 不落 span/object/why。
"""
import hashlib, json, os, pathlib, re, sys, time
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
_TAXO = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
DISC = next(k["hard_discriminant"] for k in _TAXO["knots"] if k["key"] == "display")   # r2 取自模板档案; 闸核两者相等
TPL = {"★合同原文": DISC}

# ── ② object 规范化: **测量前冻结**, 规则写死在这里 ──────────────────────
_TRAIL_PAREN = re.compile(r"\s*[（(][^）)]*[）)]\s*$")

# ★★★ 只剥**冠词**。2026-09-14 第二轮评审抓到: 原表含 my/your/his/her/their/its ⇒
#   「my Oticon」与「his Oticon」被抹成同一个对象, 而 Q 支要的正是**自己的** ——
#   那等于用规范化把被测的那一支抹掉了。
_LEAD_DET = re.compile(r"^(?:(?:the|a|an)\s+)+", re.I)

_EDGE = " \t　.,;:!?\"'`·。，、；：！？“”‘’"

def normalize_about(s):
    """★★★ 冻结的规范化规则, 只做三件事, 一件都不多:
      ① 去**尾部括注**     —— 记录 r1 的实测拦点(「the loaner ReSound Nexia (personally worn)」
                              与「the loaner ReSound Nexia」被判成两个对象)。
                              ★ 在 r2 **不可达**: object 必须逐字取自原文, 而 16 条文本零括号
                              ⇒ 带括注的 object 取不出来。保留它是为了留档, 不是为了本轮生效。
      ② 去**前导冠词**     —— the/a/an (可重复)。**刻意不含**物主/指示代词:
                              抹平 my/his/their 会把 Q 支要的「自己的」一起抹掉。
      ③ 去**首尾标点空白**
    **不做**: 别名归并 · 子串包含 · 词干还原 · 语义相似。
    ⇒ 「Phonak Audeo Sphere」与「something far simpler」规范化后仍是两个对象(对象错配臂不受影响)。
    """
    if not isinstance(s, str):
        return s
    s = s.strip()
    prev = None
    while prev != s:                      # 括注可能嵌两层
        prev = s
        s = _TRAIL_PAREN.sub("", s).strip()
    s = _LEAD_DET.sub("", s).strip()
    return s.strip(_EDGE)

PROMPT = """你在核验一条**已经定好的**标注。标签是 `display`。

`display` 的判别式(逐字):
%s

这个判别式要求**同时**满足两个必要条件:
  A = 输出新信息增量
  B = 谈论对象是自己已拥有或已经历的

文本:
\"\"\"%s\"\"\"

请判断:这段文本**是否真的**满足该判别式。如果满足,请给出证据 —— 每条证据是一段**逐字出现在上面文本里的**原文片段,并说明它支撑 A 还是 B。

只输出 JSON,不要别的:
{
  "supported": true 或 false,
  "evidence": [
    {
      "span": "逐字出现在上面文本里的片段",
      "supports": "A" 或 "B",
      "object": "逐字出现在上面文本里的片段:这条片段所陈述的那个**东西本身**在原文里的名称(是那个产品/设备/物件本身,**不是**它的某个部件、功能或属性;若原文多处提到同一个,取**最短**的那个完整指称,不要带所有格前缀、修饰从句或用途说明)",
      "increment_kind": "仅当 supports 为 A 时填:这段增量属于上面判别式所列的哪一种,照判别式里的措辞原样写,**只写其中一种**,不要连写多种;supports 为 B 时填 null"
    }
  ],
  "why_not": "supported 为 false 时,一句话说明差在哪;否则填 null"
}
supported 为 false 时,evidence 填空数组 []。
所有 span 与 object 都必须**逐字**出自上面的文本。不要改写、不要合并不相邻的词。"""

def _parse(raw):
    """抠出第一个 JSON 对象。抠不出 ⇒ 记为格式失败, **不重试**。"""
    s = raw.find("{")
    if s < 0:
        return None
    depth = 0
    for i in range(s, len(raw)):
        if raw[i] == "{":
            depth += 1
        elif raw[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(raw[s:i + 1])
                except Exception:
                    return None
    return None

CONJ = {"A": "输出新信息增量", "B": "谈论对象是自己已拥有或已经历的"}

# ══ 结局分类法(测量前冻结) ════════════════════════════════════════════
#   ★★★ 第二轮评审抓到: 原来的 compliant 记的是「**够得着** qualify()」而不是「格式合规」。
#   qualify() 里有四条**非语义**出口(missing / anon / 无 kind / 只复述标识符)全被记成合规,
#   于是 r1 的粒度退化换成**逐字方面名词**('a charge'/'wax guards'/'its app')后整批落进
#   compliant=1 / Z=0, 两条降级一条都不响 ⇒ 旧故障被洗成「判决按字面读」。
#   ⇒ 改成按 qualify() 的**真实出口**分类。
REFUSED_RIGHT = "REFUSED_RIGHT_CONJUNCT"   # 拒答, 且 why_not 命名了构造规则声明失败的那一支

REFUSED_OTHER = "REFUSED_OTHER"            # 拒答, 但没命名对(或没给理由)

MALFORMED = "MALFORMED"                    # span/object 非逐字 · supports 无效 · kind 无效 · evidence 形状错

COVERAGE_FAIL = "COVERAGE_FAIL"            # 合取项缺支撑 · 未指名对象 · 增量支没写种类 · 只复述标识符

GRANULARITY = "OBJECT_MISMATCH_GRANULARITY"  # P2 失败, 一方规范化后是另一方**真子串** ⇒ 与 r1 同因的仪器伪影

DISTINCT = "OBJECT_MISMATCH_DISTINCT"      # P2 失败, 互不包含 ⇒ 真·不同对象(对象错配臂期望的)

UPGRADED = "UPGRADED"                      # Z=1 —— 阴性上出现即**错误升格见证**

ADJUDICATED = (COVERAGE_FAIL, GRANULARITY, DISTINCT, UPGRADED)   # 真正被资格层裁决过

ISSUED = (MALFORMED,) + ADJUDICATED                              # 交了卷

# ★ why_not 的锚词表 —— **测量前冻结**, 由构造规则确定, 不由模型输出决定。
#   ★★★ 它只验**命名了哪一支**, **不验**推理对不对 —— 与逐字引文核对是同一类局限。
ANCHORS = {
    "P": ("增量", "型号", "数据", "使用细节", "纠错", "结构化经验", "新信息",
          "increment", "model number", "specific"),
    "Q": ("拥有", "经历", "用过", "戴过", "持有", "自己的", "并非自己",
          "own", "tried", "worn", "never", "experienc"),
    "SAME_OBJECT": ("同一", "同一个", "不同对象", "不同的对象", "两个对象", "不是同一",
                    "same object", "different object"),
}

def classify_refusal(t, obj):
    """拒答时, 看 why_not 有没有命名**构造规则声明失败的那一支**。

    ★★★ 为什么阴性上的拒答不是「没测到」: 在阴性上, **正确拒答就是期望行为**。
      r1 把它记成「未交卷」并触发降级 ⇒ 把**最好的结局**判成了不可读。
      (实测: 那条降级要求模型在 12 条构造阴性上主动断言 display 成立 >=4 次, 而 r1 先验是 1/12。)
    """
    want = t.get("★构造规则声明失败的那一支")
    if not want:
        return REFUSED_OTHER
    why = str((obj or {}).get("why_not") or "")
    return REFUSED_RIGHT if any(k in why for k in ANCHORS[want]) else REFUSED_OTHER

def _clean_kind(k):
    """只做**表面清洗**: 去首尾空白与中英引号。枚举成员资格的判定一个字不变。

    ★ 起因: 判别式原文里五类是**斜杠连写**的「(具体型号/数据/使用细节/纠错/结构化经验)」,
      而 r2 为了让该闸不恒真撤掉了选项菜单, 改成「照判别式里的措辞原样写」
      ⇒ 模型抄成「具体型号/数据」或带尾空格是可预期的。
    ★ 这与 object 的规范化是**同一个论证**: 消除表面变体, 不放松判据。
      「具体型号/数据」清洗后仍不在枚举里, 仍判 MALFORMED —— 那是真的没对应上。
    """
    if not isinstance(k, str):
        return None
    return k.strip().strip("\"'「」『』“”‘’ ") or None

def declared_objects(t):
    """该模板**测量前声明**的对象集合(规范化后)。

    正证据/缺P/否定Q 各声明 1 个; 对象错配声明 2 个。
    ★ 这些声明写在模板档案里、在任何调用之前冻结, 不由模型输出决定。
    """
    got = list(t.get("★可接受的逐字对象名") or [])
    got += [t.get("★可共享的逐字对象名"), t.get("about"), t.get("about_P"), t.get("about_Q")]
    return {normalize_about(x) for x in got if x}

def _granularity(t, objs):
    """P2 失败时, 这是**仪器伪影**还是**真·不同对象**?

    ★★★ 判据不是子串关系 —— 逐字约束之后, r1 的死因换了形态:
      「方面」不再是含对象名的描述短语(「Oticon More 1 助听器**的电池续航表现**」),
      而是一个**独立名词**('a charge' / 'wax guards' / 'its app'), 它**不含**对象名,
      子串测试测不到。
    ⇒ 改用**档案声明**: 两个 object 里只要有一个**不在**该模板声明的对象集合里,
      说明模型在某一支上指到了档案没预期的东西(部件/属性/别的名词) ⇒ 与 r1 同因的通道故障。
      两个都在声明集合里 ⇒ 模型指到的确实是那两个不同的物 ⇒ 对象错配臂期望的结局。
    """
    dec = declared_objects(t)
    return not set(objs).issubset(dec)

def _judge(t, obj):
    """把模型交出的证书送进**现有资格层**, 返回 (outcome, why, state)。

    ★ 这里**不替模型补任何字段**: span / supports / object / increment_kind 缺一,
      该条证据就带着它的缺失去撞 fail-closed 分支。
    ★ 结局取自上面冻结的分类法; Z=1 ⟺ outcome == UPGRADED。
    """
    import cce_label_qualification as LQ

    def _out(oc, why, st=None):
        return oc, why, st

    if not obj or not obj.get("supported"):
        return _out(classify_refusal(t, obj),
                    "模型判**不支持**; why_not=%r" % (str((obj or {}).get("why_not") or "")[:110],))
    ev_in = obj.get("evidence") or []
    if not isinstance(ev_in, list) or not ev_in:
        return _out(MALFORMED, "交了卷但 evidence 为空或形状不对")
    ev = []
    for e in ev_in:
        if not isinstance(e, dict):
            return _out(MALFORMED, "evidence 元素不是对象")
        sup = CONJ.get(str(e.get("supports", "")).strip().upper())
        if sup is None:                                  # ③ 模型自己填错条款 ⇒ 可达的失败
            return _out(MALFORMED, "证据没有对应到 A/B 任一必要条件: %r" % (e.get("supports"),))
        raw_obj = e.get("object")
        if not isinstance(raw_obj, str) or raw_obj.strip() not in t["text"]:
            return _out(MALFORMED, "object **不是原文逐字片段**: %r" % (raw_obj,))
        raw_obj = raw_obj.strip()
        raw_span = e.get("span") or ""
        # ★★★ 附件 A 那道闸必须在**原样**上算, 不能吃规范化的红利。
        #   第二轮评审实测: about 被剥掉「the」而 span 没剥 ⇒ 残余里留下「the」冒充内容
        #   ⇒ 「只复述型号名」的证书能拿到 Z=1 ⇒ **伪造**出 COUNTEREXAMPLE_FOUND 终局判决。
        #   6/12 阴性可凭此通过(NEGP-4 / NEGQ-1..4 / MIS-4, 反事实对照已实算)。
        if sup == CONJ["A"]:
            # ★★★ 两边都规范化后再算残余。只在原样上算会留一个洞:
            #   span='the Oticon Intent' + object='Oticon Intent' ⇒ 残余 'the'(3 字符)过闸
            #   ⇒ 纯复述型号名的证书拿到 UPGRADED ⇒ **伪造** COUNTEREXAMPLE_FOUND 终局判决。
            #   零调用实测: 6/12 阴性可走这条路。
            rest = "".join(normalize_about(raw_span)
                           .replace(normalize_about(raw_obj), " ").split())
            if len(rest) < 2:
                return _out(COVERAGE_FAIL,
                            "增量支去掉**原样**对象标识后没剩下内容(附件 A: 复述型号名不产生增量): "
                            "span=%r object=%r" % (raw_span[:60], raw_obj))
        try:
            ev.append(LQ.EvidenceSpan(raw_span, sup, t["text"],
                                      about=normalize_about(raw_obj) or None,
                                      increment_kind=_clean_kind(e.get("increment_kind"))))
        except Exception as ex:
            return _out(MALFORMED, "证书构造即被拒(span 非逐字 / kind 不在枚举内): %s"
                        % str(ex).split("\n")[0][:130])
    q = LQ.qualify("display", t["text"], evidence=ev,
                   required_conjuncts=[CONJ["A"], CONJ["B"]])
    why, st = q["why"][:220], q["state"]
    if st == LQ.CITED_UNVERIFIED:
        return _out(UPGRADED, why, st)
    used = [x for x in ev if x.supports in (CONJ["A"], CONJ["B"])]
    objs = sorted({x.about for x in used if x.about})
    if "落在**不同对象**上" in why:
        return _out(GRANULARITY if _granularity(t, objs) else DISTINCT, why, st)
    return _out(COVERAGE_FAIL, why, st)      # missing / anon / 无 kind 等非语义出口


# ══ 采集协议 v3(同源于 probes/citation_certificate_protocol_v3.py) ═══════════════════════════════════
E_JSON, E_SHAPE, E_SUPPORTS, E_SPAN, E_OBJECT, E_KIND_MENU, E_KIND_MULTI, E_KIND_ON_B = ("E_JSON", "E_EVIDENCE_SHAPE", "E_SUPPORTS_INVALID", "E_SPAN_NOT_VERBATIM", "E_OBJECT_NOT_VERBATIM", "E_KIND_NOT_IN_MENU", "E_KIND_MULTI", "E_KIND_ON_B")
CODES = (E_JSON, E_SHAPE, E_SUPPORTS, E_SPAN, E_OBJECT, E_KIND_MENU, E_KIND_MULTI, E_KIND_ON_B)

def kind_menu(disc=None):
    """五类名字从判别式括号里机械导出: 「(具体型号/数据/使用细节/纠错/结构化经验)」→ 列表。"""
    m = re.search(r"[（(]([^）)]*)[）)]", disc or DISC); return [x.strip() for x in m.group(1).split("/") if x.strip()]


def prompt_v3(text):
    menu = kind_menu(); menu_txt = " / ".join("「%s」" % k for k in menu)
    p = PROMPT % (DISC, text)
    old_kind = '"increment_kind": "仅当 supports 为 A 时填:这段增量属于上面判别式所列的哪一种,照判别式里的措辞原样写,**只写其中一种**,不要连写多种;supports 为 B 时填 null"'
    assert old_kind in p, "★ r2 提示词的 kind 行变了 —— v3 的替换点失效"
    new_kind = '"increment_kind": "仅当 supports 为 A 时填, **只能是下面五个之一, 原样抄一个, 只填一个, 不要用斜杠连写**: %s ;supports 为 B 时填 null"' % menu_txt
    p = p.replace(old_kind, new_kind, 1)
    tail = "所有 span 与 object 都必须**逐字**出自上面的文本。不要改写、不要合并不相邻的词。"
    assert tail in p
    p = p.replace(tail, tail + "\n「逐字」的意思是: **从上面的文本里复制粘贴出的一段连续文字**(大小写、标点、空格都一样)。如果你找不到能原样复制的片段, 就把 supported 填 false, 不要改写成近似的话。", 1)
    return p


def repair_prompt(prev_json_text, codes):
    """修复重问: 只给错误码与格式规则, **不给判据、不给对错**; 要求只修格式不改判断。"""
    rules = {E_JSON: "输出不是合法 JSON 对象", E_SHAPE: "evidence 不是对象数组或为空", E_SUPPORTS: "某条 evidence 的 supports 不是 \"A\" 或 \"B\"",
             E_SPAN: "某条 evidence 的 span 不是文本里可复制粘贴的连续原文", E_OBJECT: "某条 evidence 的 object 不是文本里可复制粘贴的连续原文",
             E_KIND_MENU: "某条 evidence 的 increment_kind 不是给定五个之一", E_KIND_MULTI: "某条 evidence 的 increment_kind 连写了多个, 只能填一个", E_KIND_ON_B: "supports 为 B 的 evidence 填了 increment_kind, 应为 null"}
    lst = "\n".join("- %s: %s" % (c, rules[c]) for c in codes if c in rules)
    return ("你上一份回答有**格式**问题(只是格式, 不涉及判断对错):\n%s\n\n请**只修正格式**, 不要改变你对 supported 的判断, 也不要新增或删除证据条目(除非某条无法逐字给出, 那就删掉它)。"
            "重新输出**完整**的 JSON, 与之前相同的结构。\n\n你上一份回答:\n%s" % (lst, prev_json_text))


def reason_codes(obj, text, menu=None):
    """把一张证书(已解析 JSON 或 None)分类成错误码集合 —— 与 _judge 的 MALFORMED 分支同源, 但**只回码不回文本**。空集合 ⇒ 格式合规(语义另说)。"""
    menu = set(menu or kind_menu()); codes = []
    if not isinstance(obj, dict): return [E_JSON]
    if not obj.get("supported"): return []            # 拒答不是格式问题
    ev = obj.get("evidence")
    if not isinstance(ev, list) or not ev or not all(isinstance(e, dict) for e in ev): return [E_SHAPE]
    for e in ev:
        sup = str(e.get("supports", "")).strip().upper()
        if sup not in ("A", "B"): codes.append(E_SUPPORTS)
        span = e.get("span"); obj_ = e.get("object")
        if not isinstance(span, str) or not span.strip() or span not in text: codes.append(E_SPAN)
        if not isinstance(obj_, str) or not obj_.strip() or obj_.strip() not in text: codes.append(E_OBJECT)
        k = e.get("increment_kind")
        if sup == "A":
            kc = _clean_kind(k)
            if kc is None: codes.append(E_KIND_MENU)
            elif "/" in kc or "、" in kc: codes.append(E_KIND_MULTI)
            elif kc not in menu: codes.append(E_KIND_MENU)
        elif sup == "B" and k not in (None, "", "null"): codes.append(E_KIND_ON_B)
    return sorted(set(codes))



# ══ 影子段 ══════════════════════════════════════════════════════════════════════════════════════
def _call_model(prompt):
    """可被测试替换的唯一出口: 返回 (raw_text, meta)。生产走 exp_crossmodel_desire.call_model(MEASUREMENT_MODEL)。"""
    from exp_crossmodel_desire import call_model
    import cce_knot_classify as CK
    return call_model(CK.MEASUREMENT_MODEL, prompt, temperature=0.0, max_retries=1)


def _sha16(s): return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _one_cert(text, call):
    """一张证书: 首答 → 有格式码则一次修复重问 → _judge。返回**无原文**的记录。"""
    t0 = time.time(); raw, meta = call(prompt_v3(text)); calls = 1; repaired = False
    obj = _parse(raw) if raw and raw.strip() else None
    if (meta or {}).get("error") or obj is None:
        return {"outcome": "CALL_FAIL", "state": None, "sec": round(time.time() - t0, 2), "witness": [], "n_evidence": 0, "reason_codes": ["E_JSON"] if obj is None and not (meta or {}).get("error") else [], "repaired": False, "calls": calls}
    codes = reason_codes(obj, text)
    if codes:
        raw2, meta2 = call(repair_prompt(json.dumps(obj, ensure_ascii=False)[:4000], codes)); calls += 1; repaired = True
        obj2 = _parse(raw2) if raw2 and raw2.strip() and not (meta2 or {}).get("error") else None
        if obj2 is not None: obj = obj2
    t = {"id": "s2b", "arm": "PROD", "text": text, "推导": {}, "结构": ""}
    oc, why, st = _judge(t, obj)
    if oc in (GRANULARITY, DISTINCT): oc = "P2_FAIL"
    witness = []
    if oc == UPGRADED:
        try:
            import cce_label_qualification as LQ
            ev = [LQ.EvidenceSpan(e.get("span") or "", CONJ.get(str(e.get("supports", "")).strip().upper()), text, about=normalize_about((e.get("object") or "").strip()) or None, increment_kind=_clean_kind(e.get("increment_kind"))) for e in obj.get("evidence") or []]
            q = LQ.qualify("display", text, evidence=ev, required_conjuncts=[CONJ["A"], CONJ["B"]]); witness = sorted(_sha16(w) for w in ((q.get("P2") or {}).get("witness") or []))
        except Exception:
            witness = []
    return {"outcome": oc, "state": st, "sec": round(time.time() - t0, 2), "witness": witness, "n_evidence": len(obj.get("evidence") or []), "reason_codes": reason_codes(obj, text), "repaired": repaired, "calls": calls}


def shadow_certificates(text, call=None):
    """影子段主入口。返回 {decision, state, certs, witness_sha16, calls}; state ∈ {CITED_UNVERIFIED, UNCONFIRMED_CANDIDATE}; citable 恒 False。"""
    call = call or _call_model
    with ThreadPoolExecutor(max_workers=2) as ex:
        c1, c2 = list(ex.map(lambda _: _one_cert(text, call), (0, 1)))
    up1, up2 = c1["outcome"] == UPGRADED, c2["outcome"] == UPGRADED; inter = sorted(set(c1["witness"]) & set(c2["witness"]))
    if "CALL_FAIL" in (c1["outcome"], c2["outcome"]): decision = "CALL_FAIL"
    elif up1 and up2 and inter: decision = "CITED_UNVERIFIED"
    elif up1 and up2: decision = "BOTH_UPGRADED_NO_COMMON_WITNESS"
    elif up1 != up2: decision = "DISAGREE"
    else: decision = "BOTH_NOT_UPGRADED"
    return {"decision": decision, "state": "CITED_UNVERIFIED" if decision == "CITED_UNVERIFIED" else "UNCONFIRMED_CANDIDATE", "certs": [c1, c2], "witness_sha16": inter,
            "calls": c1["calls"] + c2["calls"], "citable_as_confirmed": False, "★怎么读": "③′ = 出处可核·语义未验(MIS-4 类照过); ④ 需确定性识别器, 未实现。"}
