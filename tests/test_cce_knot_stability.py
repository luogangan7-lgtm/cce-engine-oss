#!/usr/bin/env python3
"""s2_knots n 次抽样聚合的离线闸。不需要 API key —— 模型调用被桩替换。

存在理由(2026-08-18): 同项重跑实测 run 32096357295 —— 整项指纹逐字相同, 断言经反向测试 ——
完全相同的读数对 0/6, 单结权重极差 0.65。即 stage2 单次调用给出的是一次抽样, 不是一个测量,
而它此前被当读数写进台账。本闸钉住聚合语义, 让这件事不能悄悄退回去。

★ CI 遍历 tests/test_*.py 执行, 本文件末尾断言那个遍历机制还在。
  那份清单是**硬编码的**, `tests/test_cce_*` 只是 PR 触发路径过滤, 不是执行清单 ——
  新增测试文件不改那份清单, 它就是一个从不运行的永久绿闸(2026-08-18 对抗评审指出, 已实查确认)。
"""
import json
import re
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
assert b["support"] == 0.25, b
# 2026-08-18 语义更正: median/intensity 现在是「出现时的中位数」, 不掺 0 ——
# 掺 0 会把「强度」与「出现率」乘在一起, 造成 occur=3/5 低估 25%、偶数 n 报半值。
assert b["intensity"] == 0.2, b
assert b["range"] == 0.0, f"只出现 1 次, 极差应为 0 而非 0.2: {b}"

# ★ 2026-08-18 三次更正 —— 本处旧断言是 `belong 不进 knots`。
#   那条编码的是**已被废止的契约**: support 闸当过滤器用。
#   实测 P1a FAIL(3/3 文本有结在闸上翻转, 结集一致率 0.50/0.50/0.33), 且
#   occur/n 的抖动过散参数仅 1.20(p=0.159) ⇒ 仪器没漂移, 是布尔闸把
#   一个 ±0.22 的测量洗成了干净的类别。闸已降为注记。
#   ⚠️ 不是删掉这条断言, 是**换成新契约下必须成立的那条** ——
#      少数派结必须**在** knots 里, 且带得动它自己的不确定度, weight 恒 0。
bk = next((k for k in r["knots"] if k["key"] == "belong"), None)
assert bk is not None, "少数派结必须发布, 不得再被 continue 掉"
assert bk["support_majority"] is False and bk["weight"] == 0.0
assert bk["occur"] == 1 and bk["n"] == 4
assert bk["support_ci95"][1] > bk["support"], "必须带 Wilson 区间, 且上界高于点估计"
assert all(k["weight"] == 0.0 for k in r["knots"] if not k["support_majority"])
assert abs(sum(k["weight"] for k in r["knots"]) - 1.0) < 1e-9, "过闸结 weight 仍和为 1"

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
# 2026-08-18: 原断言写 max_range >= 0.5, 那个数字是按**掺 0** 的旧语义标定的。
# 新语义下同一输入是 0.35(pain_seek 出现时在 0.30–0.65 之间), 这才是真实极差。
# 改成不依赖魔数的判据: 不稳结的极差必须显著大于同一次调用里稳定结的极差。
_pk = unstable["sampling"]["per_knot"]
_unstable_r = _pk["pain_seek"]["range"]          # 三次出现, 0.30/0.40/0.65
_stable_r = _pk["suspend"]["range"]              # 单次出现, 极差 0
assert _unstable_r > _stable_r + 0.2, (_unstable_r, _stable_r)
assert unstable["sampling"]["max_range"] == _unstable_r, unstable["sampling"]

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
# 2026-08-18: CI 原先是**硬编码的 11 行清单**, 新增测试忘了加进去就永不执行(假检查, 且无声)。
# 已改成遍历 tests/test_*.py + 数量下限自守。本断言随之从「我在清单里」
# 改成「遍历机制还在」—— 后者更强: 它保证的是**所有**测试都跑, 不只是我自己。
assert "for t in tests/test_*.py" in wf, \
    "CI 必须遍历 tests/test_*.py —— 退回硬编码清单会让新增测试永不执行"
assert re.search(r'test "\$n" -ge \d+', wf), \
    "遍历必须配数量下限自守 —— 否则路径写错会静默跑零个测试而 CI 全绿"

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

# ── 7. 强度与出现率分开 (2026-08-18 对抗评审后修) ────────────────────────────
# 此前 median(缺席记 0) 把「强度」与「出现率」乘在一起, 后果:
#   occur=3/5 时报值系统性低估约 25%; 偶数 n 上 occur=n/2 报真值的一半。
r = agg([[("display", 0.4)], [("display", 0.4)], [("display", 0.4)], [("audit", 0.9)]])
d = r["sampling"]["per_knot"]["display"]
assert d["occur"] == 3 and d["n"] == 4, d
assert d["support"] == 0.75, d
assert d["intensity"] == 0.4, f"intensity 必须是**出现时**的中位数, 不掺 0: {d}"
assert d["median"] == d["intensity"], "median 是兼容别名"
assert d["range"] == 0.0, f"三次都是 0.4, 极差应为 0 而不是 0.4(掺 0 会算成 0.4): {d}"

# 7a. ★ 偶数 n 的半值 bug: occur=n/2 时旧实现报真值的一半
r = agg([[("display", 0.4)], [("display", 0.4)], [("audit", 0.9)], [("audit", 0.9)]])
dd = r["sampling"]["per_knot"]["display"]
assert dd["intensity"] == 0.4, f"n=4 occur=2 必须报 0.4 而不是 0.2: {dd}"
assert dd["occur"] * 2 == dd["n"], dd
# 旧断言是「2/4 不进输出」。同上, 闸已降为注记 —— 改测它现在必须成立的样子:
# 恰好一半**进**输出, 但 support_majority=False、weight=0, 且区间横跨 0.5。
_d = next((k for k in r["knots"] if k["key"] == "display"), None)
assert _d is not None and _d["support_majority"] is False and _d["weight"] == 0.0
assert _d["support_ci95"][0] < 0.5 < _d["support_ci95"][1], \
    f"occur=n/2 的区间必须横跨 0.5 —— 这正是「切在这里区分不开」的量化表达: {_d['support_ci95']}"

# 7b. 支持度阈值是显式的, 且能被读出来
assert K.SUPPORT_RULE == "occur * 2 > n", K.SUPPORT_RULE
assert K._has_support({"occur": 3, "n": 5}) and not K._has_support({"occur": 2, "n": 5})
assert not K._has_support({"occur": 2, "n": 4}), "恰好一半不算多数"

# 7c. knots 每项带 support, 下游能看见「这个读数有多少次抽样支持」
r = agg([[("display", 0.6), ("audit", 0.4)]] * 3)
assert all("support" in k for k in r["knots"]), r["knots"][0]
assert r["knots"][0]["support"] == 1.0

# ── 8. provenance: from_temperature 必须对应真正成功的那一档 ─────────────────
# 一个专门记出处的字段记错出处, 比没有这个字段更坏。
import inspect
src = inspect.getsource(K.stage1)
assert "paired" in src and "from_temperature\": paired[0][0]" in src.replace("'", '"'), \
    "from_temperature 必须取自真正成功的那一档, 不能恒取 temps[0]"

# ── 9. top1 判据的 n 依赖 (2026-08-18 对抗评审后修) ─────────────────────────
# 旧字段 top1_stable = len(set(tops))==1 有两个问题:
#   · n=1 时恒真 ⇒ 扣发闸在单抽下永不触发
#   · P(全体一致) ≈ p^n, 随 n 单调下降是构造性的 ⇒ 提高 n 即收紧闸, 与现象无关
# 这意味着「把 n 从 1 提到 5 后 top1_stable 变差」这句话在数学上是必然的, 不是发现。
r1 = agg([[("display", 0.6), ("audit", 0.4)]])                  # n=1
# ★★★ 2026-09-06: 这条断言原文是
#     `assert ... is True, "n=1 必然 unanimous —— 这正是问题"`
#   ——**报错文案自己写着「这正是问题」, 然后把这个问题钉死。**
#   与 test_cce_structural_gate 那条(2026-09-05 修)同形: 测试识别出了缺陷,
#   却把它固化成契约。⇒ 一个能说出病名的闸, 不等于一个会治病的闸。
#   现在判据改为三态: 一个观测点上**观察不到**一致性 ⇒ None(不可判), 不是 True。
assert r1["sampling"]["top1_unanimous"] is None, (
    "★ n=1 时 top1_unanimous 必须是 None(不可判) —— "
    "恒 True 会让下游 playbook 扣发闸在单抽下**永不触发**")
assert r1["sampling"]["top1_mode_share"] == 1.0, r1["sampling"]

# 9a. ★ mode_share 跨 n 可比: 同一个「4/5 命中」在 n=5 与 n=10 上给相同的数
five = agg([[("display", 0.6), ("audit", 0.4)]] * 4 + [[("audit", 0.6), ("display", 0.4)]])
ten = agg([[("display", 0.6), ("audit", 0.4)]] * 8 + [[("audit", 0.6), ("display", 0.4)]] * 2)
assert five["sampling"]["top1_mode_share"] == 0.8, five["sampling"]
assert ten["sampling"]["top1_mode_share"] == 0.8, ten["sampling"]
assert five["sampling"]["top1_mode_share"] == ten["sampling"]["top1_mode_share"], \
    "同一命中率在不同 n 上必须给相同的 mode_share —— 这正是 unanimous 做不到的"
assert five["sampling"]["top1_unanimous"] is False and ten["sampling"]["top1_unanimous"] is False

# 9b. unanimous 在同一命中率下随 n 变化 —— 用反例钉死它不可跨 n 比较
p8_n2 = agg([[("display", 0.6), ("audit", 0.4)]] * 2)
p8_n5 = agg([[("display", 0.6), ("audit", 0.4)]] * 4 + [[("audit", 0.6), ("display", 0.4)]])
assert p8_n2["sampling"]["top1_unanimous"] is True
assert p8_n5["sampling"]["top1_unanimous"] is False
# 两者的 mode_share 分别是 1.0 与 0.8 —— 差异来自抽样, 不来自被测对象

# 9c. 众数身份也要报出来, 否则占比是个悬空的数
assert five["sampling"]["top1_mode"] == "display", five["sampling"]
assert "caveat_unanimous" in five["sampling"], "必须带上不可跨 n 比较的告诫"

print("test_cce_knot_stability: OK (聚合 / 四层 / 强度×出现率 / 偶数n / provenance / top1 的 n 依赖 / CI 自防)")
