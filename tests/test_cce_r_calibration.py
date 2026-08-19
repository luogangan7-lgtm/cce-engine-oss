#!/usr/bin/env python3
"""gen4 live R=8 标定（run 32241812064，192 次真实调用）。

★ 本文件要钉住的不是「R=4 够用」，而是**这个结论的边界**：
  所选文本对在 gen1 上未分开、在 gen4 上强分开，效应量涨 2.8 倍 ⇒ power 饱和 ⇒
  RECOMMEND_R=4 只对那个量级的效应成立，对「生产该取多少 R」几乎没信息。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_ksep as K  # noqa: E402

F = ROOT / "tests" / "data" / "live_r8_calibration_20260819.json"
if F.exists():
    d = json.loads(F.read_text(encoding="utf-8"))
    assert d["instrument"] == "565470cf26c16d01", "必须跑在 gen4 上"
    # ── 1. 投料完整: 三臂各 8/8, 零失败零弃权 ─────────────────────────────
    assert all(v == 8 for v in d["R_qualified"].values())
    assert all(v == 0 for v in d["R_failed"].values()), "本轮零失败(上一轮因单点失败整轮作废)"
    assert set(d["raw"]) == {"T0", "T0b", "T1"}, "必须三臂 —— 两臂分不出 power 与型 I"

    Q = {n: [r["knots"] for r in v if r["qualified"]] for n, v in d["raw"].items()}
    f = lambda n, k: [f"{n}{i}" for i in range(k)]  # noqa: E731

    # ── 2. ★ 型 I 在**真实独立 rep** 上受控(此前只有 bootstrap 版) ─────────
    for r, v in d["curve"].items():
        assert v["null"] <= 0.05 + 1e-9 or v["null"] <= 0.02, f"R={r} 零参照 {v['null']} 超标"
    nul = K.separation(Q["T0"], Q["T0b"], f("a", 8), f("c", 8))
    assert nul["p"] > 0.05 and nul["T"] < 0.01, f"同文本零参照必须不分开: {nul}"

    # ── 3. ★★ power 饱和 ⇒ 结论范围受限, 必须写进数据 ─────────────────────
    assert all(v["power"] == 1.0 for v in d["curve"].values()), "本轮 power 全为 1.000(饱和)"
    assert "饱和" in d["scope_note"] and "几乎没信息" in d["scope_note"], \
        "★ 饱和的 power 曲线不得被当成『R=4 够用』的一般结论"

    # ── 4. ★ 效应量不跨代转移 —— 这是标定不可搬的**实测**证据 ──────────────
    sep = K.separation(Q["T0"], Q["T1"], f("a", 8), f("b", 8))
    assert abs(sep["T"] - 0.06174) < 5e-5 and sep["p"] < 0.001
    assert sep["T"] / 0.02208 > 2.5, \
        "★ 同一对文本 gen1 T=0.02208(未分开) → gen4 T=0.06174(强分开), 涨 2.8 倍。" \
        "此前『标定不可搬』是论证, 现在是**实测**"

    # ── 5. 撤回我此前的「R 下限至少 8」 ────────────────────────────────────
    rp = (ROOT / "scripts" / "cce_resample_power.py").read_text(encoding="utf-8")
    assert "gen1" in rp and ("不是下界" in rp or "conditional" in rp), \
        "那份 0 调用分析必须自带『非下界/条件于 gen1』的限定 —— 它的结论已被 gen4 实测超越"

    # ── 6. 第一个分辨率数据点(重标定第 4 步的开头, 不是全部) ────────────────
    rd = d["resolution_datum"]
    assert rd["T_same"] < 0.01 and rd["instrument"] == "565470cf26c16d01"
    assert "不构成 profile" in rd["note"], "一个文本的同输入重复不等于 resolution profile"
    assert K.SIGNIFICANCE_CONTRACT["measurement"]["delta_resolution"] is None, \
        "★ 单点还不足以标定 delta_resolution —— 不许因为拿到一个数就填上去"

    print("test_cce_r_calibration: OK (三臂/零失败 · 真实型I受控 · power饱和已标注 · "
          "效应量不跨代转移(实测) · 分辨率首个数据点)")
