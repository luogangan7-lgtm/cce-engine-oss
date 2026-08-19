#!/usr/bin/env python3
"""Draw ledger: pre-aggregation 的逐 draw 必须完整落盘。

理由(2026-08-18, 外部源码审计 + 库内早先的 E0 使能项):
  stage1 每个 draw 只留 tops(**顶层标签**)与 appraisal, 四层完整向量算完 top 就丢;
  stage2 的 draws 在 _stage2_aggregate 内部算完也丢。
  后果: 事后无法重算不同聚合 / 重算 within_js / 做维度级 bootstrap /
        研究某维度为什么抖 / 研究 co-occurrence 与 latent structure。
  ★ API 调用比 JSON 存储贵得多 —— 事后发现 raw draw 没留是**不可逆**损失。

★ 并且 ledger 必须**不改变 instrument_hash** —— 它是输出字段, 不是仪器定义。
  否则今天六个 run 会与后续不可比, 那就本末倒置了。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_knot_classify as K  # noqa: E402

TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))

# ── 1. 九结全集必须来自同一处真相, 不能各写一份 ──────────────────────────────
assert set(K.KNOTS_ALL) == {k["key"] for k in TAXO["knots"]}, \
    "KNOTS_ALL 与 knot_taxonomy 不一致 —— 两份全集必然漂移"
assert len(K.KNOTS_ALL) == 9


# ── 2. stage2 draw ledger: 完整 9 维, 缺席显式记 0 ──────────────────────────
def _agg(spec, shim=False):
    n = len(next(iter(spec.values())))
    draws = []
    for i in range(n):
        ks = [{"key": k, "intensity": v[i], "evidence_quote": "", "signature": {}}
              for k, v in spec.items() if v[i] > 0]
        d = {"knots": ks, "levers_present": [], "notes": ""}
        if shim:
            d["_weight_shim_fired"] = True
        draws.append(d)
    orig = K._stage2_draw
    K._stage2_draw = lambda p, t, tag: draws[int(tag[1:]) % len(draws)]
    try:
        return K._stage2_aggregate("x", TAXO, n=len(draws))
    finally:
        K._stage2_draw = orig


SPEC = {"pain_seek": [0.9, 0.9, 0.9, 0.9, 0.9],
        "audit":     [0.5, 0.5, 0.5, 0.0, 0.0],
        "belong":    [0.3, 0.3, 0.0, 0.0, 0.0]}
out = _agg(SPEC)
led = out["draw_ledger"]
assert len(led) == 5, f"每次抽样都要有一条 ledger, 实得 {len(led)}"
for row in led:
    assert set(row["knot_vector"]) == set(K.KNOTS_ALL), \
        "★ 必须是完整 9 维 —— 只存出现过的结就等于没解决问题"
# 缺席必须是显式 0, 不是缺键
assert led[3]["knot_vector"]["audit"] == 0.0 and led[3]["knot_vector"]["belong"] == 0.0
assert led[0]["knot_vector"]["audit"] == 0.5 and led[0]["knot_vector"]["pain_seek"] == 0.9
assert all(r["top1"] == "pain_seek" for r in led)

# ★ 从 ledger 必须能**重算**聚合值 —— 这才是它存在的意义
import statistics as st  # noqa: E402
for k in ("pain_seek", "audit", "belong"):
    nz = [r["knot_vector"][k] for r in led if r["knot_vector"][k] > 0]
    occ = len(nz)
    per = out["sampling"]["per_knot"][k]
    assert per["occur"] == occ, f"{k}: ledger 重算 occur={occ} != 报告 {per['occur']}"
    assert abs(per["intensity"] - st.median(nz)) < 1e-9, f"{k}: ledger 重算不出 intensity"

# ── 3. ★ 量夹垫片必须被记录(静默量纲混合的唯一可见性) ───────────────────────
assert all(r["weight_shim_fired"] is False for r in _agg(SPEC)["draw_ledger"])
assert all(r["weight_shim_fired"] is True for r in _agg(SPEC, shim=True)["draw_ledger"]), \
    "垫片触发必须落盘 —— 否则和为1的 weight 与自由 intensity 混进同一个中位数, 永远看不见"

# ── 4. ★★ ledger 不得改变 instrument_hash ──────────────────────────────────
# 它是输出字段, 不是仪器定义。若它进了 hash, 今天六个 run 会与后续不可比。
# ⚠️ s1_pairing 的真实值是 f-string `round_robin_over_{n}_s1_draws`, 不是 "round_robin"。
#   我第一次写这条测试时猜错了字符串, 于是它报「ledger 改变了指纹」——
#   一个**假阳性**, 差点让我以为改坏了仪器。断言里写死真实值, 不再猜。
spec = K.instrument_id(TAXO, k=3, knot_n=5, s1_pairing="round_robin_over_3_s1_draws")
# ⚠️ 2026-08-18 [2/4]: 本断言原为 `== "57ec6cf478d3875e"`。
#   [2/4] 把 s1 prompt 与 abstention 策略纳入指纹, **哈希必然改变** ——
#   物理仪器没变, 变的是身份定义更完整了。断言更新为新哈希 + 换代桥接, 不是删除。
assert spec["instrument_hash"] == "565470cf26c16d01", (
    f"仪器指纹变了({spec['instrument_hash']}) —— 若非有意换代, 先查是什么改动引起的。\n"
    f"当前谱系: gen1→gen2→gen3 ea70b373d5bef630→gen4(本代, 仅重划哈希作用域)")
assert K.INSTRUMENT_LINEAGE[0]["hash"] == "57ec6cf478d3875e", "谱系首代必须留着"
# ★ ledger 本身仍必须是**仪器中性**的: 它是输出字段, 不该出现在仪器定义里
assert "draw_ledger" not in json.dumps(spec["spec"]), "ledger 不该出现在仪器定义里"
assert "KNOTS_ALL" not in json.dumps(spec["spec"])

# ── 4b. ★ s1_pairing 嵌了**运行时成功数**, 指纹随之变 —— 钉住这个已知性质 ──
#   一次瞬时 API 失败(k_ok < k_requested)就会换一把尺子。
#   这本身是**对的**(2 个 draw 拼出来的读数确实不是同一种测量),
#   但它不明显: 没人预期网络抖动会改变仪器身份。钉在这里, 让它是已知而非意外。
_h = {n: K.instrument_id(TAXO, k=3, knot_n=5,
                         s1_pairing=f"round_robin_over_{n}_s1_draws")["instrument_hash"]
      for n in (1, 2, 3)}
assert len(set(_h.values())) == 3, "s1 成功数不同必须给出不同仪器 —— 否则会静默混比"
assert _h[3] == "565470cf26c16d01", "n=3 应给出当前(gen4)指纹"

# ── 5. 反向测试: 去掉「缺席记 0」, 断言必须红 ────────────────────────────────
_partial = {k: v for k, v in led[3]["knot_vector"].items() if v > 0}
assert set(_partial) != set(K.KNOTS_ALL), "反向用例必须构造出不完整向量"

# ── 6. stage1 per_draw 必须带完整四层向量, 不只是 tops ─────────────────────
import inspect  # noqa: E402
src = inspect.getsource(K.stage1)
for _v in ("desire_vec", "need_vec", "emotion_vec", "action_vec"):
    assert f'"{_v}": pv["{_v}"]' in src, \
        f"stage1 per_draw 缺 {_v} —— 只留 tops 等于丢掉重研究能力"
assert '"tops"' in src, "tops 仍应保留(下游已有读法)"

print("test_cce_draw_ledger: OK (9维完整/缺席记0/可重算聚合/垫片可见/指纹不变/stage1四层)")
