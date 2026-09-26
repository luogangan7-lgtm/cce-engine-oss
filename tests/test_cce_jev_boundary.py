# -*- coding: utf-8 -*-
"""桥闸: 把 experiments/jev/tests 接进既有测试发现路径(tests/test_cce_*.py ⇒ dev_runsuite / CI contract job 都会跑到)。
守: ① 子套件真被发现且全绿、零 skip ② 本机 guard 拒绝 ③ 全仓 requirements 不含模型依赖 ④ 资产锁由 GitHub prepare 生成并经评审、许可带 owner 引用。"""
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JEV = ROOT / "experiments" / "jev"


def test_jev_pure_suite_is_discovered_and_green(tmp_path):
    junit = tmp_path / "junit.xml"
    env = {k: v for k, v in os.environ.items() if not k.startswith("GITHUB_")}; env["PYTHONDONTWRITEBYTECODE"] = "1"
    p = subprocess.run([sys.executable, "-m", "pytest", str(JEV / "tests"), "-q", "-p", "no:cacheprovider", "--assert=plain", f"--junitxml={junit}"],
                       cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=900)
    assert junit.is_file(), p.stdout[-2000:] + p.stderr[-2000:]
    root = ET.parse(junit).getroot(); suites = [root] if root.tag == "testsuite" else list(root)
    tests = sum(int(s.get("tests", 0)) for s in suites); fails = sum(int(s.get("failures", 0)) + int(s.get("errors", 0)) for s in suites)
    skipped = sum(int(s.get("skipped", 0)) for s in suites)
    assert tests >= 40 and fails == 0 and skipped == 0 and p.returncode == 0, (tests, fails, skipped, p.stdout[-3000:])


def test_local_guard_and_repo_boundaries():
    sys.path.insert(0, str(ROOT))
    from experiments.jev import execution_guard as G
    from experiments.jev.contracts import JevError
    try:
        G.require({k: v for k, v in os.environ.items() if not k.startswith("GITHUB_")}, None)
        raise AssertionError("guard passed on a plain machine")
    except JevError as e:
        assert e.code == "EXECUTION_LOCATION_FORBIDDEN"
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "torch" not in req and "transformers" not in req and "decider" not in req
    al = json.loads((JEV / "locks" / "model.assets.lock.json").read_text(encoding="utf-8"))
    assert al["status"] == "READY" and al.get("generated_by", "").startswith("cce-jev-prepare.yml") and al["reviewed"]["run"].startswith("https://github.com/")
    for pf in (JEV / "permits").glob("*.json"):
        assert json.loads(pf.read_text(encoding="utf-8"))["owner_approval_reference"].strip(), pf.name
    assert not list(ROOT.rglob("*.safetensors")) and not list(ROOT.rglob("*.gguf"))
