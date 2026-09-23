#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闸: accuracy/ 的离线隔离与五种失效定向测试 —— **现跑, 不读留档**。

★ 「判断仪器准不准的那道闸」两轮审计都没测过它自己(零 API 纪律结构性排除)。
  本测试是那块空白的第一批填充。**它只填「离线软件验证」这一层。**
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "probes"))
import accuracy_offline_harness as H   # noqa: E402
import accuracy_directed_tests as T    # noqa: E402


def test_harness_loads_without_a_real_key_and_sets_env_before_import():
    """★ GPT: **不要在测试文件顶层先导入目标模块, 再期待函数级 fixture 补环境变量。**"""
    src = (ROOT / "probes/accuracy_offline_harness.py").read_text(encoding="utf-8")
    assert "先设环境, 再 import" in src
    # 顶层不得直接 import run_gates
    assert "import run_gates" not in src.split("def load")[0], \
        "★ 装置顶层直接导入了被测模块 —— 那正是 GPT 点名的反模式"
    m = H.load()
    assert hasattr(m, "annot_dist") and hasattr(m, "admit_annotators")


def test_patch_point_is_where_the_code_actually_looks_it_up():
    """★ GPT: **替换对象必须位于被测代码实际查找它的命名空间。**
    run_gates 写 `import urllib.request` 后 `urllib.request.urlopen(...)`
    ⇒ 模块里**不存在** `urlopen` 这个名字, 替它是「看似 mock 了实际没替成功」。"""
    rg = (ROOT / "accuracy/run_gates.py").read_text(encoding="utf-8")
    assert "import urllib.request" in rg and "urllib.request.urlopen(" in rg
    m = H.load()
    assert not hasattr(m, "urlopen"), "★ 若模块里有 urlopen 这个名字, 替换点要重判"
    seen = {}
    def _resp(md, p):                      # ★ 原来写成 setdefault(...) or "..." —— setdefault 返回 True
        seen["hit"] = True                 #   会短路掉 or 右边, 返回 True 而不是 JSON。闸如实判红了。
        return '{"knots":[{"key":"itch","weight":1}]}'
    m2 = H.load(responses=_resp)
    _id, d = m2.annot_dist(("MiniMax-M3", {"id": "x", "b": "t"}))
    assert seen.get("hit") and d == {"itch": 1.0}, "★ 替换没生效 —— 说明替错了命名空间"


def test_tripwire_states_its_scope_and_is_not_overclaimed():
    """★ GPT: socket 拦截**只控制指定库**, 不能当成「全进程所有网络出口都已关闭」的证明。"""
    m = H.load()
    s = m._OFFLINE_TRIPWIRE.scope
    assert "不覆盖" in s and "子进程" in s and "C 扩展" in s, "★ 作用域被夸大了"
    assert m._OFFLINE_TRIPWIRE.tripped == [], "★ 绊线被触发 ⇒ 有真实连接尝试"


def test_tripwire_actually_fires_on_a_real_connect():
    """★ 反向: 绊线必须真的会响, 否则「未触发」毫无意义。"""
    import socket
    with H._Tripwire() as tw:
        try:
            socket.socket().connect(("127.0.0.1", 9))
            raise AssertionError("★ 绊线没响 —— 它是摆设")
        except H.NetworkTripwire:
            pass
    assert tw.tripped, "★ 触发记录为空"


def test_all_five_failure_modes_pass_computed_now():
    r = T.build()
    bad = {k: v["判"] for k, v in r["五种失效"].items() if v["判"] != "PASS"}
    assert not bad, f"★ 未通过: {bad}"
    assert len(r["五种失效"]) == 5
    # ★ ⑤ 必须在 —— 一个永远拒绝的闸同样能通过全部负例
    assert "⑤合法基线被一律拒绝" in r["五种失效"]
    return r


def test_mutants_are_caught_and_invalid_ones_are_not_counted():
    """★★★ GPT: 因**语法错误或导入失败**而红, **不算**检出。"""
    r = T.build()
    for row in r["变异检定"]:
        assert row["★判"].startswith("PASS(检出)"), f"★ {row['id']}: {row['★判']}"
        assert row["变异版确实走到目标路径"] is True, f"★ {row['id']} 没走到目标路径"
        assert row["源码确实被改动"] is True, f"★ {row['id']} 源码没被改 —— 锚点失效"
    src = (ROOT / "probes/accuracy_directed_tests.py").read_text(encoding="utf-8")
    assert "不计为检出" in src, "★ 「变异无效不计为检出」的规则没写进代码"
    return len(r["变异检定"])


def test_reverse_a_broken_anchor_is_reported_as_invalid_not_as_caught():
    """★ 反向: 锚点找不到时必须判「变异无效」, 不许默默当成检出。"""
    try:
        H.load(source_mutator=lambda s: (_ for _ in ()).throw(
            AssertionError("★ 变异锚点不在源码里 —— 变异**无效**, 不计为检出")))
        raise AssertionError("★ 锚点失效没有报错")
    except AssertionError as e:
        assert "不计为检出" in str(e)


def test_conclusion_scope_matches_the_substitution_boundary():
    """★★★ GPT: **证据范围必须与替换边界一致。**"""
    r = T.build()
    assert "离线软件验证" in r["★★★据此能支持的结论"]
    assert "不能**证明真实模型的语义判断准确率" in r["★★★据此能支持的结论"]
    for x in ("真实 provider 的语义判断准确率", "真实 provider 的重复稳定性"):
        assert any(x in y for y in r["★仍未验证的"]), f"★ 未验证清单缺: {x}"
    assert "一条都没用" in r["★★不许"], "★ 必须声明没把撤销的八条当金标塞回来"


def test_repo_files_untouched_by_mutation():
    """★ 变异是**内存字符串替换**, 仓里文件必须一字不改。"""
    before = (ROOT / "accuracy/run_gates.py").read_text(encoding="utf-8")
    H.load(source_mutator=lambda s: s.replace('    if not of:', '    if False:', 1))
    after = (ROOT / "accuracy/run_gates.py").read_text(encoding="utf-8")
    assert before == after, "★★★ 变异改到了仓里的文件"


if __name__ == "__main__":
    test_harness_loads_without_a_real_key_and_sets_env_before_import()
    test_patch_point_is_where_the_code_actually_looks_it_up()
    test_tripwire_states_its_scope_and_is_not_overclaimed()
    test_tripwire_actually_fires_on_a_real_connect()
    r = test_all_five_failure_modes_pass_computed_now()
    nm = test_mutants_are_caught_and_invalid_ones_are_not_counted()
    test_reverse_a_broken_anchor_is_reported_as_invalid_not_as_caught()
    test_conclusion_scope_matches_the_substitution_boundary()
    test_repo_files_untouched_by_mutation()
    print("test_cce_accuracy_offline: OK ("
          "★★★两轮审计**结构性排除**的 accuracy/ 现在可测了: **先设环境再 import**, "
          "替换点是 `urllib.request.urlopen`(**被测代码调用时实际查找的那个名字**; 模块里没有 `urlopen` 可替) | "
          "★五种失效**全过**: 缺必需规则当场 KeyError · of=0 判 NOT_EXAMINED 并扣发整轮 · "
          "解析失败五种形态**全返回 None** · 零/一/全不合格**都不回退全员** · "
          "**合法基线仍被接纳**(UNRESOLVED 留在 primary) | "
          f"★{nm}/{nm} 变异**全被检出**, 且每个都确认「**确实走到目标路径**」—— "
          "因语法错/导入失败而红的**判变异无效, 不计为检出** | "
          "★绊线**如实写作用域**(不覆盖子进程/C 扩展/已建连接), 且反向验过它真的会响 | "
          "★变异是**内存替换**, 仓里文件一字未改 | "
          "★★★结论范围与替换边界一致: 只支持**对这份闸实现的离线软件验证**, "
          "**不能**证明真实模型的准确率或重复稳定性)")
