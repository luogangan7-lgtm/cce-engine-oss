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

# ── 7. Phase 1 实测（run 32246651860，192 调用） ─────────────────────────────
import json  # noqa: E402
PLF = ROOT / "tests" / "data" / "perturbation_ladder_20260819.json"
if PLF.exists():
    pl = json.loads(PLF.read_text(encoding="utf-8"))
    assert pl["instrument"] == "565470cf26c16d01" and pl["verdict"].startswith("LADDER_USABLE")
    c = pl["comparisons"]
    # ① 零参照不分开（型 I 前提）
    assert not c["L0b"]["separated"], "零参照分开则整轮不可读"
    # ② ★ 不变性：表层改写比 L0 自己重跑**还更接近** L0
    for b in ("B1", "B2"):
        assert not c[b]["separated"], f"{b} 不该分开 —— 姿态未变"
        assert c[b]["T"] < c["L0b"]["T"], \
            f"★ {b} 的 T({c[b]['T']}) 应低于零参照({c['L0b']['T']}) —— 同义/格式改写不产生可测位移"
    # ③ ★★ 敏感性：去词化的情境/立场改变被读出，且远高于零参照
    for a in ("A1", "A3"):
        assert c[a]["separated"] and c[a]["T"] > 6 * c["L0b"]["T"], \
            f"★ {a} 必须分开且远高于零参照 —— 否则是 SEMANTIC_BLIND(真证伪)"
    # ④ ★ 禁止两处过度声称（写进数据，不只写在报告里）
    sn = pl["scope_note"]
    assert "不能说: 它专门在读「心理姿态」" in sn, \
        "★ A 臂同时改了所说的事 —— 姿态与内容改变在本设计里分不开，不得声称只读姿态"
    assert "单调性" in sn and "Phase 2" in sn, "★ 前登记禁止本轮宣称 T(A1)<T(A3)"
    assert "n=1 base text" in sn
    # ⑤ attempt ledger 真的在记：本轮有 4 次 INFRA 重试，没有 ledger 就完全不可见
    inf = sum(r["op"]["n_infra_failed"] for v in pl["raw"].values() for r in v)
    assert inf > 0, "本轮确有 infra 重试；若为 0 需复查 ledger 是否真的在记"
    assert any(r["op"]["first_attempt_success_rate"] < 1.0
               for v in pl["raw"].values() for r in v), "首次失败必须留痕"
    print("  Phase1 已钉: B 轴不动(低于零参照) / A 轴 6.5-9.8 倍 / 两处过度声称已封 / ledger 生效")
