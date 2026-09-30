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


def calibrated_atoms():
    """校对通过的原子 {knot: {atom 下标}}; 没有校对结果 ⇒ 空(一个都不判)。"""
    if not os.path.exists(CAL):
        return {}
    r = json.load(open(CAL, encoding="utf-8"))
    out = {}
    for key, v in (r.get("per_atom") or {}).items():
        if v.get("verdict") == "CALIBRATED":
            k, i = key.rsplit("#", 1)
            out.setdefault(k, set()).add(int(i))
    return out


def atoms_alignment(reader_top1, top1_usable, text, call=None):
    """生产出口。reader_top1: 读者 s2 的 top-1 结; top1_usable: 该读数是否在出口闸 usable 里(K1 + 稳定)。"""
    if not reader_top1 or not top1_usable:
        return {"status": "withheld", "reason": "读者 top-1 结不可用(不稳或无 K1 判定) —— 没有「对哪个结对齐」就不判", "atoms": []}
    cal = calibrated_atoms().get(reader_top1, set())
    if not cal:
        return {"status": "withheld", "knot": reader_top1, "reason": f"{reader_top1} 没有校对通过的原子 —— 一个都不判", "atoms": []}
    res = judge(reader_top1, text, framing="a", call=call)
    if res is None:
        return {"status": "failed", "knot": reader_top1, "reason": "判官调用或格式失败", "atoms": []}
    atoms = [dict(r, calibrated=r["i"] in cal) for r in res]
    for r in atoms:
        if not r["calibrated"]:
            r["canonical"] = "not_calibrated"      # 没过校对: 不判(不是「没做」)
    judged = [r for r in atoms if r["calibrated"]]
    return {"status": "ok", "knot": reader_top1, "atoms": atoms,
            "summary": {"calibrated": len(judged), "satisfied": sum(r["canonical"] == "satisfied" for r in judged),
                        "unsatisfied": sum(r["canonical"] == "unsatisfied" for r in judged),
                        "uncertain": sum(r["canonical"] == "uncertain" for r in judged)},
            "★rule": "只看逐原子状态; 不出总分、不出放行布尔。uncertain 与 not_calibrated 都不是「没做」。"}
