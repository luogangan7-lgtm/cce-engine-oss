# -*- coding: utf-8 -*-
"""闸: 断言表 v2 维持撤销的 2 条 display(Q 支)断言 —— 对应 (用例×display) 已由增量支(甲)断言覆盖, 登记与现算一致; 清单不得再说「零覆盖」。零调用。"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "probes")); sys.path.insert(0, str(ROOT / "scripts"))
import withdrawn_display_assertions_reclassify as R
D = json.loads((ROOT / "tests/data/local_contract_assertions_v2.json").read_text(encoding="utf-8")); W = D["★★★2026-09-23 撤销项处置"]


def _display_rows(u): return [a for a in D["断言"] if a["用例"] == u and a["输出谓词"] == "top1 != 'display'"]


def test_registered_cases_equal_probe_kept_withdrawn_and_each_cell_is_covered():
    assert list(W["用例×结 覆盖情况"]) == R.build()["★维持撤销"]
    for u, v in W["用例×结 覆盖情况"].items():
        live = [a for a in _display_rows(u) if a["★★★断言状态"] == "已裁定"]; wd = [a for a in _display_rows(u) if a["★★★断言状态"].startswith("**已撤销")]
        assert len(live) == 1 and len(wd) == 1 and live[0]["条款定位"] == v["覆盖该格的已裁定断言 条款定位"] and "增量支" in live[0]["条款定位"]
        assert wd[0]["条款定位"] == v["被撤销的那条 条款定位"] and {a["文本sha256_8"] for a in D["断言"] if a["用例"] == u} == {v["文本sha256_8"]}


def test_the_zero_coverage_claim_is_retracted_not_repeated():
    assert "不成立" in W["★我先前在清单里写错的一句"] and "合取" in W["★我先前在清单里写错的一句"]
    from cce_open_items import items, DECIDED
    it = next(x for x in items() if "条已撤销" in x["项"]); assert it["类"] == DECIDED and "有覆盖" in it["证据"] and "无需新断言" in it["项"]
