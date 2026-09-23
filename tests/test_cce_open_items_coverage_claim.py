#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闸: 清单里关于「覆盖」的**计数断言必须现算**, 不许口述。

★★★ 为什么建它(2026-09-14, 抓到的是我自己):
我在 `cce_open_items.py` 里写过「维持撤销的那 2 个用例仍**零覆盖**」——
**那是假的**。实测 C_明确放弃_0/1 各有 **5 条已裁定断言**, 只有 display 那条被撤,
是**部分覆盖 5/6**。

★★ 更要紧的是: 我当天刚给那一节建了**结构闸**(要求「仍未做」列够项数、不许空占位),
   它**没抓到这句假话** —— **结构闸查形状, 不查真假**。这是结构判据的诚实边界,
   不是它的缺陷; 缺的是**另一种**闸。本文件就是那一种。
"""
import collections
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
A = json.loads((ROOT / "tests/data/local_contract_assertions_v2.json").read_text(encoding="utf-8"))


def _coverage():
    per = collections.defaultdict(lambda: {"总": 0, "已裁定": 0})
    for a in A["断言"]:
        per[a["用例"]]["总"] += 1
        if a["★★★断言状态"] == "已裁定":
            per[a["用例"]]["已裁定"] += 1
    zero = sorted(c for c, v in per.items() if v["已裁定"] == 0)
    partial = sorted((c, v["已裁定"], v["总"]) for c, v in per.items()
                     if 0 < v["已裁定"] < v["总"])
    full = sorted(c for c, v in per.items() if v["已裁定"] == v["总"])
    return zero, partial, full


def _list_text():
    r = subprocess.run([sys.executable, str(ROOT / "scripts/cce_open_items.py")],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, "★ 清单跑不起来:\n%s" % r.stderr[-600:]
    return r.stdout


def test_no_case_with_assertions_is_called_zero_coverage():
    """★★★ 核心: 一个**有已裁定断言**的用例, 不许在清单里被说成「零覆盖」。"""
    zero, partial, _ = _coverage()
    txt = _list_text()
    named_zero = set()
    for m in re.finditer(r"(C_[^\s，,。、)）]+)[^。]{0,40}零覆盖", txt):
        named_zero.add(m.group(1))
    wrong = sorted(named_zero - set(zero))
    assert not wrong, (
        "★★★ 清单把这些**有已裁定断言**的用例说成了「零覆盖」: %r\n"
        "  实际覆盖: %r\n"
        "  —— 这正是 2026-09-14 抓到的那句假话的形状(我自己写的)。" % (wrong, partial))
    return zero, partial


def test_the_partial_coverage_is_stated_with_its_real_number():
    """★★ 部分覆盖必须报**真实比例**, 不许含糊成「零」或「有」。"""
    _, partial, _ = _coverage()
    if not partial:
        return None
    txt = _list_text()
    for case, ok, tot in partial:
        assert "%d/%d" % (ok, tot) in txt or ("%d 条已裁定" % ok) in txt, (
            "★★ %s 是部分覆盖(%d/%d), 清单里没有报出这个数 —— "
            "「部分」不报数就等于没说" % (case, ok, tot))
    return partial


def test_the_undecided_list_is_the_real_zero_coverage_set():
    """★ 真正零覆盖的应当是 `未裁定用例` 那一组 —— 两处口径必须一致。"""
    zero, _, _ = _coverage()
    declared = set(A.get("未裁定用例") or [])
    # 未裁定用例本来就不在断言表里 ⇒ 它们在 _coverage() 里根本不出现, 这才是对的
    assert not (set(zero) & declared) or set(zero) <= declared, (
        "★ 零覆盖集合 %r 与 未裁定用例 %r 口径对不上" % (zero, sorted(declared)))
    assert declared, "★ 未裁定用例列表空了 —— 那 10 条去哪了?"
    return sorted(declared)


def test_this_gate_catches_what_the_structural_gate_cannot():
    """★★★ 自证: 把一句假的「零覆盖」塞进清单文本, 本闸必须判红。

    (结构闸查的是「有没有列够项」, 它对这句假话是**结构上**看不见的。)
    """
    zero, partial, _ = _coverage()
    assert partial, "★ 现在没有部分覆盖的用例 —— 本自证失去对象, 请换一个"
    fake = "%s ... 仍**零覆盖**" % partial[0][0]
    named = set(re.findall(r"(C_[^\s，,。、)）]+)[^。]{0,40}零覆盖", fake))
    assert named and not (named <= set(zero)), (
        "★★★ 本闸的判据抓不到「把部分覆盖说成零覆盖」这句假话 —— 那它就没有存在的意义")


if __name__ == "__main__":
    zero, partial = test_no_case_with_assertions_is_called_zero_coverage()
    p = test_the_partial_coverage_is_stated_with_its_real_number()
    und = test_the_undecided_list_is_the_real_zero_coverage_set()
    test_this_gate_catches_what_the_structural_gate_cannot()
    print("test_cce_open_items_coverage_claim: OK ("
          f"★★★建它是因为**抓到了我自己**: 我在清单里写过「维持撤销的那 2 个用例仍**零覆盖**」——**那是假的**, "
          f"实测它们各有 5 条已裁定断言, 是**部分覆盖 {partial[0][1]}/{partial[0][2]}** | "
          "★★更要紧: 我当天刚给那一节建的**结构闸**(要求列够项数、不许空占位)**没抓到这句假话** —— "
          "**结构闸查形状, 不查真假**。那是结构判据的诚实边界, 不是缺陷; 缺的是**另一种**闸, 本文件就是那一种 | "
          f"★真·零覆盖 {len(zero)} 个 · 部分覆盖 {len(partial)} 个(必须报出真实比例, 「部分」不报数等于没说) · "
          f"未裁定用例 {len(und)} 条(那才是真正没有任何断言的一组) | "
          "★自证: 把「把部分覆盖说成零覆盖」这句假话喂给本闸的判据, 它必须能认出来)")
