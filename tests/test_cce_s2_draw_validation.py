#!/usr/bin/env python3
"""s2 单次 draw 的类型/取值闸(2026-09-28 诊断 #16)。零真实调用。

此前 _stage2_draw 只查 knots 是 list 且 key 在分类学里: knot 是裸字符串 ⇒ x.get 抛错; intensity 是字符串/null/1.7
⇒ 收下后在聚合或写盘时把整条链崩掉。现在这类 draw 与解析失败同样处理: 落 raw、重试, 三次都坏返回 None
(由聚合层按 n_ok 决定), 不崩。
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_knot_classify as KC  # noqa: E402

TAXO = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
K0 = TAXO["knots"][0]["key"]
OK = {k["key"] for k in TAXO["knots"]}

BAD = {"裸字符串 knot": {"knots": [K0]},
       "intensity 是字符串": {"knots": [{"key": K0, "intensity": "0.8"}]},
       "intensity 是 null": {"knots": [{"key": K0, "intensity": None}]},
       "intensity 越界": {"knots": [{"key": K0, "intensity": 1.7}]},
       "intensity 是布尔": {"knots": [{"key": K0, "intensity": True}]},
       "weight 垫片越界": {"knots": [{"key": K0, "weight": -0.1}]},
       "未知 key": {"knots": [{"key": "not_a_knot", "intensity": 0.5}]}}
GOOD = {"knots": [{"key": K0, "intensity": 0.8}]}

for name, d in BAD.items():
    assert KC._s2_draw_violation(d, OK), name
assert KC._s2_draw_violation(GOOD, OK) is None
assert KC._s2_draw_violation({"knots": []}, OK) is None, "空列表是合法弃权, 不是违规"
assert KC._s2_draw_violation({"knots": [{"key": K0, "weight": 0.3}]}, OK) is None, "旧 schema 的 weight 走垫片, 合法"

KC.RAW_DIR = tempfile.mkdtemp()           # 失败原文落临时目录, 不写真仓
calls = []


def fake(outputs):
    def call_model(model, prompt, temperature=0.0):
        calls.append(1)
        return json.dumps(outputs[min(len(calls) - 1, len(outputs) - 1)], ensure_ascii=False), {"finish_reason": "stop"}
    return call_model


for name, bad in BAD.items():                # 坏一次 ⇒ 重试拿到好的
    calls.clear(); KC.call_model = fake([bad, GOOD])
    d = KC._stage2_draw("p", TAXO, "t")
    assert d and d["knots"][0]["intensity"] == 0.8 and len(calls) == 2, (name, d, len(calls))
    calls.clear(); KC.call_model = fake([bad])  # 三次都坏 ⇒ None, 不抛
    assert KC._stage2_draw("p", TAXO, "t") is None and len(calls) == 3, name
assert any(Path(KC.RAW_DIR).iterdir()), "坏 draw 要落 raw"   # 文件名只到秒, 同秒同档会互相覆盖 —— 属诊断 #18 取证项

print(f"test_cce_s2_draw_validation: OK ({len(BAD)} 类坏 draw 各自: 被拒 · 重试取到好的 · 三次都坏返回 None 不崩 | 弃权与 weight 垫片不误伤)")
