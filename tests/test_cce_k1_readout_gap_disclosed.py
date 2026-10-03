"""K1 读数形式缺口(2026-10-03)不许静默消失: K1 判在 knots[0], 生产发布 top1_mode。

G-P 结果落地前, 生产状态表两格「结层 top-1」都必须带缺口说明; k=5 那格还得说明 G-P 不覆盖它。
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def test_top1_rows_disclose_readout_gap():
    if os.path.exists(os.path.join(ROOT, "tests/data/gate_gp_result.json")):
        return   # G-P 已出结果: 由结果更新本格, 届时改写此守卫
    import cce_production_status as P
    top1 = {r["组件"]: r["证据"] for r in P.rows() if r["组件"].startswith("结层 top-1")}
    assert len(top1) == 2
    for k, ev in top1.items():
        assert "knots[0]" in ev and "top1_mode" in ev, k
    assert "G-P 只覆盖 k=3" in top1["结层 top-1 @ outbound_post (k=5)"]


if __name__ == "__main__":
    test_top1_rows_disclose_readout_gap()
    print("test_cce_k1_readout_gap_disclosed: OK")
