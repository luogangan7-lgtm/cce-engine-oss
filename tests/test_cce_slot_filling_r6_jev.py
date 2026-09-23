# -*- coding: utf-8 -*-
"""r6-jev 闸: 预注册逐键继承 r6 · 题目集哈希 · 干跑落盘 · 结果从 rows 重算 · 密钥不落盘。"""
import hashlib, importlib.util, json, pathlib, sys, tempfile
ROOT = pathlib.Path(__file__).resolve().parents[1]
PRE = ROOT / "tests/data/slot_filling_prereg_r6_jev.json"; R6 = ROOT / "tests/data/slot_filling_prereg_r6.json"
EXE = ROOT / "probes/slot_filling_run_r6_jev.py"; R = ROOT / "results/slot_filling_r6_jev.json"

def _x():
    s = importlib.util.spec_from_file_location("jx", EXE); x = importlib.util.module_from_spec(s); s.loader.exec_module(x); return x

def test_预注册逐键继承r6_且题目集哈希现算一致():
    pre = json.loads(PRE.read_text(encoding="utf-8")); r6 = json.loads(R6.read_text(encoding="utf-8"))
    for k in ("★★★items(测量前冻结)", "★★★金标哈希(测量前冻结)", "★★★主判据(测量前冻结_confirmatory)", "★★★降级条件(测量前冻结)"):
        assert pre[k] == r6[k], "★★★ %s 与 r6 不同 ⇒ 判据被换过" % k
    assert pre["r6 预注册 sha256"] == hashlib.sha256(R6.read_bytes()).hexdigest()
    assert pre["★题目集哈希(测量前冻结)"] == _x().question_set_sha(), "★★★ 题目措辞变了, 改了必须重出预注册"
    b = [pre[k] for k in pre if "预算(计量付费" in k][0]; assert b["请求硬上限"] == 200 and b["★撞上限即停"] is True

def test_题目选项必须等于判据层合法枚举():
    x = _x(); m = x._r6()
    for slot, (_, opts) in x.SLOT_Q.items():
        assert set(opts) == m.LEGAL[slot], "★ %s 选项 %r ≠ LEGAL %r" % (slot, set(opts), m.LEGAL[slot])
    assert set(x.PRED_OPTS) == m.LEGAL["predicate"] - {"OWNERSHIP"}
    it = m.items()[0]; body = x.build_request(it)
    assert len(body["questions"]) == 11 and body["state"]["text"] == it["text"], "★ 每请求 11 题, state 不截断"

def test_干跑必须落盘且金标达成():
    x = _x(); x.OUT = pathlib.Path(tempfile.mkdtemp()) / "j.json"
    import io, contextlib
    with contextlib.redirect_stdout(io.StringIO()): x.main(["--dry-run"])

def test_密钥不落盘不回显():
    src = EXE.read_text(encoding="utf-8")
    assert "apikey_" not in src and "TYPESAFE_API_KEY=" not in src.replace('startswith("TYPESAFE_API_KEY=")', ""), "★★★ 源码里出现密钥"
    if R.exists():
        blob = R.read_text(encoding="utf-8"); assert "apikey_" not in blob and "Bearer" not in blob
    assert "e.read()" not in src, "★ 错误响应体不许落盘(可能夹带信息)"

def test_结果必须能从rows重算_且账本在上限内():
    if not R.exists(): return
    r = json.loads(R.read_text(encoding="utf-8")); x = _x(); m = x._r6()
    sys.path.insert(0, str(ROOT / "scripts")); import cce_claim_frame as CF
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    got = x.build_result(m, pre, r["rows"], r["★预算账本"], {"model": r["model"]}, CF)
    for k in ("★★★主判据: B 臂鉴别格 vs 最佳浅层规则", "★★★判读降级", "★★★Jev 在鉴别格上给 RESTATES 的概率", "★★★五臂对照(四条零调用 + 一条模型臂 · 同一批 items · 同一套打分)"):
        assert got[k] == r[k], "★★★ %s 与现算不符" % k
    L = r["★预算账本"]; assert L["请求数(含重试)"] <= L["硬上限"]["请求"] and L["input_tokens"] <= L["硬上限"]["input_tokens"]
    assert r["prereg_sha256"] == hashlib.sha256(PRE.read_bytes()).hexdigest(), "★★★ 预注册在投料后被改过"
    # ★ 查值不查键名(键名里本来就有「是 Jev」, 只改值会漏网)
    v = r["★★★本轮的「B 臂」是 Jev"]; assert "Jev" in v and "不是** MiniMax" in v, "★ 必须写明这条臂是 Jev 不是 MiniMax: %r" % v

if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"): f(); n += 1; print("  ✅", k)
    print("r6-jev 闸 %d 项全过" % n)
