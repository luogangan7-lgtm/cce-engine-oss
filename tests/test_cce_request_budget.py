#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闸: 跨轮请求预算闸自己有没有检定力。**全用假请求, 零真实调用。**"""
import json, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import cce_request_budget as B  # noqa: E402


def test_all_six_offline_checks_pass():
    r = B.selftest()
    bad = [k for k, v in r.items() if not k.startswith("★并发实际") and v is not True]
    assert not bad, f"★ 未通过: {bad}"
    assert r["★并发实际放行"] == 10, "★ 并发放行数不等于上限 —— 原子预留失效"
    return r


def test_the_four_forbidden_moves_are_actually_blocked():
    """★★★ GPT 明令禁止四件事。其中「改大旧上限」是**代码能拦**的, 必须真拦住。"""
    import tempfile, shutil
    tmp = pathlib.Path(tempfile.mkdtemp()); keep, B.STATE = B.STATE, tmp / "s.json"
    try:
        B.reserve("X", 5, 1)
        try:
            B.reserve("X", 50, 1); raise AssertionError("★ 改大旧上限没被拦")
        except B.BudgetExceeded as e:
            assert "改大旧上限" in str(e) and "新开一张授权单" in str(e)
        # ★ 另外三件(重置计数/回填日期/宣布可继续)是**流程约束**, 代码拦不住 ⇒ 必须写在文案里
        src = (ROOT / "scripts/cce_request_budget.py").read_text(encoding="utf-8")
        for f in ("重置已用计数", "回填授权日期", "代码补好了所以可以继续"):
            assert f in src, f"★ 禁止项 {f} 没写进文件 —— 代码拦不住的必须写下来"
    finally:
        B.STATE = keep; shutil.rmtree(tmp, ignore_errors=True)


def test_it_declares_it_does_not_restore_authorization():
    """★★★ 最重要的一条: 补闸**不产生放行资格**。这句必须在, 且必须显眼。"""
    src = (ROOT / "scripts/cce_request_budget.py").read_text(encoding="utf-8")
    assert "补这个闸**不等于**恢复放行" in src
    assert "不产生任何放行资格" in src


def test_failed_requests_are_counted():
    """★ GPT: 「已发出的失败请求不能因为没有有效结果就从『请求次数』中抹掉」。"""
    r = B.selftest()
    assert r["⑤失败请求仍计数"] is True


def test_it_wraps_the_outbound_call_not_a_wrapper_of_a_wrapper():
    """★ 反向: 闸必须包在**真正发请求**的那一层 —— 包错层则重试绕过它。
    构造一个「内部自己重试 3 次」的函数, 若闸包在外层, 计数会少算 2/3。"""
    import tempfile, shutil
    tmp = pathlib.Path(tempfile.mkdtemp()); keep, B.STATE = B.STATE, tmp / "s.json"
    try:
        sent = {"n": 0}
        def outbound():                      # ← 真正发请求的那一层
            sent["n"] += 1
        guarded = B.wrap(outbound, "L", 10, "layer")
        def retrying():                      # ← 上层的重试循环
            for _ in range(3):
                guarded()
        retrying()
        assert sent["n"] == 3 and B.status("L")["used"] == 3, \
            "★ 包对层时计数应等于真实发出数"
        # 反向: 若把闸包在**重试循环外面**, 3 次发出只会记 1 次
        sent2 = {"n": 0}
        def outbound2(): sent2["n"] += 1
        def retrying2():
            for _ in range(3): outbound2()
        wrong = B.wrap(retrying2, "W", 10, "wrong-layer")
        wrong()
        assert sent2["n"] == 3 and B.status("W")["used"] == 1, \
            "★ 反向构造失效 —— 包错层本应少算, 说明这个测试没有区分度"
    finally:
        B.STATE = keep; shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    r = test_all_six_offline_checks_pass()
    test_the_four_forbidden_moves_are_actually_blocked()
    test_it_declares_it_does_not_restore_authorization()
    test_failed_requests_are_counted()
    test_it_wraps_the_outbound_call_not_a_wrapper_of_a_wrapper()
    print("test_cce_request_budget: OK ("
          "★DEV-001 暴露的机制缺口已补: 跨轮上限从**只在文档里**变成**在代码里** | "
          "★六条离线自检全过(**全用假请求, 零真实调用**): 上限前放行 · 上限后拦住且**不产生调用** · "
          f"**重启不清零** · **四进程并发抢 10 个额度只放行 {r['★并发实际放行']} 个** · "
          "**失败请求仍计数** · **改大旧上限被拒** | "
          "★反向验过**包错层**: 闸包在重试循环外面时 3 次发出只记 1 次 ⇒ 必须包在真正发请求那一层 | "
          "★★★但补闸**不产生任何放行资格** —— 代码拦不住的另三件(重置计数/回填日期/宣布可继续)已写进文件)")
