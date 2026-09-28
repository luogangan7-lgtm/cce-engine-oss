#!/usr/bin/env python3
"""k=3 仪器的 top-1 判定从单文本升到 5 文本 + 非退化(2026-09-29 诊断 #2)。零调用。
守: ① 判定文件可由 probes/k1_top1_multitext.py 从已提交 raw draw 逐字现算 ② 同一脚本复现已提交的 k=5 判定
③ 生产 k=3 路由指向它 ④ 把某个文本改成不一致 / 把 5 个文本改成同一众数 ⇒ 判 TOP1_FAIL。"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
_s = importlib.util.spec_from_file_location("_k1m", ROOT / "probes/k1_top1_multitext.py")
M = importlib.util.module_from_spec(_s); _s.loader.exec_module(M)
import cce_k1_status as S  # noqa: E402

committed = json.loads((ROOT / "tests/data/phase2/k1_top1_k3_verdict.json").read_text(encoding="utf-8"))
assert M.build_k3() == committed, "★ 判定文件与现算不符 —— 手改过或数据漂了"
assert M.check_k5()
assert Path(S.K1_VERDICT).name == "k1_top1_k3_verdict.json"
st = S.layer_status(instrument_hash="565470cf26c16d01")
assert st["top1"]["usable"] and "5/5 文本" in st["top1"]["reason"] and not st["intensity"]["usable"]

# 反向: 在内存里改 raw draw, 判法必须翻
rows = [json.loads(l) for l in (ROOT / "tests/data/phase2/k1_v2_checkpoint.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
tmp = ROOT / "tests/data/phase2"
def _judge(mut):
    rr = json.loads(json.dumps(rows)); mut(rr)
    f = Path(__import__("tempfile").mkdtemp()) / "cp.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in rr), encoding="utf-8")
    keep = M.P; M.P = str(f.parent)
    try:
        per, deg, ok = M.judge("cp.jsonl", "565470cf26c16d01")
    finally:
        M.P = keep
    return ok and deg["pass"]
assert _judge(lambda rr: None)
def _flip2(rr):
    first = [r for r in rr if r["base_id"] == rr[0]["base_id"]]
    for r in first[:2]: r["top1"] = "audit"
assert not _judge(_flip2), "一个文本只剩 6/8 一致必须不达标"
assert not _judge(lambda rr: [r.__setitem__("top1", "reward") for r in rr]), "5 个文本同一众数 = 退化, 必须不达标"
print("test_cce_k1_top1_k3_multitext: OK (判定可现算 | k=5 复现 | 生产路由已指向 5 文本判定 | 6/8 与退化各自判不达标)")
