#!/usr/bin/env python3
"""Designed Perturbation Ladder 的**设计前提**必须可机器检验。

★ 本文件的由来是两次自查失败：
  ① 初版「A 臂不得含 rubric 词汇」是**空检查** —— rubric 判别式是中文而语料是英文，
     必然通过，观察不到失败。已弃用。
  ② 换成英文心理词表后，初版把多词短语与单词写在同一行，被拆成单词 ⇒
     `left ear` 命中 `left`，**假阳性**。改为一行一词条。
  ③ 长度混杂：A 臂初稿 405/450 字 vs L0 293 字 ⇒ A 分开可能是长度效应。
     已改写到 279–307（极差 10%）。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAD = ROOT / "tests" / "data" / "ladder"

VOCAB = [l.strip() for l in (LAD / "PSYCH_VOCAB.txt").read_text(encoding="utf-8").split("\n")
         if l.strip() and not l.startswith("#")]
ARMS = {f.stem: f.read_text(encoding="utf-8").strip()
        for f in LAD.glob("*.txt") if f.name != "PSYCH_VOCAB.txt"}


def _body(t):
    """只取 [楼主正文] 段 —— 标题行各臂共用, 不参与姿态判定。"""
    return t.split("[楼主正文]", 1)[-1].split("[现场已有回复]", 1)[0]


def hits(t):
    return sorted({w for w in VOCAB if re.search(r"\b" + re.escape(w) + r"\b", t.lower())})


# ── 1. 六个变体齐全 ─────────────────────────────────────────────────────────
assert set(ARMS) == {"L0_base", "A1_delex_mild", "A3_delex_moderate",
                     "B1_surface_rewrite", "B2_format_only"}, sorted(ARMS)

# ── 2. ★ 去词化: A 臂不得命名感受/评价/动机 ─────────────────────────────────
for name in ("A1_delex_mild", "A3_delex_moderate"):
    assert not hits(ARMS[name]), f"{name} 含心理状态词 {hits(ARMS[name])} —— 去词化不成立"

# ── 3. ★★ 反向测试: 这个检查必须能观察到失败 ────────────────────────────────
bad = "I feel frustrated that they didn't ask, and I want something that works."
assert set(hits(bad)) >= {"feel", "frustrated", "want"}, "★ 检查抓不住违例 = 装饰"
# 且不得假阳性(初版把 'left out' 拆开, 让 'left ear' 命中 'left')
assert not hits("hearing loss in my left ear"), "★ 'left ear' 不得命中 —— 多词短语须一行一条"
for line in (LAD / "PSYCH_VOCAB.txt").read_text(encoding="utf-8").split("\n"):
    s = line.strip()
    if s and not s.startswith("#"):
        assert s.count(" ") <= 2, f"词条 {s!r} 太长, 可能是把多条写在了一行"

# ── 4. ★ 长度混杂: 各臂长度极差须 <15% ──────────────────────────────────────
lens = {k: len(v) for k, v in ARMS.items()}
lo, hi = min(lens.values()), max(lens.values())
assert (hi - lo) / lo < 0.15, \
    f"★ 长度极差 {(hi-lo)/lo:.0%} 过大({lens}) —— A 臂分开会分不清是姿态还是长度"

# ── 5. ★ B 轴必须**保持**核心事实与诉求(表层改写, 不是换内容) ────────────────
for name in ("B1_surface_rewrite", "B2_format_only"):
    t = ARMS[name].lower()
    assert "outside" in t and "ear" in t, f"{name} 丢了核心诉求"
    assert ("crash" in t or "car" in t), f"{name} 丢了核心事实"
    assert "?" in _body(ARMS[name]), f"{name} 正文必须仍是提问姿态"
# 而 A3 **不再是**提问姿态(姿态确实变了) —— 这是 A 轴与 B 轴的分野
# ⚠️ 只能看**正文**: 标题行 "Over-the-ear hearing aids?" 各臂共用, 自带问号,
#    初版断言整段文本不含 "?" 于是被标题绊倒 —— 断言的作用域写错了。
assert "?" not in _body(ARMS["A3_delex_moderate"]), "A3 正文应已从求助变为告知"
assert "?" in _body(ARMS["A1_delex_mild"]), "A1 正文仍是问句, 但问的对象从产品变成了依据"

# ── 6. 命名纪律 ─────────────────────────────────────────────────────────────
src = (ROOT / "probes" / "perturbation_ladder.py").read_text(encoding="utf-8")
assert "Known Effect-Size Ladder" in src and "禁止" in src, \
    "必须显式禁止 Known Effect-Size Ladder 这个叫法 —— 单调性是待检验对象不是前提"
assert "拿仪器对它自己的定义做检验" in src, \
    "必须写明为何不采用『调 rubric 触发词』的剂量臂(库内已否决)"

print("test_cce_ladder_design: OK (六臂齐 / 去词化可证伪 / 无假阳性 / 长度极差<15% / "
      "B保内容 A变姿态 / 命名纪律)")
