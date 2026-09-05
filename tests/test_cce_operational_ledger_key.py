"""operational 账本必须用 **draw 序号**当主键, 不许拿温度值兜底。

## 这条闸为什么存在
2026-09-06 消融审计实测出的 fail-silent:
`_op_summary` 此前写 `by_t.setdefault(a["temperature"], []).append(a)`,
用**温度值**当 draw 主键。温度一旦重复(阶梯被截短 / k 超出阶梯长度而补出重复值 /
有意同温重复采样), 多个 draw **塌成一个桶**:
  n_draws 3 → 1 · first_attempt_success 2 → 0 · rate 0.6667 → **0.0**
而**退出码正常、无任何告警**。8/8 确定性复现。

★ 这是本项目反复栽的那类坏法: **数字合理、闸全绿、账本已经错了。**
  它比归零更难发现 —— 归零至少会触发非退化闸, 这种不会。

★★ 而温度阶梯在这里成了**事实上的主键**, 代码里一个字都没说明。
   同一天的底噪 A/A 里, 若有人把阶梯改成同温重复(那正是 A/A 的标准做法),
   账本会静默算错而没人知道。
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import cce_knot_classify as KC  # noqa: E402


def _att(draw=None, temp=0.0, attempt=1, status="SUCCESS"):
    a = {"temperature": temp, "attempt": attempt, "status": status, "error_class": None}
    if draw is not None:
        a["draw"] = draw
    return a


def test_same_temperature_draws_do_not_collapse():
    """★ 三个 draw 全用同一个温度 —— 旧实现给 n_draws=1, 正确答案是 3。"""
    att = [_att(draw=i, temp=0.0) for i in range(3)]
    r = KC._op_summary(att)
    assert r["n_draws"] == 3, (
        f"★ 三个同温 draw 塌成了 {r['n_draws']} 个 —— 温度又被当成主键了"
    )
    assert r["first_attempt_success"] == 3
    assert r["first_attempt_success_rate"] == 1.0


def test_retries_within_one_draw_still_group():
    """同一个 draw 的多次重试仍应归成一桶 —— 修主键不能把重试也拆开。"""
    att = [_att(draw=0, attempt=1, status="INFRA_FAILED"),
           _att(draw=0, attempt=2, status="SUCCESS"),
           _att(draw=1, attempt=1, status="SUCCESS")]
    r = KC._op_summary(att)
    assert r["n_draws"] == 2, f"★ 重试被算成了独立 draw: n_draws={r['n_draws']}"
    # draw 0 的**首次**尝试失败了 ⇒ 只有 draw 1 算首次成功
    assert r["first_attempt_success"] == 1
    assert r["first_attempt_success_rate"] == 0.5


def test_missing_draw_key_produces_no_number_at_all():
    """★★ 缺主键时**不给数**, 而不是拿温度猜 —— 兜底正是那个 bug 的成因。

    「查不了」不许写成「查过了没问题」。
    """
    att = [_att(temp=0.0), _att(temp=0.0), _att(temp=0.0)]   # 无 draw 键
    r = KC._op_summary(att)
    assert r["n_draws"] is None, f"★ 缺 draw 序号却给出了 n_draws={r['n_draws']} —— 那是在猜"
    assert r["first_attempt_success"] is None
    assert r["first_attempt_success_rate"] is None
    assert "★ledger_degraded" in r and "draw" in r["★ledger_degraded"], \
        "★ 降级必须**显式说明**, 不能只是把字段留空"
    # 与 draw 无关的计数仍应正常产出 —— 降级要精确, 不是整块弃疗
    assert r["n_attempts"] == 3
    assert r["n_infra_failed"] == 0


def test_production_path_stamps_the_draw_index():
    """生产路径必须真的把 draw 序号写进 attempt —— 否则上面几条都白测。"""
    src = (ROOT / "scripts" / "cce_knot_classify.py").read_text(encoding="utf-8")
    assert 'attempts.append({"draw": i,' in src, \
        "★ one() 不再写入 draw 序号 ⇒ 生产账本会走进降级分支"
    assert "ex.map(one, list(enumerate(temps)))" in src, \
        "★ one() 的入参不再带序号 ⇒ draw 序号无从得来"


def _reverse_checks():
    """反向验证: 把旧的错法放回去, 闸必须判红。"""
    n = 0
    orig = KC._op_summary

    def old_impl(attempts):
        by_t = {}
        for a in attempts:
            by_t.setdefault(a["temperature"], []).append(a)
        first_ok = sum(1 for v in by_t.values() if v[0]["status"] in ("SUCCESS", "ABSTAIN"))
        return {"attempts": attempts, "n_attempts": len(attempts), "n_draws": len(by_t),
                "first_attempt_success": first_ok,
                "first_attempt_success_rate": round(first_ok / len(by_t), 4) if by_t else None,
                "n_infra_failed": 0, "n_parse_failed": 0}

    KC._op_summary = old_impl
    try:
        for fn in (test_same_temperature_draws_do_not_collapse,
                   test_missing_draw_key_produces_no_number_at_all):
            try:
                fn()
                raise SystemExit(f"★ 反向验证失败: 换回温度当主键后 {fn.__name__} 仍绿")
            except AssertionError:
                n += 1
        # 旧实现在**温度互异**时恰好也对 —— 这正是它能潜伏这么久的原因, 记在这里
        att = [_att(draw=i, temp=t) for i, t in enumerate([0.0, 0.3, 0.6])]
        assert old_impl(att)["n_draws"] == 3, \
            "旧实现在温度互异时应当也对(它就是这样躲过所有测试的)"
    finally:
        KC._op_summary = orig
    return n


if __name__ == "__main__":
    test_same_temperature_draws_do_not_collapse()
    test_retries_within_one_draw_still_group()
    test_missing_draw_key_produces_no_number_at_all()
    test_production_path_stamps_the_draw_index()
    n = _reverse_checks()
    print("test_cce_operational_ledger_key: OK ("
          "同温三 draw 不塌桶(旧实现给 1) | 同 draw 的重试仍归一桶 | "
          "缺 draw 序号则 n_draws/first_ok 全为 None 且显式标 ★ledger_degraded | "
          "生产路径确实写入 draw 序号 | "
          f"{n} 条反向验证判红, 且已确认旧实现在温度互异时也对 —— 那正是它潜伏至今的原因)")
