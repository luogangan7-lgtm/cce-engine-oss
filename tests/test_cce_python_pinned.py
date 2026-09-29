# -*- coding: utf-8 -*-
"""闸: Python 版本与依赖版本本机/CI 同步(owner 2026-09-29「Python版本需要同步」)。

起因: 本机 3.14 / CI 3.11, 3.12 起内建 sum() 对浮点改为补偿求和 ⇒ 同一份结果本机逐字复现、CI 红;
依赖不钉版本 ⇒ 本机 rapidocr 1.2.3(连 requirements 的 >=1.3 都不满足)、CI 装 1.4.4, 测的不是生产跑的那个 OCR。
单一真相源: .python-version(解释器) + constraints.txt(全部传递依赖, uv pip compile 生成)。
"""
import pathlib, re, sys
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
WANT = (ROOT / ".python-version").read_text(encoding="utf-8").strip()


def test_this_interpreter_is_the_pinned_one():
    assert re.fullmatch(r"3\.\d+", WANT), WANT
    assert "%d.%d" % sys.version_info[:2] == WANT, "★ 跑测试的解释器与 .python-version 不符 —— 本机用 .venv/bin/python"


def test_every_setup_python_reads_the_pin_file():
    n = 0
    for f in sorted((ROOT / ".github/workflows").glob("*.yml")):
        wf = yaml.safe_load(f.read_text(encoding="utf-8"))
        for jn, job in (wf.get("jobs") or {}).items():
            for st in job.get("steps") or []:
                if "actions/setup-python" in str(st.get("uses", "")):
                    w = st.get("with") or {}
                    assert w.get("python-version-file") == ".python-version" and "python-version" not in w, (f.name, jn, w)
                    n += 1
    assert n >= 20, n


def test_requirements_go_through_the_lock():
    lock = (ROOT / "constraints.txt").read_text(encoding="utf-8")
    pinned = {re.split(r"[=<>; ]", l)[0].lower().replace("_", "-") for l in lock.splitlines() if "==" in l and not l.startswith("#")}
    for req in ("requirements.txt", "requirements-media.txt"):
        lines = [l.split("#")[0].strip() for l in (ROOT / req).read_text(encoding="utf-8").splitlines()]
        assert "-c constraints.txt" in lines, req
        for l in lines:
            if l and not l.startswith("-"):
                name = re.split(r"[=<>!~ \[]", l)[0].lower().replace("_", "-")
                assert name in pinned, (req, name)


def test_runsuite_refuses_a_wrong_interpreter():
    src = (ROOT / "probes/dev_runsuite.py").read_text(encoding="utf-8")
    assert '.python-version' in src and 'sys.exit(3)' in src and "env=_ENV" in src
