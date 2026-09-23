#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/data/ablation_verdicts_v3.json 的守卫 —— 判决表必须**现算一致**。

★ 它守的不是「文件在不在」, 是四件会悄悄烂掉的事:
  ① 留档说一套、代码算另一套(tally / coverage / 每行的 ablated_files 都现算比对)
  ② NO_CONSUMER 没跑注入检验却不声张(缺 injection_test 必须出现在 ★evidence_gaps 里, 藏不住)
  ③ UNREACHABLE 没写复活条件(缺 unreachable_condition 同上)
  ④ deletable 退化成 verdict 的函数(造一条推导出来的假数据, 必须判红)

★ 反向测试(runner 里实跑, 见 REVERSE 段): 每一条断言都在一份**被做坏的**数据上验过会红。
★ 零网络: 加载期装 socket.socket.connect 绊线, 末尾断言未触发。
  作用域如实: 只覆盖本进程内经 socket 新建的连接; 不覆盖已建连接 / 子进程 / C 扩展自带栈。
"""
import copy, json, os, pathlib, re, socket, sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC_PATH = ROOT / "tests/data/ablation_verdicts_v3.json"

# ── R1 绊线 ────────────────────────────────────────────────────────────────
_TRIPPED = []
_orig_connect = socket.socket.connect
def _guard(sock, address, *a, **kw):
    _TRIPPED.append(address)
    raise AssertionError("★★★ 离线隔离被突破: %r" % (address,))
socket.socket.connect = _guard

DOC = json.loads(DOC_PATH.read_text(encoding="utf-8"))
ROWS = DOC["verdicts"]

VERDICT_WORDS = {"LOAD_BEARING_L2", "LOAD_BEARING_L1_ONLY", "UNREACHABLE",
                 "NO_CONSUMER", "CIRCULAR", "INCONCLUSIVE"}


# ── 现算 ①: 生产面与覆盖率 ─────────────────────────────────────────────────
def recompute_scope(doc):
    rule = doc["★coverage"]["scope_rule"]
    out = []
    for d in rule["dirs_recursive_py"]:
        for r, _, fs in os.walk(ROOT / d):
            for f in fs:
                if f.endswith(".py"):
                    out.append(str(pathlib.Path(r, f).relative_to(ROOT)))
    for d in rule["dirs_flat_json"]:
        for f in sorted(os.listdir(ROOT / d)):
            if f.endswith(".json"):
                out.append("%s/%s" % (d, f))
    return sorted(set(out))


def nlines(rel):
    with open(ROOT / rel, "rb") as fh:
        return sum(1 for _ in fh)


def recompute_coverage(doc):
    """完全从**文件系统 + verdicts 行**重算, 一个数都不读 ★coverage。"""
    scope = recompute_scope(doc)
    ln = {p: nlines(p) for p in scope}
    touched = sorted({f for r in doc["verdicts"] for f in r["ablated_files"]})
    in_scope = [f for f in touched if f in ln]
    return {
        "scope_files": len(scope),
        "scope_lines": sum(ln.values()),
        "n_touched_files": len(in_scope),
        "touched_files_union": in_scope,
        "lines_in_touched_files": sum(ln[f] for f in in_scope),
        "file_level_pct": round(100.0 * len(in_scope) / len(scope), 2),
        "line_level_pct_GENEROUS_UPPER_BOUND":
            round(100.0 * sum(ln[f] for f in in_scope) / sum(ln.values()), 2),
        "per_file_lines": ln,
    }


# ── 断言 ───────────────────────────────────────────────────────────────────
def check_tally(doc):
    """① tally 必须 == 现算。"""
    rows = doc["verdicts"]
    assert doc["★tally"] == dict(Counter(r["verdict"] for r in rows)), (
        "★tally 与现算不符: 档案 %r vs 现算 %r" % (doc["★tally"], dict(Counter(r["verdict"] for r in rows))))
    assert doc["★n_verdicts"] == len(rows), "★n_verdicts 与现算不符"
    assert doc["★tally_by_status"] == dict(Counter(r["status"] for r in rows)), "★tally_by_status 与现算不符"
    assert sum(doc["★tally"].values()) == len(rows), "tally 之和 != 行数"
    bad = sorted({r["verdict"] for r in rows} - VERDICT_WORDS)
    assert not bad, "出现词表外的判决词: %r" % bad


def check_coverage(doc):
    """① 覆盖率数字必须 == 现算(含逐文件行数, 漂移时能指名道姓)。"""
    got, want = recompute_coverage(doc), doc["★coverage"]
    for k in ("scope_files", "scope_lines", "n_touched_files", "lines_in_touched_files",
              "file_level_pct", "line_level_pct_GENEROUS_UPPER_BOUND", "touched_files_union"):
        if got[k] != want[k]:
            extra = ""
            if k in ("scope_lines", "lines_in_touched_files"):
                drift = {p: (want["per_file_lines"].get(p), got["per_file_lines"].get(p))
                         for p in set(want["per_file_lines"]) | set(got["per_file_lines"])
                         if want["per_file_lines"].get(p) != got["per_file_lines"].get(p)}
                extra = "\n  漂移的文件(档案行数, 现在行数): %r" % drift
            raise AssertionError("★coverage.%s 与现算不符: 档案 %r vs 现算 %r%s" % (k, want[k], got[k], extra))
    assert got["per_file_lines"] == want["per_file_lines"], "★coverage.per_file_lines 与现算不符"
    # 覆盖率是**慷慨上界**这件事必须写在产物里, 不许下游当成逐行覆盖
    assert "慷慨上界" in want["★这个数是什么"], "覆盖率口径的自我声明被删了"


def check_every_row_wellformed(doc):
    ids = [r["id"] for r in doc["verdicts"]]
    assert len(ids) == len(set(ids)), "verdict id 有重复"
    for r in doc["verdicts"]:
        for k in ("id", "round", "component", "verdict", "status", "deletable",
                  "deletable_reason", "operating_point_ref", "source_artifact", "ablated_files"):
            assert k in r, "%s 缺字段 %s" % (r["id"], k)
        assert isinstance(r["deletable"], bool), "%s 的 deletable 不是布尔" % r["id"]
        assert r["ablated_files"], "%s 没有 ablated_files" % r["id"]
        for f in r["ablated_files"]:
            assert (ROOT / f).exists(), "%s 指向不存在的文件 %s" % (r["id"], f)


def check_no_consumer_has_injection(doc):
    """② 每条 NO_CONSUMER 必须有 injection_test; 没有的必须**逐条列在 ★evidence_gaps 里**, 藏不住。"""
    gaps = {(g["id"], g["missing"]) for g in doc["★evidence_gaps"]}
    for r in doc["verdicts"]:
        if r["verdict"] != "NO_CONSUMER":
            continue
        inj = str(r.get("injection_test") or "").strip()
        if len(inj) < 10:
            assert (r["id"], "injection_test") in gaps, (
                "%s 是 NO_CONSUMER 却既没有 injection_test 也没进 ★evidence_gaps: %s"
                % (r["id"], r["component"][:60]))


def check_unreachable_has_condition(doc):
    """③ 每条 UNREACHABLE 必须有 unreachable_condition; 没有的必须进 ★evidence_gaps。"""
    gaps = {(g["id"], g["missing"]) for g in doc["★evidence_gaps"]}
    for r in doc["verdicts"]:
        if r["verdict"] != "UNREACHABLE":
            continue
        uc = str(r.get("unreachable_condition") or "").strip()
        if len(uc) < 10:
            assert (r["id"], "unreachable_condition") in gaps, (
                "%s 是 UNREACHABLE 却既没有 unreachable_condition 也没进 ★evidence_gaps: %s"
                % (r["id"], r["component"][:60]))



def check_deletable_ledger_matches_every_row(doc):
    """★★★ 2026-09-11 补: ④ 的聚合判据**翻单行抓不到**。

    原判据是「某个 verdict 词下 deletable 同时出现 True 与 False」——
    把某一行从 False 翻成 True, 同判决词的其余行仍两值俱全 ⇒ **照样过**。
    我抽验时实测漏掉了这个变异。

    ★ 为什么不用文本判据: 试过按理由措辞推(含「不可删」⇒False / 含「该删」⇒True),
      实测**误伤 7 行**(v3-066 的理由是「这不是「该删」的组件」, 否定句里含肯定词)。
      **会误报的闸不上** —— 它会训练读者忽略它。

    ⇒ 改成逐字台账: 每行的 deletable 与 deletable_reason 的 sha8 必须与 ★deletable_ledger 相同。
    ★ 它是**改动探测器, 不是正确性证明** —— 它不说哪一行判得对, 只保证改动不会悄悄发生。
    """
    import hashlib
    led = doc.get("★deletable_ledger", {}).get("条目")
    assert isinstance(led, dict) and led, "★★★ ★deletable_ledger 不在 —— 单行改动又变得抓不到了"
    rows = {r["id"]: r for r in doc["verdicts"]}
    assert set(led) == set(rows), (
        "台账与判决表的 id 集合不一致: 台账独有 %r / 表独有 %r"
        % (sorted(set(led) - set(rows))[:5], sorted(set(rows) - set(led))[:5]))
    bad = []
    for rid, (dele, why8) in led.items():
        r = rows[rid]
        now8 = hashlib.sha256(str(r.get("deletable_reason") or "").encode()).hexdigest()[:8]
        if bool(r["deletable"]) != bool(dele):
            bad.append("%s 的 deletable 由 %s 变成 %s, 台账没同步" % (rid, dele, r["deletable"]))
        elif now8 != why8:
            bad.append("%s 的 deletable_reason 变了(%s→%s), 台账没同步" % (rid, why8, now8))
    assert not bad, "★★★ deletable 被改动而台账未同步:\n  " + "\n  ".join(bad[:8])
    # 台账自己不许退化成 verdict 的函数(否则同步它就等于同步了一份推导)
    import collections
    m = collections.defaultdict(set)
    for rid, (dele, _) in led.items():
        m[rows[rid]["verdict"]].add(bool(dele))
    assert any(len(v) > 1 for v in m.values()), "★ 台账里每个判决词只对应一个 deletable ⇒ 它成了 verdict 的函数"
    return len(led), sum(1 for v in led.values() if v[0])

def check_evidence_gaps_are_real(doc):
    """★evidence_gaps 不许当垃圾桶: 列进去的必须真的缺, 不许拿它豁免有字段的行。"""
    by_id = {r["id"]: r for r in doc["verdicts"]}
    for g in doc["★evidence_gaps"]:
        r = by_id.get(g["id"])
        assert r is not None, "★evidence_gaps 指向不存在的行 %s" % g["id"]
        assert len(str(r.get(g["missing"]) or "").strip()) < 10, (
            "%s 被列进 ★evidence_gaps 说缺 %s, 但它其实有" % (g["id"], g["missing"]))


def check_deletable_independent_of_verdict(doc):
    """④ deletable 不得是 verdict 的函数。

    判据: 存在**至少一个** verdict 词, 在它下面 deletable 同时出现 True 与 False。
    若每个 verdict 词都只对应唯一一个 deletable 取值 ⇒ 这一列没带任何 verdict 之外的信息,
    等价于从 verdict 推导出来的 —— 判红。
    """
    m = {}
    for r in doc["verdicts"]:
        m.setdefault(r["verdict"], set()).add(r["deletable"])
    split = {k: v for k, v in m.items() if len(v) > 1}
    assert split, (
        "deletable 退化成了 verdict 的函数(每个判决词只对应一个取值): %r\n"
        "  ⇒ 这一列没有独立信息, 等于从 verdict 推导出来的。" % {k: sorted(v) for k, v in m.items()})
    # 每条 deletable 还必须自带独立理由; 没有的必须进 ★evidence_gaps, 藏不住
    gaps = {(g["id"], g["missing"]) for g in doc["★evidence_gaps"]}
    for r in doc["verdicts"]:
        why = str(r.get("deletable_reason") or "").strip()
        if len(why) < 8:
            assert (r["id"], "deletable_reason") in gaps, (
                "%s 的 deletable 没有独立理由, 也没进 ★evidence_gaps: %s" % (r["id"], r["component"][:60]))
        assert why not in VERDICT_WORDS, "%s 的 deletable_reason 只是抄了 verdict 词" % r["id"]


def check_v2_preserved(doc):
    """v2 的 30 条一条不许少; 被改判/被替换的必须原文留档。"""
    v2 = json.loads((ROOT / "tests/data/ablation_verdicts_v2.json").read_text(encoding="utf-8"))
    v2rows = [r for r in doc["verdicts"] if r["round"].startswith("v2")]
    assert len(v2rows) == len(v2["verdicts"]) == 30, (
        "v2 条目数对不上: 产物里 %d, v2 文件里 %d" % (len(v2rows), len(v2["verdicts"])))
    orig = {json.dumps(v, sort_keys=True, ensure_ascii=False) for v in v2["verdicts"]}
    kept = {json.dumps(r["_v2_original"], sort_keys=True, ensure_ascii=False) for r in v2rows}
    assert orig == kept, "有 v2 条目的原文被改动或丢失"
    rerun = [r for r in doc["verdicts"] if r["status"] == "SUPERSEDED_BY_V3_RERUN"]
    assert len(rerun) == 3, "ksep 重跑替换的应当恰好 3 条, 实为 %d" % len(rerun)
    for r in rerun:
        b = r["★replaced_by_v3_rerun"]
        assert b.get("v2_verdict") and b.get("v3_verdict"), "%s 没留 v2 旧判决" % r["id"]
        assert len(str(b.get("replacement_reason") or "")) > 30, "%s 没写替换理由" % r["id"]
        assert r["verdict"] == b["v3_verdict"], "%s 的当前判决与重跑结果不符" % r["id"]


def check_changed_rows_keep_the_original(doc):
    """凡改过判的行, 原判必须逐字留档, 且 was != now。"""
    KEYS = ("★overturned_by_recheck", "★downgraded_by_v3_completeness_audit")
    n = 0
    for r in doc["verdicts"]:
        if r["status"] in ("OVERTURNED_AND_REPLACED", "DOWNGRADED_L3_TAUTOLOGY"):
            blk = next((r[k] for k in KEYS if k in r), None)
            assert blk, "%s 标了被改判却没有留档块" % r["id"]
            assert blk["was"] != blk["now"], "%s 的 was 与 now 相同" % r["id"]
            assert r["verdict"] == blk["now"], "%s 的当前判决与留档的 now 不符" % r["id"]
            assert "original_row_preserved_verbatim" in blk, "%s 没保留原行" % r["id"]
            assert len(str(blk.get("why") or "")) > 50, "%s 改判没给理由" % r["id"]
            n += 1
    assert n == 13, "改判行数应为 13(7 推翻 + 6 重言降级), 实为 %d" % n



def check_ce3_closure_retests_keep_the_original(doc):
    """★★★ 2026-09-11 第二轮补: 重测过的行也必须逐字留下原判。

    第一轮的 check_changed_rows_keep_the_original 只认 OVERTURNED_AND_REPLACED /
    DOWNGRADED_L3_TAUTOLOGY 两个 status, 而第二轮(CE-3 闭合)重测用的是新 status
    RETESTED_BY_CE3_CLOSURE —— 它当时**一条断言都没有**, 原行被悄悄丢掉抓不到。

    ★ 与第一轮那条的差别: 这里**不要求** was != now。加宽观测面后判决不变是有价值的结果,
      照样要留档; 但「新覆盖了哪一面」必须写出来, 否则「重测过」是空话。
    """
    n = 0
    for r in doc["verdicts"]:
        if r["status"] != "RETESTED_BY_CE3_CLOSURE":
            continue
        b = r.get("★retested_by_ce3_closure")
        assert b, "%s 标了第二轮重测却没有留档块" % r["id"]
        assert "original_row_preserved_verbatim" in b, "%s 没保留原行" % r["id"]
        o = b["original_row_preserved_verbatim"]
        assert o.get("id") == r["id"], "%s 留档的原行不是它自己" % r["id"]
        assert b.get("verdict_before") == o.get("verdict"), (
            "%s 留档块写的 verdict_before 与原行不符: %r vs %r" % (r["id"], b.get("verdict_before"), o.get("verdict")))
        assert b.get("verdict_now") == r["verdict"], "%s 当前判决与留档的 verdict_now 不符" % r["id"]
        assert bool(b.get("deletable_before")) == bool(o.get("deletable")), (
            "%s 留档块写的 deletable_before 与原行不符" % r["id"])
        assert bool(b.get("deletable_now")) == bool(r["deletable"]), "%s 的 deletable 与留档的 deletable_now 不符" % r["id"]
        assert len(str(b.get("why") or "")) > 50, "%s 重测没给理由" % r["id"]
        assert len(str(b.get("新覆盖了哪一面") or "")) > 20, (
            "%s 说重测过却没写新覆盖了哪一面 —— 那就不是重测, 是重抄" % r["id"])
        assert b.get("artifact") and b.get("independent_recheck"), "%s 没写出处(产物 + 独立复核)" % r["id"]
        n += 1
    assert n == 13, "第二轮重测行数应为 13, 实为 %d" % n

def check_tautology_downgrade_carries_its_measurement(doc):
    """L3 重言降级不许只是口头断言 —— 必须带本轮实测的分辨力对照。"""
    rows = [r for r in doc["verdicts"] if r["evidence_class"] == "L3_TAUTOLOGY_ONLY"]
    assert len(rows) == 6, "L3_TAUTOLOGY_ONLY 应为 6 行, 实为 %d" % len(rows)
    for r in rows:
        c = r["★downgraded_by_v3_completeness_audit"]["tautology_control_measured_this_round"]
        # 关键: 装饰臂(纯空格)与语义臂必须都改变了哈希, 且都不等于基线 ⇒ 判据零分辨力
        base = c["base_gate_protocol_hash"]
        assert "changed" in c["arm1_signature_congruence_semantic"]
        assert "changed" in c["arm2_same_field_TRAILING_SPACE_decorative"], (
            "%s: 装饰臂没有改变哈希 —— 那这条降级就不成立, 该改回去" % r["id"])
        assert "UNCHANGED" in c["arm4_hard_discriminant_not_in_materials"], (
            "%s: 阴性对照臂也变了 ⇒ 判据恒真, 这份对照本身无效" % r["id"])
        assert base not in c["arm2_same_field_TRAILING_SPACE_decorative"]
        assert c["tripwire_tripped"] == [] and c["frozen_sha_identical"] is True


def check_frozen_files(doc):
    import hashlib
    for p, want in doc["★frozen_files_sha256"].items():
        got = hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
        assert got == want, "冻结生产件被改动: %s\n  档案 %s\n  现算 %s" % (p, want, got)


def check_operating_points_named(doc):
    """M7: 每条判决的工况必须指得到一个真存在的工况块。"""
    op = doc["★operating_point"]
    named = {k for k in op if k.startswith("OP_")}
    assert len(named) >= 4, "工况块少于 4 个 —— 本轮明明是四个互不相同的工况"
    for r in doc["verdicts"]:
        assert r["operating_point_ref"], "%s 没有 operating_point_ref" % r["id"]
    # market 那条假声明必须留着更正, 不许被悄悄删掉了事
    assert "★★market_字段的工况声明是假的(本轮实测更正)" in op, "market 的更正记录被删了"


def check_unablated_is_named_not_summarised(doc):
    """「还差什么」必须逐条列名。"""
    w = doc["★what_is_still_unablated"]
    core = json.loads((ROOT / "config/cce_core_manifest.json").read_text(encoding="utf-8"))
    touched = {f for r in doc["verdicts"] for f in r["ablated_files"]}
    assert sorted(w["①_声明为核心却零消融"]["core_files_never_ablated"]) == \
        sorted(f for f in core["core_files"] if f not in touched), "core 未消融清单与现算不符"
    assert sorted(w["①_声明为核心却零消融"]["parser_plane_never_ablated"]) == \
        sorted(f for f in core["parser_plane"] if f not in touched), "parser_plane 未消融清单与现算不符"
    assert len(w["②_被真实消费却零判决(逐个列名)"]) >= 8, "②「零判决」清单太短, 像是写了「基本覆盖」"
    for it in w["②_被真实消费却零判决(逐个列名)"]:
        assert it.get("item") and it.get("consumed_by") and it.get("why_it_matters")
    scope = recompute_scope(doc)
    ln = {p: nlines(p) for p in scope}
    never = [p for p in scope if p not in touched]
    assert w["③_合计"]["n_files_never_touched"] == len(never), "③ 未触及文件数与现算不符"
    assert w["③_合计"]["lines_never_touched"] == sum(ln[p] for p in never), "③ 未触及行数与现算不符"


CHECKS = [check_tally, check_coverage, check_every_row_wellformed,
          check_no_consumer_has_injection, check_unreachable_has_condition,
          check_evidence_gaps_are_real, check_deletable_independent_of_verdict,
          check_deletable_ledger_matches_every_row,
          check_v2_preserved, check_changed_rows_keep_the_original,
          check_ce3_closure_retests_keep_the_original,
          check_tautology_downgrade_carries_its_measurement,
          check_frozen_files, check_operating_points_named,
          check_unablated_is_named_not_summarised]


# ── 反向测试: 每条断言都在做坏的数据上验过会红 ─────────────────────────────
def _broken_tally(d):
    d["★tally"]["LOAD_BEARING_L2"] += 1
    return d

def _broken_coverage(d):
    d["★coverage"]["file_level_pct"] = 88.8
    return d

def _broken_no_consumer(d):
    """把一条有 injection_test 的 NO_CONSUMER 的字段抹掉, 又不进 gaps。"""
    for r in d["verdicts"]:
        if r["verdict"] == "NO_CONSUMER" and r.get("injection_test"):
            r["injection_test"] = ""
            return d
    raise RuntimeError("反向测试锚点没命中")

def _broken_unreachable(d):
    for r in d["verdicts"]:
        if r["verdict"] == "UNREACHABLE" and r.get("unreachable_condition"):
            r.pop("unreachable_condition")
            return d
    raise RuntimeError("反向测试锚点没命中")

def _broken_deletable_derived(d):
    """★ 造一条 deletable 完全由 verdict 推导出来的假数据。"""
    DERIVE = {"NO_CONSUMER": True}
    for r in d["verdicts"]:
        r["deletable"] = DERIVE.get(r["verdict"], False)
    return d

def _broken_v2_dropped(d):
    for i, r in enumerate(d["verdicts"]):
        if r["round"].startswith("v2"):
            d["verdicts"].pop(i)
            d["★tally"] = dict(Counter(x["verdict"] for x in d["verdicts"]))
            d["★n_verdicts"] = len(d["verdicts"])
            d["★tally_by_status"] = dict(Counter(x["status"] for x in d["verdicts"]))
            return d
    raise RuntimeError("反向测试锚点没命中")

def _broken_overturn_loses_original(d):
    for r in d["verdicts"]:
        if r["status"] == "OVERTURNED_AND_REPLACED":
            r["★overturned_by_recheck"].pop("original_row_preserved_verbatim")
            return d
    raise RuntimeError("反向测试锚点没命中")

def _broken_tautology_control_is_vacuous(d):
    """把装饰臂改成「没变」—— 那这条降级就失去依据, 必须红。"""
    for r in d["verdicts"]:
        if r.get("evidence_class") == "L3_TAUTOLOGY_ONLY":
            c = r["★downgraded_by_v3_completeness_audit"]["tautology_control_measured_this_round"]
            c["arm2_same_field_TRAILING_SPACE_decorative"] = c["base_gate_protocol_hash"] + " (UNCHANGED)"
            return d
    raise RuntimeError("反向测试锚点没命中")

def _broken_unablated_summarised(d):
    d["★what_is_still_unablated"]["②_被真实消费却零判决(逐个列名)"] = [
        {"item": "基本覆盖", "consumed_by": "-", "why_it_matters": "-"}]
    return d

def _broken_deletable_reason_blank(d):
    """把一条有理由的 deletable_reason 抹成「不可删。」又不进 gaps。"""
    for r in d["verdicts"]:
        if len(str(r.get("deletable_reason") or "")) > 30:
            r["deletable_reason"] = "不可删。"
            return d
    raise RuntimeError("反向测试锚点没命中")

def _broken_gaps_used_as_bin(d):
    """把一条**有** injection_test 的行塞进 gaps 当豁免。"""
    for r in d["verdicts"]:
        if r["verdict"] == "NO_CONSUMER" and len(str(r.get("injection_test") or "")) >= 10:
            d["★evidence_gaps"].append({"id": r["id"], "component": r["component"],
                                        "verdict": r["verdict"], "missing": "injection_test",
                                        "round": r["round"]})
            return d
    raise RuntimeError("反向测试锚点没命中")


def _broken_retest_loses_original(d):
    """★ 第二轮重测行丢掉原文 —— 必须红。"""
    for r in d["verdicts"]:
        if r["status"] == "RETESTED_BY_CE3_CLOSURE":
            r["★retested_by_ce3_closure"].pop("original_row_preserved_verbatim")
            return d
    raise RuntimeError("反向测试锚点没命中")


def _broken_retest_has_no_new_face(d):
    """★ 说重测过却答不出新覆盖了哪一面 —— 必须红(那是重抄不是重测)。"""
    for r in d["verdicts"]:
        if r["status"] == "RETESTED_BY_CE3_CLOSURE":
            r["★retested_by_ce3_closure"]["新覆盖了哪一面"] = "面更全了"
            return d
    raise RuntimeError("反向测试锚点没命中")


REVERSE = [
 ("tally 被篡改",                     _broken_tally),
 ("覆盖率写死一个好看的数",            _broken_coverage),
 ("NO_CONSUMER 抹掉注入检验且不声张",  _broken_no_consumer),
 ("UNREACHABLE 删掉复活条件",          _broken_unreachable),
 ("★deletable 改成由 verdict 推导",    _broken_deletable_derived),
 ("删掉一条 v2 条目",                  _broken_v2_dropped),
 ("改判了却不留原文",                  _broken_overturn_loses_original),
 ("重言降级的装饰臂对照被做成空过",     _broken_tautology_control_is_vacuous),
 ("「还差什么」写成「基本覆盖」",        _broken_unablated_summarised),
 ("★evidence_gaps 被当成豁免垃圾桶",   _broken_gaps_used_as_bin),
 ("deletable_reason 抹成复述自己",      _broken_deletable_reason_blank),
 ("★第二轮重测行丢掉原文",              _broken_retest_loses_original),
 ("★重测行答不出新覆盖了哪一面",          _broken_retest_has_no_new_face),
]


def run():
    for fn in CHECKS:
        fn(DOC)
    print("正向: %d 条断言全过" % len(CHECKS))

    reds = 0
    for name, mk in REVERSE:
        bad = mk(copy.deepcopy(DOC))
        try:
            for fn in CHECKS:
                fn(bad)
        except AssertionError as e:
            reds += 1
            print("  反向见红 ✓ %-32s %s" % (name, str(e).split("\n")[0][:90]))
            continue
        raise AssertionError("★★★ 反向测试没见红(恒绿闸): %s" % name)
    assert reds == len(REVERSE)
    print("反向: %d/%d 条实际见红" % (reds, len(REVERSE)))

    assert _TRIPPED == [], "★★★ 离线绊线被触发: %r" % _TRIPPED
    print("绊线 tripped=[] (作用域: 本进程内经 socket 新建的连接; 不覆盖已建连接/子进程/C 扩展自带栈)")
    c = DOC["★coverage"]
    print("覆盖率(现算一致): 文件级 %s%% (%d/%d) · 行级慷慨上界 %s%% (%d/%d)" % (
        c["file_level_pct"], c["n_touched_files"], c["scope_files"],
        c["line_level_pct_GENEROUS_UPPER_BOUND"], c["lines_in_touched_files"], c["scope_lines"]))
    print("判决 %d 条 | %r" % (DOC["★n_verdicts"], DOC["★tally"]))


run()
socket.socket.connect = _orig_connect
print("OK tests/test_cce_ablation_verdicts_v3.py")
