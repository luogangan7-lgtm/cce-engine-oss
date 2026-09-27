# -*- coding: utf-8 -*-
"""闸: CI contract job 不许空跑。2026-09-24 两次真实 run 才暴露: 私仓 contract job 用 `python3 tests/test_x.py` 循环 —— pytest 风格文件 0 断言恒绿, 遇 `import pytest` 直接崩(runner 没装 pytest)。
守: ① workflow 合同步骤跑 probes/dev_runsuite.py 而不是裸循环 ② requirements 含 pytest ③ dev_runsuite 对 pytest 风格文件选 pytest 命令、有真红时非零退出。"""
import importlib.util, pathlib, re, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_workflow_contract_step_uses_runsuite_not_bare_loop():
    wf = (ROOT / ".github/workflows/cce-submit.yml").read_text(encoding="utf-8")
    step = wf.split("Submission, content, subject-window, cross-plane and response gates")[1].split("      - name:")[0]
    assert "python3 probes/dev_runsuite.py" in step and 'for t in tests/test_*.py' not in step
    assert re.search(r"^pytest", (ROOT / "requirements.txt").read_text(encoding="utf-8"), re.M)


def test_runsuite_routes_pytest_style_to_pytest_and_exits_nonzero_on_red():
    s = importlib.util.spec_from_file_location("_rs", ROOT / "probes/dev_runsuite.py"); src = (ROOT / "probes/dev_runsuite.py").read_text(encoding="utf-8")
    assert "sys.exit(1 if real else 0)" in src and 'glob("test_*.py")' in src   # 遍历同一集合 tests/test_*.py, 不退回硬编码清单
    with tempfile.TemporaryDirectory() as tmp:
        a = pathlib.Path(tmp) / "test_a.py"; a.write_text("def test_x():\n    assert True\n", encoding="utf-8")
        b = pathlib.Path(tmp) / "test_b.py"; b.write_text("assert 1 == 1\n", encoding="utf-8")
        ns = {}; exec(compile("import re, sys\n" + src.split("def cmd(t):")[0].split("\n")[-1] + "def cmd(t):" + src.split("def cmd(t):")[1].split("\n")[0], "cmd", "exec"), ns)
        assert "pytest" in " ".join(ns["cmd"](a)) and "pytest" not in " ".join(ns["cmd"](b))


def test_runsuite_has_no_machine_path_and_refuses_zero_tests():
    """★ 2026-09-24 第二次空跑(公仓 PR #2 的 contract job): ROOT 写死本机绝对路径 ⇒ runner 上 0 个测试 ⇒「绿 0/红 0」恒绿。
    守: ① probes/ 与 workflows 里不许出现本机绝对路径(字面量在闸里拼接) ② 真跑一份复制到临时目录的 runsuite: 空 tests/ 必须非零退出, 有一个 pytest 风格测试时报 绿 1。"""
    local_prefix = "/" + "Volumes/" + "data"   # 拼出来: 本闸自己不许含这个字面量(仓外素材闸会把它当成依赖)
    for rel in ("probes/dev_runsuite.py", "probes/dev_refresh_cov.py", ".github/workflows/cce-submit.yml"):
        assert local_prefix not in (ROOT / rel).read_text(encoding="utf-8"), rel
    src = (ROOT / "probes/dev_runsuite.py").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp); (root / "probes").mkdir(); (root / "tests").mkdir()
        rs = root / "probes" / "dev_runsuite.py"; rs.write_text(src, encoding="utf-8")
        p = subprocess.run([sys.executable, str(rs)], capture_output=True, text=True, cwd=tmp, timeout=120)
        assert p.returncode != 0 and "空跑" in p.stdout, (p.returncode, p.stdout)
        (root / "tests" / "test_one.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
        p = subprocess.run([sys.executable, str(rs)], capture_output=True, text=True, cwd=tmp, timeout=300)
        assert p.returncode == 0 and "绿 1 / 红 0" in p.stdout, (p.returncode, p.stdout, p.stderr)
        (root / "tests" / "test_two.py").write_text("def test_y():\n    assert False\n", encoding="utf-8")
        p = subprocess.run([sys.executable, str(rs)], capture_output=True, text=True, cwd=tmp, timeout=300)
        assert p.returncode == 1 and "真红 1" in p.stdout, (p.returncode, p.stdout)


def test_runsuite_names_parallel_only_reds_without_failing():
    """★ 2026-09-27: 两次「并行红 1 / 串行真红 0」, 旧 runsuite 不报名字 ⇒ 查不出是谁。
    埋一对互抢同一把排他锁文件的测试: 并行必有一个红、串行都绿。守: 退出码仍 0(不是真红), 但必须点名「仅并行红 1」+ 测试名 + 并行那次的报错尾巴。"""
    src = (ROOT / "probes/dev_runsuite.py").read_text(encoding="utf-8")
    body = ("import os, pathlib, time\n"
            "def test_hold():\n"
            "    lock = pathlib.Path(__file__).parent / 'shared.lock'\n"
            "    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)  # 并发时第二个进程在这里 FileExistsError\n"
            "    try: time.sleep(4)\n"
            "    finally: os.close(fd); lock.unlink()\n")
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp); (root / "probes").mkdir(); (root / "tests").mkdir()
        rs = root / "probes" / "dev_runsuite.py"; rs.write_text(src, encoding="utf-8")
        for n in ("a", "b"): (root / "tests" / ("test_lock_%s.py" % n)).write_text(body, encoding="utf-8")
        p = subprocess.run([sys.executable, str(rs)], capture_output=True, text=True, cwd=tmp, timeout=300)
        assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
        assert "绿 1 / 红 1" in p.stdout and "真红 0" in p.stdout and "[仅并行红] 1" in p.stdout, p.stdout
        named = re.findall(r"^### \[仅并行红\] (test_lock_[ab]\.py)$", p.stdout, re.M)
        assert len(named) == 1 and "FileExistsError" in p.stdout.split("### [仅并行红]")[1], p.stdout
