"""K1 读数形式缺口(2026-10-03)与 G-P 判定(2026-10-04)不许静默消失。

K1 判在 knots[0], 生产发布 top1_mode。G-P 未出结果时两格都要带缺口说明;
G-P (a) FAIL 后 k=3 那格必须是「已测·不达标」并引 G-P 数字, 且写明生产路由未改(待 owner);
k=5 那格 G-P 不覆盖, 缺口说明照留。
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
GPR = os.path.join(ROOT, "tests/data/gate_gp_result.json")


def _top1():
    import cce_production_status as P
    rows = {r["组件"]: r for r in P.rows() if r["组件"].startswith("结层 top-1")}
    assert len(rows) == 2
    return rows["结层 top-1 @ reply / response (k=3)"], rows["结层 top-1 @ outbound_post (k=5)"]


def test_k5_keeps_gap_caveat():
    _, k5 = _top1()
    assert "knots[0]" in k5["证据"] and "top1_mode" in k5["证据"] and "G-P 只覆盖 k=3" in k5["证据"]


def test_k3_follows_gp_verdict():
    import cce_production_status as P
    k3, _ = _top1()
    if not os.path.exists(GPR):
        assert "knots[0]" in k3["证据"] and "若 FAIL 本格须降级" in k3["证据"]
        return
    a = json.load(open(GPR, encoding="utf-8"))["a_production_rerun_stability"]
    if a["verdict"] == "FAIL":
        assert k3["状态"] == P.FAILED
        assert f"{a['agree']}/{a['n_pairs']}" in k3["证据"] and "生产路由未改" in k3["证据"]


if __name__ == "__main__":
    test_k5_keeps_gap_caveat(); test_k3_follows_gp_verdict()
    print("test_cce_k1_readout_gap_disclosed: OK")
