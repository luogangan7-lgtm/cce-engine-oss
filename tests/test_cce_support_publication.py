#!/usr/bin/env python3
"""C1: knots 发布全部被观测到的结 + occur/n + Wilson 区间, support 闸降为注记。

★ 本文件存在的理由: 我向用户承诺了「下游逐值不变」。
  承诺必须被**测**, 不能被**声称** —— 这正是前五次失效的共同形状。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_knot_classify as K      # noqa: E402
import cce_align_v2 as A           # noqa: E402

TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))


def _raises(fn, needle):
    try:
        fn()
    except Exception as exc:
        assert needle in str(exc), f"抛错了但理由不对: {exc}"
        return
    raise AssertionError(f"应当抛错却没有抛 (期望含 {needle!r})")


# ── 1. Wilson 区间在边界不塌 (反向测试: 朴素 se 会给 0) ──────────────────────
assert K._wilson(5, 5)[0] < 1.0, "5/5 的区间下界必须 <1 —— 否则等于宣称完全确定"
assert K._wilson(5, 5)[0] < 0.6, f"5/5 下界应约 0.57, 实得 {K._wilson(5, 5)[0]}"
assert K._wilson(0, 5)[1] > 0.4, "0/5 的上界必须远离 0"
assert K._wilson(0, 5) == [0.0, 0.4345] and K._wilson(5, 5) == [0.5655, 1.0]
# ★ 闸切在区分不开的地方: 刚过闸与刚没过闸的区间大幅重叠
lo3, hi3 = K._wilson(3, 5)
lo2, hi2 = K._wilson(2, 5)
assert lo3 < hi2 and lo2 < hi3, "3/5 与 2/5 的区间必须重叠 —— 这是闸不该切在这里的证据"
assert K._wilson(1, 0) == [0.0, 1.0], "n=0 必须给最宽区间, 不能除零"


# ── 2. 用假抽样驱动聚合, 不发任何 API 调用 ──────────────────────────────────
def _fake_draws(spec):
    """spec: {knot: [每次抽样的 intensity, 0 表示该次未出现]}"""
    n = len(next(iter(spec.values())))
    draws = []
    for i in range(n):
        ks = [{"key": k, "intensity": v[i], "evidence_quote": "", "signature": {}}
              for k, v in spec.items() if v[i] > 0]
        draws.append({"knots": ks, "levers_present": [], "notes": ""})
    return draws


def _agg(spec, monkey=True):
    orig = K._stage2_draw
    draws = _fake_draws(spec)
    K._stage2_draw = lambda p, t, tag: draws[int(tag[1:]) % len(draws)]
    try:
        return K._stage2_aggregate("x", TAXO, n=len(draws))
    finally:
        K._stage2_draw = orig


SPEC = {"pain_seek": [0.9, 0.9, 0.9, 0.9, 0.9],   # 5/5 过闸
        "audit":     [0.5, 0.5, 0.5, 0.0, 0.0],   # 3/5 过闸(勉强)
        "belong":    [0.3, 0.3, 0.0, 0.0, 0.0],   # 2/5 未过闸
        "suspend":   [0.2, 0.0, 0.0, 0.0, 0.0]}   # 1/5 未过闸
out = _agg(SPEC)
by = {k["key"]: k for k in out["knots"]}

# ── 3. ★ 全部被观测到的结都要发布 (改动前 belong/suspend 会被 continue 掉) ──
assert set(by) == set(SPEC), f"未过闸的结被丢了: 缺 {set(SPEC) - set(by)}"
assert by["belong"]["support_majority"] is False
assert by["suspend"]["support_majority"] is False
assert by["pain_seek"]["support_majority"] is True
assert by["audit"]["support_majority"] is True
for k, v in by.items():
    assert v["occur"] == sum(1 for x in SPEC[k] if x > 0) and v["n"] == 5
    assert v["support_ci95"] == K._wilson(v["occur"], 5)

# ── 4. ★★ 下游承诺: {key: weight} 对过闸结逐值不变, 未过闸恒 0 ──────────────
# 改动前 weight = intensity / sum(过闸结的 intensity)。手算钉死, 不引用实现。
expect_tot = 0.9 + 0.5
assert by["pain_seek"]["weight"] == round(0.9 / expect_tot, 4) == 0.6429
assert by["audit"]["weight"] == round(0.5 / expect_tot, 4) == 0.3571
assert by["belong"]["weight"] == 0.0 and by["suspend"]["weight"] == 0.0
assert abs(sum(v["weight"] for v in by.values()) - 1.0) < 1e-9, "过闸结的 weight 仍须和为 1"

# ── 5. ★★ 真正的下游: score() 三个数值字段必须逐值相同 ─────────────────────
#
# ⚠️ 2026-08-18: 本节初稿直接调 A.score(detect=True) —— 那会让 dissolve_hit 发
#   **真实 LLM 调用**(3 次表决/结)。本地无 key 时它重试到超时后返回 (0.0, "检测失败"),
#   于是 dissolution 两边恒为 0, **拆除那一半是空过的**, 而单文件耗时 124 秒。
#   一个既慢又测不到东西的检查, 正是「检查必须能观察到失败」要防的。
#
#   改法: 把 dissolve_hit 打成**非零**常量桩。这样既离线确定, 又真的让
#   `w * hit` 这一项带上非零 hit —— 零权重是否杀掉贡献, 才第一次被真正检验。
_orig_hit = A.dissolve_hit
A.dissolve_hit = lambda knot, text, votes=3: (0.7, "stub")

TEXT = ("Can't hear across the table? Don't blame the aid. Try the seat. "
        "Here's the mechanism and the next step you can take tonight.")
POST = {"pain_seek": 0.6, "audit": 0.4}
old_map = {k: v["weight"] for k, v in by.items() if v["support_majority"]}   # 改动前会得到的
new_map = {k: v["weight"] for k, v in by.items()}                            # 改动后会得到的
assert len(new_map) == len(old_map) + 2, "新 map 必须多出两个零权重条目, 否则本测试没测到东西"
for mode in ("post", "reply"):
    a = A.score(old_map, POST, TEXT, mode=mode)
    b = A.score(new_map, POST, TEXT, mode=mode)
    for f in ("alignment_score", "resonance", "dissolution"):
        assert a[f] == b[f], f"{mode}/{f}: 零权重条目改变了下游分数 {a[f]} != {b[f]}"
    assert len(b["detail"]) > len(a["detail"]), "detail 应多出零贡献行(无消费者, 已核)"
    assert all(d["contrib"] == 0.0 for d in b["detail"] if d["knot"] in ("belong", "suspend"))
    # 桩必须真的生效: 阻挡族的 response 应为 0.7 而不是 0.0(检测失败)
    blk = [d for d in b["detail"] if d["mode"] != "共鸣"]
    assert blk and all(d["response"] == 0.7 for d in blk), \
        f"桩没生效, 本节又在空过: {blk[:2]}"
    # ★ 非零 hit 下, 零权重结的贡献仍为 0 —— 这才是真正被检验的那一步
    assert any(d["knot"] in ("belong", "suspend") and d["response"] == 0.7
               for d in blk), "零权重结必须**参与**检测却贡献 0, 而不是被跳过"
A.dissolve_hit = _orig_hit

# hooks_for 取 top2, 零权重不得挤进来
import reply_batch as RB  # noqa: E402
assert RB.hooks_for(old_map) == RB.hooks_for(new_map), "零权重条目改变了钩子选择"

# ── 6. families / intensity / drive_brake 仍只用过闸结 (本次不动) ────────────
assert set(out["intensity"]) == {"pain_seek", "audit"}, \
    "intensity 仍应只含过闸结 —— 本次刻意不动它, 动它是另一个变更"
assert out["families"]["推动"]["mass"] > 0

# ── 7. 反向测试: 把过滤器加回去, 测试必须红 ─────────────────────────────────
_kept = [k for k in out["knots"] if k["support_majority"]]
assert set(x["key"] for x in _kept) != set(SPEC), \
    "若 out_knots 只剩过闸结, 第 3 节的断言就该失败 —— 确认该断言真的在测东西"

print("test_cce_support_publication: OK "
      "(全量发布 / Wilson 边界不塌 / 下游 score+hooks 逐值不变 / 反向测试)")
