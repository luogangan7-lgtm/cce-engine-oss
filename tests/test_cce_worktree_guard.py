#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闸: 工作区写入边界 —— 重点是**它真能拦住 DEV-002 那条路径**, 且**不许自称权限闭合**。"""
import json, pathlib, shutil, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import cce_worktree_guard as G  # noqa: E402


def _sandbox():
    """★ 在临时目录里造一个**带未提交/未跟踪内容**的 git 仓, 不碰真仓。"""
    d = pathlib.Path(tempfile.mkdtemp(prefix="wtg_test_"))
    subprocess.run(["git", "init", "-q", str(d)], check=True)
    subprocess.run(["git", "-C", str(d), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(d), "config", "user.name", "t"], check=True)
    (d / "tracked.py").write_text("committed = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(d), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(d), "commit", "-qm", "base"], check=True)
    # 未提交改动 + 未跟踪文件
    (d / "tracked.py").write_text("committed = 1\nUNCOMMITTED = 2\n", encoding="utf-8")
    (d / "untracked.py").write_text("UNTRACKED = 3\n", encoding="utf-8")
    return d


def _with_root(d, fn):
    old_root, old_ledger = G.ROOT, G.LEDGER
    G.ROOT, G.LEDGER = d, d / ".ledger.json"
    try:
        return fn()
    finally:
        G.ROOT, G.LEDGER = old_root, old_ledger


def test_copy_carries_worktree_bytes_not_HEAD():
    """★★★ 第十轮点名的陷阱: **只从 HEAD 建 worktree 不算保存了当前工作。**
    反向对照: 同一份材料用 `git archive HEAD` 取, 未提交改动与未跟踪文件**会丢**。"""
    d = _sandbox()
    try:
        sid, copy_dir = _with_root(d, lambda: G.snapshot(["tracked.py", "untracked.py"], "t"))
        assert "UNCOMMITTED" in (copy_dir / "tracked.py").read_text(encoding="utf-8"), \
            "★★★ 副本丢了未提交改动"
        assert (copy_dir / "untracked.py").exists(), "★★★ 副本丢了未跟踪文件"
        # ★ 反向对照: HEAD 路线确实会丢 —— 证明这个检查有区分度
        head = subprocess.run(["git", "-C", str(d), "show", "HEAD:tracked.py"],
                              capture_output=True, text=True).stdout
        assert "UNCOMMITTED" not in head, "★ 对照失效: HEAD 里居然有未提交内容"
        ls = subprocess.run(["git", "-C", str(d), "ls-tree", "--name-only", "HEAD"],
                            capture_output=True, text=True).stdout
        assert "untracked.py" not in ls, "★ 对照失效: HEAD 里居然有未跟踪文件"
        return True
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_it_refuses_to_overwrite_changes_made_after_snapshot():
    """★★★★ DEV-002 的形态: 回写会**覆盖别人在此期间的改动**。必须**拒绝**。"""
    d = _sandbox()
    try:
        def go():
            sid, cp = G.snapshot(["tracked.py"], "t")
            (cp / "tracked.py").write_text("MY_EDIT = 1\n", encoding="utf-8")     # 我在副本里改
            (d / "tracked.py").write_text("SOMEONE_ELSE = 9\n", encoding="utf-8")  # 别人改了原件
            try:
                G.apply(sid, authorized_by="test")
                return "**没拦住 —— 闸失效**"
            except G.OriginalChanged as e:
                return str(e)
        msg = _with_root(d, go)
        assert "拒绝回写" in msg and "DEV-002" in msg, msg
        assert (d / "tracked.py").read_text(encoding="utf-8") == "SOMEONE_ELSE = 9\n", \
            "★★★ 别人的改动被覆盖了 —— 这正是要防的事"
        return True
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_normal_apply_works_and_leaves_a_rollback():
    """★ 合法路径必须能走通 —— **一个永远拒绝的闸同样能通过全部负例**。"""
    d = _sandbox()
    try:
        def go():
            sid, cp = G.snapshot(["tracked.py"], "t")
            (cp / "tracked.py").write_text("MY_EDIT = 1\n", encoding="utf-8")
            imp = G.impact(sid)
            assert imp[0]["副本里被我改过"] is True
            assert imp[0]["★原件在快照后被别人改过"] is False
            return G.apply(sid, authorized_by="test")
        r = _with_root(d, go)
        assert r["applied"] == ["tracked.py"]
        assert (d / "tracked.py").read_text(encoding="utf-8") == "MY_EDIT = 1\n"
        rb = pathlib.Path(r["rollback_dir"]) / "tracked.py"
        assert rb.exists() and "UNCOMMITTED" in rb.read_text(encoding="utf-8"), \
            "★ 回滚副本没留住回写前的字节"
        return True
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_authorization_is_required_but_declared_bypassable():
    """★★ 授权是**流程提示不是权限约束** —— 报错文案必须自己说清这一点。"""
    d = _sandbox()
    try:
        def go():
            sid, cp = G.snapshot(["tracked.py"], "t")
            (cp / "tracked.py").write_text("X = 1\n", encoding="utf-8")
            try:
                G.apply(sid)
                return "**没要求授权**"
            except PermissionError as e:
                return str(e)
        msg = _with_root(d, go)
        assert "我自己就能填它" in msg and "不是权限约束" in msg, msg
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_it_never_calls_itself_a_permission_closure():
    """★★★★ 最重要: 它必须**自陈不是权限闭合**, 且分清两个证明。这段不许被删。"""
    n = G.what_this_is_not()
    assert "不能叫权限闭合" in n["★★★★它不是权限闭合"] or "可绕过的防误写措施" in n["★★★★它不是权限闭合"]
    assert "改本文件的权限" in n["★★★★它不是权限闭合"], "★ 必须承认我能改它自己"
    p = n["★两个不能混淆的证明"]
    assert "这次检查到的原件没有变化" in p["前后哈希相同"]
    assert "本模块不提供这个" in p["执行者没有相应写权限"]
    assert "自行解除限制的能力" in n["★真边界需要谁持有"]
    assert "不是「工作区治理」整章" in n["★范围"], "★ 范围必须限定在本次候选修改"
    src = (ROOT / "scripts/cce_worktree_guard.py").read_text(encoding="utf-8")
    assert "不是不可绕过的边界" in src, "★ 源码里的自陈被删了"


if __name__ == "__main__":
    a = test_copy_carries_worktree_bytes_not_HEAD()
    b = test_it_refuses_to_overwrite_changes_made_after_snapshot()
    c = test_normal_apply_works_and_leaves_a_rollback()
    test_authorization_is_required_but_declared_bypassable()
    test_it_never_calls_itself_a_permission_closure()
    print("test_cce_worktree_guard: OK ("
          "★★★★**它真能拦住 DEV-002 那条路径**: 我在副本里改、别人同时改了原件 ⇒ "
          "**拒绝回写**, 且实测**别人的改动没被覆盖** | "
          "★★★副本带走的是**工作树当前字节**(未提交改动 + 未跟踪文件都在), "
          "反向对照证明 **HEAD 路线两样都会丢** —— 这正是第十轮点名的陷阱 | "
          "★合法路径仍走得通并留**可回滚副本**(一个永远拒绝的闸同样能过全部负例) | "
          "★★授权报错文案**自己说明**「我自己就能填它, 这是流程提示不是权限约束」 | "
          "★★★★它**自陈不是权限闭合**: 我仍握 shell+仓写权+**改它自己的权限** ⇒ "
          "只能登记为**可绕过的防误写措施**; 「前后哈希相同」只证明这次原件没变, "
          "「执行者没有写权限」才约束下一次 —— **本模块不提供后者, 真边界需 owner 或运行环境持有**)")
