# -*- coding: utf-8 -*-
"""候选隔离: 跑完整假后端 suite 后, 仓库树里除 reports 目标目录外零新文件; 源码不写生产产物名。"""
import json
import os
import re
from pathlib import Path

from experiments.jev import run_suite as RS
from experiments.jev.tests.fakes import FakeBackend, FakeTokenizer, fake_upstream

ROOT = Path(__file__).resolve().parents[3]
JEV = ROOT / "experiments" / "jev"
CFG = {"temperature": 1.3, "version": "v10", "isolated_levels": True, "max_options": 255, "schema_first": False, "neutralize_none": False}


def _snapshot(root):
    out = {}
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in (".git", "__pycache__", "node_modules", ".pytest_cache")]
        for f in fn:
            p = Path(dp) / f
            try:
                out[str(p)] = p.stat().st_mtime_ns
            except OSError:
                pass
    return out


def test_full_fake_run_writes_only_into_report_dir(tmp_path):
    before = _snapshot(ROOT)
    policy = json.loads((JEV / "policies" / "cpu_smoke.json").read_text(encoding="utf-8"))
    rep = RS.run("s0-smoke-v1", tmp_path / "reports" / "x", policy, CFG, {"model_version": "v10"}, lambda L: FakeBackend(L), FakeTokenizer, fake_upstream)
    assert rep["execution_status"] == "SUCCEEDED"
    after = _snapshot(ROOT)
    changed = {p for p in set(before) | set(after) if before.get(p) != after.get(p) and "__pycache__" not in p}
    assert not changed, changed


def test_sources_never_name_production_outputs():
    forbidden = re.compile(r"s0_context\.json|cce_population|\"usable\"|complete\s*=\s*True|results/")
    for p in sorted(JEV.glob("*.py")):
        src = p.read_text(encoding="utf-8")
        for line in src.splitlines():
            if line.strip().startswith("#") or '"""' in line or "PRODUCTION_FORBIDDEN" in line or "writes" in line.lower():
                continue
            assert not forbidden.search(line), (p.name, line)
