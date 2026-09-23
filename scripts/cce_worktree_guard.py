#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""原始工作区写入边界 —— DEV-002 的根因修补。**范围只到本次候选修改。**

★★★★ 它是什么, 更要紧的是它**不是**什么(web GPT 第十轮原话):
  「若执行者还能自行撤掉只读、改保护配置, 或者通过同一套工具访问不受限的原路径,
    那么**只能登记为可绕过的防误写措施, 不能叫权限闭合**。」
  ⇒ 我(本执行者)仍握有 shell、仓写权、以及**改本文件的权限**。
    **本模块是防误写 + 可发现, 不是不可绕过的边界。** 这句话有测试钉住, 不许被删。

★★ 两个**不能混淆**的证明(第十轮):
  · **前后哈希相同** ⇒ 只证明「**这次检查到的原件没有变化**」
  · **执行者没有相应写权限** ⇒ 才是在「**约束下一次能做什么**」
  本模块只提供前者。**后者需要 owner 或运行环境持有, 我做不到。**

★★★ 关键陷阱(第十轮点名):
  「副本**必须反映当前工作树中的相关未提交、未跟踪内容**,
    **不能只从 HEAD 建一个新 worktree, 就当成已经保存了当前工作**。」
  ⇒ snapshot() 复制的是**工作树当前字节**, 与 git 状态无关。有反向测试钉住。
"""
import hashlib, json, os, pathlib, shutil, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
LEDGER = ROOT / "results" / ".worktree_guard.json"


class OriginalChanged(RuntimeError):
    """★ 原件在快照之后被改动过 ⇒ **拒绝回写**, 不许覆盖别人的改动(DEV-002 的形态)。"""


def _sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def _load():
    if LEDGER.exists():
        return json.loads(LEDGER.read_text(encoding="utf-8") or "{}")
    return {"snapshots": {}}


def _save(d):
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def snapshot(paths, note=""):
    """把**工作树当前字节**复制到可丢弃副本, 并记下原件 sha。

    ★ 复制的是**磁盘上现在的内容** —— 未提交/未跟踪的一律带走。
      **不走 git**: `git worktree add` / `git archive HEAD` 都只给 HEAD 的字节。
    """
    d = _load()
    sid = hashlib.sha256((repr(sorted(map(str, paths))) + note).encode()).hexdigest()[:12]
    copy_dir = pathlib.Path(tempfile.mkdtemp(prefix=f"wtguard_{sid}_"))
    rec = {"note": note, "copy_dir": str(copy_dir), "files": {}}
    for rel in paths:
        src = ROOT / rel
        if not src.exists():
            raise FileNotFoundError(f"★ 要保护的原件不存在: {rel}")
        dst = copy_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)                       # ★ 字节级复制, 不经 git
        rec["files"][rel] = {"sha_at_snapshot": _sha(src), "size": src.stat().st_size}
    d["snapshots"][sid] = rec
    _save(d)
    return sid, copy_dir


def impact(sid):
    """回写前先算**影响面** —— 哪些文件会变、变多少行。不做任何写入。"""
    d = _load()["snapshots"][sid]
    out = []
    for rel, meta in d["files"].items():
        src, cp = ROOT / rel, pathlib.Path(d["copy_dir"]) / rel
        now, edited = _sha(src), _sha(cp)
        changed_by_me = edited != meta["sha_at_snapshot"]
        changed_underneath = now != meta["sha_at_snapshot"]
        diff = subprocess.run(["diff", "-u", str(src), str(cp)], capture_output=True, text=True).stdout
        out.append({"文件": rel, "副本里被我改过": changed_by_me,
                    "★原件在快照后被别人改过": changed_underneath,
                    "净增删行": sum(1 for l in diff.splitlines()
                                 if l[:1] in "+-" and not l.startswith(("+++", "---")))})
    return out


def apply(sid, authorized_by=None):
    """把副本回写原件。**四道检查, 缺一拒绝。**"""
    d = _load()
    rec = d["snapshots"][sid]
    imp = impact(sid)

    # ① 原件在快照之后被改动过 ⇒ 拒绝(**这正是 DEV-002 的形态: 覆盖了别人的未提交改动**)
    drift = [x["文件"] for x in imp if x["★原件在快照后被别人改过"]]
    if drift:
        raise OriginalChanged(
            f"★★★ 原件在快照之后变了: {drift} —— **拒绝回写**。"
            "覆盖别人的未提交改动正是 DEV-002 的形态。请重新 snapshot 并合并。")
    # ② 必须有授权标识
    if not authorized_by:
        raise PermissionError(
            "★ 回写原件需要 authorized_by。★★ 但**我自己就能填它** ⇒ "
            "**这是流程提示, 不是权限约束**(见模块 docstring)。")
    # ③ 无改动则不写(避免无意义的 mtime 扰动)
    todo = [x["文件"] for x in imp if x["副本里被我改过"]]
    if not todo:
        return {"applied": [], "reason": "副本与快照一致, 无需回写"}
    # ④ 回写前把**原件当前字节**再存一份(可回滚)
    rollback = pathlib.Path(tempfile.mkdtemp(prefix=f"wtrollback_{sid}_"))
    for rel in todo:
        (rollback / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, rollback / rel)
        shutil.copy2(pathlib.Path(rec["copy_dir"]) / rel, ROOT / rel)
    rec["applied"] = {"files": todo, "authorized_by": authorized_by,
                      "rollback_dir": str(rollback),
                      "sha_after": {rel: _sha(ROOT / rel) for rel in todo}}
    _save(d)
    return {"applied": todo, "rollback_dir": str(rollback), "authorized_by": authorized_by}


def what_this_is_not():
    return {
     "★★★★它不是权限闭合": "我(本执行者)仍握有 shell、仓写权、**以及改本文件的权限** ⇒ "
                  "按 web GPT 第十轮, **只能登记为「可绕过的防误写措施」**。",
     "★两个不能混淆的证明": {
       "前后哈希相同": "只证明「**这次检查到的原件没有变化**」",
       "执行者没有相应写权限": "**才是**在「约束下一次能做什么」 —— **本模块不提供这个**"},
     "★真边界需要谁持有": "**owner 或运行环境。** 需要移走的是「**本次执行 agent 自行解除限制的能力**」。",
     "★它确实提供的": ["副本带走**工作树当前字节**(含未提交/未跟踪), 不走 git",
                 "回写前**检测原件是否在快照后被改过**, 是则**拒绝回写**(DEV-002 的形态)",
                 "回写前给**影响面**", "回写时留**可回滚副本**"],
     "★范围": "**只做本次候选修改需要的隔离**, 不是「工作区治理」整章。",
    }


if __name__ == "__main__":
    print(json.dumps({"block": "WORKTREE_GUARD", "★这不是什么": what_this_is_not()},
                     ensure_ascii=False, indent=1))
