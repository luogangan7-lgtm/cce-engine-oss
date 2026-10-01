#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""accuracy/run_gates.py main() 编排与 G-K2 链路的离线软件验证 —— 现算, 不信存盘。

守: ① 探针现算 == tests/data/accuracy_main_e2e_offline.json ② 7 臂的性质全真 ③ 5 条源码变异全被检出且源码真被改
    ④ 「事实抽取全断」那条崩法若被修好, 本闸红 —— 提醒同步改登记(不许登记与代码各说各话)。
★ 证据范围: 离线软件验证。不证明真实 provider 的语义准确率与重复稳定性(见 tests/data/accuracy_real_provider_prereg.json)。
反向: 每条断言都在做坏的副本上验过会红。零网络: socket 绊线(探针每臂另有自己的绊线)。
"""
import copy, json, pathlib, socket, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "probes"))
_TRIPPED = []
_orig = socket.socket.connect
def _guard(s, addr, *a, **k):
    _TRIPPED.append(addr)
    raise AssertionError("★★★ 离线隔离被突破: %r" % (addr,))
socket.socket.connect = _guard

import accuracy_main_e2e_offline as E  # noqa: E402

FRESH = json.loads(json.dumps(E.main(), ensure_ascii=False))
STORED = json.loads((ROOT / "tests/data/accuracy_main_e2e_offline.json").read_text(encoding="utf-8"))


def check_recomputed(f, s):
    assert f == s, "★ 现算与存盘不一致 —— run_gates 或探针变了, 重跑 probes/accuracy_main_e2e_offline.py 并复核"


def check_properties(f, s):
    bad = {arm: [k for k, v in p.items() if not v] for arm, p in f["properties"].items() if not all(p.values())}
    assert not bad, "★ 编排性质不成立: %r" % bad
    assert len(f["properties"]) == 7 and f["★all_properties_hold"] == {k: True for k in f["properties"]}


def check_mutations(f, s):
    for mid, m in f["mutations"].items():
        assert m["source_mutated"], "%s 源码没被改动 —— 空变异臂" % mid
        assert m["detected"] and m["properties_turned_false"], "%s 没被检出 —— 性质集有盲区" % mid
    assert len(f["mutations"]) == 5 and f["★all_mutations_detected"] is True


def check_outage_finding_current(f, s):
    o = f["★finding_fact_outage"]["observed"]
    assert o["exception"] == "IndexError" and o["raw_written"] and not o["gates_result_written"], (
        "★ 事实抽取全断那条崩法的现象变了(可能被修了): %r —— 同步改 ★finding_fact_outage 的登记" % o)


CHECKS = [check_recomputed, check_properties, check_mutations, check_outage_finding_current]


def _both(edit):
    def mk(f, s):
        f, s = copy.deepcopy(f), copy.deepcopy(s)
        edit(f); edit(s)
        return f, s
    return mk

REVERSE = [
    ("存盘被手改", lambda f, s: (f, {**copy.deepcopy(s), "written_at": "x"})),
    ("一条性质翻假", _both(lambda d: d["properties"]["D_全员被剔除"].__setitem__("扣发返回 2", False))),
    ("一条变异漏检", _both(lambda d: d["mutations"]["M5_overall不看G-K1"].__setitem__("detected", False))),
    ("空变异臂", _both(lambda d: d["mutations"]["M3_扣发返回0"].__setitem__("source_mutated", False))),
    ("崩法被修而登记没改", _both(lambda d: d["★finding_fact_outage"]["observed"].__setitem__("exception", None))),
]


def run():
    for fn in CHECKS:
        fn(FRESH, STORED)
    print("正向: %d 条断言全过" % len(CHECKS))
    for name, mk in REVERSE:
        f, s = mk(FRESH, STORED)
        try:
            for fn in CHECKS:
                fn(f, s)
        except AssertionError as e:
            print("  反向见红 ✓ %-12s %s" % (name, str(e)[:70]))
            continue
        raise AssertionError("★★★ 反向测试没见红(恒绿闸): %s" % name)
    assert _TRIPPED == [], "★★★ 绊线被触发: %r" % _TRIPPED


run()


def check_real_provider_prereg_frozen():
    """真实 provider 那一半的预注册: sha 钉在跑批里; 离线演练能走完五格; 改一个字节跑批拒跑。★ 只跑 --offline, 绝不发真实请求。"""
    import hashlib
    import accuracy_real_provider_run as RP
    assert hashlib.sha256(RP.PREREG.read_bytes()).hexdigest() == RP.PREREG_SHA256, "★ 预注册被改过而钉住的 sha 没跟 —— 预注册必须跑前冻结"
    pre = json.loads(RP.PREREG.read_text(encoding="utf-8"))
    assert pre["budget"]["hard_cap_requests"] == RP.CAP == 200 and pre["budget"]["calls_planned"] <= RP.CAP
    dry = RP.run(offline=True)
    assert set(dry["cells"]) == {"S1_MiniMax-M3", "S1_MiniMax-M2.7", "S2_MiniMax-M3", "S2_MiniMax-M2.7", "S3"}, dry["cells"].keys()
    saved = RP.PREREG_SHA256
    RP.PREREG_SHA256 = "0" * 64
    try:
        RP.run(offline=True)
        raise AssertionError("★★★ 反向没见红: 预注册 sha 不符时跑批没有拒跑")
    except SystemExit:
        print("  反向见红 ✓ 预注册 sha 不符 ⇒ 跑批拒跑")
    finally:
        RP.PREREG_SHA256 = saved


check_real_provider_prereg_frozen()
assert _TRIPPED == [], "★★★ 绊线被触发: %r" % _TRIPPED
socket.socket.connect = _orig
print("OK tests/test_cce_accuracy_main_e2e_offline.py")
