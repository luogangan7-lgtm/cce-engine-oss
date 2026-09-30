# -*- coding: utf-8 -*-
"""s1 散布闸扣发率序贯监测: 区间算法、查看点规则、当前状态如实为「攒样本」。"""
import importlib.util, json, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
_s = importlib.util.spec_from_file_location("_wm", ROOT / "probes/within_js_monitor.py"); M = importlib.util.module_from_spec(_s); _s.loader.exec_module(M)


def test_clopper_pearson_known_values():
    assert M.clopper_pearson(0, 10, 0.05) == (0.0, 0.3085)          # 10 条零超限, 上界仍 ~31%
    lo, hi = M.clopper_pearson(7, 54, 0.05)
    assert lo >= 0.05 and hi <= 0.25                                 # 54 = 能整个落在带内的最小 n
    assert all(M.clopper_pearson(k, 53, 0.05)[0] < 0.05 or M.clopper_pearson(k, 53, 0.05)[1] > 0.25 for k in range(54))


def test_sequential_rule():
    assert M.judge([True] * 5 + [False] * 20) == ("ACCUMULATING", None, None)
    assert M.judge([False] * 60)[0] == "CONTINUE"                    # 60 条零超限: 99% 上界 ~8.5%, 还判不了
    assert M.judge([False] * 120)[:2] == ("OUT_OF_BAND", 120)
    assert M.judge([True] * 40 + [False] * 20)[:2] == ("OUT_OF_BAND", 60)
    mid = ([True] + [False] * 5) * 10                                # 1/6: 60 条时跨界 ⇒ 继续
    assert M.judge(mid)[0] == "CONTINUE"
    assert M.judge(mid * 3)[0] in ("IN_BAND", "UNRESOLVED") and M.judge(mid * 3)[1] in (120, 180)
    assert M.judge([True] * 60 + [False] * 200)[:2] == ("OUT_OF_BAND", 60)   # 判定后不再看后面的
    assert abs(sum(a for _, a in M.LOOKS) - 0.05) < 1e-12


def test_current_state_is_not_a_band_claim():
    pre = json.loads((ROOT / "tests/data/within_js_monitor_prereg.json").read_text(encoding="utf-8"))
    assert [m for m, _ in M.LOOKS] == pre["sequential_rule"]["looks"] and [a for _, a in M.LOOKS] == pre["sequential_rule"]["error_spend"]
    for inst, v in M.build().items():
        assert v["n_texts"] == len({sha for _, sha, _ in M.events(inst)[:180]})          # 文本级, 不重复
        if v["n_texts"] < 60:
            assert all(x["verdict"] == "ACCUMULATING" for x in v["per_layer"].values())
