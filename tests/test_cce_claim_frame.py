# -*- coding: utf-8 -*-
"""命题框架层的闸。

★★★ 分工(变异实测逼出来的):
  **最小对照**测**端到端能力上界**; **规则级单元测试**测**每一条规则单独是否在起作用**。
  起因: 2026-09-14 变异实测发现 polarity / possession / time 三条规则在最小对照上
  **被冗余保护** —— 删掉任一条, 端到端结果**一点不变**。而
  **ONE_NEGATED 那条分支(「沉默不是否定」, 库内 2026-09-10 最值钱的教训)完全零覆盖**:
  把它从 UNDERDETERMINED 改成 REFUTES, 10 对最小对照**一个都没红**。
"""
import importlib.util, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
ANN = ROOT / "tests/data/claim_frame_annotations.json"
RES = ROOT / "results/claim_frame_upper_bound.json"
BASE = ROOT / "results/semantic_blindspot_scan.json"
PROBE = ROOT / "probes/claim_frame_upper_bound.py"

import cce_claim_frame as CF                                        # noqa: E402

P, Q = CF.CONJ_P, CF.CONJ_Q
FULL_Q = dict(speaker="SELF", polarity="ASSERTED", time="PAST_OR_PRESENT",
              citation="DIRECT", possession="OWNED", predicate="OWNERSHIP")
FULL_P = dict(speaker="SELF", polarity="ASSERTED", time="PAST_OR_PRESENT",
              citation="DIRECT", possession="OWNED", predicate="OF_DECLARED_KIND",
              increment_kind="数据")


def _q(**ov):
    kw = dict(FULL_Q); kw.update(ov)
    return CF.adjudicate(CF.ClaimFrame("x", Q, object="o", **kw))


def _p(**ov):
    kw = dict(FULL_P); kw.update(ov)
    return CF.adjudicate(CF.ClaimFrame("x", P, object="o", **kw))


# ── 规则级: 每条规则单独可测 + 正向对照 ────────────────────────────────
def test_规则_否定辖域():
    assert _q()[0] == CF.SUPPORTS, "★ 正向对照失败 —— 全默认应当支持"
    assert _q(polarity="NEGATED")[0] == CF.REFUTES
    assert _p(polarity="NEGATED")[0] == CF.REFUTES


def test_规则_说话者不是自己():
    assert _q()[0] == CF.SUPPORTS
    assert _q(speaker="OTHER")[0] == CF.REFUTES


def test_规则_未来时():
    assert _q()[0] == CF.SUPPORTS
    assert _q(time="FUTURE")[0] == CF.REFUTES


def test_规则_析取要两支都否_沉默不是否定_库内最值钱教训():
    """★★★ 库内 2026-09-10 最值钱的教训, 编码在这里。
    变异实测发现它在最小对照上**零覆盖** —— 所以必须有这条单元测试。"""
    assert _q()[0] == CF.SUPPORTS, "★ 正向对照"
    both = _q(possession="BOTH_NEGATED")
    one = _q(possession="ONE_NEGATED")
    assert both[0] == CF.REFUTES, "★ 两支都否定应当是**反驳**"
    assert one[0] == CF.UNDERDETERMINED, (
        "★★★ 只否一支被判成了 %r —— 应当是**证据不足**。"
        "「没有提供经历证据」与「明确没有经历」**不是同一件事**; "
        "合同未规定证据不足时的回退, **不许靠常识补成反驳**。" % (one[0],))
    assert "沉默不是否定" in one[1]


def test_规则_缺槽位落证据不足而不是反驳():
    for s in ("speaker", "polarity", "time", "possession"):
        st, why, _ = _q(**{s: CF.UNSPEC})
        assert st == CF.UNDERDETERMINED, "★ 缺 %s 应落证据不足, 实际 %r" % (s, st)
        assert "不许靠常识补" in why or "证据不足" in why


def test_规则_转述与类型不符是依赖解释的_可关():
    """★ 这两条**依赖解释**(合同没定义「输出」是否含转述, 也没定义五类成立条件)
    ⇒ 必须**可关**, 且关掉后它们不再拦。"""
    assert _p(citation="REPORTED")[0] == CF.REFUTES
    assert _p(predicate="NOT_OF_DECLARED_KIND")[0] == CF.REFUTES
    for ov in ({"citation": "REPORTED"}, {"predicate": "NOT_OF_DECLARED_KIND"}):
        kw = dict(FULL_P); kw.update(ov)
        st, _, _ = CF.adjudicate(CF.ClaimFrame("x", P, object="o", **kw),
                                 use_interpretation=False)
        assert st == CF.SUPPORTS, "★ 关掉解释档后 %r 仍在拦 ⇒ 它没被正确归档" % ov
    # 依据档必须标对
    assert _p(citation="REPORTED")[2] == CF.BY_INTERPRETATION
    assert _q(speaker="OTHER")[2] == CF.BY_CONTRACT


def test_未知槽位取值不许静默当成UNSPECIFIED():
    try:
        CF.ClaimFrame("x", Q, object="o", speaker="MAYBE_SELF")
    except ValueError as e:
        assert "不在" in str(e)
    else:
        raise AssertionError("★ 未知取值被静默接受了")


def test_乘性因子链_任一条件不支持则整体不许输出():
    good_p = CF.ClaimFrame("a", P, object="o", **FULL_P)
    good_q = CF.ClaimFrame("b", Q, object="o", **FULL_Q)
    assert CF.allow_label([good_p, good_q])["allow"] is True, "★ 正向对照"
    bad_q = dict(FULL_Q); bad_q["speaker"] = "OTHER"
    assert CF.allow_label([good_p, CF.ClaimFrame("b", Q, object="o", **bad_q)])["allow"] is False
    assert CF.allow_label([good_p])["allow"] is False, "★ 缺 Q 的证据应当不许输出"
    assert CF.allow_label([])["allow"] is False, "★ 零证据必须 fail-closed"


def test_零证据必须判负_不许vacuous_pass():
    """★ 库内 FAIL-VACUOUS 铁律: n=0 的断言必须判负, 禁止报 PASS。"""
    r = CF.allow_label([])
    assert r["allow"] is False and "fail-closed" in r["why"]


# ── 端到端上界 ────────────────────────────────────────────────────────
def test_上界结果由冻结判据现算():
    if not RES.exists():
        return
    spec = importlib.util.spec_from_file_location("ub", PROBE)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    res = json.loads(RES.read_text(encoding="utf-8"))
    rows = res["rows"]
    for tier in ("只用合同明文", "明文+解释"):
        leak = sum(r[tier]["★错误放行"] for r in rows)
        assert res["★★★合计"][tier] == "%d/%d" % (leak, len(rows)), "★ %s 合计与现算不符" % tier
    ctrl = sum(r["明文+解释"]["★对照有效"] for r in rows)
    assert res["★★★合计"]["对照有效(明文+解释)"] == "%d/%d" % (ctrl, len(rows))
    assert ctrl == len(rows), (
        "★★★ 对照不再全部有效 ⇒ 判据可能退化成恒拒, 那 0/10 就毫无意义")


def test_两档必须分开报_且明文档不得靠解释撑着():
    if not RES.exists():
        return
    res = json.loads(RES.read_text(encoding="utf-8"))
    mx = {"否定辖域", "归属", "时态"}
    for k, v in res["★★★逐类错误放行"].items():
        if k in mx:
            assert v["只用合同明文"] == "0/2", (
                "★★★ %s 是**合同明文**支持的判定, 只用明文就该拦住, 实际 %s"
                % (k, v["只用合同明文"]))
        else:
            assert v["只用合同明文"] == "2/2" and v["明文+解释"] == "0/2", (
                "★★★ %s **依赖解释**: 只用明文应当拦不住(实际 %s), 加解释后才拦住(实际 %s) —— "
                "若只用明文就拦住了, 说明它被错归成了明文规则"
                % (k, v["只用合同明文"], v["明文+解释"]))
    note = res["★★★两档为什么必须分开报"]
    assert "不许合并" in note and "冒充" in note, (
        "★ 必须明写「不许合并成一个总数」与「会让靠解释拦住的冒充合同支持的」")


def test_产物自带能力上界声明():
    if not RES.exists():
        return
    res = json.loads(RES.read_text(encoding="utf-8"))
    k = [x for x in res if "能力上界" in x][0]
    v = res[k]
    for must in ("槽位标注正确", "另一个未测的问题", "不承诺"):
        assert must in v, "★ 上界声明里缺: %s" % must
    assert res["★对照基线(现有资格层, 同一批 10 对)"] == "10/10", (
        "★ 对照基线丢了 —— 没有它就看不出这层买到了什么")


def test_规则冗余必须被如实登记():
    """★ 端到端对照全绿**不等于**每条规则都在起作用。
    变异实测发现 polarity/possession/time 三条互相冗余, ONE_NEGATED 零覆盖 —— 这要留档。"""
    if not RES.exists():
        return
    res = json.loads(RES.read_text(encoding="utf-8"))
    k = [x for x in res if "规则冗余" in x]
    assert k, "★★★ 冗余发现没留档 ⇒ 下一个人会以为端到端全绿就够了"
    v = res[k[0]]
    body = json.dumps(v, ensure_ascii=False)
    assert "零覆盖" in body and "ONE_NEGATED" in body, "★ 缺最要命那条(ONE_NEGATED 零覆盖)"
    assert "冗余是**真实的**" in body or "真实的" in body, (
        "★ 必须说明冗余是**语义上真实共现**, 不是标注错误")
    mut = v["★★★变异实测复核(镜像_未动仓)"]
    assert mut["小计"].count("7/7"), "★ 变异复核结果变了"
    assert all("被抓到" in x for k2, x in mut.items() if k2 != "小计"), (
        "★★★ 有变异没被抓到 —— 那条规则又回到零覆盖了")
    assert "★通则" in v


def test_本层未接进生产_且说清楚了():
    if not RES.exists():
        return
    res = json.loads(RES.read_text(encoding="utf-8"))
    k = [x for x in res if "与现有资格层的关系" in x][0]
    v = res[k]
    assert "新增一道, 不替换" in v and "未接进生产" in v, (
        "★ 必须写明这层是新增、未接线 —— 否则会被读成「已经在用了」")


def test_probe零调用():
    src = PROBE.read_text(encoding="utf-8")
    for bad in ("call_model", "MINIMAX", "requests.post", "_load_key"):
        assert bad not in src, "★★★ 上界测量里出现模型调用入口 %r" % bad


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("命题框架层闸 %d 项全过" % n)
