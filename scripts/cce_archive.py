#!/usr/bin/env python3
"""Archive Plane (§44 P5): 长期结构化归档, 不让短期 artifact 承担长期学习。

## ★ 2026-09-03 更正: 上面这个「起点」是错的, 错在**查错了仓**
原记录写「远端 gh api actions/artifacts total_count = 0 ⇒ 32 个 run 全部不可重建」。
实测该查询是对**私仓 luogangan7-lgtm/cce-engine** 做的, 而 2026-08-17 起
生产入口已迁到**公开仓 luogangan7-lgtm/cce-engine-oss** —— run 在那边, 私仓自然 404。
换仓复查: 索引内 37 条里 **15 条仍有 artifact 且 expired=false**, 另有文档引用的 8 条同样活着。

## 根因不是「查错了」, 是「这个查询根本没有代码」
原来的可用性判断是**人工跑一次 gh api, 把结论写死进 docstring 与索引**。
没有可重跑的检查 ⇒ 查错了仓没有任何东西会发现, 而且它从写下的那一刻起就是错的。
⇒ 现在 IRRECOVERABLE 是一条**要被审的断言**: 必须带 checked_against(查过哪些远端)
   与 checked_at, 且 checked_against 必须覆盖**全部 push 远端**。缺一, 闸红。

## 起点(更正后)
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
RESTRICTED_OFFTREE = "RESTRICTED_OFFTREE"


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


def push_remotes() -> list[str]:
    """本仓所有 push 远端的 owner/repo。★ 现读 git, 不写死 ——
    写死一个仓正是 2026-09-03 更正的那个错的来源。"""
    import subprocess
    out = subprocess.run(["git", "remote", "-v"], cwd=ROOT,
                         capture_output=True, text=True).stdout
    repos = set()
    for line in out.splitlines():
        if "(push)" not in line:
            continue
        m = re.search(r"[:/]([\w.-]+/[\w.-]+?)(?:\.git)?\s+\(push\)", line)
        if m:
            repos.add(m.group(1))
    return sorted(repos)


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

    # ④ ★「不可恢复」是断言, 不是观察 —— 必须说清在哪些远端查过
    #    这条闸就是为 2026-09-03 那次更正而设: 只查一个仓得出的「不可恢复」不是结论。
    # ★ 由索引**声明**, 不由现读 git 决定 —— 否则闸的强度取决于它在哪台机器上跑
    #   (2026-09-03 CI 实跑暴露: CI 只有一个 remote, 「全部 push 远端」缩水成「那一个」)。
    remotes = set(index.get("required_remotes") or [])
    if not remotes:
        errors.append("索引缺 required_remotes —— 「查过全部远端」这句话没有对照物")
    # ★ 2026-09-28: 这里曾复用变量名 live(上面是被引用的 run_id 表) ⇒ 下面 stats["referenced"] 数的是远端个数(报「被引用 2」)
    remotes_live = set(push_remotes())
    extra = remotes_live - remotes
    if extra:
        # 本机多出来的 remote 必须补进声明, 否则会有一个从没查过的仓
        errors.append(f"本机存在未声明的 push 远端 {sorted(extra)} —— "
                      "补进 config/cce_archive_index.json 的 required_remotes, 否则等于没查它")
    for rid, row in sorted(indexed.items()):
        if row["status"] != IRRECOVERABLE:
            continue
        checked = set(row.get("checked_against") or [])
        if not checked:
            errors.append(f"{rid} 标 IRRECOVERABLE 却没写 checked_against —— "
                          "「查不到」必须说清在哪儿查的, 否则查错仓也没人知道")
        elif remotes - checked:
            errors.append(f"{rid} 标 IRRECOVERABLE 但漏查了 push 远端 "
                          f"{sorted(remotes - checked)} —— 只查一个仓不足以断言不可恢复")
        if not row.get("checked_at"):
            errors.append(f"{rid} 标 IRRECOVERABLE 却没写 checked_at —— "
                          "可用性会随时间变, 无日期的判定不可复核")

    # ⑤ ★ 2026-09-28: 移出仓库树不等于没了 —— 公开远端上 artifact 与运行日志是另一份副本(诊断 #29)。
    #    RESTRICTED_OFFTREE 且取自公开远端的, 必须登记公开副本已清的证据(谁核的、何时、各剩几份)。
    public = set(index.get("public_remotes") or [])
    for rid, row in sorted(indexed.items()):
        if row["status"] != RESTRICTED_OFFTREE or row.get("recovered_from") not in public:
            continue
        pc = row.get("public_copies_cleared") or {}
        if not (pc.get("artifacts_remaining") == 0 and pc.get("logs") == "deleted" and pc.get("checked_at")):
            errors.append(f"{rid} 含真实身份且取自公开远端 {row.get('recovered_from')}, 却没有「公开副本已清」的证据 —— "
                          "仓库树里移走了, 公开 artifact 与日志可能还在")

    stats = {"referenced": len(set(live) - set(index.get("negative_test_run_ids", {}))),
             "indexed": len(indexed),
             "locally_archived": sum(1 for r in indexed.values() if r["status"] == LOCALLY_ARCHIVED),
             "irrecoverable": sum(1 for r in indexed.values() if r["status"] == IRRECOVERABLE),
             "evidence_refs": len(evidence_refs_in_registries()),
             "push_remotes": push_remotes()}
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


def _identity_hits(name: str, blob: bytes) -> int:
    """落进仓库树之前的化名不变式(与入口闸同一份规则)。只返回计数, 不返回名字。"""
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from cce_identity import ID_FIELDS, is_pseudonym, real_mentions
    text = blob.decode("utf-8", errors="ignore")
    n = len(real_mentions(text))
    if name.endswith(".json"):
        try:
            stack = [json.loads(text)]
        except ValueError:
            stack = []
        while stack:
            x = stack.pop()
            if isinstance(x, dict):
                n += sum(1 for k, v in x.items() if k in ID_FIELDS and isinstance(v, str) and not is_pseudonym(v))
                stack += list(x.values())
            elif isinstance(x, list):
                stack += x
    return n


def pull(run_ids: list[str], repo: str, reason: str) -> int:
    """★ 2026-09-28: archive_run() 的第一个调用方(此前零调用, 「每个 run 都归档」只是散文)。
    手动按 run_id 拉取 artifact → 化名闸 → 落 archive/<run_id>/ → 入册。含非化名身份的 run 不进树, 大声报出。
    ponytail: 手动指定 run_id; 「每个 run 完成时自动归档」仍未接线(见 cce_open_items)。"""
    import subprocess
    import tempfile
    import time
    index = json.load(open(INDEX, encoding="utf-8"))
    bad = 0
    for rid in run_ids:
        meta = json.loads(subprocess.run(["gh", "api", f"repos/{repo}/actions/runs/{rid}"],
                                         capture_output=True, text=True, check=True).stdout)
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(["gh", "run", "download", rid, "-R", repo, "-D", td], check=True, capture_output=True)
            arts = {}
            for dp, _, fs in os.walk(td):
                for f in fs:
                    rel = os.path.relpath(os.path.join(dp, f), td)
                    arts[rel.replace(os.sep, "__")] = open(os.path.join(dp, f), "rb").read()
        hits = sum(_identity_hits(n, b) for n, b in arts.items())
        if hits:
            print(f"✗ {rid}: {hits} 处非化名身份 ⇒ 不进仓库树(应走 RESTRICTED_OFFTREE 进保险库)")
            bad += 1
            continue
        archive_run(rid, {"run_id": rid, "repo": repo, "url": meta["html_url"], "workflow": meta["path"],
                          "head_sha": meta["head_sha"], "event": meta["event"], "display_title": meta["display_title"],
                          "conclusion": meta["conclusion"], "created_at": meta["created_at"],
                          "recovered_at": time.strftime("%Y-%m-%d")}, arts)
        index["runs"][rid] = {"status": LOCALLY_ARCHIVED, "referenced_in": ["config/cce_archive_index.json"],
                              "reason": reason, "checked_against": [repo], "checked_at": meta["updated_at"][:10],
                              "local_path": f"archive/{rid}", "files": len(arts) + 1,
                              "★rebuildable_locally": "是。经 cce_archive.py --pull 逐件落档(过化名闸)"}
        print(f"✓ {rid}: {len(arts)} 个文件落 archive/{rid}")
    with open(INDEX, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(index, ensure_ascii=False, indent=1) + "\n")
    return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--pull":
        # 用法: cce_archive.py --pull <run_id>... [--repo owner/name] [--reason 文本]
        args, repo, reason = sys.argv[2:], "luogangan7-lgtm/cce-engine-oss", "手动拉取归档"
        if "--repo" in args:
            i = args.index("--repo"); repo = args[i + 1]; args = args[:i] + args[i + 2:]
        if "--reason" in args:
            i = args.index("--reason"); reason = args[i + 1]; args = args[:i] + args[i + 2:]
        sys.exit(pull(args, repo, reason))
    sys.exit(main())
