#!/usr/bin/env python3
"""降级运行必须在聚合层可见, 且不许报 production_verified(2026-09-28 诊断 #17 / #19 / #20 / #34)。

· s0 读出走了 MiniMax 回退: 此前只躺在单条产物的一个字符串里, 聚合层照报 verified(缺 secret 从 09-23 到 09-28 没人发现)。
· s2 有 draw 失败(5 取 2): 此前照发 playbook_primary 与 top1, 而 K1 判定是在满额 n 上标定的。
· s0 后端随读数一起落(qualified_readout.s0_read_backend): instrument_hash 看不见喂给 s1 的上下文换了生成器。
"""
import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_full_run as F  # noqa: E402
from cce_submission import write_package  # noqa: E402
from cce_workflow_manifest import build  # noqa: E402

# ── 聚合层 ──
example = json.loads((ROOT / "examples/cce_submission_outbound_reply_v1.json").read_text(encoding="utf-8"))
contract = json.loads((ROOT / "config/cce_submission_contract_v1.json").read_text(encoding="utf-8"))
chain = contract["profiles"]["outbound_reply"]["stages"]


def aggregate(backend, s2_short=None):
    with tempfile.TemporaryDirectory() as t:
        pkg, art = Path(t) / "pkg", Path(t) / "art"
        write_package(example, pkg)
        normalized = json.loads((pkg / "normalized.json").read_text(encoding="utf-8"))
        item = normalized["items"][0]
        (art / "item-0").mkdir(parents=True)
        (art / "item-0" / "manifest.json").write_text(json.dumps({
            "text_sha256": item["_meta"]["text_sha256"], "complete": True, "failed_at": None,
            "submission": item["_meta"], "chain": chain,
            "stages": {"s1_readout": {"status": "OK"}, "s0_context": {"status": "OK", "read_backend": backend},
                       "qualified_readout": {"status": "OK", "s2_short": s2_short}}}), encoding="utf-8")
        return build(normalized, art)


ok = aggregate("jev")
assert ok["complete"] and ok["production_verified"] and ok["degraded"] == [], ok
fb = aggregate("minimax_fallback(NO_TYPESAFE_API_KEY)")
assert fb["complete"], "降级不是失败: 链照样完整"
assert fb["production_verified"] is False and len(fb["degraded"]) == 1 and "回退" in fb["degraded"][0], fb
assert fb["jobs"][0]["s0_read_backend"].startswith("minimax_fallback")
short = aggregate("jev", "s2 n_ok=2 < n_requested=5")
assert short["production_verified"] is False and "n_ok=2" in short["degraded"][0], short
assert aggregate("none")["production_verified"], "全声明、没发读出调用 ⇒ 不是降级"

# ── 出口闸: s2 缺 draw 时扣发 playbook_primary 与 top1 ──
base = json.loads((ROOT / "archive/33842088048/cce-subject-item-7-33842088048__s1_readout.json").read_text(encoding="utf-8"))


def qualified(n_ok, n_req=5, backend="jev"):
    cce = copy.deepcopy(base)
    cce["stage2"]["sampling"].update({"n_ok": n_ok, "n_requested": n_req})
    F.MANIFEST.clear()
    F.MANIFEST["s1_readout"] = {"status": "OK", "tops": {"desire": "x"}}
    F.MANIFEST["s2_knots"] = {"status": "OK", "playbook_primary": "write it like this", "knots": [["reward", 1.0]],
                              "n": n_ok, "top1_mode_share": 1.0, "top1_mode": "reward", "max_range": 0.1}
    ctx = {"cce": cce, "ctx_layer": {"read_backend": backend}}
    F.qualified(ctx)
    return F.MANIFEST["qualified_readout"]


full = qualified(5)
assert "s2.playbook_primary" in full["usable_keys"] and full["s2_short"] is None and full["s0_read_backend"] == "jev"
part = qualified(2)
assert "s2.playbook_primary" not in part["usable_keys"] and "s2.distribution.top1" not in part["usable_keys"], part
assert "n_ok=2" in part["withheld"]["s2.playbook_primary"] and "n_ok=2" in part["withheld"]["s2.distribution.top1"]
assert qualified(5, backend="minimax_fallback(x)")["s0_read_backend"].startswith("minimax_fallback")

# ── 读者基线也过出口闸(诊断 #23) ──
rd = copy.deepcopy(base)
rd["stage1"]["within_js"] = dict(rd["stage1"]["within_js"], need_vec=F.WITHIN_JS_MAX["need_vec"] + 0.05)
ro = F._reader_out(rd, "reader body")
assert ro["tops"]["need"] is None and "need_vec" in ro["tops_withheld"]["need"], ro
F.MANIFEST.clear()
F.MANIFEST["reader_baseline"] = {"status": "OK", **ro}
F.MANIFEST["s1_readout"] = {"status": "OK", "tops": {"desire": "x"}}
F.MANIFEST["s2_knots"] = {"status": "OK"}
F.qualified({"cce": copy.deepcopy(base), "reader_cce": rd, "ctx_layer": {"read_backend": "jev"}})
q = F.MANIFEST["qualified_readout"]
assert "reader.tops.need" in q["withheld"] and "reader.tops.need" not in q["usable_keys"], q
assert "reader.tops.desire" in q["usable_keys"] and "reader.knots" in q["withheld"], q

# ── media_ingest 链上没有 s1/s2: 不得报 s1/s2 扣发(诊断 #26) ──
F.MANIFEST.clear()
F.MANIFEST["foundation_adapt"] = {"status": "OK", "observations": 3, "kinds": ["ocr"]}
F.MANIFEST["event_assemble"] = {"status": "OK", "events": 1, "event_types": ["x"]}
F.qualified({})
_mq = F.MANIFEST["qualified_readout"]
assert all(k.startswith("p3.") for k in list(_mq["withheld"]) + _mq["usable_keys"]), _mq
with tempfile.TemporaryDirectory() as _t:
    _pf = Path(_t) / "p.json"; _pf.write_text(json.dumps({"duration": 1.0, "audio": {"present": False}, "ocr": [1]}), encoding="utf-8")
    F.MANIFEST.clear(); F.media_validate({"text_file": str(_pf)})
    assert F.MANIFEST["media_validate"]["channels_present"] == ["ocr"], F.MANIFEST["media_validate"]

# ── s0 拒答只在出站两档; response 模式情境全未知走先验(canary 36421041849 item 7) ──
import cce_s0_jev as _S0  # noqa: E402
_keep_read = _S0.s0_jev_read
_S0.s0_jev_read = lambda body, facets: ({f["key"]: "未知" for f in facets}, {}, None)   # Jev 如实: 全读不出
try:
    for _mode, _ok in (("response", True), ("outbound_post", False)):
        with tempfile.TemporaryDirectory() as _t:
            (Path(_t) / "x.txt").write_text("short reply", encoding="utf-8")
            F.MANIFEST.clear()
            try:
                F.s0({"text_file": str(Path(_t) / "x.txt"), "context": "c", "mode": _mode, "outdir": _t})
            except RuntimeError:
                pass
            _st = F.MANIFEST["s0_context"]
            assert (_st["status"] == "OK") == _ok, (_mode, _st)
            if _ok:
                assert _st["拒答豁免"] and _st["read_backend"] == "jev"
            else:
                assert "拒答" in _st["error"]
finally:
    _S0.s0_jev_read = _keep_read

# ── 媒体链的 measurement_complete 看出口闸, 不看它没有的 s1(canary 36421035662) ──
_media = json.loads((ROOT / "archive/33840200869/cce-submission-source__submission.json").read_text(encoding="utf-8"))
with tempfile.TemporaryDirectory() as t:
    pkg, art = Path(t) / "pkg", Path(t) / "art"
    write_package(_media, pkg)
    nm = json.loads((pkg / "normalized.json").read_text(encoding="utf-8"))
    it = nm["items"][0]
    (art / "item-0").mkdir(parents=True)
    (art / "item-0" / "manifest.json").write_text(json.dumps({
        "text_sha256": it["_meta"]["text_sha256"], "complete": True, "failed_at": None, "submission": it["_meta"],
        "chain": ["media_validate", "foundation_adapt", "event_assemble", "qualified_readout"],
        "stages": {"qualified_readout": {"status": "OK"}}}), encoding="utf-8")
    _agg = build(nm, art)
assert _agg["complete"] and _agg["jobs"][0]["measurement_complete"] is True, _agg

print("test_cce_degraded_runs: OK (s0 回退 / s2 缺 draw ⇒ complete 但 production_verified=false 且列入 degraded | "
      "5 取 2 ⇒ playbook_primary 与 top1 扣发 | s0 后端随读数落 | 读者 tops 过同一道散布闸并进台账 | 媒体链不报不在链上的段 | s0 拒答只在出站两档 | 媒体测量完成看出口闸)")
