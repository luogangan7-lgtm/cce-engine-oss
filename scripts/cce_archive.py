#!/usr/bin/env python3
"""Archive Plane (§44 P5): 长期结构化归档, 不让短期 artifact 承担长期学习。

## 实测出来的起点(2026-09-01)
仓库里有 32 个被引用的 GitHub run_id(台账 / 仪器谱系 / 文档), 其中:
    本地有 artifact 的:  0 / 32
    远端还留着 artifact: 0     (gh api actions/artifacts -> total_count = 0)
⇒ 这 32 个 run **已经不可重建**, 而且**追不回来** ——
   §44 P5 担心的事情不是将来会发生, 是已经发生过了。

所以本模块**不假装**能重建它们。它做三件能做的事:
  1. 把损失如实登记(status=IRRECOVERABLE), 而不是留一份看起来完整的索引;
  2. 保证**今后**每个 run 在完成时就落到本地归档;
  3. 守住真正重要的那条线 —— 任何被当作证据引用的东西必须本地存在且钉了 hash。

## 为什么第 3 条才是重点
§44 P5 的原话是「禁止依赖短期 GitHub artifact 承担长期 Population / Mechanism 学习」。
实测: 机制注册表的 14 条 evidence_refs **全部指向本地文件, 0 条指向 run_id** ——
学习链本来就没有建在会过期的东西上。这条闸把它钉死, 防止下一条机制图省事直接引 run_id。

## 重建的纪律
rebuild() 缺任何一块都**大声失败**, 绝不静默补空 ——
静默补空会产出一份「看起来完整」的重建结果, 比重建失败坏得多。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, "config", "cce_archive_index.json")
ARCHIVE_DIR = os.path.join(ROOT, "archive")

RUN_ID = re.compile(r"\b3\d{10}\b")

LOCALLY_ARCHIVED = "LOCALLY_ARCHIVED"
IRRECOVERABLE = "IRRECOVERABLE"


class ArchiveRebuildError(RuntimeError):
    """重建缺件。★ 绝不降级为「返回空壳」。"""


def _sha(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:16]


def archive_run(run_id: str, manifest: dict, artifacts: dict[str, bytes]) -> str:
    """把一个 run 落到本地归档。今后每个 run 完成时调它。"""
    dest = os.path.join(ARCHIVE_DIR, run_id)
    os.makedirs(dest, exist_ok=True)
    with open(os.path.join(dest, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1, sort_keys=True)
    for name, blob in artifacts.items():
        with open(os.path.join(dest, name), "wb") as fh:
            fh.write(blob)
    listing = {"run_id": run_id,
               "files": {name: _sha(os.path.join(dest, name))
                         for name in sorted(os.listdir(dest)) if name != "_listing.json"}}
    with open(os.path.join(dest, "_listing.json"), "w", encoding="utf-8") as fh:
        json.dump(listing, fh, ensure_ascii=False, indent=1)
    return dest


def rebuild(run_id: str, archive_dir: str = ARCHIVE_DIR) -> dict:
    """按 run_id 重建 manifest 与 artifacts。缺件即抛, 不静默补空。"""
    dest = os.path.join(archive_dir, run_id)
    listing_path = os.path.join(dest, "_listing.json")
    if not os.path.isdir(dest):
        raise ArchiveRebuildError(f"run {run_id} 本地无归档 —— 重建不可能, 不返回空壳")
    if not os.path.exists(listing_path):
        raise ArchiveRebuildError(f"run {run_id} 缺 _listing.json —— 无从判断是否缺件")
    listing = json.load(open(listing_path, encoding="utf-8"))
    missing, drifted = [], []
    for name, pinned in listing["files"].items():
        path = os.path.join(dest, name)
        if not os.path.exists(path):
            missing.append(name)
        elif _sha(path) != pinned:
            drifted.append(name)
    if missing:
        raise ArchiveRebuildError(f"run {run_id} 缺 {len(missing)} 个 artifact: {missing} "
                                  "—— 重建失败, 不静默补空")
    if drifted:
        raise ArchiveRebuildError(f"run {run_id} 有 {len(drifted)} 个 artifact 内容变了: {drifted}")
    manifest_path = os.path.join(dest, "manifest.json")
    if not os.path.exists(manifest_path):
        raise ArchiveRebuildError(f"run {run_id} 缺 manifest.json")
    return {"run_id": run_id, "manifest": json.load(open(manifest_path, encoding="utf-8")),
            "artifacts": sorted(n for n in listing["files"] if n != "manifest.json"),
            "verified_sha": True}


def scan_referenced_run_ids() -> dict[str, list[str]]:
    """全仓扫被引用的 run_id 及其出处。"""
    out: dict[str, list[str]] = {}
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames
                       if d not in {".git", "__pycache__", "results", "archive"}]
        for fn in filenames:
            if not fn.endswith((".json", ".py", ".md", ".yml", ".yaml")):
                continue
            path = os.path.join(dirpath, fn)
            try:
                text = open(path, encoding="utf-8").read()
            except (UnicodeDecodeError, OSError):
                continue
            for rid in set(RUN_ID.findall(text)):
                out.setdefault(rid, []).append(os.path.relpath(path, ROOT))
    return {k: sorted(v) for k, v in sorted(out.items())}


def evidence_refs_in_registries() -> list[tuple[str, str]]:
    """机制注册表里被当作证据引用的路径。(mechanism_id, ref)"""
    reg_path = os.path.join(ROOT, "config", "mechanism_registry.json")
    if not os.path.exists(reg_path):
        return []
    reg = json.load(open(reg_path, encoding="utf-8"))
    rows = []
    for m in reg.get("mechanisms", []):
        refs = list(m.get("evidence_refs", [])) + list(m.get("replications", []))
        if m.get("prereg_ref"):
            refs.append(m["prereg_ref"])
        rows += [(m["id"], r) for r in refs]
    return rows


def check() -> tuple[bool, list[str], dict]:
    index = json.load(open(INDEX, encoding="utf-8"))
    errors: list[str] = []

    # ① 长期学习链不得建在会过期的东西上
    for mech_id, ref in evidence_refs_in_registries():
        if RUN_ID.fullmatch(str(ref)):
            errors.append(f"机制 {mech_id} 直接引用 run_id {ref} —— "
                          "GitHub artifact 会过期, 长期学习不得建在它上面")
        elif not os.path.exists(os.path.join(ROOT, ref)):
            errors.append(f"机制 {mech_id} 的证据 {ref} 本地不存在")

    # ② 索引必须与实际一致: 新出现的 run_id 不许静默不入册
    live = scan_referenced_run_ids()
    indexed = index["runs"]
    # 反向测试必须写出假 run_id 才能证明闸会红。登记在册, 且**只准出现在那一个文件里** ——
    # 否则「登记一下」就成了绕过闸的办法。
    neg = index.get("negative_test_run_ids", {})
    NEG_HOME = "tests/test_cce_archive_plane.py"
    for rid, srcs in live.items():
        if rid in neg and set(srcs) - {NEG_HOME, "config/cce_archive_index.json"}:
            errors.append(f"反向探针 run_id {rid} 出现在 {sorted(set(srcs) - {NEG_HOME})} —— "
                          f"只许出现在 {NEG_HOME}")
    for rid in sorted(set(live) - set(indexed) - set(neg)):
        errors.append(f"run {rid} 被引用但未入归档索引(出处 {live[rid][:2]}) —— "
                      "新 run 必须入册并声明是否本地可重建")

    # ③ 声称本地归档的必须真的能重建
    for rid, row in sorted(indexed.items()):
        if row["status"] != LOCALLY_ARCHIVED:
            continue
        try:
            rebuild(rid)
        except ArchiveRebuildError as exc:
            errors.append(f"索引声称 {rid} 本地已归档, 但重建失败: {exc}")

    stats = {"referenced": len(set(live) - set(index.get("negative_test_run_ids", {}))),
             "indexed": len(indexed),
             "locally_archived": sum(1 for r in indexed.values() if r["status"] == LOCALLY_ARCHIVED),
             "irrecoverable": sum(1 for r in indexed.values() if r["status"] == IRRECOVERABLE),
             "evidence_refs": len(evidence_refs_in_registries())}
    return (not errors), errors, stats


def main() -> int:
    ok, errors, stats = check()
    print("=" * 62)
    print("Archive Plane 闸 (§44 P5)")
    print("=" * 62)
    print(f"被引用的 run_id {stats['referenced']} · 已入册 {stats['indexed']} · "
          f"本地可重建 {stats['locally_archived']} · 不可恢复 {stats['irrecoverable']}")
    print(f"机制证据引用 {stats['evidence_refs']} 条, 全部必须是本地文件而非 run_id")
    for e in errors:
        print("  ✗ " + e)
    print("ARCHIVE_PASS" if ok else "ARCHIVE_FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
