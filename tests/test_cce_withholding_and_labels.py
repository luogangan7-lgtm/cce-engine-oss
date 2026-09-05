"""三条消融审计缺陷的闸: 扣发记录不许消失 · 制备身份不许自相矛盾 · 标签不许在浮点噪声上翻。

## ④ 扣发记录消失(cce_full_run 出口闸)
`for name, val in (s1m.get("tops") or {}).items():` —— `tops` 为 `{}` 时(k<2 判 WITHHOLD、
s1 弃权、全部失败)循环体**一次都不执行** ⇒ 四条扣发记录**既不进 usable 也不进 withheld,
直接消失**。而 s1 manifest 里明明写着 `tops_withheld="all(insufficient_replicates)"`。
★ 这与出口闸自己的立意直接相反:「withheld 不是弱证据, 是**没有读数**」——
  一条没被记为 withheld 的缺席, 下游读到的是**什么都没发生**。
★ 顺带遮住了一个 AttributeError: `tops_withheld` 有 dict 与 str 两种形状,
  旧代码只按 dict 取; 真走到 str 分支会崩 —— 被「循环不执行」一直遮着。

## ⑤ preparation_id 兜底 ⇒ 同一份读数自相矛盾
两个生产调用点都不传 `preparation_id` ⇒ 兜底成 `RAW_PREPARATION_ID`,
而 stage1 同一份读数里记的是真实制备 id。**22/22 存量读数自相矛盾**,
且把同一制备打成两个 measurement_procedure_id。

## ⑨ top_label 打平时按索引取胜 ⇒ 换个排列就换标签
消融审计实测: archive/33748217410 的 need 层, 归档取 N06、重算取 N02,
而整条 need_vec 与 within_js 到 12 位小数完全相同。
★★ 审计把机制描述成「相差 1 ULP」, **那是错的** —— 它引的两个十进制串
(0.2833333333333333 与 0.28333333333333334)解析成**同一个 double**。
真实机制是 **精确打平**: `max(range(n), key=lambda j: vec[j])` 取**首个**最大索引,
而索引序依赖 keys 的排列 ⇒ 换实现/换排列就换标签。
★ 这个更正由本文件的**反向验证**抓出: 注入旧实现后断言仍绿, 查下去发现夹具没构造出差异。
标签是 s1 四层 top 的来源, 一路吃到 s2 配对。
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import cce_full_run as F                    # noqa: E402
import cce_knot_classify as KC              # noqa: E402
from exp_v4_full_validation import top_label  # noqa: E402

KEYS = ["N02", "N06", "N09"]


# ── ⑨ ─────────────────────────────────────────────────────────────────────
def test_one_ulp_does_not_flip_the_label():
    """★★ 2026-09-06 更正: 消融审计把这条缺陷描述成「1 ULP 之差换标签」,
    并引了 archive 里那两个字面量 0.2833333333333333 与 0.28333333333333334。
    **那两个十进制串解析成同一个 double**(差恰为 0.0) —— 它们不是 1 ULP。
    ⇒ **真实机制不是浮点漂移, 是精确打平按索引取胜**(见下一条),
      而索引序依赖 keys 的排列 ⇒ 换个实现/换个排列就换标签。
    ★ 这个更正是本文件的**反向验证抓出来的**: 注入旧实现后断言仍绿,
      查下去发现夹具根本没构造出差异。差点发出一条测不了它宣称之事的闸。

    本条改用 math.nextafter 构造**真正的** 1 ULP 对, 作为防御性覆盖:
    取整(round 到 9 位)本来就该吃掉这一级差异。
    """
    import math
    x = 0.2833333333333333
    y = math.nextafter(x, 1.0)
    assert y != x and abs(y - x) > 0, "★ 夹具没构造出真实的 ULP 差"
    assert top_label([x, y, 0.1], KEYS) == top_label([y, x, 0.1], KEYS), (
        f"★ 1 ULP 之差翻了标签: {top_label([x, y, 0.1], KEYS)} vs "
        f"{top_label([y, x, 0.1], KEYS)}"
    )


def test_tie_is_broken_by_label_name_not_index():
    """打平按标签名, 不按索引 —— 否则结果依赖 keys 的排列顺序。"""
    vec = [0.5, 0.5, 0.1]
    assert top_label(vec, ["N06", "N02", "N09"]) == "N02", "★ 打平应取名序最小"
    # 换个排列, 结论必须一样
    assert top_label([0.5, 0.1, 0.5], ["N06", "N09", "N02"]) == "N02", \
        "★ 结果依赖 keys 排列 ⇒ 跨实现不可复现"


def test_degenerate_inputs_unchanged():
    assert top_label([], KEYS) is None
    assert top_label([0.0, 0.0, 0.0], KEYS) == "N02"   # 调用侧另有 sum>0 守卫


# ── ④ ─────────────────────────────────────────────────────────────────────
def _withheld_for(s1m):
    """复刻出口闸里那段逻辑的输入→输出, 只测这一段。"""
    usable, withheld = {}, {}
    _tops, _wh = s1m.get("tops"), s1m.get("tops_withheld")

    def _reason(name, default):
        if isinstance(_wh, dict):
            return _wh.get(name, default)
        return _wh if isinstance(_wh, str) and _wh else default

    if _tops:
        for name, val in _tops.items():
            (usable if val is not None else withheld)[f"s1.tops.{name}"] = (
                val if val is not None else _reason(name, "超噪声底"))
    else:
        why = (_wh if isinstance(_wh, str) and _wh else None) or (
            f"s1 未产出 tops(measurement_status={s1m.get('measurement_status')!r}, "
            f"n={s1m.get('n')!r})")
        for name in F._LAYER_OF_TOP:
            withheld[f"s1.tops.{name}"] = why
    return usable, withheld


def test_empty_tops_records_four_withholdings_not_zero():
    """★ 核心: tops 为空时, 四层**一条不少**地记为扣发。"""
    u, w = _withheld_for({"tops": {}, "tops_withheld": "all(insufficient_replicates)",
                          "measurement_status": "insufficient_replicates", "n": 1})
    assert len(w) == 4, f"★ 只记了 {len(w)} 条扣发, 应为 4 —— 记录又消失了"
    assert not u
    assert all(v == "all(insufficient_replicates)" for v in w.values()), \
        "★ 扣发理由丢了 —— 必须写明**为什么没有**"


def test_empty_tops_with_no_reason_still_records_something_checkable():
    u, w = _withheld_for({"tops": {}, "tops_withheld": None,
                          "measurement_status": "abstain", "n": 0})
    assert len(w) == 4
    assert "abstain" in list(w.values())[0], "★ 没有现成理由时也要给出可核的状态"


def test_string_shaped_tops_withheld_does_not_crash():
    """旧代码对 str 形状的 tops_withheld 会 AttributeError —— 被上一个 bug 遮着。"""
    u, w = _withheld_for({"tops": {"desire": None, "need": "N02"},
                          "tops_withheld": "all(insufficient_replicates)"})
    assert w["s1.tops.desire"] == "all(insufficient_replicates)"
    assert u["s1.tops.need"] == "N02"


def test_production_path_has_the_else_branch():
    src = (ROOT / "scripts" / "cce_full_run.py").read_text(encoding="utf-8")
    assert "for name in _LAYER_OF_TOP:" in src, \
        "★ 出口闸里没有 tops 为空时的 else 分支 ⇒ 扣发记录会再次消失"


# ── ⑤ ─────────────────────────────────────────────────────────────────────
def test_preparation_id_is_passed_at_both_production_sites():
    src = (ROOT / "scripts" / "cce_knot_classify.py").read_text(encoding="utf-8")
    n = src.count('preparation_id=s1.get("preparation_id")')
    assert n == 2, f"★ 只有 {n} 个生产调用点传了 preparation_id, 应为 2"


def test_preparation_id_actually_reaches_the_identity():
    """传进去要真的改变 measurement_procedure_id, 否则这个形参是装饰。"""
    import json
    taxo = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))
    kw = dict(k=3, knot_n=5, s1_pairing="round_robin_over_3_s1_draws")
    a = KC.instrument_id(taxo, **kw)
    b = KC.instrument_id(taxo, preparation_id="prep_deadbeef", **kw)
    assert a["preparation_id"] != b["preparation_id"]
    assert a["measurement_procedure_id"] != b["measurement_procedure_id"], \
        "★ 换制备不换 measurement_procedure_id ⇒ 制备身份没有进入联合身份"
    assert a["instrument_hash"] == b["instrument_hash"], \
        "★ 制备不该改变**仪器**指纹 —— 那是两个身份"


def _reverse_checks():
    n = 0
    # ① 退回「循环不执行就什么都不记」⇒ 必须红
    def broken(s1m):
        u, w = {}, {}
        for name, val in (s1m.get("tops") or {}).items():
            (u if val is not None else w)[f"s1.tops.{name}"] = val or "超噪声底"
        return u, w
    g = globals()
    orig = g["_withheld_for"]
    g["_withheld_for"] = broken
    try:
        for fn in (test_empty_tops_records_four_withholdings_not_zero,
                   test_empty_tops_with_no_reason_still_records_something_checkable):
            try:
                fn()
                raise SystemExit(f"★ 反向验证失败: 退回旧逻辑后 {fn.__name__} 仍绿")
            except AssertionError:
                n += 1
    finally:
        g["_withheld_for"] = orig

    # ② 退回索引取胜的 top_label ⇒ 必须红
    import exp_v4_full_validation as V
    saved = V.top_label
    g2 = globals()
    old_tl = saved
    g2["top_label"] = lambda vec, keys, _n=9: (
        keys[max(range(len(vec)), key=lambda j: vec[j])] if vec else None)
    try:
        for fn in (test_one_ulp_does_not_flip_the_label,
                   test_tie_is_broken_by_label_name_not_index):
            try:
                fn()
                raise SystemExit(f"★ 反向验证失败: 退回索引取胜后 {fn.__name__} 仍绿")
            except AssertionError:
                n += 1
    finally:
        g2["top_label"] = old_tl
    return n


if __name__ == "__main__":
    test_one_ulp_does_not_flip_the_label()
    test_tie_is_broken_by_label_name_not_index()
    test_degenerate_inputs_unchanged()
    test_empty_tops_records_four_withholdings_not_zero()
    test_empty_tops_with_no_reason_still_records_something_checkable()
    test_string_shaped_tops_withheld_does_not_crash()
    test_production_path_has_the_else_branch()
    test_preparation_id_is_passed_at_both_production_sites()
    test_preparation_id_actually_reaches_the_identity()
    n = _reverse_checks()
    print("test_cce_withholding_and_labels: OK ("
          "空 tops 记满 4 条扣发且带理由(旧实现记 0 条) | str 形状的 tops_withheld 不再崩 | "
          "preparation_id 两个生产调用点都传且真的改变 measurement_procedure_id(不改仪器指纹) | "
          "1 ULP 不翻标签 · 打平按名序不按索引 | "
          f"{n} 条反向验证: 退回「记录消失」与「索引取胜」各自判红)")
