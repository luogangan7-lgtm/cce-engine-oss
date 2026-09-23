"""★★★ JS 这条硬判据线的**度量定义**必须被固定向量钉住。零 API。

## 为什么
`mean_JS <= 0.25` 是 G-K1 的判决线之一, 而「JS」这三个字在实现上有两个岔口:
① **散度 vs 距离**: SciPy 的 `scipy.spatial.distance.jensenshannon` 返回的是**平方根**(距离),
   不是散度。实测差别不小: 0.7/0.3 vs 0.3/0.7 的 divergence 是 **0.1187**, 距离是 **0.3445**
   —— 同一条 0.25 线, 一个过一个不过。
② **两份实现**: 生产用 `exp_crossmodel_desire.js_divergence`(吃**列表**),
   闸用 `run_gates.js_div`(吃**字典**)。本仓栽过「两份实现悄悄漂移」。

⇒ 本闸做三件: 固定向量对答案 · 两份实现逐位比对 · 钉住「不是 sqrt」。

## ★★ 还必须记住的一条(本闸只登记, 不判红)
闸的分布是**截断到 top-3(且每个 >=0.1)再归一化**的; 生产的是完整九维。
⇒ **同一个 0.25 在两边不是同一件事**: 截断会在标注者选了不同 top-3 时**系统性抬高** JS,
   在选同一组时**压低**它。这不是 bug, 是这条线的**含义依赖于截断规则** ——
   引用「JS <= 0.25」时必须连着说清楚是在哪种分布上算的。
"""
import math
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
os.environ.setdefault("MINIMAX_API_KEY", "ZERO_API_TEST_SENTINEL_NOT_A_KEY")
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "accuracy"))

# ★ 固定向量与期望值 —— 手算可复核(log 底为 2, 故 ∈[0,1])
VECTORS = [
    ("完全相同",           {"a": 1.0},            {"a": 1.0},             0.0),
    ("不相交的点质量",      {"a": 1.0},            {"b": 1.0},             1.0),
    ("点 vs 均分二元",      {"a": 1.0},            {"a": .5, "b": .5},     0.311278),
    ("0.7/0.3 vs 0.3/0.7", {"a": .7, "b": .3},    {"a": .3, "b": .7},     0.118709),
    ("★退化面板 50/50",     {"a": .5, "b": .5},    {"a": .5, "b": .5},     0.0),
]


def _impls():
    import run_gates as RG
    from exp_crossmodel_desire import js_divergence
    keys = list(RG.KNOTS)
    return RG.js_div, js_divergence, keys


def _named(d, keys):
    return {(keys[0] if k == "a" else keys[1]): v for k, v in d.items()}


def test_fixed_vectors_hit_the_expected_values():
    """★ 度量的**数值定义**被固定向量钉住 —— 换了底数/公式/归一化都会红。"""
    gate, _, keys = _impls()
    for name, p, q, want in VECTORS:
        got = gate(_named(p, keys), _named(q, keys))
        assert abs(got - want) < 1e-6, f"★★★ 「{name}」现算 {got:.6f} != 期望 {want} —— JS 的定义变了"


def test_the_two_implementations_agree_bit_for_bit():
    """★★ 生产(列表)与闸(字典)两份实现必须逐位一致 —— 本仓栽过「两份实现悄悄漂移」。"""
    gate, prod, keys = _impls()
    for name, p, q, _ in VECTORS:
        pk, qk = _named(p, keys), _named(q, keys)
        a = gate(pk, qk)
        b = prod([pk.get(k, 0.0) for k in keys], [qk.get(k, 0.0) for k in keys])
        assert abs(a - b) < 1e-12, f"★★★ 「{name}」两份实现不一致: 闸 {a} vs 生产 {b}"


def test_it_is_the_divergence_not_the_sqrt_distance():
    """★★★ 若哪天有人换成 SciPy 的 jensenshannon(返回**平方根**), 0.25 这条线的含义就变了。"""
    gate, _, keys = _impls()
    p, q = _named({"a": .7, "b": .3}, keys), _named({"a": .3, "b": .7}, keys)
    d = gate(p, q)
    assert abs(d - 0.118709) < 1e-6, "★ 数值变了"
    assert abs(math.sqrt(d) - 0.344542) < 1e-6
    assert d < 0.25 < math.sqrt(d), (
        "★★★ 这一对**恰好跨在 0.25 两侧**: 散度 0.1187 过线, 距离 0.3445 不过。"
        "⇒ 换成距离会让判据在**不改一个阈值数字**的情况下变严。本条就是防这个。")


def test_the_truncation_dependence_is_written_down():
    """★★ 闸的分布是截断到 top-3 再归一化的 ⇒ 0.25 的含义依赖截断规则。这条必须留档。"""
    src = (ROOT / "tests" / "test_cce_js_metric_definition.py").read_text(encoding="utf-8")
    assert "截断到 top-3" in src and "含义依赖于截断规则" in src, "★ 截断依赖性的说明不见了"
    import run_gates as RG
    assert "最多3个" in RG.DIST_TMPL and ">=0.1" in RG.DIST_TMPL, \
        "★ 闸 prompt 的截断规则变了 —— 0.25 的含义随之改变, 请复核本闸的说明"


def _reverse_checks():
    n = 0
    import run_gates as RG
    real = RG.js_div

    # ① 换成 sqrt(距离) ⇒ 红
    RG.js_div = lambda p, q: math.sqrt(real(p, q))
    try:
        test_fixed_vectors_hit_the_expected_values()
        raise SystemExit("★ 反向验证失败: 换成距离后仍绿")
    except AssertionError:
        n += 1
    finally:
        RG.js_div = real

    # ② 换成自然对数底 ⇒ 红
    RG.js_div = lambda p, q: real(p, q) * math.log(2)
    try:
        test_fixed_vectors_hit_the_expected_values()
        raise SystemExit("★ 反向验证失败: 换底后仍绿")
    except AssertionError:
        n += 1
    finally:
        RG.js_div = real

    # ③ 两份实现漂移 ⇒ 红
    RG.js_div = lambda p, q: real(p, q) + 1e-6
    try:
        test_the_two_implementations_agree_bit_for_bit()
        raise SystemExit("★ 反向验证失败: 两份实现漂移后仍绿")
    except AssertionError:
        n += 1
    finally:
        RG.js_div = real
    return n


if __name__ == "__main__":
    test_fixed_vectors_hit_the_expected_values()
    test_the_two_implementations_agree_bit_for_bit()
    test_it_is_the_divergence_not_the_sqrt_distance()
    test_the_truncation_dependence_is_written_down()
    n = _reverse_checks()
    print(f"test_cce_js_metric_definition: OK ("
          f"{len(VECTORS)} 个固定向量对上期望值(log2 散度, ∈[0,1]) | "
          f"★★生产(列表) 与 闸(字典) **两份实现逐位一致** | "
          f"★★★钉住「是散度不是 sqrt 距离」—— 0.7/0.3 那一对散度 0.1187 过线、距离 0.3445 不过, "
          f"换实现会**不改阈值数字就把判据变严** | 闸的 top-3 截断依赖已留档 | "
          f"{n} 条反向验证判红(换 sqrt / 换底 / 两实现漂移))")
