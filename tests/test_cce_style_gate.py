#!/usr/bin/env python3
"""出站文风闸的守卫。`.github/workflows/cce-submit.yml:131` 每次出站都跑它，
退出码非 0 就拦稿 —— 它决定内容能不能发出去。

## 2026-09-01 重标定前的实测（真脚本，两个集合）

    真人语料 拦下 72/104 = 69%
    我方稿件 拦下 34/48  = 70%

**两者几乎相等 ⇒ 判别力 ≈ −1%。它不是闸，是近乎无差别的拦截器。**
根因 2026-08-17 已记：拿真人**中位数的一半**当下限是构造性缺陷 ——
中位数上方永远只有一半样本。

## 重标定做了什么

逐条量真人分布后发现「分位数判据」也救不了两条规则：`short_frac` 零值占比
42%/38%/30%（全量/≥25词/≥50词）、`contraction` 32%/22%/10%。
**零值占比高于目标误杀率时，任何非零阈值都必然误杀那么多真人** ⇒ 这两条
结构上不能当 ERROR，降为 WARN。只有 `first_person` 在 ≥50 词时零值降到 4%，
撑得起 p5 分位阈值。长度不足 ⇒ **弃权**（与 CCE 仪器「没有空读数」那个缺陷同形：
12 词的评论算不出人称密度，就不该给它一个自信的判决）。

## 本文件守的三件事
① 判别力（真正要守的性质，旧闸就死在这）② 不是永远绿 ③ 两个率都钉死，重标定必须重新报数
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SC = ROOT / "scripts" / "style_check.py"

snap = json.loads((ROOT / "accuracy" / "data" / "reddit_snapshot_20260809.json")
                  .read_text(encoding="utf-8"))
HUMAN = [c["body"] for p in snap["posts"].values() for c in p["comments"]]
OURS = [d for f in sorted((ROOT / "run_items").glob("*.json"))
        for it in json.loads(f.read_text(encoding="utf-8"))
        if len((d := (it.get("draft") or "").strip()).split()) >= 25]
assert (len(HUMAN), len(OURS)) == (104, 48), \
    f"语料规模变了 真人{len(HUMAN)}/我方{len(OURS)}（原 104/48），下面的率需重测"


def blocked(text):
    """跑真脚本。**不重实现判据** —— 2026-09-01 手搓复现给 72%、真脚本 69%，差 3 个点。"""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as f:
        f.write(text)
        p = Path(f.name)
    try:
        return subprocess.run([sys.executable, str(SC), str(p)],
                              capture_output=True).returncode != 0
    finally:
        p.unlink(missing_ok=True)


n_false = sum(1 for t in HUMAN if blocked(t))     # 误杀真人
n_catch = sum(1 for t in OURS if blocked(t))      # 拦下我方稿
fp, tp = n_false / len(HUMAN), n_catch / len(OURS)

# ── ① ★ 判别力：闸必须区分得开真人与我方稿 ────────────────────────────────
assert tp - fp >= 0.50, (
    f"★ 判别力 {tp - fp:+.0%}（拦我方 {tp:.0%} − 误杀真人 {fp:.0%}）< 50%。\n"
    "  重标定前正是 +1%（69% vs 70%）—— 那种闸拦下什么都不说明问题。\n"
    "  **只放宽阈值会让判别力一起掉**，所以这条必须和下面两条一起看。")

# ── ② 不是永远绿（铁律 2）────────────────────────────────────────────────
assert blocked(""), (
    "★ 空输入被放行 —— 入口自检缺失。2026-09-01 加长度门时我正是打开了这个洞："
    "空稿的分布式规则全部弃权、类别型规则又都 0 命中 ⇒ ERROR=0 ⇒ 放行。"
    "入口自检必须在长度门**之前**：弃权(12 词真评论指标不可评)与无效输入(空稿)是两件事。")
# ★ 已知限制（写明，不用断言假装它不存在）：<50 词的稿件只剩类别型规则把关。
#   "x" 这类退化输入按设计是「指标不可评 ⇒ 弃权」，**不会**被拦。
#   这个门之所以不掏空闸，是因为实际投料全在门以上 —— 下面这条钉住它。
short_ours = [t for t in OURS if len(t.split()) < 50]
assert not short_ours, (
    f"★ 我方稿件出现 {len(short_ours)} 条 <50 词。长度门会对它们弃权分布式规则，"
    "闸只剩类别型把关 —— 此前 48/48 全在门以上，所以门不掏空闸。"
    "比例一变，这个前提就没了，必须重新评估门槛位置。")

# 类别型 ERROR（大纲标签句/破折号）不受长度门影响，长文短文都该拦
assert blocked("The problem is clear. " + "We evaluated the approach carefully. " * 30), \
    "★ 行首大纲标签句必须被拦（该规则在真人语料上误报为 0）"

# ── ③ 两个率钉死：任何重标定都必须重新报数 ────────────────────────────────
assert (n_false, n_catch) == (3, 28), (
    f"★ 误杀 {n_false}/104、拦下我方 {n_catch}/48（原 3/48 与 28/48）。\n"
    "  历史：2026-09-01 重标定前是 72/104 与 34/48。数字变了就更新架构文档与本断言，"
    "不许悄悄漂 —— 这道闸在拦真要发出去的内容。")

# ── ④ 结构性判决不得被悄悄改回 ────────────────────────────────────────────
src = SC.read_text(encoding="utf-8")
n_err, n_warn = src.count("err.append("), src.count("warn.append(")
assert (n_err, n_warn) == (4, 10), \
    (f"★ ERROR/WARN 从 (4,10) 变成 ({n_err},{n_warn})。重标定把 short_frac 与 "
     "contraction 由 ERROR 降为 WARN（零值占比 30-42% / 10-32%，当硬闸必然大批误杀）；"
     "把它们改回 ERROR 前必须先证明零值占比降下来了。")
assert "LENGTH_FLOOR_WORDS = 50" in src and "FP_PCTILE = 5" in src, \
    "★ 重标定常量必须是显式常量，不许再藏回算术里（上一次教训：中位数的一半就是藏着的阈值）"
i = src.index('if d["short_frac"] < 0.08:')
assert "warn.append(" in src[i:i + 300], "★ short_frac 被改回 ERROR"

print(f"test_cce_style_gate: OK (★判别力 {tp - fp:+.0%} = 拦我方 {n_catch}/48 − "
      f"误杀真人 {n_false}/104 · 空稿·标签句均拦 · ERROR{n_err}/WARN{n_warn} · 长度门与分位常量显式)")
