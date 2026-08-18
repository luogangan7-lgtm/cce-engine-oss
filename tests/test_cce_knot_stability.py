#!/usr/bin/env python3
"""s2_knots n 次抽样聚合的离线闸。不需要 API key —— 模型调用被桩替换。

存在理由(2026-08-18): 同项重跑实测 run 32096357295 —— 整项指纹逐字相同, 断言经反向测试 ——
完全相同的读数对 0/6, 单结权重极差 0.65。即 stage2 单次调用给出的是一次抽样, 不是一个测量,
而它此前被当读数写进台账。本闸钉住聚合语义, 让这件事不能悄悄退回去。

★ 本文件必须同时出现在 .github/workflows/cce-submit.yml 的 contract 作业命令清单里。
  那份清单是**硬编码的**, `tests/test_cce_*` 只是 PR 触发路径过滤, 不是执行清单 ——
  新增测试文件不改那份清单, 它就是一个从不运行的永久绿闸(2026-08-18 对抗评审指出, 已实查确认)。
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("MINIMAX_API_KEY", "stub-not-used")

import cce_knot_classify as K  # noqa: E402

TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))
KEYS = [k["key"] for k in TAXO["knots"]]


def _stub(draws):
    """把 _stage2_draw 换成按序回放固定抽样, 使聚合逻辑可离线判定。"""
    seq = list(draws)
    state = {"i": 0}

    def fake(prompt, taxo, tag):
        d = seq[state["i"] % len(seq)]
        state["i"] += 1
        return None if d is None else {"knots": [{"key": k, "intensity": w} for k, w in d],
                                       "levers_present": [], "notes": ""}
    return fake


def agg(draws, n=None):
    orig = K._stage2_draw
    K._stage2_draw = _stub(draws)
    try:
        return K._stage2_aggregate("prompt", TAXO, n=n or len(draws))
    finally:
        K._stage2_draw = orig


# ── 1. 聚合语义 ──────────────────────────────────────────────────────────────
r = agg([[("display", 0.6), ("audit", 0.4)],
         [("display", 0.5), ("audit", 0.5)],
         [("display", 0.7), ("audit", 0.3)]])
per = r["sampling"]["per_knot"]
assert r["sampling"]["n_ok"] == 3
assert per["display"]["median"] == 0.6, per
assert per["display"]["range"] == 0.2, per          # 0.7 - 0.5
assert per["display"]["occur"] == 3 and per["display"]["n"] == 3

# 缺席记 0, 分母恒为成功抽样数 —— 不是「出现过的次数」。
# 这条最容易写错: 若分母取 occur, 一个只出现 1 次的噪声结会显示成满分稳定。
r = agg([[("display", 1.0)],
         [("display", 0.8), ("belong", 0.2)],
         [("display", 1.0)],
         [("display", 1.0)]])
b = r["sampling"]["per_knot"]["belong"]
assert b["occur"] == 1 and b["n"] == 4, b
assert b["median"] == 0.0, b                        # 4 次里 3 次为 0 → 中位数 0
assert b["max"] == 0.2 and b["range"] == 0.2, b
assert all(k["key"] != "belong" for k in r["knots"]), "中位数为 0 的结不进 knots"

# ── 2. top1_stable 是二元判据, 不含阈值 ────────────────────────────────────
same = agg([[("display", 0.6), ("audit", 0.4)]] * 4)
assert same["sampling"]["top1_stable"] is True
assert same["sampling"]["top1_draws"] == ["display"] * 4

flip = agg([[("display", 0.6), ("audit", 0.4)],
            [("audit", 0.6), ("display", 0.4)],
            [("display", 0.6), ("audit", 0.4)],
            [("display", 0.6), ("audit", 0.4)]])
assert flip["sampling"]["top1_stable"] is False, "首结翻转必须判不稳"
assert set(flip["sampling"]["top1_draws"]) == {"display", "audit"}

# ── 3. ★ 反向测试: 闸必须能观察到失败 ──────────────────────────────────────
# 3a. 权重全同 → 极差必须为 0; 若聚合把噪声算进去, 这条会红。
flat = agg([[("display", 0.5), ("audit", 0.5)]] * 5)
assert flat["sampling"]["max_range"] == 0.0, flat["sampling"]

# 3b. 造一份「明显不稳」的抽样, 闸必须报不稳。
#     这是本闸存在的全部意义 —— 它若对这种输入仍报稳, 就是假检查。
unstable = agg([[("pain_seek", 0.65)],
                [("audit", 0.50), ("pain_seek", 0.30)],
                [("audit", 0.55), ("display", 0.45)],
                [("pain_seek", 0.40), ("suspend", 0.35)]])
assert unstable["sampling"]["top1_stable"] is False
assert unstable["sampling"]["max_range"] >= 0.5, unstable["sampling"]

# 3c. 部分抽样失败时分母必须跟着降, 不能拿失败当 0 稀释。
partial = agg([[("display", 0.6)], None, [("display", 0.8)], None])
assert partial["sampling"]["n_ok"] == 2, partial["sampling"]
assert partial["sampling"]["per_knot"]["display"]["n"] == 2

# 3d. 全部失败必须抛错, 不得静默返回空 —— 静默放行正是本轮在修的形态。
try:
    agg([None, None, None])
    raise AssertionError("全部抽样失败时必须抛错")
except RuntimeError:
    pass

# ── 4. knots 保持既有形状, 下游 5 个消费者不需要改 ──────────────────────────
r = agg([[("display", 0.6), ("audit", 0.4)]] * 3)
for k in r["knots"]:
    assert {"key", "weight", "name", "family", "playbook"} <= set(k), k
    assert k["key"] in KEYS
assert [k["weight"] for k in r["knots"]] == sorted([k["weight"] for k in r["knots"]], reverse=True)

# ── 5. 本文件必须在 CI 的硬编码执行清单里 ──────────────────────────────────
# 不做这条断言, 本文件就可能变成一个从不运行的永久绿闸 —— 它自己防它自己。
wf = (ROOT / ".github" / "workflows" / "cce-submit.yml").read_text(encoding="utf-8")
assert "python3 tests/test_cce_knot_stability.py" in wf, \
    "本测试未进 cce-submit.yml 的执行清单 —— 那份清单是硬编码的, 不进去就永不执行"

# ── 6. 四层结构 (重构文档 §22) ───────────────────────────────────────────────
# 此前是单层 9-simplex: 权重和恒为 1 ⇒ 一个分量升必然压低其他 ⇒
# 「想要很强」与「审查也很强」不能同时表达。实测 21 次里 20 次总和恰为 1.0。
r = agg([[("reward", 0.88), ("audit", 0.81)]] * 3)

# 6a. ★ 独立强度不受和为 1 约束 —— 这是整个第 2 层存在的理由
inten = r["intensity"]
assert inten["reward"] == 0.88 and inten["audit"] == 0.81, inten
assert abs(sum(inten.values()) - 1.0) > 0.5, \
    f"intensity 不得被归一化, 当前和 {sum(inten.values())} —— 归一了就退回 simplex"

# 6b. 族内组成各自和为 1, 两族分开
fam = r["families"]
assert abs(sum(fam["推动"]["composition"].values()) - 1.0) < 1e-6, fam["推动"]
assert abs(sum(fam["阻挡"]["composition"].values()) - 1.0) < 1e-6, fam["阻挡"]
assert set(fam["推动"]["composition"]) == {"reward"}, fam["推动"]
assert set(fam["阻挡"]["composition"]) == {"audit"}, fam["阻挡"]

# 6c. mass 与 intensity 同量纲(取族内最大), 不是求和 —— 求和会 >1 而丢掉量纲
assert fam["推动"]["mass"] == 0.88 and fam["阻挡"]["mass"] == 0.81, fam

# 6c-2. ★ 同族多结时 max 与 sum 才分得开。
# 2026-08-18: 变异测试发现上一条抓不到「mass 改成求和」—— 每族只有 1 个活跃结时两者相等。
# 这是测试自身的洞, 由变异测试找出来的, 补此用例钉死。
multi = agg([[("reward", 0.6), ("belong", 0.5), ("display", 0.4),
              ("audit", 0.7), ("suspend", 0.3)]] * 3)
mf = multi["families"]
assert mf["推动"]["mass"] == 0.6, f"推动族 mass 必须是最大值 0.6, 不是和 1.5: {mf['推动']}"
assert mf["阻挡"]["mass"] == 0.7, f"阻挡族 mass 必须是最大值 0.7, 不是和 1.0: {mf['阻挡']}"
assert mf["推动"]["members_active"] == 3 and mf["阻挡"]["members_active"] == 2, mf
assert all(0.0 <= v <= 1.0 for f in mf.values() for v in [f["mass"]]), \
    "mass 必须落在 [0,1] 与 intensity 同量纲 —— 求和会破坏这一点"
assert abs(sum(mf["推动"]["composition"].values()) - 1.0) < 1e-6, mf["推动"]
assert abs(sum(mf["阻挡"]["composition"].values()) - 1.0) < 1e-6, mf["阻挡"]
db = r["drive_brake"]
assert db["drive_mass"] == 0.88 and db["brake_mass"] == 0.81, db
assert db["quadrant"] == "high_drive/high_brake", db

# 6d. 高推动 + 低阻挡 必须与上面落在不同象限（否则象限是死的）
r2 = agg([[("reward", 0.9), ("audit", 0.1)]] * 3)
assert r2["drive_brake"]["quadrant"] == "high_drive/low_brake", r2["drive_brake"]

# 6e. legacy weight 仍是全局组成(和为1), 下游 {key: weight} 读法不破
w = {k["key"]: k["weight"] for k in r["knots"]}
assert abs(sum(w.values()) - 1.0) < 1e-3, w
assert all("intensity" in k for k in r["knots"]), "knots 每项必须同时带 intensity"

# 6f. ★ 反向测试: 若聚合层把 intensity 归一了, 6a 必红 —— 这里再钉一次两者的关系
r3 = agg([[("reward", 0.5), ("audit", 0.5)]] * 3)
assert r3["intensity"]["reward"] == 0.5, "intensity 是原始强度, 不随其他结变化"
assert abs(r3["knots"][0]["weight"] - 0.5) < 1e-3, "weight 是组成, 此例恰为 0.5"

print("test_cce_knot_stability: OK (聚合语义 / top1 二元判据 / 反向测试 / 形状兼容 / 四层结构 / CI 自防)")
