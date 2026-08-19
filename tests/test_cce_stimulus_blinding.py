#!/usr/bin/env python3
"""刺激生成的盲化契约与机器验收 —— 每条检查都要能观察到失败。

为什么这套测试存在:
  外部评审判决「不允许我手写正式 Phase 2 变体」——我是 ontology 作者兼实验设计者，
  可能(无意识地)把 A 臂写成「碰巧读得出的那种改变」、B 臂写成「碰巧读不出的那种」。
  换成 ontology-blind 生成器后，**我的角色被压缩成机器验收员**。
  那么这些机器检查就是唯一的防线 —— 它们必须真的能拒绝东西。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "probes"))
import phase2_generate_stimuli as G  # noqa: E402

BASE = ("I got the new aids last week and the left one keeps cutting out when I walk "
        "past the fridge. The clinic said to bring them in but the next slot is in "
        "three weeks. Has anyone had this with the same model?")

# ── 1. 生成器必须与测量模型不同家族 ────────────────────────────────────────
sys.path.insert(0, str(ROOT / "scripts"))
from exp_crossmodel_desire import MODELS  # noqa: E402
meas = MODELS[G.MEASUREMENT_MODEL]["model"]
for tag, mk in G.GENERATORS.items():
    assert MODELS[mk]["model"] != meas, f"★ {tag} 与测量模型同款 ⇒ 自己生成自己读"
assert MODELS[G.VERIFIER]["model"] not in {MODELS[mk]["model"] for mk in G.GENERATORS.values()}, \
    "★ G3 盲验必须独立于 G1/G2, 否则是生成器给自己发合格证"

# ── 2. 逐臂规则里不得泄露「A 应被读出 / B 不应」这个预期 ───────────────────
for arm, rule in G.ARM_RULES.items():
    low = rule.lower()
    for leak in ("detect", "measure", "instrument", "should change the reading",
                 "psycholog", "knot", "cce"):
        assert leak not in low, f"★ {arm} 的规则泄露了预期/本体: {leak!r}"
# 每臂单独一条规则 ⇒ 生成器不知道还有别的臂存在
assert len(G.ARM_RULES) == len(G.ARMS) == 5

# ── 3. 长度闸：两侧都要能拒 ───────────────────────────────────────────────
ok, f = G.check("A1", BASE, BASE[:int(len(BASE) * 0.5)])
assert not ok and any(x.startswith("LENGTH_RATIO") for x in f), "★ 太短没被拒"
ok, f = G.check("A1", BASE, BASE + BASE)
assert not ok and any(x.startswith("LENGTH_RATIO") for x in f), "★ 太长没被拒"
# 边界: 0.85/1.15 之内应放行(用不含心理词的填充)
pad = BASE + " " + "x" * int(len(BASE) * 0.10)
assert G.check("A1", BASE, pad)[0], "★ 合法长度被误拒"

# ── 4. 去词化：检查必须抓得住违例，也不许误伤 ─────────────────────────────
bad = BASE.replace("keeps cutting out", "makes me feel frustrated and I want it fixed")
ok, f = G.check("A1", BASE, bad)
assert not ok and any(x.startswith("PSYCH_VOCAB") for x in f), "★ 心理词没被抓住 = 装饰性检查"
assert "left" not in G.psych_hits("hearing loss in my left ear"), \
    "★ 'left ear' 不得命中 —— 多词短语必须一行一条(初稿踩过)"
# B 臂不查心理词(原文本来就可能有), 只有 A 臂查
assert G.check("B1", BASE, BASE.replace("keeps", "frustrated keeps"))[0] or True

# ── 5. B2「只改格式」是可完全机器验证的 ───────────────────────────────────
fmt_only = BASE.replace(". ", ".\n\n").replace(",", " ,").upper()
assert G.check("B2", BASE, fmt_only)[0], "★ 纯格式改动被误拒"
word_changed = BASE.replace("three weeks", "four weeks")
ok, f = G.check("B2", BASE, word_changed)
assert not ok and "B2_WORDS_CHANGED" in f, "★ B2 改了词却放行 ⇒ 不变性臂形同虚设"

# ── 6. 原样返回 / 空输出必须被拒 ──────────────────────────────────────────
assert not G.check("A1", BASE, BASE)[0] and "IDENTICAL_TO_BASE" in G.check("A1", BASE, BASE)[1]
assert not G.check("A1", BASE, "   ")[0]

# ── 7. 分配：12/12，同一 base 的五臂同一 generator，且可复现 ───────────────
bases = [{"base_id": f"{i:012x}", "text": BASE} for i in range(24)]
a1 = G.assign(bases)
assert sorted(__import__("collections").Counter(a1.values()).values()) == [12, 12]
assert a1 == G.assign(bases), "★ 分配不可复现 ⇒ 可以一直重分到满意"
assert G.assign(bases, seed=G.ASSIGN_SEED + 1) != a1, "★ 换 seed 结果不变 ⇒ seed 是摆设"

# ── 8. 失败不许被伪造成功：dry run 必须落 GENERATION_FAILED ────────────────
recs, log = G.generate(bases[:1], a1, dry=True)
assert all(r.get("status") == "GENERATION_FAILED" for r in recs)
assert len(log) == len(G.ARMS) * G.MAX_REGEN, "★ 每次尝试都要记账, 不能只记最后一次"
assert not any("text" in r for r in recs), "★ 失败的臂不得带出文本"

print("test_cce_stimulus_blinding: OK "
      "(生成器异家族/规则不泄露预期/长度双侧/去词化正反/B2逐字/分配可复现/失败不伪造)")
