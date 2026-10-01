# -*- coding: utf-8 -*-
"""对齐出口 v4: 读者 top-1 结的 playbook **逐原子三值**判定(2026-09-30)。

为什么重做(生产状态表: playbook_hit 已测·不达标):
  ① 旧出口 = 每个结一个 0–1 的整体命中度 × 结权重, 而结权重 K1-v2 判 0/5 不可用 ⇒ 整个分数不可用;
  ② 同一原子三种问法 27% / 100% / 3%(提问框架支配判定), 且禁令的「满足」是缺席, 旧问法要求为缺席引原文。
新出口不碰权重: 只用读者**稳定且可用**的 top-1 结(K1 判定 TOP1_USABLE), 对它的每个原子单独判三值 ——
  【做】做了 / 没做 / 不确定;  【禁】违反 / 未违反 / 不确定。有东西在场的一侧(做了、违反)必须给逐字子串, 缺席一侧不要子串。
只报**校对通过**的原子(results/align_atoms_calibration.json 的 calibrated: 构造正反例 × 两种相反问法 × 两次 全对);
没过校对的原子不判, 记「未校对」—— 不是「没做」。不出总分、不出放行布尔(全占比 / 禁布尔 gate)。
owner 2026-09-29: 人给不出个体金标 ⇒ 这里的校对是构造出的局部真值(必要条件), 不是金标。
"""
import json
import os
import re

import cce_align_v2 as A

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# ★ 生产只认 v5 的最终校对名单(results/align_atoms_v5.json): 留出集 8/8(v4.1)→ 再加 C 集 16/16 + 真实回复上两种问法一致率 >= 0.85。
#   v4 开发集、v4.1 留出集的结果文件保留作记录。
CAL = os.path.join(ROOT, "results", "align_atoms_v5.json")
if not os.path.exists(CAL):      # v5 结果落地之前沿用 v4.1 留出名单(suspend/audit 在那份里本来就 0 个通过, 拆分不影响)
    CAL = os.path.join(ROOT, "results", "align_atoms_heldout_v41.json")
_NEG = ("不", "别", "绝不", "勿", "禁止")

PROMPT_A = """你判定一段回复草稿对一份"拆除动作清单"的逐条符合情况。

【读者的阻挡结】{knot}
判据(读者处于该状态的表现): {discr}

【回复草稿】
{text}

【逐条判定】每条独立判, 不判好坏; 只是谈论相关话题不算做。
· 标【做】的条目: 草稿里**有句子在做**这件事 ⇒ state="做了", 并给出那句的原样子串; 草稿明确没有做 ⇒ "没做"; 草稿信息不足以判断 ⇒ "不确定"。
· 标【禁】的条目: 草稿里**有句子违反**这条禁令 ⇒ state="违反", 并给出违反处的原样子串; 找不到违反 ⇒ "未违反"(不需要子串); 信息不足以判断 ⇒ "不确定"。
{items}

只输出JSON: {{"atoms": [{{"i": 序号, "state": "做了|没做|违反|未违反|不确定", "quote": "原样子串, 缺席一侧填空"}}]}}"""

# ★ 反向问法(框架不变性校对用): 不问「做了/违反」, 问「符合这条要求吗」。映射回同一个规范值后必须与 A 一致。
PROMPT_B = """下面是一份回复写作要求清单, 请逐条检查一段回复草稿**是否符合**每条要求。

【读者的阻挡结】{knot}
判据(读者处于该状态的表现): {discr}

【回复草稿】
{text}

【逐条检查】每条独立判, 不判好坏; 只是谈论相关话题不等于落实了要求。
· 标【做】的要求(要求草稿做某事): 符合 = 草稿里有句子落实了它(给出原样子串); 不符合 = 没有落实(不需要子串)。
· 标【禁】的要求(要求草稿不做某事): 符合 = 草稿里没有做被禁止的事(不需要子串); 不符合 = 有句子做了被禁止的事(给出原样子串)。
· 信息不足以判断 ⇒ "不确定"。
{items}

只输出JSON: {{"atoms": [{{"i": 序号, "state": "符合|不符合|不确定", "quote": "原样子串, 不需要时填空"}}]}}"""


# ★ 2026-09-30 v5: suspend / audit 的**测量侧**操作化拆分(不改 config/knot_taxonomy.json 的 playbook 原文, 那是 Core)。
#   原子原文一条塞了多件事(suspend#0「给判据+零成本测试塌缩不确定性+如实说trade」= 三件; audit 两条各两件), v4/v4.1 两轮校对里
#   这两结 0 个原子通过。拆成一条只说一件事的可判条目; source = 它出自 playbook 的第几条。与 2026-09-05 belong 的 A2 拆分同性质。
#   owner 2026-09-30「进行解决吧」。拆分后的条目同样要过校对才进生产。
OPERATIONAL = {
    "suspend": [("给出一条可用来做决定的判据(说明按什么来选)", False, 0),
                ("给出一个零成本的测试办法(免费试用、借用、现成可做的对比), 用来消除不确定", False, 0),
                ("如实说出取舍(选这个会失去什么)", False, 0),
                ("不推购买(包括用零风险承诺、样品、他人证言来催单)", True, 1)],
    "audit": [("不辩解(不为自己的做法或资历辩护)", True, 0),
              ("不表演(不摆资历、不表忠心、不夸耀自己)", True, 0),
              ("给出可验证的事实(具体数字、来源或可查的记录)", False, 1),
              ("明确邀请对方检验或追问具体细节", False, 1)],
}


def atoms_of(knot):
    if knot in OPERATIONAL:
        return [(t, neg) for t, neg, _src in OPERATIONAL[knot]]
    raw = A.PLAYBOOK.get(knot, "")
    parts = [p.strip() for p in re.split(r"[;；]", raw) if p.strip()]
    return [(p, any(p.startswith(n) or n in p[:3] for n in _NEG)) for p in parts]


VERSION = "v5"   # v4.1 判官 + suspend/audit 操作化拆分(其余 7 结的清单与 v4.1 逐字相同)


def _norm(s):
    """逐字核对前的归一: 大小写、空白、标点与引号样式(’ ‘ “ ” 等)不算改字。v4.1(2026-09-30): v4 校对里 8 次方向对、
    只因模型把 ' 写成 ’ 之类被判 uncertain。归一只抹掉排版差异, 词一个都不许变。"""
    s = s.lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"[\s\W_]+", " ", s).strip()


def canonical(state, quote, is_prohibition, framing, text):
    """→ "satisfied" | "unsatisfied" | "uncertain"。在场一侧(做了 / 违反 / B 的对应侧)必须给**逐字在草稿里**的子串(排版归一后), 否则 uncertain。"""
    q = (quote or "").strip()
    present_ok = bool(q) and bool(_norm(q)) and _norm(q) in _norm(text)
    if framing == "a":
        if is_prohibition:
            m = {"违反": ("unsatisfied", True), "未违反": ("satisfied", False)}
        else:
            # v4.1: 【做】条目上答「违反」且给了逐字子串 = 草稿里有句子在做相反的事 ⇒ 没做到(v4 校对里 6 次方向对、标签不在集合里)
            m = {"做了": ("satisfied", True), "没做": ("unsatisfied", False), "违反": ("unsatisfied", True)}
    else:
        if is_prohibition:
            m = {"不符合": ("unsatisfied", True), "符合": ("satisfied", False)}
        else:
            m = {"符合": ("satisfied", True), "不符合": ("unsatisfied", False)}
    if state not in m:
        return "uncertain"
    val, needs_quote = m[state]
    return val if (present_ok or not needs_quote) else "uncertain"


def judge(knot, text, framing="a", temperature=0.0, call=None):
    """一次判定 → [{"i", "atom", "is_prohibition", "state", "quote", "canonical"}] 或 None(调用/格式失败)。"""
    items = atoms_of(knot)
    listing = "\n".join(f"{i + 1}. 【{'禁' if neg else '做'}】{t}" for i, (t, neg) in enumerate(items))
    tmpl = PROMPT_A if framing == "a" else PROMPT_B
    out = (call or A._call)(tmpl.format(knot=knot, discr=A.DISCR.get(knot, ""), text=text, items=listing), temperature=temperature)
    d = A._extract_json(out)
    if not isinstance(d, dict) or not isinstance(d.get("atoms"), list):
        return None
    got = {}
    for a in d["atoms"]:
        try:
            i = int(a["i"]) - 1
        except Exception:
            continue
        if 0 <= i < len(items):
            got[i] = (str(a.get("state") or ""), str(a.get("quote") or ""))
    if len(got) != len(items):
        return None
    return [{"i": i, "atom": items[i][0], "is_prohibition": items[i][1], "state": got[i][0], "quote": got[i][1],
             "canonical": canonical(got[i][0], got[i][1], items[i][1], framing, text)} for i in range(len(items))]


# ★ 2026-09-30 生产判官 = Jev。预注册发货规则(tests/data/align_atoms_jev_prereg.json): Jev 校对通过的条目数 > MiniMax v5 的 5 个才切换;
#   实测 Jev 14/29(构造草稿准确率 0.969)vs v5 5/19 ⇒ 切换。两台判官不混用; 闸钉「Jev 名单确实更大」, 否则这行常量就是空口。
PRODUCTION_JUDGE = "jev"


def calibrated_atoms(judge=None):
    """校对通过的原子 {knot: {atom 下标}}; 没有校对结果 ⇒ 空(一个都不判)。judge: "jev" | "minimax", 缺省 = 生产判官。"""
    jev = (judge or PRODUCTION_JUDGE) == "jev"
    if jev and v3_shipped() is not None:
        return v3_shipped()
    if jev and os.path.exists(JEV_V2):         # V2: 真实回复上的受控变形测试(预注册 align_atoms_v2)通过的条目 + 机械条目
        per = json.load(open(JEV_V2, encoding="utf-8")).get("per_atom") or {}
        out = {}
        for k, i in [tuple(key.rsplit("#", 1)) for key, v in per.items() if v.get("verdict") == "VALIDATED"] + [(k, i) for k, i in MECHANICAL]:
            out.setdefault(k, set()).add(int(i))
        return out
    if jev and os.path.exists(JEV_FINAL):      # 最终名单: 全部条目在 60 条真实回复上对称复核后的判定(预注册 align_atoms_jev_n3)
        per = json.load(open(JEV_FINAL, encoding="utf-8")).get("per_atom") or {}
        out = {}
        for key, v in per.items():
            if v.get("verdict") == "CALIBRATED":
                k, i = key.rsplit("#", 1)
                out.setdefault(k, set()).add(int(i))
        return out
    path = JEV_CAL if jev else CAL
    if not os.path.exists(path):
        return {}
    per = dict(json.load(open(path, encoding="utf-8")).get("per_atom") or {})
    if jev and os.path.exists(JEV_CAL_REWARD):          # reward 结的题面已重做: 只认它自己那次校对
        per = {k: v for k, v in per.items() if not k.startswith("reward#")}
        per.update(json.load(open(JEV_CAL_REWARD, encoding="utf-8")).get("per_atom") or {})
    out = {}
    for key, v in per.items():
        if v.get("verdict") == "CALIBRATED":
            k, i = key.rsplit("#", 1)
            out.setdefault(k, set()).add(int(i))
    return out


def atoms_alignment(reader_top1, top1_usable, text, call=None, post=None):
    """生产出口。reader_top1: 读者 s2 的 top-1 结; top1_usable: 该读数是否在出口闸 usable 里(K1 + 稳定)。
    call / post: 测试桩(MiniMax 判官用 call, Jev 判官用 post)。"""
    if not reader_top1 or not top1_usable:
        return {"status": "withheld", "reason": "读者 top-1 结不可用(不稳或无 K1 判定) —— 没有「对哪个结对齐」就不判", "atoms": []}
    cal = calibrated_atoms().get(reader_top1, set())
    if not cal:
        return {"status": "withheld", "knot": reader_top1, "reason": f"{reader_top1} 没有校对通过的原子 —— 一个都不判", "atoms": []}
    v3 = PRODUCTION_JUDGE == "jev" and v3_shipped() is not None
    v2 = PRODUCTION_JUDGE == "jev" and not v3 and os.path.exists(JEV_V2)
    if v3:
        jr, err = judge_jev_v3(reader_top1, text, post=post)
        if jr is None:
            return {"status": "failed", "knot": reader_top1, "reason": "Jev 判官调用失败: %s" % err, "atoms": []}
        items = atoms_of(reader_top1)
        # 五个题面的全占比照报; 主值 = 面板值(≥4 票同侧且 0 票相反), 否则 uncertain。指导用条目不问、不判
        res = [{"i": i, "atom": items[i][0], "is_prohibition": items[i][1], "quote": "", "p_a": None,
                "state": "guidance_only" if i not in jr else "votes=" + "/".join(v[:3] for v in jr[i]["votes"]),
                "share": None if i not in jr else {k: round(jr[i]["votes"].count(k) / len(jr[i]["votes"]), 2) for k in ("satisfied", "unsatisfied", "uncertain")},
                "canonical": "guidance_only" if i not in jr else jr[i]["panel"]} for i in range(len(items))]
    elif v2:
        jr, err = judge_jev_v2(reader_top1, text, post=post)
        if jr is None:
            return {"status": "failed", "knot": reader_top1, "reason": "Jev 判官调用失败: %s" % err, "atoms": []}
        items = atoms_of(reader_top1); opposite = {"satisfied", "unsatisfied"}
        # 只用问法 A; 同极性改写 A′ 给出相反确定值 ⇒ uncertain。指导用条目(只看回复判不了)不问、不判, 但留在清单里
        res = [{"i": i, "atom": items[i][0], "is_prohibition": items[i][1], "quote": "", "p_a": (jr.get(i) or {}).get("p_a"),
                "state": "guidance_only" if i not in jr else "A=%s/A'=%s" % (jr[i]["a"], jr[i]["p"]),
                "canonical": "guidance_only" if i not in jr else ("uncertain" if {jr[i]["a"], jr[i]["p"]} == opposite else jr[i]["a"])}
               for i in range(len(items))]
    elif PRODUCTION_JUDGE == "jev":
        jr, err = judge_jev(reader_top1, text, post=post)
        if jr is None:
            return {"status": "failed", "knot": reader_top1, "reason": "Jev 判官调用失败: %s" % err, "atoms": []}
        items = atoms_of(reader_top1)
        # 两种问法不一致 ⇒ uncertain(只会更保守: 校对时要求的正是两问法一致)
        res = [{"i": i, "atom": items[i][0], "is_prohibition": items[i][1], "state": "A=%s/B=%s" % (jr[i]["a"], jr[i]["b"]), "quote": "",
                "canonical": jr[i]["a"] if jr[i]["a"] == jr[i]["b"] else "uncertain", "p_a": jr[i]["p_a"]} for i in range(len(items))]
    else:
        res = judge(reader_top1, text, framing="a", call=call)
    if res is None:
        return {"status": "failed", "knot": reader_top1, "reason": "判官调用或格式失败", "atoms": []}
    atoms = [dict(r, calibrated=r["i"] in cal) for r in res]
    scan = complete_scan(text) if PRODUCTION_JUDGE == "jev" else True      # MiniMax 题面带全文
    ok_abs = absent_validated() if PRODUCTION_JUDGE == "jev" else set()
    for r in atoms:
        if not r["calibrated"] and r["canonical"] != "guidance_only":
            r["canonical"] = "not_calibrated"      # 没过校对: 不判(不是「没做」)
        r["tri"] = tri_state(r["canonical"], r["is_prohibition"], scan, (reader_top1, r["i"]) in ok_abs or (reader_top1, r["i"]) in MECHANICAL)
    judged = [r for r in atoms if r["calibrated"]]
    return {"status": "ok", "judge": PRODUCTION_JUDGE, "judge_version": "v3" if v3 else ("v2" if v2 else VERSION), "knot": reader_top1, "atoms": atoms,
            "★v2_reading": "【做】satisfied = 检出一句在做; unsatisfied = 未检出(不是证明没做)。【禁】unsatisfied = 检出违规; satisfied = 未检出违规。" if (v2 or v3) else None,
            "★v3_reading": "share = 五个冻结题面里各答案的占比(题面支持度, 不是真值概率); 主值要 ≥4 票同侧且 0 票相反。" if v3 else None,
            "summary": {"calibrated": len(judged), "satisfied": sum(r["canonical"] == "satisfied" for r in judged),
                        "unsatisfied": sum(r["canonical"] == "unsatisfied" for r in judged),
                        "uncertain": sum(r["canonical"] == "uncertain" for r in judged),
                        "tri": {t: sum(r["tri"] == t for r in judged) for t in ("SATISFIED", "VIOLATED", "INDETERMINATE")}},
            "complete_scan": scan,
            "★tri_reading": "tri = 主张层三值。在场见证(【做】检出执行 / 【禁】检出违规)单独成立; 缺席结论(【禁】SATISFIED / 【做】VIOLATED)"
                            "要 complete_scan(判官看到整篇)且该条目缺席一侧过了构造稿准入(results/align_atoms_tri.json 禁令 / results/align_atoms_tri_do.json 【做】), 否则 INDETERMINATE。",
            "★rule": "只看逐原子状态; 不出总分、不出放行布尔。uncertain 与 not_calibrated 都不是「没做」。"}


# ══ 三值主张层(2026-10-01, docs/decisions/PLAYBOOK_TRI_STATE_AUDIT_DECIDED_2026-10-01.md) ════════════════════
# 旧反转(「找不到违反」⇒ 未违反)把假违反换成了假满足。按 safety property(Alpern & Schneider 1985): 违反由有限坏前缀(一句)见证即成立;
# 满足是全称命题, 只有扫完整篇且检出器对该条目足够灵敏时才可下(Reiter 闭世界)。两条都不满足 ⇒ INDETERMINATE。
# ★ 这是本项目的操作化, 不是 LLM-judge 的命名标准做法(2026-09-05 调研明说无文献命名过它)。
JEV_STATE_MAX = 2000          # 判官只看到 text[:2000](judge_jev* 的 state)
TRI_RESULT = os.path.join(ROOT, "results", "align_atoms_tri.json")          # 【禁】缺席一侧(SATISFIED)
TRI_DO_RESULT = os.path.join(ROOT, "results", "align_atoms_tri_do.json")    # 【做】缺席一侧(VIOLATED), 2026-10-01 第二轮


def complete_scan(text):
    return len(text) <= JEV_STATE_MAX


def absent_validated():
    """缺席一侧过了构造稿准入的条目 {(结, 下标)}(禁令轮 ∪ 【做】轮); 没有结果 ⇒ 空集(缺席结论一律 INDETERMINATE)。"""
    out = set()
    for path in (TRI_RESULT, TRI_DO_RESULT):
        if os.path.exists(path):
            per = json.load(open(path, encoding="utf-8")).get("per_atom") or {}
            out |= {(k, int(i)) for k, i in (key.rsplit("#", 1) for key, v in per.items() if v.get("verdict") == "ADOPTED")}
    return out


def tri_state(canonical, is_prohibition, scan_ok, absent_ok):
    present, absent = witness_value(is_prohibition), ("satisfied" if is_prohibition else "unsatisfied")
    if canonical == present:
        return "VIOLATED" if is_prohibition else "SATISFIED"
    if canonical == absent and scan_ok and absent_ok:
        return "SATISFIED" if is_prohibition else "VIOLATED"
    return "INDETERMINATE"


# ══ Jev 判官(2026-09-30) ═══════════════════════════════════════════════════════════════════════
# v5 加严后 MiniMax 判官只剩 5 个原子可判, reward/display/inertia/suspend 四结为 0。换一台判官试: 生产 s0 已在用的
# TypeSafe Jev 闭选分类器(重测 κ≈1, 逐题给概率, 约 $0.00005/次)。一题只问一个原子; Jev 以英文为主 ⇒ 每个原子配一句英文操作化描述
# (测量侧翻译, playbook 原文不动; 下标与 atoms_of(knot) 逐位对应, 闸钉长度与做/禁类型一致)。
ATOMS_EN = {
    "pain_seek": ["give a lever, the mechanism behind the problem, and a concrete next step the reader can act on",
                  "make an empty promise or guarantee an outcome without acknowledging limits"],
    "injustice": ["acknowledge that the reader's grievance is legitimate",
                  "point the reader to a concrete, actionable accountability path (for example: document what happened, file a complaint, get a case or reference number)",
                  "defend or excuse the party responsible for the problem"],
    "belong": ["include a line telling the reader they are not alone or that others share this experience",
               "give a piece of new, specific knowledge",
               "give more than one piece of new advice or information (a list of several tips)",
               "assign the reader tasks or homework"],
    "reward": ["keep it short (one or two sentences) and close the exchange",
               "play down the writer's own role or give the credit to the reader",
               "add further information or new topics after the reader's need is already met"],
    "display": ["step back and put the reader's contribution in the foreground",
                "treat the reader as a peer or equal",
                "build on the reader's contribution instead of correcting them"],
    "itch": ["paint a vivid scene or identity that the reader can picture themselves in",
             "assign the reader tasks or homework",
             "keep the longing pleasant (wistful enjoyment) rather than sad or bitter"],
    "suspend": ["give one criterion the reader can use to make the decision",
                "give a zero-cost way to test the options (a free trial, a loaner, a comparison they can already do) to resolve the uncertainty",
                "state an honest trade-off (what the reader would give up with an option)",
                "push the reader to buy (including by zero-risk promises, samples, or other people's testimonials)"],
    "inertia": ["address the specific reason the reader gave for not acting",
                "propose one small, reversible step",
                "preach or moralize about what the reader ought to do"],
    "audit": ["defend or justify the writer's own method or credentials",
              "perform or show off (cite credentials, loyalty, or the writer's own virtues)",
              "give a verifiable fact (a specific number, source, or checkable record)",
              "explicitly invite the reader to check the claim or ask about specific details"],
}
JEV_CAL = os.path.join(ROOT, "results", "align_atoms_jev.json")

# ★ 2026-09-30 reward 结重做(ALIGN_ATOMS_JEV 里 reward 0/3: 构造草稿全对, 但真实回复上问法 B 常答 unclear ——
#   原描述带着只看回复判不了的前提「需求已闭之后」「收束对话」)。其余 8 个结的描述与已校对的题面**逐字不变**(ATOMS_EN_V1 留档, 闸钉)。
#   · reward#0「短收」改为**机械规则**, 不问模型: 句数 <= 2 且词数 <= 40。
#   · reward#1 / #2 改成只看回复文本本身的描述。
ATOMS_EN_V1 = {k: list(v) for k, v in ATOMS_EN.items()}
ATOMS_EN["reward"] = ["keep it short (at most two sentences)",          # 机械判, 这句不发给模型
                      "explicitly give the credit to the reader or explicitly minimize the writer's own contribution (for example: 'you did all the work', 'I barely did anything')",
                      "introduce new information, advice, or a new topic beyond acknowledging or congratulating the reader"]
JEV_CAL_REWARD = os.path.join(ROOT, "results", "align_atoms_jev_reward.json")
JEV_FINAL = os.path.join(ROOT, "results", "align_atoms_jev_final.json")
SHORT_MAX_SENTENCES, SHORT_MAX_WORDS = 2, 40


def _is_short(text):
    sents = [x for x in re.split(r"(?<=[.!?])\s+", text.strip()) if x.strip()]
    return len(sents) <= SHORT_MAX_SENTENCES and len(text.split()) <= SHORT_MAX_WORDS


MECHANICAL = {("reward", 0): _is_short}      # (结, 下标) → 规则; 规则判的条目两种「问法」恒一致
_JEV_MAP = {"a": {False: {"done": "satisfied", "not_done": "unsatisfied"}, True: {"violated": "unsatisfied", "not_violated": "satisfied"}},
            "b": {False: {"complies": "satisfied", "does_not_comply": "unsatisfied"}, True: {"complies": "satisfied", "does_not_comply": "unsatisfied"}}}


def jev_questions(knot, table=None):
    qs = {}
    for i, ((_, neg), en) in enumerate(zip(atoms_of(knot), (table or ATOMS_EN)[knot])):
        if table is None and (knot, i) in MECHANICAL:
            continue
        if neg:
            qs["%da" % i] = {"type": "choice", "instructions": "Judge the reply text only. Does the reply do the following thing, which it should NOT do: %s? Merely mentioning the topic does not count." % en,
                             "criteria": {"violated": "the reply contains a sentence that does this", "not_violated": "the reply does not do this", "unclear": "cannot tell from the reply; do not guess"}}
            qs["%db" % i] = {"type": "choice", "instructions": "Requirement for the reply: it must not %s. Does the reply comply with this requirement?" % en,
                             "criteria": {"complies": "the reply does not do the forbidden thing", "does_not_comply": "the reply contains a sentence doing the forbidden thing", "unclear": "cannot tell from the reply; do not guess"}}
        else:
            qs["%da" % i] = {"type": "choice", "instructions": "Judge the reply text only. Does the reply do the following: %s? Merely mentioning the topic does not count." % en,
                             "criteria": {"done": "the reply contains a sentence that does this", "not_done": "the reply does not do this", "unclear": "cannot tell from the reply; do not guess"}}
            qs["%db" % i] = {"type": "choice", "instructions": "Requirement for the reply: it should %s. Does the reply comply with this requirement?" % en,
                             "criteria": {"complies": "the reply contains a sentence that fulfils the requirement", "does_not_comply": "the reply does not fulfil the requirement", "unclear": "cannot tell from the reply; do not guess"}}
    return qs


def judge_jev(knot, text, post=None):
    """一次 Jev 调用判该结全部原子的两种问法 → {下标: {"a": 规范值, "b": 规范值, "p_a": 概率表}} 或 (None, err)。"""
    import cce_s0_jev as S0
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not key:
        return None, "NO_TYPESAFE_API_KEY"
    resp, err = (post or S0._post)({"model": S0.MODEL, "state": text[:2000], "questions": jev_questions(knot)}, key)
    if err or not resp:
        return None, err or "EMPTY_RESPONSE"
    out = {}
    try:
        for i, (_, neg) in enumerate(atoms_of(knot)):
            if (knot, i) in MECHANICAL:
                v = "satisfied" if MECHANICAL[(knot, i)](text) else "unsatisfied"
                out[i] = {"a": v, "b": v, "p_a": None}; continue
            a, b = resp["answers"]["%da" % i], resp["answers"]["%db" % i]
            out[i] = {"a": _JEV_MAP["a"][neg].get(a["choice"], "uncertain"), "b": _JEV_MAP["b"][neg].get(b["choice"], "uncertain"),
                      "p_a": a.get("probabilities")}
    except (KeyError, TypeError) as e:
        return None, "BAD_SHAPE:%s" % type(e).__name__
    return out, None


# ══ V2(2026-09-30): 单问法 A + 同极性改写 A′ 反证, 真实底稿变形测试准入 ═══════════════════════════════
# 网页 GPT 调研(2026-09-30)的三条更正:
#   ① 「做了 X 吗」(A)与「符合『应当做 X』的要求吗」(B)未必是同一个命题(条件项尤其), B 多答 unclear 不说明 A 错 ——
#      A/B 一致率不该当准入门。生产仪器只用 A; 再用同极性改写 A′ 作反证: 两者给出**相反的确定答案** ⇒ uncertain(单边弃权不算冲突)。
#   ② 自洽 ≠ 判得对。准入改看真实底稿上的受控变形测试(probes/align_atoms_v2.py): 充分见证检出 / 难负例不误触发 / 中性编辑不动 / 逐字恢复。
#      这只验证了**在场一侧**(做了 / 违反了)的检出与抗误触发 —— 缺席一侧的读数是「未检出」, 不是「证明没做」。
#   ③ 只看单篇回复判不了的条目登记为「指导用」, 不判、不删、留在分母里。
# V1(A/B 一致率)的代码与结果原样保留作记录; V2 名单落 results/align_atoms_v2.json 后生产才切换(预注册发货规则)。
GUIDANCE_ONLY = {
    ("inertia", 0): "要判「是否针对读者给出的那个具体理由」必须同时看到读者原话; 只给回复稿, 同一段回复在两种读者原话下正确判定不同 —— 单篇回复不可识别",
    ("display", 1): "「被当同侪」是宽泛的关系品质: 说一句「我们都是老用户」不足以证明整体平等相待, 没有充分见证可构造 —— 不从单篇回复测量",
}
JEV_V2 = os.path.join(ROOT, "results", "align_atoms_v2.json")


def jev_questions_v2(knot):
    """A(与 V1 的 A 题逐字相同)+ A′(同极性改写)。机械规则与指导用条目不出题。"""
    v1 = jev_questions(knot)
    qs = {}
    for i, ((_, neg), en) in enumerate(zip(atoms_of(knot), ATOMS_EN[knot])):
        if (knot, i) in MECHANICAL or (knot, i) in GUIDANCE_ONLY:
            continue
        qs["%da" % i] = v1["%da" % i]
        if neg:
            qs["%dp" % i] = {"type": "choice", "instructions": "Read the reply. Is there at least one sentence in it that does this (something the reply is not supposed to do): %s? Talking about the topic without doing it does not count." % en,
                             "criteria": {"violated": "yes, a sentence in the reply does this", "not_violated": "no sentence in the reply does this", "unclear": "cannot tell from the reply; do not guess"}}
        else:
            qs["%dp" % i] = {"type": "choice", "instructions": "Read the reply. Is there at least one sentence in it that does this: %s? Talking about the topic without doing it does not count." % en,
                             "criteria": {"done": "yes, a sentence in the reply does this", "not_done": "no sentence in the reply does this", "unclear": "cannot tell from the reply; do not guess"}}
    return qs


def judge_jev_v2(knot, text, post=None):
    """一次 Jev 调用 → ({下标: {"a": 规范值, "p": A′ 规范值, "p_a": 概率表}}, err)。机械条目按规则填; 指导用条目不在返回里。"""
    import cce_s0_jev as S0
    out = {}
    for i in range(len(atoms_of(knot))):
        if (knot, i) in MECHANICAL:
            v = "satisfied" if MECHANICAL[(knot, i)](text) else "unsatisfied"
            out[i] = {"a": v, "p": v, "p_a": None}
    qs = jev_questions_v2(knot)
    if not qs:
        return out, None
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not key:
        return None, "NO_TYPESAFE_API_KEY"
    resp, err = (post or S0._post)({"model": S0.MODEL, "state": text[:2000], "questions": qs}, key)
    if err or not resp:
        return None, err or "EMPTY_RESPONSE"
    try:
        for i, (_, neg) in enumerate(atoms_of(knot)):
            if "%da" % i not in qs:
                continue
            a, p = resp["answers"]["%da" % i], resp["answers"]["%dp" % i]
            out[i] = {"a": _JEV_MAP["a"][neg].get(a["choice"], "uncertain"), "p": _JEV_MAP["a"][neg].get(p["choice"], "uncertain"), "p_a": a.get("probabilities")}
    except (KeyError, TypeError) as e:
        return None, "BAD_SHAPE:%s" % type(e).__name__
    return out, None


def witness_value(is_prohibition):
    """在场一侧的规范值: 【做】= satisfied(检出执行), 【禁】= unsatisfied(检出违规)。"""
    return "unsatisfied" if is_prohibition else "satisfied"


# ══ V3(2026-09-30): 多题面面板 ═════════════════════════════════════════════════════════════════
# V2 确认里多数条目栽在「同一条真实回复上 A 与同义改写 A′ 给相反确定答案」。心理测量的做法是多题项: 一个条目用 K=5 个冻结题面去问,
# 报全占比; ≥4 票同侧且 0 票相反才给确定值, 否则 uncertain(网页 GPT 2026-09-30: 合法的重设计, 前提是分歧照报、覆盖率受约束;
# 占比 = 「这五个题面里的支持度」, 不是真值概率)。第 6 个题面只作审计(与生产面板不相交), 生产不问。
_P_DO = {"done": "yes, the reply does this", "not_done": "no, the reply does not do this", "unclear": "cannot tell from the reply; do not guess"}
_P_NO = {"violated": "yes, the reply does this", "not_violated": "no, the reply does not do this", "unclear": "cannot tell from the reply; do not guess"}
FORMS_V3 = [   # (【做】题面, 【禁】题面, 选项); 下标 0 / 1 = V2 的 A / A′(逐字), 5 = 审计题面
    None, None,
    ("Consider only what is written in the reply. Does the writer, somewhere in the reply, actually do this: %s? A passing reference to the subject is not enough.",
     "Consider only what is written in the reply. Does the writer, somewhere in the reply, actually do this (which a reply should avoid): %s? A passing reference to the subject is not enough."),
    ("Check the reply for one specific action: to %s. Is that action carried out in the reply? Naming the subject without carrying out the action does not count.",
     "Check the reply for one specific action that it should avoid: to %s. Is that action carried out in the reply? Naming the subject without carrying out the action does not count."),
    ("Statement: \"In this reply the writer does the following: %s.\" Based only on the reply text, is the statement true? It is true only if the reply really does it, not if it only brings up the theme.",
     "Statement: \"In this reply the writer does the following, which should be avoided: %s.\" Based only on the reply text, is the statement true? It is true only if the reply really does it, not if it only brings up the theme."),
    ("Would a careful reader say that this reply does the following: %s? Do not count it if the reply only touches on the theme.",
     "Would a careful reader say that this reply does the following, which it is meant to avoid: %s? Do not count it if the reply only touches on the theme."),
]
PANEL_V3, AUDIT_V3, PANEL_MIN = (0, 1, 2, 3, 4), 5, 4
JEV_V3 = os.path.join(ROOT, "results", "align_atoms_v3.json")


def jev_questions_v3(knot, forms=PANEL_V3):
    """{"<条目下标>_<题面下标>": 题} —— 机械与指导用条目不出题。"""
    v2 = jev_questions_v2(knot); qs = {}
    for i, ((_, neg), en) in enumerate(zip(atoms_of(knot), ATOMS_EN[knot])):
        if (knot, i) in MECHANICAL or (knot, i) in GUIDANCE_ONLY:
            continue
        for f in forms:
            qs["%d_%d" % (i, f)] = v2["%d%s" % (i, "ap"[f])] if f < 2 else {"type": "choice", "instructions": FORMS_V3[f][1 if neg else 0] % en, "criteria": dict(_P_NO if neg else _P_DO)}
    return qs


def panel_value(votes):
    """五个题面的规范值 → 面板值: ≥PANEL_MIN 票同侧且 0 票相反才确定。"""
    s, u = votes.count("satisfied"), votes.count("unsatisfied")
    if s >= PANEL_MIN and u == 0: return "satisfied"
    if u >= PANEL_MIN and s == 0: return "unsatisfied"
    return "uncertain"


def judge_jev_v3(knot, text, post=None, forms=PANEL_V3):
    """一次 Jev 调用 → ({下标: {"votes": [各题面规范值], "panel": 面板值}}, err)。机械条目按规则填(五票同值)。"""
    import cce_s0_jev as S0
    out = {}
    for i in range(len(atoms_of(knot))):
        if (knot, i) in MECHANICAL:
            v = "satisfied" if MECHANICAL[(knot, i)](text) else "unsatisfied"
            out[i] = {"votes": [v] * len(forms), "panel": v}
    qs = jev_questions_v3(knot, forms)
    if not qs:
        return out, None
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not key:
        return None, "NO_TYPESAFE_API_KEY"
    resp, err = (post or S0._post)({"model": S0.MODEL, "state": text[:2000], "questions": qs}, key)
    if err or not resp:
        return None, err or "EMPTY_RESPONSE"
    try:
        for i, (_, neg) in enumerate(atoms_of(knot)):
            if "%d_%d" % (i, forms[0]) not in qs:
                continue
            votes = [_JEV_MAP["a"][neg].get(resp["answers"]["%d_%d" % (i, f)]["choice"], "uncertain") for f in forms]
            out[i] = {"votes": votes, "panel": panel_value(votes)}
    except (KeyError, TypeError) as e:
        return None, "BAD_SHAPE:%s" % type(e).__name__
    return out, None


V3_SHIP_MIN = 5      # 预注册发货规则: V3 VALIDATED 条数 > V2 的 5 条才改用 V3


def v3_shipped():
    """V3 发货了 ⇒ {结: {下标}}(VALIDATED + 机械条目); 没有结果或没达到发货线 ⇒ None(生产留在 V2)。"""
    if not os.path.exists(JEV_V3):
        return None
    per = json.load(open(JEV_V3, encoding="utf-8")).get("per_atom") or {}
    ok = [tuple(k.rsplit("#", 1)) for k, v in per.items() if v.get("verdict") == "VALIDATED"]
    if len(ok) <= V3_SHIP_MIN:
        return None
    out = {}
    for k, i in ok + list(MECHANICAL):
        out.setdefault(k, set()).add(int(i))
    return out
