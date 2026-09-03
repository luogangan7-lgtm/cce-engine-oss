#!/usr/bin/env python3
"""§44.9 P5 的验收 gate: 任一历史 run 可按 run_id 完整重建其 manifest 与 artifacts。

文档指定的反向测试: 删一个 artifact, 重建必须失败而不是静默补空。
"""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cce_archive as A  # noqa: E402

INDEX = json.load(open(os.path.join(ROOT, "config", "cce_archive_index.json"), encoding="utf-8"))
ARCHIVED = sorted(r for r, row in INDEX["runs"].items() if row["status"] == A.LOCALLY_ARCHIVED)

# ── 正向: 闸绿, 且确有可重建的 run ─────────────────────────────────────
ok, errors, stats = A.check()
assert ok, f"基线: Archive 闸必须通过: {errors}"
assert ARCHIVED, "必须至少有一个本地可重建的 run, 否则这条 gate 无从验证"
for rid in ARCHIVED:
    r = A.rebuild(rid)
    assert r["run_id"] == rid and r["verified_sha"] and r["manifest"], rid
    assert r["artifacts"], f"{rid} 重建出来一个 artifact 都没有"

# ── 反向 1(文档指定): 删一个 artifact -> 必须失败, 不许静默补空 ────────
rid = ARCHIVED[0]
src = os.path.join(A.ARCHIVE_DIR, rid)
with tempfile.TemporaryDirectory() as td:
    alt_root = os.path.join(td, "archive")
    shutil.copytree(src, os.path.join(alt_root, rid))
    listing = json.load(open(os.path.join(alt_root, rid, "_listing.json"), encoding="utf-8"))
    victim = sorted(n for n in listing["files"] if n != "_listing.json")[0]
    os.remove(os.path.join(alt_root, rid, victim))
    try:
        got = A.rebuild(rid, archive_dir=alt_root)
    except A.ArchiveRebuildError as exc:
        assert victim in str(exc) and "不静默补空" in str(exc)
    else:
        raise AssertionError(f"★ 反向失败: 删了 artifact {victim} 却重建成功 -> {got['artifacts']}")

# ── 反向 2: artifact 内容被改 -> 也必须失败(不只是「文件在不在」) ───────
with tempfile.TemporaryDirectory() as td:
    alt_root = os.path.join(td, "archive")
    shutil.copytree(src, os.path.join(alt_root, rid))
    listing = json.load(open(os.path.join(alt_root, rid, "_listing.json"), encoding="utf-8"))
    victim = sorted(n for n in listing["files"] if n != "_listing.json")[0]
    with open(os.path.join(alt_root, rid, victim), "ab") as fh:
        fh.write(b"\n# tampered\n")
    try:
        A.rebuild(rid, archive_dir=alt_root)
    except A.ArchiveRebuildError as exc:
        assert "内容变了" in str(exc)
    else:
        raise AssertionError("★ 反向失败: artifact 内容被改却重建成功 —— 只查了文件存在与否")

# ── 反向 3: 未归档的 run 不许返回空壳 ─────────────────────────────────
try:
    A.rebuild("39999999999")
except A.ArchiveRebuildError as exc:
    assert "不返回空壳" in str(exc)
else:
    raise AssertionError("★ 反向失败: 从没归档过的 run 也能「重建」")

# ── 反向 4: 长期学习链不得建在会过期的东西上 ──────────────────────────
for mech_id, ref in A.evidence_refs_in_registries():
    assert not A.RUN_ID.fullmatch(str(ref)), \
        f"★ 机制 {mech_id} 直接引用 run_id {ref} —— GitHub artifact 会过期"
    assert os.path.exists(os.path.join(ROOT, ref)), f"机制 {mech_id} 的证据 {ref} 本地不存在"
assert stats["evidence_refs"] >= 14

# 反向: 造一条引 run_id 的机制, 闸必须红
reg_path = os.path.join(ROOT, "config", "mechanism_registry.json")
saved = open(reg_path, encoding="utf-8").read()
try:
    reg = json.loads(saved)
    reg["mechanisms"].append({"id": "reverse_probe", "claim": "x", "status": "CANDIDATE",
                              "evidence_refs": ["31306754953"]})
    json.dump(reg, open(reg_path, "w"), ensure_ascii=False, indent=1)
    ok2, errors2, _ = A.check()
    assert not ok2 and any("run_id" in e for e in errors2), \
        "★ 反向失败: 机制直接引用 run_id 作证据, 闸却是绿的"
finally:
    open(reg_path, "w", encoding="utf-8").write(saved)
assert A.check()[0], "还原后闸应恢复绿"

# ── 反向 5: 新出现的 run_id 不许静默不入册 ────────────────────────────
#    用一个**未登记**的 id, 否则测到的是「探针位置规则」而不是「未入册规则」。
FRESH = "3" + "1234567890"
assert FRESH not in INDEX["runs"] and FRESH not in INDEX["negative_test_run_ids"]
probe = os.path.join(ROOT, "docs", "_archive_reverse_probe.md")
with open(probe, "w", encoding="utf-8") as fh:
    fh.write(f"reverse probe run {FRESH}\n")
try:
    ok3, errors3, _ = A.check()
    assert not ok3 and any(FRESH in e and "未入归档索引" in e for e in errors3), \
        f"★ 反向失败: 新 run_id 被引用却没入册, 闸是绿的: {errors3}"
finally:
    os.remove(probe)
assert A.check()[0]

# ── 反向 6: 反向探针 id 只许出现在本文件里 ────────────────────────────
probe2 = os.path.join(ROOT, "docs", "_archive_reverse_probe2.md")
with open(probe2, "w", encoding="utf-8") as fh:
    fh.write("leaked " + "39999999999" + "\n")
try:
    ok4, errors4, _ = A.check()
    assert not ok4 and any("只许出现在" in e for e in errors4), \
        "★ 反向失败: 把反向探针 id 抄到别处也照样绿 —— 那「登记一下」就成了绕闸的办法"
finally:
    os.remove(probe2)
assert A.check()[0]

# ── 已发生的损失必须如实登记, 不许留一份「看起来完整」的索引 ───────────
# 2026-09-03 大幅更正: 原「32 个 run 全部不可重建」是**查错仓**得出的 ——
# 只查了私仓 cce-engine, 而生产入口 2026-08-17 起在公开仓 cce-engine-oss。
# 换仓复查后 23 个 run 仍活着, 已全部取回落档。
assert stats["irrecoverable"] == 19, stats
assert stats["locally_archived"] >= 24, stats
# ★ 2026-09-03: 26 -> 25。archive/31993570335 的 actor_ref 是两个真实论坛 handle,
#   已整目录移出仓库树(RESTRICTED_OFFTREE)。本仓可 fast-forward 到**公开仓**,
#   含真名的产物不得留在树内; 但**不就地改写以求过闸** —— 改写破坏字节保真,
#   宁可它不在树里, 不可它在树里却是假的。
_r = INDEX["runs"]["31993570335"]
assert _r["status"] == "RESTRICTED_OFFTREE" and _r.get("location"), _r
assert "不就地改" in _r["★why_not_pseudonymize"] or "字节保真" in _r["★why_not_pseudonymize"]
assert not os.path.isdir(os.path.join(ROOT, "archive", "31993570335")), \
    "★ 含真实身份的归档又回到树里了"
assert "查错了仓" in INDEX["finding"], "更正必须写在 finding 里, 不能悄悄改数字"

# ── 反向 7: ★「不可恢复」缺出处 / 漏查一个 push 远端 -> 必须红 ──────────
#    这条闸就是为上面那次更正而设: 只查一个仓得出的「不可恢复」不是结论。
import copy, json as _json, tempfile, os as _os

def _alt(mut):
    idx = copy.deepcopy(INDEX)
    mut(idx)
    fd, tmp = tempfile.mkstemp(suffix=".json"); _os.close(fd)
    _json.dump(idx, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    orig = A.INDEX
    try:
        A.INDEX = tmp
        return A.check()
    finally:
        A.INDEX = orig; _os.unlink(tmp)

_dead = next(r for r, v in INDEX["runs"].items() if v["status"] == "IRRECOVERABLE")

ok7a, e7a, _ = _alt(lambda i: i["runs"][_dead].pop("checked_against"))
assert not ok7a and any("没写 checked_against" in x for x in e7a), \
    "★ 不写在哪儿查的就断言不可恢复 —— 必须红"

ok7b, e7b, _ = _alt(lambda i: i["runs"][_dead].update(
    {"checked_against": ["luogangan7-lgtm/cce-engine"]}))
assert not ok7b and any("漏查了 push 远端" in x for x in e7b), \
    "★ 只查一个仓 —— 必须红(这正是 2026-09-03 那次错的形状)"

ok7c, e7c, _ = _alt(lambda i: i["runs"][_dead].pop("checked_at"))
assert not ok7c and any("没写 checked_at" in x for x in e7c), \
    "★ 可用性会随时间变, 无日期的判定不可复核"

# 远端表必须是**现读 git**, 不是写死 —— 写死一个仓正是那个错的来源
assert set(A.push_remotes()) >= {"luogangan7-lgtm/cce-engine",
                                 "luogangan7-lgtm/cce-engine-oss"}, A.push_remotes()

print(f"test_cce_archive_plane: OK "
      f"(可重建 {len(ARCHIVED)} run · 不可恢复 {stats['irrecoverable']} 已如实登记, "
      f"两仓复查 {A.push_remotes()} | "
      "删件/改件/未归档/引 run_id 作证据/新 run 不入册/不可恢复缺出处或漏查仓 —— 各自见红)")
