# -*- coding: utf-8 -*-
"""闸: s0 无金标重测 (probes/s0_retest.py → results/s0_retest.json)。零调用。"""
import importlib.util, json, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "results/s0_retest.json"; RUN1 = ROOT / "results/s0_jev_shadow.json"
_s = importlib.util.spec_from_file_location("_rt", ROOT / "probes/s0_retest.py"); rt = importlib.util.module_from_spec(_s); _s.loader.exec_module(rt)


def _res(): return json.loads(OUT.read_text(encoding="utf-8"))


def test_kappa_multi_is_a_real_gate():
    """κ 的三条边界: 完全一致=1 · 独立随机≈0 · 常数读出=None。"""
    assert rt.kappa_multi(list("aabb"), list("aabb"))["kappa"] == 1.0
    assert rt.kappa_multi(list("aabb"), list("abab"))["kappa"] == 0.0
    assert rt.kappa_multi(list("aaaa"), list("aaaa"))["kappa"] is None
    assert rt.kappa_multi(list("abcabc"), list("abcabd"))["kappa"] < 1.0


def test_upper_bound_recomputes_from_rows():
    """准确率上界 = 1 − d/(2n), 由 rows 现算逐面逐臂一致; 不同的条数也现算。"""
    res = _res(); rows1 = json.loads(RUN1.read_text(encoding="utf-8"))["rows"]
    r1 = {"mm": {r["ptr"]: r["mm"] for r in rows1 if r["mm_ok"]}, "jev": {r["ptr"]: r["jev"] for r in rows1 if r["jev_ok"]}}
    r2 = {"mm": {r["ptr"]: r["mm"] for r in res["rows"] if r["mm_ok"]}, "jev": {r["ptr"]: r["jev"] for r in res["rows"] if r["jev_ok"]}}
    for arm in ("mm", "jev"):
        got = rt.arm_stats(r1[arm], r2[arm], arm)
        for k in rt.KEYS:
            assert got[k]["两轮不同"] == res["★★★逐面逐臂"][arm][k]["两轮不同"], (arm, k)
            assert got[k]["kappa"] == res["★★★逐面逐臂"][arm][k]["kappa"], (arm, k)
            assert res["★★★逐面逐臂"][arm][k]["★准确率上界(两轮均值)"] == round(1 - got[k]["两轮不同"] / (2 * got[k]["n"]), 4)


def test_structural_constraint_recomputes_and_is_time_only_design():
    """情绪余温 结构违反数由 rows 现算一致; 两轮提示词/题目集 sha 与轮1 产物一致(只有时间在变)。"""
    res = _res(); run1 = json.loads(RUN1.read_text(encoding="utf-8"))
    r2 = {r["ptr"]: r["mm"] for r in res["rows"] if r["mm_ok"]}
    assert rt.struct_check(r2, "mm")["违反结构约束(填了 正向/负向/中性)"] == res["★★★情绪余温结构约束"]["mm"]["轮2"]["违反结构约束(填了 正向/负向/中性)"]
    assert res["★与第一轮配对"]["轮1 提示词 sha"] == run1["★MiniMax 提示词 sha"]
    assert res["★与第一轮配对"]["轮1 Jev 题目集 sha"] == run1["★Jev 题目集 sha"] == rt.shadow.question_sha()
    assert set(r["ptr"] for r in res["rows"]) == set(r["ptr"] for r in run1["rows"])


def test_no_gold_no_text_no_accuracy_claim():
    """产物不含金标字段、不含原文、不写「更准」; 账本不超上限。"""
    res = _res(); s = json.dumps(res, ensure_ascii=False)
    assert "金标" not in json.dumps(res["★★★逐面裁决(只比稳定性)"], ensure_ascii=False)
    assert "更准" not in s.replace("不得说哪臂更准", "")
    assert all(set(r) == {"ptr", "mm_ok", "mm", "jev_ok", "jev", "jev_conf", "jev_err"} for r in res["rows"])   # 无 text 键
    assert "apikey_" not in s and "apikey_" not in (ROOT / "probes/s0_retest.py").read_text(encoding="utf-8")
    assert res["★账本"]["minimax"] <= rt.shadow.CAP and res["★账本"]["req"] <= rt.shadow.CAP * 2


def test_dry_run_zero_call():
    p = subprocess.run([sys.executable, str(ROOT / "probes/s0_retest.py"), "--dry-run"], capture_output=True, text=True, cwd=ROOT)
    assert p.returncode == 0 and "[dry-run] 42 条" in p.stdout, p.stdout[-400:] + p.stderr[-400:]
