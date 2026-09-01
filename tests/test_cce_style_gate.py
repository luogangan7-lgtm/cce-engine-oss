#!/usr/bin/env python3
"""出站文风闸的守卫 —— 它在 CI 生产路径上决定内容能不能发出去，此前零测试。

`.github/workflows/cce-submit.yml:131` 每次出站都跑 `style_check.py run/input.txt`，
退出码非 0 就拦稿。这道闸至今没有任何测试。

## 本文件钉住的两件事

**① 它不是永远绿的**（铁律 2：检查必须能观察到失败）。
**② ★ 它当前误杀 72/104 = 69% 的真人语料 —— 而那 104 条正是它自己的基准。**

② 不是"通过项"，是**登记在案的失准**。2026-08-17 记过：
「style_check 当前误杀 65% 真人语料……**先修标定，再开闸**」，
但 2026-08-18 的 `if` 还是把 outbound_post 一并打开了。标定至今未修，
实测比当时还高（69% vs 65%）。

把这个数钉死的用意：任何重标定都**必须重新报数**，不能悄悄变好或变坏。
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SC = ROOT / "scripts" / "style_check.py"
CORPUS = ROOT / "accuracy" / "data" / "reddit_snapshot_20260809.json"

snap = json.loads(CORPUS.read_text(encoding="utf-8"))
HUMAN = [c["body"] for p in snap["posts"].values() for c in p["comments"]]
assert len(HUMAN) == 104, f"基准语料条数变了：{len(HUMAN)}（原 104），下面的数字需重测"


def gate(text):
    """跑真脚本，返回 True=放行。不重实现判据 —— 重实现出的数不是这道闸的数。"""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as f:
        f.write(text)
        p = Path(f.name)
    try:
        return subprocess.run([sys.executable, str(SC), str(p)],
                              capture_output=True).returncode == 0
    finally:
        p.unlink(missing_ok=True)


# ── ① 反向：这些必须被拦（否则它是永远绿的假闸）──────────────────────────
assert not gate(""), "★ 空输入被放行 —— 入口自检缺失，这类闸会恒绿"
assert not gate("x"), "★ 单字符被放行"
assert not gate("The comprehensive evaluation of the aforementioned methodology "
                "demonstrates that the underlying assumptions require substantial "
                "reconsideration in light of the empirical evidence presented herein. " * 8), \
    "★ 通篇长句无短促断句必须被拦（短句<8% 是 ERROR 级）"

# ── ② 正向：真人语料里至少有一部分能过（否则闸是永远红的）────────────────
passed = [t for t in HUMAN if gate(t)]
assert passed, "★ 一条真人语料都过不了 = 永远红。永远红与永远绿是同一种失效。"

# ── ③ ★ 误杀率：登记在案的失准，不是通过项 ────────────────────────────────
killed = len(HUMAN) - len(passed)
assert killed == 72, (
    f"★ 真人语料误杀数从 72/104 变成 {killed}/104。这不一定是坏事"
    "（可能是终于重标定了），但**必须重新报数**：2026-08-17 的处置是"
    "「先修标定再开闸」，而 08-18 已经对 outbound_post 开闸。"
    "改了标定就要更新架构文档与本断言，不许悄悄漂。")
assert killed / len(HUMAN) > 0.5, \
    "★ 误杀率跌破 50% 说明标定已改 —— 同上，重新报数"

# ── ④ ERROR 集不得静默扩张（多一条 ERROR 就多一批误杀）──────────────────
src = SC.read_text(encoding="utf-8")
n_err = src.count("err.append(")
n_warn = src.count("warn.append(")
assert (n_err, n_warn) == (5, 7), (
    f"★ ERROR/WARN 条数从 (5,7) 变成 ({n_err},{n_warn})。"
    "在 69% 误杀率未修之前新增 ERROR，会直接放大误杀。")
# 电报体上限是**有意**的软边界，必须留在 WARN 侧
i_short_hi = src.index('short_frac"] > 0.45')
assert "warn.append(" in src[i_short_hi:i_short_hi + 200], \
    ("★ 短句占比上限（电报体保护）被提成 ERROR。代码注释写明「越界只 WARN」，"
     "是有意的软边界；提成 ERROR 属改判据，需先重标定。")

print(f"test_cce_style_gate: OK (空/单字符/全长句均被拦 · 真人语料放行 {len(passed)}/104 · "
      f"★误杀 {killed}/104={killed*100//104}% 已钉住 · ERROR{n_err}/WARN{n_warn})")
