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
# 2026-09-02: cce.yml 退役注释引用了两个历史失败 run(31691417474/31691414219)
# 作为「本步不可达」的实证 ⇒ 归档索引随之 +2。闸当场抓到它们未入册, 已补登记。
assert stats["irrecoverable"] == 34, stats
assert "已经发生过了" in INDEX["finding"]

print(f"test_cce_archive_plane: OK "
      f"(可重建 {len(ARCHIVED)} run · 不可恢复 {stats['irrecoverable']} 已如实登记 | "
      "删件/改件/未归档/引 run_id 作证据/新 run 不入册 —— 各自见红)")
