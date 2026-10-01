#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v2 七条 UNREACHABLE 的复活工况消融 + ksep 三条重跑的语料锁 —— 现算, 不信存盘。

守四件事:
  ① 探针现算 == tests/data/ablation_v3/unreachable_revival.json(逐字节)
  ② 判决表 7 行的 ★revival_ablation_2026_10_01 块与产物一致; 判决词仍是 UNREACHABLE(生产工况没变)
  ③ 每个工况有效(空操作臂 0 变 · 基线跑两遍相同) · 生产工况上组件臂 L2 0 变 · 绊线未触发
     —— 生产一旦有变, UNREACHABLE 这个词就错了, 必须红
  ④ ksep 三条重跑(v2-001..003)的语料锁: tests/data/ablation_v3/ksep_rerun.json 的 corpus_lock 7 个文件 sha256 现算相同
     —— 语料再被改, 那三条判决当场失效(上次是并行 agent 改了 panel_analysis.json +948/−316, 没人发现)
反向: 每条断言都在做坏的副本上验过会红。零网络: socket 绊线, 末尾断言未触发。
"""
import copy, hashlib, json, pathlib, socket, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "probes"))

_TRIPPED = []
_orig = socket.socket.connect
def _guard(s, addr, *a, **k):
    _TRIPPED.append(addr)
    raise AssertionError("★★★ 离线隔离被突破: %r" % (addr,))
socket.socket.connect = _guard

import ablation_unreachable_revival as U  # noqa: E402

ART = ROOT / "tests/data/ablation_v3/unreachable_revival.json"
TABLE = json.loads((ROOT / "tests/data/ablation_verdicts_v3.json").read_text(encoding="utf-8"))
KSEP = json.loads((ROOT / "tests/data/ablation_v3/ksep_rerun.json").read_text(encoding="utf-8"))
IDS = ("v2-004", "v2-007", "v2-008", "v2-009", "v2-011", "v2-012", "v2-015")
KEY = "★revival_ablation_2026_10_01"

FRESH = U.main()
STORED = json.loads(ART.read_text(encoding="utf-8"))


def _ops(row):
    o = row["ops"]
    return list(o["reply_loop"].values()) + list(o["reply_batch"].values()) if "reply_loop" in o else \
        [v for v in o.values() if isinstance(v, dict) and "arms" in v]


def check_recomputed(fresh, stored, table, ksep):
    assert json.loads(json.dumps(fresh, ensure_ascii=False, default=list)) == stored, "★ 探针现算与存盘产物不一致 —— 代码或语料变了, 重跑探针"


def check_table_blocks(fresh, stored, table, ksep):
    rows = {r["id"]: r for r in table["verdicts"]}
    for rid in IDS:
        r, a = rows[rid], stored["rows"][rid]
        b = r.get(KEY)
        assert b, "%s 缺 %s 块" % (rid, KEY)
        assert r["verdict"] == "UNREACHABLE" == b["verdict_in_production"], "%s 判决词被改了 —— 生产工况没变, 不许改" % rid
        assert b["verdict_at_revival_condition"] == a["verdict_at_revival_condition"], "%s 表里的复活工况判决与产物不一致" % rid
        assert b["prod_L2_unchanged"] is a["prod_unchanged"] is True, "%s 生产工况上组件臂 L2 有变 ⇒ UNREACHABLE 不成立" % rid
        assert b["★still_unreachable_in_production"] is True


def check_ops_valid(fresh, stored, table, ksep):
    assert stored["file_integrity_identical"] is True and "tripped=[]" in stored["★zero_api"], "产物自报绊线/文件完整性不过"
    for rid in IDS:
        for op in _ops(stored["rows"][rid]):
            assert op["valid"] and op["noop_zero_change"] and op["determinism_base_twice_identical"], "%s 有工况作废(空操作臂变了或基线不确定)" % rid


def check_ksep_corpus_lock(fresh, stored, table, ksep):
    bad = [p for p, s in ksep["corpus_lock"].items() if hashlib.sha256((ROOT / p).read_bytes()).hexdigest() != s]
    assert not bad, "★ ksep 三条判决(v2-001..003)的语料变了: %r ⇒ 那三条需重跑" % bad
    assert len(ksep["corpus_lock"]) == 7


CHECKS = [check_recomputed, check_table_blocks, check_ops_valid, check_ksep_corpus_lock]


def _b_flip_verdict(f, s, t, k):
    t = copy.deepcopy(t)
    next(r for r in t["verdicts"] if r["id"] == "v2-008")[KEY]["verdict_at_revival_condition"] = "NO_CONSUMER"
    return f, s, t, k

def _b_word_changed(f, s, t, k):
    t = copy.deepcopy(t)
    next(r for r in t["verdicts"] if r["id"] == "v2-004")["verdict"] = "LOAD_BEARING_L2"
    return f, s, t, k

def _both(f, s, edit):
    """现算与存盘同改 ⇒ 绕过 ①, 证明后面的断言自己会红。"""
    f, s = copy.deepcopy(f), copy.deepcopy(s)
    edit(f); edit(s)
    return f, s

def _b_prod_moved(f, s, t, k):
    f, s = _both(f, s, lambda d: d["rows"]["v2-015"].__setitem__("prod_unchanged", False))
    return f, s, t, k

def _b_noop_moved(f, s, t, k):
    f, s = _both(f, s, lambda d: d["rows"]["v2-007"]["ops"]["OP_cond(market=cn, profile=hearing_aid)"].__setitem__("valid", False))
    return f, s, t, k

def _b_stale_artifact(f, s, t, k):
    s = copy.deepcopy(s)
    s["rows"]["v2-009"]["ops"]["OP_cond(market=intl, profile=agent_memory)"]["arms"]["table_emptied"]["L2"] = 0
    return f, s, t, k

def _b_corpus_lock(f, s, t, k):
    k = copy.deepcopy(k)
    p = next(iter(k["corpus_lock"]))
    k["corpus_lock"][p] = "0" * 64
    return f, s, t, k


REVERSE = [("表里复活判决被改", _b_flip_verdict), ("判决词被改成承重", _b_word_changed),
           ("生产工况上有变", _b_prod_moved), ("工况作废", _b_noop_moved),
           ("存盘产物与现算不符", _b_stale_artifact), ("ksep 语料被改", _b_corpus_lock)]


def run():
    args = (FRESH, STORED, TABLE, KSEP)
    for fn in CHECKS:
        fn(*args)
    print("正向: %d 条断言全过" % len(CHECKS))
    for name, mk in REVERSE:
        bad = mk(*args)
        try:
            for fn in CHECKS:
                fn(*bad)
        except AssertionError as e:
            print("  反向见红 ✓ %-16s %s" % (name, str(e)[:80]))
            continue
        raise AssertionError("★★★ 反向测试没见红(恒绿闸): %s" % name)
    assert _TRIPPED == [], "★★★ 绊线被触发: %r" % _TRIPPED
    print("复活工况判决:", {rid: STORED["rows"][rid]["verdict_at_revival_condition"] for rid in IDS})


run()
socket.socket.connect = _orig
print("OK tests/test_cce_unreachable_revival.py")
