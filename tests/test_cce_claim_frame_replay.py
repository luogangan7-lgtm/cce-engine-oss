# -*- coding: utf-8 -*-
"""已付费真实证书回放的闸。

★★★ 本文件守的头一件事是一个**我自己犯过的错**:
  默认槽位原本写的是 possession="OWNED" —— 那是 **fail-open**。
  r3/MIS-2 的文本是「诊所展示机…**Mine** are a much older pair」, 说话人对
  「有没有用过那台展示机」**沉默**, 而默认值把它补成了 OWNED,
  等于**替模型补了一个文本不支持的槽位**。
  ⇒ 默认必须全 UNSPECIFIED: **漏标落证据不足**, 而不是落支持。
"""
import importlib.util, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
ANN = ROOT / "tests/data/claim_frame_replay_annotations.json"
ANN2 = ROOT / "tests/data/claim_frame_annotations.json"
RES = ROOT / "results/claim_frame_replay.json"
PROBE = ROOT / "probes/claim_frame_replay.py"
import cce_claim_frame as CF                                        # noqa: E402


def test_默认槽位必须全部是UNSPECIFIED_否则是fail_open():
    """★★★ 两份标注档案的默认都必须 fail-closed。"""
    for f in (ANN, ANN2):
        d = json.loads(f.read_text(encoding="utf-8"))
        dflt = d["★默认槽位"]
        bad = {k: v for k, v in dflt.items() if v != CF.UNSPEC}
        assert not bad, (
            "★★★ %s 的默认槽位里有**肯定值** %r —— 那是 fail-open: "
            "漏标会被补成「支持」而不是「证据不足」。"
            "(2026-09-14 实测: 默认 possession='OWNED' 把 r3/MIS-2 的沉默补成了拥有)"
            % (f.name, bad))
        k = [x for x in d if "默认为什么必须是" in x]
        assert k and "fail-open" in d[k[0]], "★ 缺「默认为什么必须 UNSPECIFIED」的说明"


def test_每条证据都显式标注_不靠默认():
    d = json.loads(ANN.read_text(encoding="utf-8"))
    need = ("speaker", "polarity", "time", "citation", "predicate", "possession")
    for k, v in d["annotations"].items():
        miss = [s for s in need if s not in v]
        assert not miss, "★ %s 漏标槽位 %r —— 默认已是 UNSPECIFIED, 漏标就等于判它证据不足" % (k, miss)


def test_回放结果由冻结判据现算():
    if not RES.exists():
        return
    spec = importlib.util.spec_from_file_location("rp", PROBE)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    res = json.loads(RES.read_text(encoding="utf-8"))
    rows = res["rows"]
    neg = [r for r in rows if r["★是阴性吗"]]
    pos = [r for r in rows if not r["★是阴性吗"]]
    for t in ("只用合同明文", "明文+解释"):
        blocked = sum(1 for r in neg if not r[t]["allow"])
        assert res["★★★阴性_拦得住吗"][t]["被拦住"] == "%d/%d" % (blocked, len(neg))
        mis = sum(1 for r in pos if not r[t]["allow"])
        assert res["★★★对照_会不会误拦"][t]["★被误拦"] == "%d/%d" % (mis, len(pos))
    assert res["★回放了多少"]["真实证书"] == len(rows)


def test_对照不许被误拦():
    """★★★ 误拦比漏更糟 —— 它会让整层不可用。"""
    if not RES.exists():
        return
    res = json.loads(RES.read_text(encoding="utf-8"))
    for t in ("只用合同明文", "明文+解释"):
        v = res["★★★对照_会不会误拦"][t]
        assert v["★被误拦"].startswith("0/"), (
            "★★★ %s 误拦了对照 %s: %r —— 误拦比漏更糟, 它会让整层不可用"
            % (t, v["★被误拦"], v["误拦的"]))


def test_那次真实的错误升格必须被单列():
    """★ r3/MIS-4 是**唯一一次**真实模型产出、穿过整套验证器的语义错误证书。
    它在哪一档被拦住, 决定了要不要向 owner 提一个具体问题。"""
    if not RES.exists():
        return
    res = json.loads(RES.read_text(encoding="utf-8"))
    k = [x for x in res if "那次真实的错误升格" in x]
    assert k, "★★★ MIS-4 没被单列 —— 那是这批回放的全部意义所在"
    v = res[k[0]]
    assert v["旧层给的"] == "UPGRADED", "★ 旧层结局变了, 这条的前提要重核"
    m4 = [r for r in res["rows"] if r["轮次"] == "r3" and r["id"] == "MIS-4"][0]
    assert v["只用合同明文"] == ("拦住" if not m4["只用合同明文"]["allow"] else "**仍放行**")
    assert v["明文+解释"] == ("拦住" if not m4["明文+解释"]["allow"] else "**仍放行**")
    if m4["只用合同明文"]["allow"] and not m4["明文+解释"]["allow"]:
        s = v["★这意味着什么"]
        assert "合同明文拦不住" in s and "这条是我的提案" in s and "升成合同" in s, (
            "★★★ 必须写明: 明文拦不住它 · 那条解释是**提案**(owner 可推翻) · "
            "这给 owner 一个具体问题")


def test_边界声明_证书真实但标注仍是我做的():
    if not RES.exists():
        return
    res = json.loads(RES.read_text(encoding="utf-8"))
    v = res["★★★边界"]
    for must in ("真实模型产出", "标注仍是我做的", "能力上界", "不"):
        assert must in v, "★ 边界声明里缺: %s" % must
    assert "模型自己填槽位" in v, (
        "★ 必须写明本轮**不**回答「模型自己填槽位会填成什么样」")


def test_probe零调用():
    src = PROBE.read_text(encoding="utf-8")
    for bad in ("call_model", "MINIMAX", "requests.post", "_load_key"):
        assert bad not in src, "★★★ 回放里出现模型调用入口 %r —— 它必须零调用" % bad
    assert "已付费" in src and "边际成本近零" in src


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("回放闸 %d 项全过" % n)
