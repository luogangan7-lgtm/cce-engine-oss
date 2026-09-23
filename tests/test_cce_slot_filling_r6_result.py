# -*- coding: utf-8 -*-
"""r6 结果闸: 从 rows 里的模型原样**重新打分、重新 judge**, 与档案逐键比对。"""
import hashlib, importlib.util, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
R = ROOT / "results/slot_filling_r6.json"
PRE = ROOT / "tests/data/slot_filling_prereg_r6.json"
EXE = ROOT / "probes/slot_filling_run_r6.py"


def _r():
    return json.loads(R.read_text(encoding="utf-8")) if R.exists() else None


def _m():
    s = importlib.util.spec_from_file_location("r6x", EXE); x = importlib.util.module_from_spec(s); s.loader.exec_module(x)
    return x.patched()


def test_主判据与降级必须能从rows重新算出():
    r = _r()
    if not r:
        return
    m = _m(); sys.path.insert(0, str(ROOT / "scripts")); import cce_claim_frame as CF
    its = {it["id"]: it for it in m.items()}
    by = []
    for row in r["rows"]:
        if not row["调用成功"]:
            continue
        it = its[row["id"]]; by.append((it, m.score(row["模型原样"], it, CF)))
    arms = {list(m.ARMS)[0]: m.tally(by)}
    ref = m.run_ref([it for it, _ in by], CF)
    j = m.judge(arms, ref, r["★实际执行数"], r["调用或格式失败"])
    for k in ("★★★主判据: B 臂鉴别格 vs 最佳浅层规则", "★★★判读降级"):
        assert j[k] == r[k], "★★★ %s 与从 rows 现算不符\n  档案 %r\n  现算 %r" % (k, r[k], j[k])
    five = r["★★★五臂对照(四条零调用 + 一条模型臂 · 同一批 items · 同一套打分)"]
    for k, v in ref.items():
        assert five[k] == v, "★ 参照臂 %s 与现算不符" % k


def test_读数与预注册冻结的门一致_且门不是现场推导():
    r = _r()
    if not r:
        return
    pre = json.loads(PRE.read_text(encoding="utf-8")); FZ = [pre[x] for x in pre if "主判据(测量前冻结" in x][0]
    M = r["★★★主判据: B 臂鉴别格 vs 最佳浅层规则"]
    assert "≥%d/%d" % (FZ["★冻结的门"], FZ["★冻结的 n"]) in M["★冻结的门(预注册, 非现算)"]
    assert M["★★★净增益(鉴别格对数 − 多数类格错数)"]["冻结的阈值"] == FZ["★冻结的最佳浅层规则净增益"]
    k, n = (int(x) for x in M["B 臂鉴别格"].split("/")); assert n == FZ["★冻结的 n"]
    want = (k >= FZ["★冻结的门"]) and (M["★★★净增益(鉴别格对数 − 多数类格错数)"]["B 臂"] > FZ["★冻结的最佳浅层规则净增益"]) and M["★三个前置条件"]["③ 端到端可用过半"]
    assert ("**超过" in M["★结论"]) == want, "★★★ 结论与三个前置条件不符"


def test_执行记录_关系_预算():
    r = _r()
    if not r:
        return
    assert r["block"] == "SLOT_FILLING_RESULT_R6" and r["prereg"].endswith("slot_filling_prereg_r6.json")
    assert r["★实际执行数"] == r["★硬上限"] == 68 and len(r["rows"]) == 68 and r["★每条尝试次数(不是重试次数)"] == 1
    rel = r["★★★与 r5 的关系"]
    assert "不得直接比" in json.dumps(rel, ensure_ascii=False) and rel["预算"]["合计"] == 242 + r["★实际执行数"]
    assert r["★★★两臂提示词哈希(现算)"] == json.loads(PRE.read_text(encoding="utf-8"))["★★★两臂提示词哈希(测量前冻结)"]


def test_D6若触发必须写明零增益():
    r = _r()
    if not r:
        return
    dg = r["★★★判读降级"]
    M = r["★★★主判据: B 臂鉴别格 vs 最佳浅层规则"]
    k = int(M["B 臂鉴别格"].split("/")[0]); bk = int(M["最佳浅层规则鉴别格"].split("/")[0])
    if k <= bk:
        assert isinstance(dg, list) and any("D6" in x and "零增益" in x for x in dg), "★★★ 鉴别格 ≤ 浅层规则却没触发 D6"


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("r6 结果闸 %d 项全过(产物未生成时空过)" % n)
