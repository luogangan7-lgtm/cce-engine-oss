# -*- coding: utf-8 -*-
"""import / --help / 测试发现: 不 import torch·transformers·decider·huggingface_hub, 不联网, 不读 .env。"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
JEV = ROOT / "experiments" / "jev"
HEAVY = ("torch", "transformers", "decider", "huggingface_hub", "safetensors", "tokenizers", "requests", "dotenv")


def _run(code, extra_env=None):
    import os
    env = {k: v for k, v in os.environ.items() if not k.startswith("GITHUB_")}; env["PYTHONDONTWRITEBYTECODE"] = "1"; env.update(extra_env or {})
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(ROOT), env=env, timeout=120)


def test_importing_every_module_loads_no_heavy_dependency_and_opens_no_socket():
    mods = ["experiments.jev." + p.stem for p in sorted(JEV.glob("*.py")) if p.stem != "cli"]
    code = ("import socket, sys\n"
            "def _boom(*a, **k): raise AssertionError('network call at import')\n"
            "socket.socket.connect = _boom; socket.create_connection = _boom\n"
            "import importlib\n"
            + "\n".join(f"importlib.import_module({m!r})" for m in mods) + "\n"
            f"print('HEAVY', [m for m in {HEAVY!r} if m in sys.modules])")
    p = _run(code)
    assert p.returncode == 0, p.stderr
    assert "HEAVY []" in p.stdout, p.stdout


def test_cli_help_and_check_locks_and_plan_are_pure():
    for argv in (["--help"], ["check-locks"], ["plan", "--suite", "s0-smoke-v1"], ["plan", "--suite", "s0-compare-v1"], ["suite-files", "--suite", "s0-compare-v1"]):
        code = ("import runpy, sys, socket\n"
                "def _boom(*a, **k): raise AssertionError('network call')\n"
                "socket.socket.connect = _boom; socket.create_connection = _boom\n"
                f"sys.argv = ['cli.py'] + {argv!r}\n"
                "try:\n    runpy.run_path(%r, run_name='__main__')\nexcept SystemExit as e:\n    assert e.code in (0, None), e.code\n"
                f"print('HEAVY', [m for m in {HEAVY!r} if m in sys.modules])") % str(JEV / "cli.py")
        p = _run(code)
        assert p.returncode == 0, (argv, p.stderr, p.stdout)
        assert "HEAVY []" in p.stdout, (argv, p.stdout)


def test_no_dotenv_or_env_file_reads_and_heavy_imports_are_lazy():
    for p in sorted(JEV.rglob("*.py")):
        if "tests" in p.parts:
            continue
        src = p.read_text(encoding="utf-8")
        assert ".env" not in src.replace("os.environ", "").replace("dict(os.environ)", ""), p
        assert "dotenv" not in src and "MINIMAX" not in src and "TYPESAFE" not in src and "exp_crossmodel_desire" not in src, p
        for line in src.splitlines():
            s = line.strip()
            if re.match(r"^(import|from)\s+(torch|transformers|decider|huggingface_hub)\b", s):
                assert line.startswith("    "), f"{p}: top-level heavy import: {s}"


def test_requirements_have_no_model_dependencies():
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    for bad in ("torch", "transformers", "decider", "flash-linear", "huggingface"):
        assert bad not in req, bad
