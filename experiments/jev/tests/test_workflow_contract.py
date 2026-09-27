# -*- coding: utf-8 -*-
"""三个 workflow 的结构合同(不依赖 PyYAML): 触发 · 权限 · runner · SHA 固定 · persist-credentials · 输入不进 run: · 无模型 secret · 无 pull_request_target。"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WF = ROOT / ".github" / "workflows"
ACTS = json.loads((ROOT / "experiments" / "jev" / "locks" / "actions.lock.json").read_text(encoding="utf-8"))
SUITES = sorted(p.stem for p in (ROOT / "experiments" / "jev" / "suites").glob("*.jsonl"))
ALL_WF = ("cce-jev-contract.yml", "cce-jev-prepare.yml", "cce-jev-eval.yml", "cce-jev-llm-prepare.yml", "cce-jev-llm-eval.yml")
DECIDER_SUITES = ["s0-compare-v1", "s0-probe-v1", "s0-smoke-v1"]


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
    for wf in ALL_WF:
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
    for wf in ("cce-jev-prepare.yml", "cce-jev-eval.yml", "cce-jev-llm-prepare.yml", "cce-jev-llm-eval.yml"):
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
    assert sorted(o.strip() for o in opts.split(",")) == DECIDER_SUITES
    llm_opts = sorted(o.strip() for o in re.search(r"options:\s*\[([^\]]*)\]", _wf("cce-jev-llm-eval.yml")).group(1).split(","))
    assert sorted(DECIDER_SUITES + llm_opts) == SUITES, "每个 suite 恰好属于一个评估工作流"
    for flag in ("--network none", "--read-only", "--cap-drop ALL", "no-new-privileges", "--memory-swap 12g", "--cpus 3", "--user 1001:1001", "--pids-limit"):
        assert flag in (ROOT / "experiments" / "jev" / "runtime" / "run_remote_only.sh").read_text(encoding="utf-8"), flag
    sh = (ROOT / "experiments" / "jev" / "runtime" / "run_remote_only.sh").read_text(encoding="utf-8")
    assert "docker run --rm" not in sh and "State.OOMKilled" in ev          # OOM 与超时都是 137, 必须能事后 inspect 区分
    assert "-e HOME=/tmp" in sh and "HF_HOME=/tmp/hf" in sh                 # 只读根文件系统下的可写缓存位置
    assert "restore-keys" not in ev and "fail-on-cache-miss" in ev
    assert "check-upload" in ev and "if: always()" in ev and "retention-days: 7" in ev
    # 上传与公开 step summary 都必须在原文扫描通过之后; 时限来自已准入的策略, 不硬编码
    assert "check-upload --root \"$RUNNER_TEMP/out/reports/run\" --suite \"$SUITE_ID\"" in ev
    up = ev.rsplit("actions/upload-artifact@", 1)[1].split("with:")[0]          # 报告上传 = evaluate 里最后一个上传步骤
    assert "steps.upload_gate.outcome == 'success'" in up
    summ = ev.split("GITHUB_STEP_SUMMARY")[0].rsplit("- name:", 1)[1]
    assert "steps.upload_gate.outcome == 'success'" in summ and ev.index("id: upload_gate") < ev.index("GITHUB_STEP_SUMMARY")
    assert "policy-field --receipt admission_receipt.json --field model_load_plus_infer_deadline_s" in ev and '"$SUITE_ID" 1200' not in ev
    assert "suite-files --suite" in sh and ":ro" in sh.split("CORPUS_MOUNTS+=")[1].split("\n")[0] and "corpus:/work/corpus" not in sh   # 只挂被引用的文件
    assert "TRANSFORMERS_VERBOSITY=error" in sh


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



def test_evaluate_outer_timeout_covers_every_policy_deadline():
    import glob
    for p in glob.glob(str(ROOT / "experiments/jev/policies/*.json")):
        pol = json.loads(open(p, encoding="utf-8").read())
        if pol.get("mode") != "eval":
            continue
        llm = pol.get("backend") == "hf_choice"                 # 候选策略由 llm 工作流执行, 对照它的外层时限与包装脚本
        ev = _wf("cce-jev-llm-eval.yml" if llm else "cce-jev-eval.yml")
        tmin = int(re.search(r"evaluate:[\s\S]*?timeout-minutes: (\d+)", ev).group(1))
        slack = int(re.search(r"timeout --signal=KILL \$\(\(DEADLINE \+ (\d+)\)\)", (ROOT / "experiments/jev/runtime" / ("run_llm.sh" if llm else "run_remote_only.sh")).read_text(encoding="utf-8")).group(1))
        assert tmin * 60 >= pol["model_load_plus_infer_deadline_s"] + slack + 15 * 60, (p, tmin, slack)     # 强杀余量 + 恢复缓存/建镜像/收尾


def test_llm_workflows_matrix_from_admitted_models_no_cache_and_same_isolation():
    """hf_choice 候选工作流: 腿 = admit 从许可里核过的模型键(不是用户输入); 不用 Actions 缓存; 容器隔离与 Decider 同级;
    取件只在 evaluate/prepare 腿里(admit 不碰模型字节); 上传与摘要都在原文扫描之后。"""
    sh = (ROOT / "experiments" / "jev" / "runtime" / "run_llm.sh").read_text(encoding="utf-8")
    code = "\n".join(l for l in sh.splitlines() if not l.lstrip().startswith("#"))
    run = code.split("docker run", 1)[1].split('"$IMAGE" "${CMD[@]}"', 1)[0]             # 只认 docker run 命令本身里的旗标
    for flag in ("--network none", "--read-only", "--cap-drop ALL", "no-new-privileges", "--memory-swap 12g", "--cpus 3", "--user 1001:1001", "--pids-limit",
                 "-e HOME=/tmp", "HF_HOME=/tmp/hf", "TRANSFORMERS_VERBOSITY=error", "MKL_CBWR=AVX2", "ONEDNN_MAX_CPU_ISA=AVX2", "ATEN_CPU_CAPABILITY=avx2", "HF_HUB_OFFLINE=1"):
        assert flag in run, flag
    for flag in ("suite-files --suite", "EXECUTION_LOCATION_FORBIDDEN", "docker kill cce-jev-llm", "docker wait cce-jev-llm"):
        assert flag in code, flag
    assert "docker run --rm" not in sh and ":ro" in sh.split("MOUNTS+=(-v \"$ROOT/$f")[1].split("\n")[0] and "corpus:/work/corpus" not in sh
    for wf, leg in (("cce-jev-llm-prepare.yml", "prepare"), ("cce-jev-llm-eval.yml", "evaluate")):
        t = _wf(wf)
        admit = t.split("  admit:")[1].split("\n  " + leg + ":")[0]
        rest = t.split("\n  " + leg + ":")[1]
        assert "models: ${{ steps.admit.outputs.models }}" in admit and "id: admit" in admit and "HF_ENDPOINT" not in t
        assert "model: ${{ fromJSON(needs.admit.outputs.models) }}" in rest and "fail-fast: false" in rest
        assert "actions/cache" not in t and "restore-keys" not in t and "huggingface_hub" not in t and "pip install" not in t
        assert "run_llm.sh" in rest and "State.OOMKilled" in rest and "cce-jev-llm" in rest
        assert "${{ matrix.model }}" in rest.split("upload-artifact@")[-1]                  # 每条腿的产物名带模型键, 不互相覆盖
        up = rest.rsplit("actions/upload-artifact@", 1)[1].split("with:")[0]
        assert "steps.upload_gate.outcome == 'success'" in up
    ev = _wf("cce-jev-llm-eval.yml")
    assert "fetch-bundle --model" in ev.split("\n  evaluate:")[1] and "fetch-bundle" not in ev.split("\n  evaluate:")[0]
    assert "check-locks --require-ready --model" in ev and "--backend hf_choice" in ev
    assert 'check-upload --root "$RUNNER_TEMP/out/reports/run" --suite "$SUITE_ID"' in ev and ev.index("id: upload_gate") < ev.index("GITHUB_STEP_SUMMARY")
    assert "policy-field --receipt admission_receipt.json --field model_load_plus_infer_deadline_s" in ev
    pr = _wf("cce-jev-llm-prepare.yml")
    assert "run_llm.sh smoke" in pr and "check-upload --root prepare-out" in pr and "locks/runtime-cpu.lock.txt experiments/jev/runtime/runtime-cpu.lock.txt" in pr
    assert "pip-compile" not in pr, "候选 prepare 用已审过的运行时锁建镜像, 不重新解析依赖"
    for t_ in (pr, ev):
        assert "--build-arg WITH_DECIDER=0" in t_, "候选镜像不装 decider(构建期不再依赖外部 git)"
    assert "--field smoke_deadline_s" in pr and "run_llm.sh smoke cce-jev-cpu:prepare" in pr and " 2400 " not in pr


def test_candidate_model_locks_consistent_when_prepared():
    M = ROOT / "experiments" / "jev" / "models"
    keys = sorted(d.name for d in M.iterdir() if d.is_dir())
    assert keys == ["qwen3-4b-2507", "qwen3.5-4b"], keys
    for k in keys:
        src = json.loads((M / k / "model.source.lock.json").read_text(encoding="utf-8"))
        assert src["backend"] == "hf_choice" and src["execution_location"] == "github_hosted_actions_only" and src["remote_inference_allowed"] is False
        ap = M / k / "model.assets.lock.json"
        if not ap.is_file():
            continue
        a = json.loads(ap.read_text(encoding="utf-8"))
        assert a["status"] == "READY" and a["revision"] == src["revision"] and set(a["files"]) == set(src["files"]), k
        assert a["generated_by"].startswith("cce-jev-llm-prepare.yml") and a["reviewed"]["run"].startswith("https://github.com/"), k
        assert a["observed_load"]["param_count"] > 0 and not a["observed_load"]["loading_info"]["mismatched_keys"], k
        for name, spec in src["files"].items():
            assert a["files"][name]["size"] == spec["size"], (k, name)
            if spec["anchor"]["kind"] == "lfs_sha256":
                assert a["files"][name]["sha256"] == spec["anchor"]["value"], (k, name)
