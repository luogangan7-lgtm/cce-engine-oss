#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""命题框架层 —— 「**先确定文本支持哪些命题, 再决定哪些标签允许输出**」。

★★★ 来路: 2026-09-14 外部技术评估的第一优先方向。现有资格层验的是**形式**
  (片段逐字 · 两支同对象 · kind 在枚举内); 五类语义关系的最小对照实测它 **10/10 全部错误放行**,
  其中 **6/10 是合同明文支持的判定** ⇒ 那三类的漏没有解释空间。

★★★ 本层做什么: 把一条证据拆成**六个可独立核验的槽位**, 再由**确定性规则**判它
  支持 / 反驳 / **证据不足**。★ 库内「乘性因子链」纪律: 任一因子为 0 则整体为 0, 逐项核验。

★★★ 本层**不做**什么 —— 这是它最重要的边界:
  它**不承诺结构化抽取会正确**。它只把错误**挪到可逐项检验的地方**。
  槽位由谁填、填错多少, 是**另一个未测的问题**; 本层的验收只给出
  「**槽位标注正确时, 判据能拦住多少**」这个**能力上界**。

★★★ 三态而不是两态(库内 2026-09-10 最值钱的那条教训):
  合同**没有规定**证据不足时的回退规则 ⇒ 缺槽位只能落 **UNDERDETERMINED**, **不许靠常识补成反驳**。
  同一天对「文本没给出证据」用两套标准, 是那次栽的根。
"""

# ── 三态 ──────────────────────────────────────────────────────────────
SUPPORTS = "SUPPORTS"
REFUTES = "REFUTES"
UNDERDETERMINED = "UNDERDETERMINED"      # ★ 证据不足 ≠ 反驳

# ── 槽位取值 ──────────────────────────────────────────────────────────
UNSPEC = "UNSPECIFIED"

SPEAKER = ("SELF", "OTHER", UNSPEC)
POLARITY = ("ASSERTED", "NEGATED", UNSPEC)
TIME = ("PAST_OR_PRESENT", "FUTURE", UNSPEC)
CITATION = ("DIRECT", "REPORTED", UNSPEC)
# ★★★ possession 单独一个槽位, 因为合同的 Q 是**析取**(已拥有 **或** 已经历)。
#   2026-09-10 栽过: 只否定了第一支就当 Q 不成立, 而**沉默不是否定**。
#   ⇒ 只有 BOTH_NEGATED(两支都被明确否定) 才构成反驳; 只否一支 ⇒ ONE_NEGATED ⇒ 证据不足。
POSSESSION = ("OWNED", "EXPERIENCED", "ONE_NEGATED", "BOTH_NEGATED", UNSPEC)
# ★★★ predicate 的两个否定取值**依据不同**, 必须分开 —— 2026-09-14 拆:
#   RESTATES_IDENTIFIER  只复述/指认标识, 没有关于该对象的陈述
#                        ← **附件 A**, owner 2026-09-14 裁定**升为合同** ⇒ BY_CONTRACT
#   NOT_OF_DECLARED_KIND 有关于它的陈述, 但不属于所声明的那一类
#                        ← **五类各自的成立条件**, **仍是解释** ⇒ BY_INTERPRETATION
#   ★ 拆之前这两条混在同一个取值里, 一升就会把没升的那条**一起**当成合同。
PREDICATE_NEG = ("RESTATES_IDENTIFIER", "NOT_OF_DECLARED_KIND")

SLOTS = ("speaker", "object", "predicate", "polarity", "time", "citation", "possession")

# ── 合同的两个必要条件 ────────────────────────────────────────────────
CONJ_P = "输出新信息增量"
CONJ_Q = "谈论对象是自己已拥有或已经历的"

# ★★★ 规则分两档, **必须能分别开关** —— 因为最小对照的依据也分两档。
#   报「只用明文规则拦住多少」与「明文+解释拦住多少」是两个不同的数, 不许合并。
BY_CONTRACT = "合同明文"
BY_INTERPRETATION = "依赖解释"

# ★★★ 2026-09-14 合同变更(owner 裁定, **不是**读数推出来的):
#   附件 A「增量相对 x 成立 ⟺ 文本含关于 x 的陈述, 且该陈述**不能由 x 的公开标识本身推出**」
#   由「我的提案, 可被推翻」**升为合同明文**。见 OWNER_DECISION_ANNEX_definitions.md 的 A 节。
#   ⇒ RESTATES_IDENTIFIER 这一条从 BY_INTERPRETATION 迁到 **BY_CONTRACT**。
#   ★ **只升 A**: 「五类各自的成立条件」**未升**, NOT_OF_DECLARED_KIND 仍是 BY_INTERPRETATION。


class ClaimFrame:
    """一条证据的六槽位。★ 槽位缺失**不报错**, 落 UNSPECIFIED, 由判据判成证据不足。"""

    def __init__(self, span, supports, object=None, predicate=None,
                 speaker=UNSPEC, polarity=UNSPEC, time=UNSPEC,
                 citation=UNSPEC, possession=UNSPEC, increment_kind=None):
        if not isinstance(span, str) or not span.strip():
            raise ValueError("★ 片段为空 —— 空片段不是证据")
        for name, val, allowed in (("speaker", speaker, SPEAKER),
                                   ("polarity", polarity, POLARITY),
                                   ("time", time, TIME),
                                   ("citation", citation, CITATION),
                                   ("possession", possession, POSSESSION)):
            if val not in allowed:
                raise ValueError("★ 槽位 %s 取值 %r 不在 %r 内 —— "
                                 "未知取值不许静默当成 UNSPECIFIED" % (name, val, allowed))
        self.span = span
        self.supports = supports
        self.object = object
        self.predicate = predicate
        self.speaker = speaker
        self.polarity = polarity
        self.time = time
        self.citation = citation
        self.possession = possession
        self.increment_kind = increment_kind

    def missing_slots(self):
        out = []
        for s in SLOTS:
            v = getattr(self, s)
            if v is None or v == UNSPEC:
                out.append(s)
        return out

    def as_dict(self):
        return {s: getattr(self, s) for s in SLOTS}


def _q(f, use_interpretation):
    """判 Q = 谈论对象是**自己**已拥有或已经历的。返回 (状态, 理由, 依据档)。"""
    # ① 否定辖域 —— 合同明文: 片段落在否定辖域内, 它就不支撑肯定命题
    if f.polarity == "NEGATED":
        return REFUTES, "片段落在**否定辖域**内 ⇒ 不支撑肯定命题", BY_CONTRACT
    # ② 说话者 —— 合同明文写「**自己**已拥有或已经历」
    if f.speaker == "OTHER":
        return REFUTES, "谓词的主语**不是说话人自己** ⇒ 合同要求「自己」", BY_CONTRACT
    # ③ 时间 —— 合同明文「若谈的是**期望中未得之物**→itch」
    if f.time == "FUTURE":
        return REFUTES, "时间是**未来** ⇒ 期望中未得之物, 合同明文路由到 itch", BY_CONTRACT
    # ④ 析取的否定 —— ★★★ 只有两支都被明确否定才算反驳
    if f.possession == "BOTH_NEGATED":
        return REFUTES, "**已拥有与已经历两支都被明确否定** ⇒ Q 不成立", BY_CONTRACT
    if f.possession == "ONE_NEGATED":
        return (UNDERDETERMINED,
                "只否定了析取的**一支**, 另一支**沉默** —— "
                "**沉默不是否定**(2026-09-10 教训), 合同未规定此时的回退 ⇒ 证据不足",
                BY_CONTRACT)
    miss = [s for s in ("speaker", "polarity", "time", "possession")
            if getattr(f, s) == UNSPEC]
    if miss:
        return UNDERDETERMINED, "槽位缺失: %s ⇒ 证据不足(**不许靠常识补成反驳**)" % miss, BY_CONTRACT
    if f.possession in ("OWNED", "EXPERIENCED"):
        return SUPPORTS, "自己 · 肯定 · 非未来 · 明确%s ⇒ 支持" % f.possession, BY_CONTRACT
    return UNDERDETERMINED, "possession 未落到肯定的一支 ⇒ 证据不足", BY_CONTRACT


def _p(f, use_interpretation):
    """判 P = 输出新信息增量。返回 (状态, 理由, 依据档)。"""
    if f.polarity == "NEGATED":
        return REFUTES, "片段落在**否定辖域**内 ⇒ 不支撑肯定命题", BY_CONTRACT
    # ★ 下面两条**依赖解释** —— 合同没定义「输出」是否含转述, 也没定义五类各自的成立条件
    # ★★★ 附件 A(2026-09-14 已升为合同): 只复述/指认标识 ⇒ 不产生增量。
    #   这一条**不在** use_interpretation 门内 —— 它现在是**合同明文**。
    if f.predicate == "RESTATES_IDENTIFIER":
        return (REFUTES,
                "该片段**只复述/指认了对象标识**, 没有给出关于它的陈述 ⇒ 不产生增量。"
                "★ 依据: 附件 A(owner 2026-09-14 **已裁定升为合同**)",
                BY_CONTRACT)
    if use_interpretation:
        if f.citation == "REPORTED":
            return (REFUTES,
                    "该陈述是**转述他人主张**, 说话人并未「输出」它。"
                    "★ 合同**未定义**「输出」是否含转述 ⇒ **本条依赖解释**, 可被推翻",
                    BY_INTERPRETATION)
        if f.predicate == "NOT_OF_DECLARED_KIND":
            return (REFUTES,
                    "谓词**不属于**所声明的那一类增量。"
                    "★ 合同只**列出**五类、**未定义**各自成立条件 ⇒ **本条依赖解释**, 可被推翻",
                    BY_INTERPRETATION)
    miss = [s for s in ("polarity", "citation", "predicate") if getattr(f, s) in (None, UNSPEC)]
    if miss:
        return UNDERDETERMINED, "槽位缺失: %s ⇒ 证据不足" % miss, BY_CONTRACT
    if not f.increment_kind:
        return UNDERDETERMINED, "未声明增量种类 ⇒ 证据不足", BY_CONTRACT
    return SUPPORTS, "肯定 · 直陈 · 谓词与声明的种类相符 ⇒ 支持", BY_CONTRACT


def adjudicate(frame, use_interpretation=True):
    """判一条证据对它所声称支撑的那个必要条件是 支持/反驳/证据不足。"""
    if frame.supports == CONJ_Q:
        return _q(frame, use_interpretation)
    if frame.supports == CONJ_P:
        return _p(frame, use_interpretation)
    return UNDERDETERMINED, "该证据没有对应到合同的任一必要条件", BY_CONTRACT


def allow_label(frames, required_conjuncts=(CONJ_P, CONJ_Q), use_interpretation=True):
    """★★★ 「先确定文本支持哪些命题, 再决定哪些标签允许输出」——本层的唯一出口。

    **乘性因子链**(库内引用纪律④): 每个必要条件都必须被**支持**; 任一为反驳或证据不足 ⇒ 整体不许输出。
    返回 dict, 含 allow / per_conjunct / 理由 / 用到了哪一档规则。
    """
    if not frames:
        return {"allow": False, "why": "★ 没有任何证据 ⇒ 不许输出(fail-closed)",
                "per_conjunct": {}, "依据档": []}
    per, bases = {}, []
    for c in required_conjuncts:
        fs = [f for f in frames if f.supports == c]
        if not fs:
            per[c] = {"state": UNDERDETERMINED, "why": "该必要条件**没有任何证据**", "依据": BY_CONTRACT}
            continue
        # 一个条件有多条证据时: 只要有一条 REFUTES 就反驳; 否则取最强的那条
        best = None
        for f in fs:
            st, why, basis = adjudicate(f, use_interpretation)
            if st == REFUTES:
                best = (st, why, basis)
                break
            if best is None or (best[0] == UNDERDETERMINED and st == SUPPORTS):
                best = (st, why, basis)
        per[c] = {"state": best[0], "why": best[1], "依据": best[2]}
        bases.append(best[2])
    allow = all(v["state"] == SUPPORTS for v in per.values())
    return {"allow": allow, "per_conjunct": per,
            "依据档": sorted(set(b for b, v in zip(bases, per.values())
                              if v["state"] != SUPPORTS)) if not allow else [],
            "why": ("每个必要条件都被**支持** ⇒ 允许输出" if allow else
                    "这些必要条件未被支持: %s ⇒ **不许输出**(乘性因子链: 任一为 0 则整体为 0)"
                    % {k: v["state"] for k, v in per.items() if v["state"] != SUPPORTS})}


if __name__ == "__main__":
    ok = [ClaimFrame("gives me about 14 hours", CONJ_P, object="the Oticon More 1",
                     predicate="OF_DECLARED_KIND", polarity="ASSERTED", time="PAST_OR_PRESENT",
                     citation="DIRECT", speaker="SELF", possession="OWNED", increment_kind="数据"),
          ClaimFrame("the Oticon More 1 I own", CONJ_Q, object="the Oticon More 1",
                     predicate="OWNERSHIP", polarity="ASSERTED", time="PAST_OR_PRESENT",
                     citation="DIRECT", speaker="SELF", possession="OWNED")]
    print(allow_label(ok)["allow"], "← 正例应为 True")
