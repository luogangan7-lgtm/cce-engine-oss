# -*- coding: utf-8 -*-
"""三个 workflow 的结构合同(不依赖 PyYAML): 触发 · 权限 · runner · SHA 固定 · persist-credentials · 输入不进 run: · 无模型 secret · 无 pull_request_target。"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WF = ROOT / ".github" / "workflows"
ACTS = json.loads((ROOT / "experiments" / "jev" / "locks" / "actions.lock.json").read_text(encoding="utf-8"))
SUITES = sorted(p.stem for p in (ROOT / "experiments" / "jev" / "suites").glob("*.jsonl"))


def _wf(name):
    return (WF / name).read_text(encoding="utf-8")


def _uses(text):
    return [m.group(1).strip() for m in re.finditer(r"uses:\s*([^\s#]+)", text)]


def _run_blocks(text):
    out, cur = [], None
    for line in text.splitlines():
        if re.match(r"\s*run:\s*\|", line):
            cur = []; out.append(cur); continue
        if re.match(r"\s*run:\s*\S", line):
            out.append([line.split("run:", 1)[1]]); cur = None; continue
        if cur is not None:
            if line.strip() and not line.startswith(" " * 10) and re.match(r"\s{0,8}\S", line) and not line.startswith("          "):
                cur = None
            else:
                cur.append(line)
    return ["\n".join(b) for b in out]


def test_every_action_pinned_to_full_sha_in_lock_and_checkout_without_credentials():
    for wf in ("cce-jev-contract.yml", "cce-jev-prepare.yml", "cce-jev-eval.yml"):
        text = _wf(wf)
        for ref in _uses(text):
            action, _, sha = ref.partition("@")
            base = "/".join(action.split("/")[:2])
            assert re.fullmatch(r"[0-9a-f]{40}", sha), (wf, ref)
            assert base in ACTS and ACTS[base]["sha"] == sha, (wf, ref)
        assert text.count("actions/checkout@") == text.count("persist-credentials: false"), wf
        assert "ubuntu-24.04" in text and "self-hosted" not in text and "ubuntu-latest" not in text and "macos" not in text, wf
        for bad in ("pull_request_target", "workflow_run", "issue_comment", "repository_dispatch", "schedule:"):
            assert bad not in text, (wf, bad)
        assert "MINIMAX" not in text and "TYPESAFE" not in text and "HF_TOKEN" not in text, wf


def test_contract_workflow_is_pure():
    t = _wf("cce-jev-contract.yml")
    assert re.search(r"^permissions:\s*\n\s+contents: read", t, re.M)
    assert "pull_request" in t and "push" in t and "workflow_dispatch" not in t.split("jobs:")[0].replace("workflow_dispatch: {}", "")
    for bad in ("hf_hub_download", "huggingface", "docker", "actions/cache", "from_pretrained"):
        assert bad not in t, bad
    assert not re.search(r"pip install[^\n]*(torch|transformers|decider|huggingface)", t), "model dependency installed in contract job"
    assert "pytest" in t and "experiments/jev/tests" in t and "tests/test_cce_jev_boundary.py" in t and "junit_gate.py" in t


def test_prepare_and_eval_are_manual_single_permit_and_split_permissions():
    for wf in ("cce-jev-prepare.yml", "cce-jev-eval.yml"):
        t = _wf(wf)
        head = t.split("jobs:")[0]
        assert "workflow_dispatch:" in head and "push:" not in head and "pull_request" not in head, wf
        assert "permit_id:" in head and "cancel-in-progress: false" in head, wf
        assert re.search(r"^permissions:\s*\n\s+contents: read", t, re.M), wf
        admit = t.split("  admit:")[1].split("\n  " + ("prepare:" if "prepare" in wf else "evaluate:"))[0]
        assert "contents: write" in admit and "cce_jev_admit.py" in admit and "docker" not in admit and "pip install" not in admit, wf
        rest = t.split("\n  " + ("prepare:" if "prepare" in wf else "evaluate:"))[1]
        assert "contents: write" not in rest and "needs: admit" in rest and "GITHUB_TOKEN" not in rest, wf
        assert "ref: ${{ github.sha }}" in rest, wf
        # 输入只经 env 进入脚本, 绝不拼进 run:
        for blk in _run_blocks(t):
            assert "${{ inputs." not in blk and "github.event.inputs" not in blk, (wf, blk[:120])
    ev = _wf("cce-jev-eval.yml")
    assert "name: CCE Decider Candidate Evaluation" in ev and "group: cce-decider-candidate-eval" in ev
    opts = re.search(r"options:\s*\[([^\]]*)\]", ev).group(1)
    assert sorted(o.strip() for o in opts.split(",")) == SUITES == ["s0-smoke-v1"]
    for flag in ("--network none", "--read-only", "--cap-drop ALL", "no-new-privileges", "--memory-swap 12g", "--cpus 3", "--user 1001:1001", "--pids-limit"):
        assert flag in (ROOT / "experiments" / "jev" / "runtime" / "run_remote_only.sh").read_text(encoding="utf-8"), flag
    assert "restore-keys" not in ev and "fail-on-cache-miss" in ev
    assert "check-upload" in ev and "if: always()" in ev and "retention-days: 7" in ev


def test_locks_are_consistent_and_ready_after_github_prepare():
    L = ROOT / "experiments" / "jev" / "locks"
    src = json.loads((L / "model.source.lock.json").read_text(encoding="utf-8"))
    assets = json.loads((L / "model.assets.lock.json").read_text(encoding="utf-8"))
    rt = json.loads((L / "cpu-runtime.lock.json").read_text(encoding="utf-8"))
    import hashlib
    assert assets["revision"] == src["revision"] and assets["status"] == "READY" and set(assets["files"]) == set(src["files"])
    for name, spec in src["files"].items():           # 资产锁与源锁元数据锚点一致(GitHub 自算 sha == HF LFS sha)
        assert assets["files"][name]["size"] == spec["size"], name
        if spec["anchor"]["kind"] == "lfs_sha256":
            assert assets["files"][name]["sha256"] == spec["anchor"]["value"], name
    assert rt["status"] == "READY" and rt["dependency_lock_sha256"] == hashlib.sha256((L / "runtime-cpu.lock.txt").read_bytes()).hexdigest()
    dep = (L / "runtime-cpu.lock.txt").read_text(encoding="utf-8")
    assert "torch==2.14.0+cpu" in dep and "--hash=sha256:" in dep and "flash-linear-attention" not in dep and "triton" not in dep
    assert rt["base_image_digest"].startswith("sha256:") and rt["base_image_digest"] in (ROOT / "experiments" / "jev" / "runtime" / "Dockerfile.cpu").read_text()
    for pf in (ROOT / "experiments" / "jev" / "permits").glob("*.json"):      # 许可只能带 owner 批准引用, 单次, 有期限
        pm = json.loads(pf.read_text(encoding="utf-8"))
        assert pm["permit_id"] == pf.stem and pm["owner_approval_reference"].strip() and pm["expiry"] and pm["max_runs"] == 1 == pm["max_attempts"], pf.name
        assert pm["mode"] in ("prepare", "eval") and pm["repository"] == "luogangan7-lgtm/cce-engine-oss", pf.name
