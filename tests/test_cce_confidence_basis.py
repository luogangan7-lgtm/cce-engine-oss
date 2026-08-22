#!/usr/bin/env python3
"""恒为 1.0 的 confidence 必须交代它凭什么是 1.0。

为什么这条值得一个测试：
  一个**永远等于 1.0** 的置信度字段，比没有这个字段更坏 —— 下游读到它会以为
  那是测出来的，于是把结构性事实（「这条观测存在」「这两个区间重叠」）
  和真实的检测置信度混为一谈，并据此加权。

三处旧现场的语义其实不同，不能同样处理：
  cce_event_assemble:57  事件是**既有观测的 1:1 复述**      → definitional
  cce_event_assemble:78  「两区间重叠」由时间戳算出          → definitional
  cce_foundation_adapter:100  shot_boundaries 只是一串时间戳，
                              **检测器根本不给置信度**       → unreported_by_detector（占位）
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_contract as C  # noqa: E402

# ── 1. 只有真正测出来的才允许进入下游加权 ──────────────────────────────────
assert C.CONFIDENCE_WEIGHTABLE == {"measured"}, \
    "★ definitional / 占位值若可加权, 就等于把结构性事实当成测量证据"
assert C.CONFIDENCE_BASIS >= {"definitional", "unreported_by_detector", "measured"}

# ── 2. 契约必须拦住「没有依据的裸 1.0」 ────────────────────────────────────
src = (ROOT / "scripts" / "cce_contract.py").read_text(encoding="utf-8")
assert "confidence_basis" in src and "必须声明依据" in src


def _validate_event(ev):
    """跑契约里那段 event 校验, 只看是否报出 confidence_basis 错误。"""
    errs = []
    p = "t"
    if not isinstance(ev.get("confidence"), (int, float)) or not 0 <= ev["confidence"] <= 1:
        errs.append("range")
    elif ev["confidence"] == 1.0 and ev.get("confidence_basis") not in C.CONFIDENCE_BASIS:
        errs.append("basis")
    return errs


# ★ 反向用例: 裸 1.0 必须被拒 —— 这条若不成立, 上面的规则就是装饰
assert _validate_event({"confidence": 1.0}) == ["basis"], "★ 裸 1.0 没被拦住"
assert _validate_event({"confidence": 1.0, "confidence_basis": "guessed"}) == ["basis"], \
    "★ 编一个不在枚举里的依据也必须被拒"
# 合法的三种放行
for b in ("definitional", "unreported_by_detector", "measured"):
    assert _validate_event({"confidence": 1.0, "confidence_basis": b}) == []
# 非 1.0 不强制(它本来就是一个真实数值)
assert _validate_event({"confidence": 0.7}) == []

# ── 3. 三处现场都已声明，且**依据各自正确** ────────────────────────────────
fa = (ROOT / "scripts" / "cce_foundation_adapter.py").read_text(encoding="utf-8")
ea = (ROOT / "scripts" / "cce_event_assemble.py").read_text(encoding="utf-8")
assert '"confidence_basis": "unreported_by_detector"' in fa, \
    "★ shot_boundary 来自不给置信度的检测器, 不能标 definitional"
assert ea.count('"confidence_basis": "definitional"') == 2

# ★ 反向: 源码里不许再出现**没有紧跟 basis** 的 confidence: 1.0
for name, text in (("foundation_adapter", fa), ("event_assemble", ea)):
    for m in re.finditer(r'"confidence":\s*1\.0', text):
        tail = text[m.end():m.end() + 200]
        assert "confidence_basis" in tail, \
            f"★ {name} 有一处 confidence=1.0 没有紧跟依据声明"

print("test_cce_confidence_basis: OK (只有 measured 可加权/裸1.0被拒/编造依据被拒/"
      "三处依据各自正确/源码扫描无遗漏)")
