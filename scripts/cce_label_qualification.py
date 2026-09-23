#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合同层的标签资格 —— P3 的「未确认候选」这一档, 落在**输出层**而不是 prompt 层。

## 它解决的是哪个问题
`OWNER_DECISION_ANNEX_definitions.md` 附件 C 把先前混用的**四件事**拆开:
  ① 九结权重向量   ② top-1 读数   ③ 候选标签(未确认)   ④ 「已确认存在」的断言
并裁定: **P3 的证据义务只约束 ④**。
这一拆当场排掉了我自己报过的那个「无法同时执行」的冲突 ——
「输出端必须给一个确定标签」与「禁止无支持的确定标签」并不矛盾:
**top-1(②)照常给, 缺支持时不升格为 ④, 而落进 ③。**

## ★★★ 为什么落在输出层, 不落在 prompt 层
2026-09-13 gen9 双臂重测(1291 次真实 M3 调用, 判据测量前冻结)实测:
把判别式/负例/决策树塞进生产 s2 prompt(即「生产向闸对齐」这条路线),
**display 出现率由 1/80 涨到 40/80**, 且出现**倒挂** ——
在合同说**不该**给的 A 臂(56%)比在**可以**给的 B 臂(41%)上给得更多。
⇒ **把合同文本塞进 prompt 是已被测出会让读数更偏的路。**
  本模块因此**一个字都不进 prompt**: 它只在读数**产出之后**给它一个资格标注,
  不改 `instrument_hash`、不换代、不碰任何冻结件。

## ★ 它的默认值是 fail-closed
没有**可指名原文片段**的正面证据 ⇒ 一律 `UNCONFIRMED_CANDIDATE`。
这是附件 B 那条「**指不出原文片段的推断 = 没有证据**」的直接实现 ——
不是「弱证据」, 是没有。

## ★★ 它**不做**什么(写在代码里, 不写在注释里)
- 它**不判断**文本里有没有证据 —— 那需要读文本, 是上游的事(人或模型)。
  本模块只负责: **要求证据被指名**, 并在没被指名时**拒绝升格**。
- 它**不改变** top-1 本身。top-1 该发照发。
- 它**不是**仪器层的可用性判定 —— 那是 `cce_k1_status.knot_readout_usable`,
  回答的是「这台仪器上这种读数形态能不能引用」。两件事必须都过。
"""
import json
import re

# ══ 状态 ══════════════════════════════════════════════════════════════
# ★★★★ 2026-09-14 **降格重构**。原来只有两档(CONFIRMED / CANDIDATE), 而 CONFIRMED
#   叫「已确认存在」—— **那个名字超出了这一层实际验过的东西**。
#
#   零调用反例(webgpt 给的形状, 本仓已复现, 见 tests/test_cce_citation_layer_is_not_semantic.py):
#     原文: "I have never owned or tried the Oticon, and I still want one."
#     证书: Q 支引用 "owned or tried the Oticon" —— **片段真实存在、对象正确**,
#           但它处在 "never ..." 的**否定辖域**内, 是 Q 的**反面**。
#     旧实现: 判 CONFIRMED_PRESENT。
#   ⇒ **逐字核对只验了出处与结构, 没有验证据与必要条件之间的语义关系。**
#     且这不是一个孤例: 逐字核对同样验不了 **归属 / 时态 / 引用层级 / 类型成员资格**。
#
#   ★ 为什么**不加否定词正则**: 那是补症状 —— 它修掉这一个例子, 留着其余四类,
#     却制造「语义风险已关住」的错觉。**那正是这次要消除的误解本身。**
CANDIDATE = "UNCONFIRMED_CANDIDATE"      # ③ 没有证据 ⇒ 候选
CITED_UNVERIFIED = "CITED_SEMANTICS_UNVERIFIED"   # ③′ 有引文: 出处可核, **语义未独立验证**
RULE_CONFIRMED = "RULE_CONFIRMED"        # ④ 语义由**确定性识别器**验过 —— **尚未实现**

# ★ 兼容旧名: CONFIRMED 现在指向 ③′ 而不是 ④。任何写着「已确认存在」的下游
#   都会因此拿到一个**更弱**的状态 —— 这是有意的, 降格不该悄悄发生。
CONFIRMED = CITED_UNVERIFIED

_STATES = (CANDIDATE, CITED_UNVERIFIED, RULE_CONFIRMED)

# ★ 证据的来源决定它**最高**能到哪一档 —— 这是本次重构的核心。
PROVENANCE_CEILING = {
    "model": CITED_UNVERIFIED,   # 模型抽取: **最高只能到 ③′**, 不得单独拥有确认权
    "human": CITED_UNVERIFIED,   # 人工引用: 同样只证明出处, 语义仍需规则或另行论证
    "rule": RULE_CONFIRMED,      # 确定性识别器: 可到 ④ —— 但识别器**尚未实现**
}


# ★ 合同在 display 判别式里**枚举过**的增量种类。写死在这里是故意的:
#   它不是我发明的分类, 是从 config/knot_taxonomy.json 的判别式原文里抄来的
#   「输出**新信息增量**(具体型号/数据/使用细节/纠错/结构化经验)」——
#   本模块**不判断**一段话属不属于某一种(那要读文本), 只**要求调用方指名**是哪一种,
#   并拒绝合同没枚举过的种类。有闸现算这张表与判别式原文一致。
INCREMENT_KINDS = ("具体型号", "数据", "使用细节", "纠错", "结构化经验")


class EvidenceSpan:
    """一条正面证据 = **原文里的一个片段** + 它支撑哪个必要条件 + **它是关于哪个对象的**。

    ★ `span` 必须**逐字**出现在 `text` 里 —— 构造时当场核, 核不上直接抛。
      这条是附件 B 的可操作化: 指不出片段的推断不算证据。

    ★★ `about` 是 **P2** 的落点: 两个必要条件必须落在**同一个对象**上 ——
      `∃x[P(x) ∧ Q(x)]` 与 `(∃x P(x)) ∧ (∃y Q(y))` **不等价**。
      本模块**不做**对象识别(那要读文本), 它**要求调用方指名对象**,
      然后**机器可核地**比对两支是不是同一个。指不出对象 ⇒ 不升格。

    ★★★ `increment_kind` 只在这条片段支撑「信息增量」那一支时必填:
      库里记过一条 ——「**不能把『对象相关的事实』当作『关于对象的信息增量』**」。
      所以增量这一支额外要求: ① 指名它属于合同枚举的哪一种;
      ② 片段**去掉对象标识之后仍有内容** —— 只是复述型号名不产生增量(附件 A)。
    """

    def __init__(self, span: str, supports: str, text: str,
                 about: str = None, increment_kind: str = None):
        if not isinstance(span, str) or not span.strip():
            raise ValueError("★ 证据片段为空 —— 空片段不是证据")
        if span not in text:
            raise ValueError(
                "★★★ 证据片段**不在原文里**: %r\n  原文: %r\n"
                "  —— 指不出原文片段的推断 = 没有证据(附件 B), 不是弱证据。"
                % (span[:60], text[:120]))
        if not isinstance(supports, str) or not supports.strip():
            raise ValueError("★ 没写这条片段支撑**哪个**必要条件 —— 证据要指向条款")
        if about is not None and (not isinstance(about, str) or not about.strip()):
            raise ValueError("★ about 给了但是空的 —— 要么指名对象, 要么别给")
        if increment_kind is not None and increment_kind not in INCREMENT_KINDS:
            raise ValueError(
                "★★★ 增量种类 %r **不在合同枚举里** %r —— "
                "合同枚举过的种类之外不算增量, 不许自己加一种。"
                % (increment_kind, list(INCREMENT_KINDS)))
        self.span, self.supports = span, supports
        self.about, self.increment_kind = about, increment_kind

    def beyond_identifier(self) -> bool:
        """片段去掉对象标识之后**还剩内容**吗 —— 只复述型号名不产生增量(附件 A)。"""
        if not self.about:
            return False
        rest = self.span.replace(self.about, " ")
        return len("".join(rest.split())) >= 2

    def as_dict(self):
        return {"span": self.span, "supports": self.supports,
                "about": self.about, "increment_kind": self.increment_kind}


def qualify(knot: str, text: str, evidence=None, required_conjuncts=None,
            require_same_object: bool = True, provenance: str = "model") -> dict:
    """给一个 top-1 读数做**合同层**资格标注。

    knot:                被标注的结
    text:                被测文本(片段必须出自它)
    evidence:            EvidenceSpan 列表; **空或 None ⇒ 一律降为候选**
    required_conjuncts:  合同要求的必要条件列表; 每一条都必须**至少有一条**证据支撑
    provenance:          证据由谁产出 —— "model" / "human" / "rule"。**默认 model**(最保守的假设)。
                         它决定这次**最高**能到哪一档: 模型与人工都只能到 ③′(出处可核·语义未验),
                         只有 "rule"(确定性识别器)能到 ④ —— 而该识别器**尚未实现**。
    require_same_object: **默认 True** —— P2: 两支必须落在同一个对象上。
                         关掉它要显式传 False, 且产物里会写明「本次未检查对象绑定」。

    返回 dict, 含 state / why / evidence / ★这不说明什么。
    """
    ev = list(evidence or [])
    for e in ev:
        if not isinstance(e, EvidenceSpan):
            raise TypeError("★ 证据必须是 EvidenceSpan(构造时会核片段真在原文里), 不接受裸字符串")
    req = list(required_conjuncts or [])

    if not ev:
        return _out(CANDIDATE, knot, ev, req,
                    "没有任何**可指名原文片段**的正面证据 ⇒ 不得升格为「已确认存在」。"
                    "★ 这不是「证据弱」, 是**没有证据**(附件 B)。")
    if not req:
        return _out(CANDIDATE, knot, ev, req,
                    "★ 没有给出**合同要求的必要条件**清单 ⇒ 无法判断证据是否覆盖它们。"
                    "缺清单时**默认不升格** —— 默认值必须是保守的那一侧。")
    missing = [c for c in req
               if not any(c == e.supports for e in ev)]
    if missing:
        return _out(CANDIDATE, knot, ev, req,
                    "这些必要条件**没有任何片段支撑**: %s ⇒ 不得升格。"
                    "★ 合取项缺一即不成立, 不许用其它条款的证据顶替。" % missing)

    # ── P2: 两个必要条件必须落在**同一个对象**上 ──────────────────────────
    if require_same_object:
        used = [e for e in ev if e.supports in req]
        anon = [e.supports for e in used if not e.about]
        if anon:
            return _out(CANDIDATE, knot, ev, req,
                        "这些支撑片段**没有指名它是关于哪个对象的**: %s ⇒ 不得升格。"
                        "★ P2 要求 `∃x[P(x) ∧ Q(x)]` —— 指不出对象就无从判断两支是否落在同一个 x 上。"
                        % sorted(set(anon)))
        # ── P2 v2 (2026-09-23 授权代定, 见 P2_FAIL_FAMILIES_DECIDED_2026-09-23.md): ──
        #   合同是 `∃x[P(x) ∧ Q(x)]` —— 一个**存在**量词。v1 要求「所有证据的对象集合只有一个元素」,
        #   比合同严: 只要某支多给了一条指向别的东西的证据, 整张证书就被拦(真实语料 16 张 P2_FAIL 里 8 张是这样)。
        #   v2: **各支各自的对象集合取交集** —— 交集非空 ⇒ 存在见证 x; 交集外的证据是**多余**(记账, 不算数, 不拦)。
        #   ★ 仍然**不做**别名归并、**不认**子串/部件⊂整机: 「the Oticon」与「Oticon More」在这里还是两个对象 ⇒ fail-closed 选漏判。
        by_c = {c: sorted({e.about for e in used if e.supports == c}) for c in req}
        witness = set(by_c[req[0]]).intersection(*[set(v) for v in by_c.values()])
        if not witness:
            return _out(CANDIDATE, knot, ev, req,
                        "两个必要条件落在**不同对象**上(各支对象集合无交集): %r ⇒ 不得升格。"
                        "★★★ `∃x[P(x) ∧ Q(x)]` 与 `(∃x P(x)) ∧ (∃y Q(y))` **不等价** —— "
                        "「说了个型号」＋「用过别的东西」不能凑成一个 display。"
                        "★ 本模块**不做**别名归并(「the Oticon」与「Oticon More」在这里是两个对象): "
                        "归并需要读文本, 不归并会漏判、乱归并会误判 ⇒ **fail-closed 选漏判**。" % by_c,
                        p2={"binding": P2_BINDING, "per_conjunct_objects": by_c, "witness": []})
        surplus = [e for e in used if e.about not in witness]
        used = [e for e in used if e.about in witness]
        p2 = {"binding": P2_BINDING, "per_conjunct_objects": by_c, "witness": sorted(witness),
              "surplus_dropped": [e.as_dict() for e in surplus],
              "★surplus 怎么读": "交集之外的证据**不参与**资格判定(既不加分也不拦) —— 它指向别的对象, 与见证 x 无关。"}
        # ── 增量这一支的额外要求(库内教训: 对象相关的事实 ≠ 关于对象的信息增量) —— 只看见证 x 上的片段 ──
        for e in used:
            if not _is_increment_conjunct(e.supports):
                continue
            if not e.increment_kind:
                return _out(CANDIDATE, knot, ev, req,
                            "支撑「信息增量」的片段**没有指名它属于合同枚举的哪一种**"
                            "(%s) ⇒ 不得升格。★ 库内教训: **不能把「对象相关的事实」"
                            "当作「关于对象的信息增量」** —— 指名种类是让这件事可核。"
                            % list(INCREMENT_KINDS))
            if not e.beyond_identifier():
                return _out(CANDIDATE, knot, ev, req,
                            "支撑「信息增量」的片段 %r **去掉对象标识之后没剩下内容** ⇒ 不得升格。"
                            "★ 附件 A: 复述型号名/品类名**不产生增量** —— "
                            "增量必须是**不能由 x 的公开标识本身推出**的陈述。" % e.span)
    ceiling = PROVENANCE_CEILING.get(provenance)
    if ceiling is None:
        raise ValueError("★ 未知的证据来源 %r —— 只认 %r" % (provenance, list(PROVENANCE_CEILING)))
    if ceiling is RULE_CONFIRMED:
        raise NotImplementedError(
            "★★★ provenance='rule' 需要**确定性、窄覆盖的正证据识别器**, 它**尚未实现**。"
            "在它存在之前, 没有任何读数有资格进 ④ —— 不许用这个参数绕过去。")
    return _out(ceiling, knot, ev, req,
                "每个必要条件都有**可指名原文片段**的正面证据支撑"
                + ("; 且它们**落在同一个对象**上(P2 见证 x 存在), 增量支已指名合同枚举的种类且超出对象标识本身。"
                   if require_same_object else "; ★ **本次未检查对象绑定**(require_same_object=False)。"),
                p2=(p2 if require_same_object else {"binding": "unchecked"}))


# P2 绑定方式的版本号 —— 改它 = 改资格协议(不是仪器), 走 route 5: 预注册 + 与旧版读数「可比不可合」。
#   v1 "all_objects_equal"(2026-09-14): 所有证据的对象集合必须恰好一个元素。
#   v2 "witness_intersection"(2026-09-23 授权代定): 各支对象集合取交集, 非空即存在见证; 多余证据记账不拦。
P2_BINDING = "witness_intersection"


def _is_increment_conjunct(name: str) -> bool:
    """哪一支算「信息增量」—— 按条款名里的关键词认, 认不出就**不额外要求**(不假装认识)。"""
    return "增量" in name


def _out(state, knot, ev, req, why, p2=None):
    assert state in _STATES
    return {
        "block": "LABEL_QUALIFICATION",
        "knot": knot,
        "state": state,
        "why": why,
        "P2": p2,
        "evidence": [e.as_dict() for e in ev],
        "required_conjuncts": req,
        "★这一档是什么": {
            RULE_CONFIRMED: "④ 语义由**确定性识别器**验过 —— 可作为已确认判断引用。"
                            "★ 该识别器**尚未实现**, 现阶段不会有任何读数落到这一档。",
            CITED_UNVERIFIED: "③′ **出处可核对, 语义未独立验证** —— 片段确在原文里、对象已绑定, "
                              "但「这段话是否**支持**该必要条件」**没有被这一层验过**"
                              "(逐字核对验不了 否定/归属/时态/引用层级/类型成员资格)。"
                              "**不得**作为「已确认存在」引用。",
            CANDIDATE: "③ 候选标签 —— **top-1 照发**, 但**不得**作为「已确认存在」引用。",
        }[state],
        "★这一层没验什么": [
            "**否定辖域**: 「我从未拥有过甲」里的「拥有过甲」是真实子串, 但它支持的是 Q 的**反面**。",
            "**归属**: 「他说他用过」不是「我用过」。",
            "**时态**: 「打算买」不是「已拥有」。",
            "**引用层级**: 引述别人的话不是自述。",
            "**类型成员资格**: 片段里的那个东西是不是合同说的那类对象。",
            "★ 以上五类**都不是**逐字核对能验的。本层**不加针对某一类的补丁** —— "
            "补一类会留着其余四类, 却制造「语义风险已关住」的错觉。",
        ],
        "★它不说明什么": [
            "**不**说明 top-1 判得对或判错 —— 它只回答「有没有资格被断言为已确认存在」。",
            "**不**替代仪器层判定: 还要过 cce_k1_status.knot_readout_usable(那台仪器上这种读数形态能不能引用)。",
            "**不**进 prompt: 2026-09-13 gen9 实测把合同文本塞进生产 prompt 会让 display "
            "由 1/80 涨到 40/80 并出现倒挂(A 臂 56% > B 臂 41%) ⇒ 本模块只在读数产出**之后**工作。",
        ],
    }


def is_citable_as_confirmed(q: dict) -> bool:
    """唯一允许下游用来决定「能不能当**已确认判断**引用」的入口。

    ★★★ 2026-09-14 起它只在 ④(RULE_CONFIRMED)为真 —— 而 ④ 的识别器**尚未实现**,
      所以**现阶段它恒为 False**。这是有意的:
      零调用反例已证明这一层**允许形式合法、语义错误的证书通过**,
      ⇒ 在语义被独立验证之前, 没有东西有资格被叫作「已确认存在」。
    ★ 想知道「有没有带引文」用 has_cited_evidence(), **别用这个**。
    """
    return q.get("state") == RULE_CONFIRMED


def has_cited_evidence(q: dict) -> bool:
    """有没有**出处可核**的引文(③′) —— 这**不是**「已确认存在」。"""
    return q.get("state") == CITED_UNVERIFIED



# ══ 接线: 仪器层 × 合同层, 两道都必须过 ══════════════════════════════════
def citable_as_confirmed(knot, text, instrument_hash, evidence=None,
                         required_conjuncts=None, form="top1", **kw) -> dict:
    """**唯一**允许下游用来决定「这个标签能不能当已确认判断引用」的入口。

    ★★★ 为什么要这个函数而不是让下游各自拼:
      2026-09-13 建好合同层(qualify)之后, 全仓**零个生产调用方** —— 一层没人调的闸
      与没有这层在证据上等价, 而它更糟: 它**看起来**像有覆盖。
      ⇒ 把「两道都要过」做成**一个**入口, 下游只能整体用或整体不用, 不能只挑一道。

    两道各自回答**不同**的问题, 谁也不能顶替谁:
      · 仪器层 `cce_k1_status.knot_readout_usable(form, instrument_hash)`
        —— 「**这台仪器上**这种读数形态能不能引用」(K1 判定/继承/白名单)
      · 合同层 `qualify(...)`
        —— 「**这一条读数**有没有资格被断言为『已确认存在』」(证据义务 + 对象绑定)
    ★ 两道都过才 True。任一不过 ⇒ False, 且**分别**给出理由, 不合并成一句。
    """
    import sys as _s
    import os as _o
    _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
    import cce_k1_status as _K

    inst_ok, inst_why = _K.knot_readout_usable(form, instrument_hash=instrument_hash)
    q = qualify(knot, text, evidence=evidence, required_conjuncts=required_conjuncts, **kw)
    contract_ok = is_citable_as_confirmed(q)
    return {
        "block": "CITABLE_AS_CONFIRMED",
        "citable": bool(inst_ok and contract_ok),
        "instrument_gate": {"pass": bool(inst_ok), "why": inst_why,
                            "问的是": "这台仪器上这种读数形态能不能引用"},
        "contract_gate": {"pass": contract_ok, "why": q["why"], "state": q["state"],
                          "问的是": "这一条读数有没有资格被断言为「已确认存在」"},
        "qualification": q,
        "★两道不许互相顶替": "仪器层过了**不**代表合同层过; 合同层过了**不**代表这台仪器上能引用。"
                      "把任一道单独拿去当放行依据, 就是把两个不同的问题当成了一个。",
        "★不可引用时仍然可以做什么": "top-1 照发(它是 ② 不是 ④), 但只能标成 "
                           "**未确认候选**, 不得写成「已确认存在」。",
    }

if __name__ == "__main__":
    t = "Settled on the Oticon. Just holding off till payday to actually order it."
    print(json.dumps(qualify("display", t), ensure_ascii=False, indent=1))
    print(json.dumps(citable_as_confirmed("display", t, "d4cce4c745f3f991"),
                     ensure_ascii=False, indent=1)[:900])
