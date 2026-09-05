"""打平时的结顺序必须**跨进程确定**。

## 这条闸为什么存在
`merged = sorted(keys, key=lambda k: -stability[k]["intensity"])` 里 `keys` 是一个
**str 集合**, 打平时 `sorted` 的相对顺序取决于集合迭代顺序, 而后者受
`PYTHONHASHSEED` 随机化影响。

★ 下游是 `knots[0]` → **`playbook_primary`** —— 整条链里唯一直接指挥「怎么写」的字段。
  intensity 是 0.05 网格上的中位数, **打平非常常见**。

★★ 库内 2026-08-18 已有实测记录: 同一输入连跑 6 次, `keys[0]` 得到
   display / display / audit / audit / display / audit,
   并写明「任何做 s2_knots 聚合的实现都必须遵守」显式 tie-break。
   **规则在库里躺了 19 天, 代码一直没改。** ⇒ 缺的不是知识, 是把知识变成闸的那一步。
   这条闸就是那一步。

## 它测的是**跨进程**, 不是同进程
同一个进程里 `PYTHONHASHSEED` 是固定的, 所以同进程重复跑**测不出这个 bug**。
必须开子进程并显式换 seed —— 这也是它躲过既有 99 个测试的原因。
"""
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

SEEDS = ["0", "1", "7", "42", "1337", "99991"]

# 三方完全打平 —— 最容易暴露顺序不确定的构型
_SNIPPET = (
    "import sys;sys.path.insert(0,'scripts');import cce_knot_classify as C;"
    "st={{'display':{{'intensity':0.5}},'audit':{{'intensity':0.5}},"
    "'belong':{{'intensity':0.5}},'reward':{{'intensity':0.5}}}};"
    "keys={{'display','audit','belong','reward'}};"
    "print(','.join({expr}))"
)
FIXED = _SNIPPET.format(expr="sorted(keys, key=lambda k: (-st[k]['intensity'], k))")
BROKEN = _SNIPPET.format(expr="sorted(keys, key=lambda k: -st[k]['intensity'])")


def _run_across_seeds(snippet):
    out = set()
    for seed in SEEDS:
        env = dict(os.environ, PYTHONHASHSEED=seed)
        r = subprocess.run([sys.executable, "-c", snippet], capture_output=True,
                           text=True, env=env, cwd=str(ROOT))
        assert r.returncode == 0, f"子进程失败(seed={seed}): {r.stderr[-300:]}"
        out.add(r.stdout.strip())
    return out


def test_tiebreak_is_deterministic_across_hash_seeds():
    """★ 四方打平, 6 个不同 PYTHONHASHSEED ⇒ 结果必须**只有一种**。"""
    got = _run_across_seeds(FIXED)
    assert len(got) == 1, (
        f"★ 打平顺序随 PYTHONHASHSEED 变: {sorted(got)} —— "
        "而 knots[0] 直接决定 playbook_primary(唯一指挥「怎么写」的字段)"
    )
    assert got == {"audit,belong,display,reward"}, f"打平应按 key 升序, 实为 {got}"


def test_production_sorts_all_carry_a_tiebreak():
    """源码里所有按数值降序的 sorted 都必须带 key 作次序 —— 漏一个就是同一个 bug。"""
    src = (ROOT / "scripts" / "cce_knot_classify.py").read_text(encoding="utf-8")
    bad = [ln.strip() for ln in src.split("\n")
           if "sorted(" in ln and "key=lambda" in ln
           and ("-x[1])" in ln or '"intensity"])' in ln or "['intensity'])" in ln)]
    assert not bad, (
        "★ 这些排序仍无 tie-break, 打平时顺序随进程变:\n  " + "\n  ".join(bad)
    )
    # 三处已知点位必须都改到
    assert 'key=lambda k: (-stability[k]["intensity"], k)' in src, "★ merged 的 tie-break 没了"
    assert "key=lambda x: (-x[1], x[0])" in src, "★ mem/intensity 的 tie-break 没了"
    assert src.count("key=lambda x: (-x[1], x[0])") >= 2, \
        f"★ 只找到 {src.count('key=lambda x: (-x[1], x[0])')} 处 (-x[1], x[0]), 预期 >=2"


def _reverse_checks():
    """★ 反向验证 —— 而且这一条必须**真的看见随机**, 否则闸只是装饰。

    注意: 无 tie-break 时不保证每个 seed 都不同, 只保证**存在**跨 seed 差异。
    若这里只得到一种结果, 说明这台机器上的构型碰巧不暴露 —— 那不能当作「已验证」,
    必须如实报告, 不许当成通过。
    """
    got = _run_across_seeds(BROKEN)
    if len(got) > 1:
        return True, f"{len(got)} 种不同顺序: {sorted(got)}"
    return False, (f"★ 本机上无 tie-break 版本在 {len(SEEDS)} 个 seed 下只得到一种顺序 {got} —— "
                   "**反向验证未能触发**。这不代表 bug 不存在(库内 2026-08-18 已实测到 6 次里翻 3 次), "
                   "只代表本次构型没暴露它。如实记录, 不当作已验证。")


if __name__ == "__main__":
    test_tiebreak_is_deterministic_across_hash_seeds()
    test_production_sorts_all_carry_a_tiebreak()
    fired, detail = _reverse_checks()
    print(f"test_cce_tiebreak_determinism: OK (四方打平在 {len(SEEDS)} 个 PYTHONHASHSEED 下"
          f"顺序唯一 | 源码三处 sorted 均带 tie-break | "
          f"反向验证{'已触发: ' + detail if fired else '★未触发 —— ' + detail})")
