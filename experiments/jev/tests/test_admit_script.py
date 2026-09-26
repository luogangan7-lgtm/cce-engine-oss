# -*- coding: utf-8 -*-
"""admit 脚本(纯标准库): 无许可文件 / attempt 2 / 过期 / 锁哈希不符 / suite 不符 各自在任何 ref 创建之前拒绝; 422 ⇒ PERMIT_ALREADY_USED; 网络不明 ⇒ 按已消耗。"""
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".github" / "scripts" / "cce_jev_admit.py"
JEV = ROOT / "experiments" / "jev"


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _env(tmp_path, **over):
    env = {"PATH": os.environ.get("PATH", ""), "PERMIT_ID": "P-TEST-1", "MODE": "prepare", "GITHUB_REPOSITORY": "luogangan7-lgtm/cce-engine-oss",
           "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "1", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_REF": "refs/heads/master",
           "GITHUB_WORKFLOW_REF": "luogangan7-lgtm/cce-engine-oss/.github/workflows/cce-jev-prepare.yml@refs/heads/master",
           "GITHUB_TOKEN": "x", "GITHUB_API_URL": "http://127.0.0.1:9", "RECEIPT_OUT": str(tmp_path / "receipt.json"), "PYTHONDONTWRITEBYTECODE": "1"}
    env.update(over)
    return env


def _permit(**over):
    p = {"permit_id": "P-TEST-1", "owner_approval_reference": "test", "expiry": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)).isoformat(),
         "repository": "luogangan7-lgtm/cce-engine-oss", "workflow_id": "cce-jev-prepare.yml", "mode": "prepare", "max_runs": 1, "max_attempts": 1,
         "model_source_lock_sha256": _sha(JEV / "locks" / "model.source.lock.json"), "asset_lock_sha256": "NOT_APPLICABLE_PREPARE",
         "runtime_lock_sha256": "NOT_APPLICABLE_PREPARE", "resource_policy": "asset_prepare.json", "resource_policy_sha256": _sha(JEV / "policies" / "asset_prepare.json")}
    p.update(over)
    return p


@pytest.fixture
def permit_file():
    d = JEV / "permits"; f = d / "P-TEST-1.json"
    yield f
    if f.exists():
        f.unlink()


def _run(env):
    return subprocess.run([sys.executable, str(SCRIPT)], env=env, capture_output=True, text=True, cwd=str(ROOT), timeout=60)


def test_no_permit_file_refused(tmp_path):
    p = _run(_env(tmp_path)); assert p.returncode == 3 and "PERMIT_NOT_APPROVED" in p.stderr and not (tmp_path / "receipt.json").exists()


@pytest.mark.parametrize("over,code", [
    ({"GITHUB_RUN_ATTEMPT": "2"}, "PERMIT_ALREADY_USED"), ({"GITHUB_REF": "refs/heads/feature"}, "PERMIT_NOT_APPROVED"),
    ({"MODE": "eval", "SUITE_ID": "s0-smoke-v1"}, "PERMIT_NOT_APPROVED"), ({"PERMIT_ID": "../x"}, "PERMIT_NOT_APPROVED"),
])
def test_env_shape_refusals(tmp_path, permit_file, over, code):
    permit_file.write_text(json.dumps(_permit()))
    p = _run(_env(tmp_path, **over)); assert p.returncode == 3 and code in p.stderr, p.stderr


@pytest.mark.parametrize("over,code", [
    ({"expiry": "2020-01-01T00:00:00+00:00"}, "PERMIT_EXPIRED"), ({"model_source_lock_sha256": "0" * 64}, "PERMIT_NOT_APPROVED"),
    ({"max_runs": 2}, "PERMIT_NOT_APPROVED"), ({"owner_approval_reference": ""}, "PERMIT_NOT_APPROVED"),
    ({"asset_lock_sha256": "abc"}, "PERMIT_NOT_APPROVED"), ({"resource_policy_sha256": "0" * 64}, "PERMIT_NOT_APPROVED"),
])
def test_permit_content_refusals(tmp_path, permit_file, over, code):
    permit_file.write_text(json.dumps(_permit(**over)))
    p = _run(_env(tmp_path)); assert p.returncode == 3 and code in p.stderr, p.stderr
    assert not (tmp_path / "receipt.json").exists()


def _eval_permit(**over):
    base = dict(mode="eval", workflow_id="cce-jev-eval.yml", suite_id="s0-smoke-v1", suite_sha256=_sha(JEV / "suites" / "s0-smoke-v1.jsonl"),
                asset_lock_sha256=_sha(JEV / "locks" / "model.assets.lock.json"), runtime_lock_sha256=_sha(JEV / "locks" / "runtime-cpu.lock.txt"),
                resource_policy="cpu_smoke.json", resource_policy_sha256=_sha(JEV / "policies" / "cpu_smoke.json"))
    base.update(over)
    return _permit(**base)


EVAL_ENV = dict(MODE="eval", SUITE_ID="s0-smoke-v1", GITHUB_WORKFLOW_REF="luogangan7-lgtm/cce-engine-oss/.github/workflows/cce-jev-eval.yml@refs/heads/master")


@pytest.mark.parametrize("over,needle", [
    ({"runtime_lock_sha256": "x"}, "runtime lock"), ({"asset_lock_sha256": "0" * 64}, "asset lock"),
    ({"suite_sha256": "0" * 64}, "suite_sha256"), ({"suite_id": "other-suite"}, "suite_id"),
])
def test_eval_permit_refused_when_any_lock_or_suite_binding_differs(tmp_path, permit_file, over, needle):
    permit_file.write_text(json.dumps(_eval_permit(**over)))
    p = _run(_env(tmp_path, **EVAL_ENV))
    assert p.returncode == 3 and "PERMIT_NOT_APPROVED" in p.stderr and needle in p.stderr, p.stderr


def test_eval_permit_refused_unconsumed_when_cache_cannot_be_verified(tmp_path, permit_file):
    permit_file.write_text(json.dumps(_eval_permit()))
    p = _run(_env(tmp_path, **EVAL_ENV))          # 绑定全过, 但缓存 API 不可达 ⇒ 不消耗、拒绝
    assert p.returncode == 3 and "PERMIT_NOT_APPROVED" in p.stderr and "NOT consumed" in p.stderr, p.stderr


def _serve(state):
    import http.server, threading

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            state.setdefault("gets", []).append(self.path)
            body = json.dumps({"actions_caches": [{"key": k} for k in state.get("cache_keys", [])]}).encode()
            self.send_response(200); self.end_headers(); self.wfile.write(body)

        def do_POST(self):
            state.setdefault("posts", []).append(self.path)
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(state.get("post_code", 201)); self.end_headers(); self.wfile.write(b"{}")

        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _key():
    import importlib.util
    sp = importlib.util.spec_from_file_location("_adm", SCRIPT); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
    return m.bundle_cache_key()


def test_eval_admission_requires_cache_and_only_then_consumes(tmp_path, permit_file):
    permit_file.write_text(json.dumps(_eval_permit()))
    st = {"cache_keys": ["cce-jev-bundle-other-x64"]}; srv, url = _serve(st)
    try:
        p = _run(_env(tmp_path, GITHUB_API_URL=url, **EVAL_ENV))
        assert p.returncode == 3 and "cache missing" in p.stderr and not st.get("posts"), p.stderr     # 缓存不在 ⇒ 不 POST
        st["cache_keys"] = [_key()]
        p = _run(_env(tmp_path, GITHUB_API_URL=url, BUNDLE_CACHE_KEY="cce-jev-bundle-wrong-x64", **EVAL_ENV))
        assert p.returncode == 3 and "cache key" in p.stderr and not st.get("posts"), p.stderr
        p = _run(_env(tmp_path, GITHUB_API_URL=url, BUNDLE_CACHE_KEY=_key(), **EVAL_ENV))
        assert p.returncode == 0 and len(st["posts"]) == 1, p.stderr
        r = json.loads((tmp_path / "receipt.json").read_text()); assert r["suite_id"] == "s0-smoke-v1" and r["resource_policy"] == "cpu_smoke.json"
    finally:
        srv.shutdown()


def test_eval_permit_policy_must_match_suite_manifest_before_consumption(tmp_path, permit_file):
    cmp_ = dict(suite_id="s0-compare-v1", suite_sha256=_sha(JEV / "suites" / "s0-compare-v1.jsonl"))
    env = _env(tmp_path, **{**EVAL_ENV, "SUITE_ID": "s0-compare-v1"})
    permit_file.write_text(json.dumps(_eval_permit(**cmp_)))                                           # README 旧模板: cpu_smoke.json
    p = _run(env); assert p.returncode == 3 and "suite manifest policy" in p.stderr, p.stderr
    permit_file.write_text(json.dumps(_eval_permit(**cmp_, resource_policy="cpu_compare.json", resource_policy_sha256=_sha(JEV / "policies" / "cpu_compare.json"))))
    p = _run(env); assert p.returncode == 3 and "NOT consumed" in p.stderr, p.stderr                  # 绑定全过, 停在缓存核验(未消耗)


def test_valid_prepare_permit_reaches_ref_creation_and_unknown_network_is_treated_as_consumed(tmp_path, permit_file):
    permit_file.write_text(json.dumps(_permit()))
    p = _run(_env(tmp_path))          # GITHUB_API_URL 指向不可达端口 ⇒ 网络不明 ⇒ 按已消耗, 不重试
    assert p.returncode == 3 and "PERMIT_ALREADY_USED" in p.stderr and "treating permit as consumed" in p.stderr, p.stderr
    assert not (tmp_path / "receipt.json").exists()


def test_422_means_already_used_and_201_writes_receipt(tmp_path, permit_file):
    import http.server, threading
    permit_file.write_text(json.dumps(_permit()))
    state = {"code": 422}

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0)); body = json.loads(self.rfile.read(n))
            assert body["ref"] == "refs/tags/cce-jev-consumed/P-TEST-1" and body["sha"] == "a" * 40
            self.send_response(state["code"]); self.end_headers(); self.wfile.write(b"{}")

        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H); th = threading.Thread(target=srv.serve_forever, daemon=True); th.start()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}"
        p = _run(_env(tmp_path, GITHUB_API_URL=url)); assert p.returncode == 3 and "already exists" in p.stderr
        state["code"] = 201
        p = _run(_env(tmp_path, GITHUB_API_URL=url)); assert p.returncode == 0, p.stderr
        r = json.loads((tmp_path / "receipt.json").read_text())
        assert r["schema"] == "cce.jev.admission-receipt.v1" and r["execution_commit"] == "a" * 40 and r["consumed_ref"].endswith("P-TEST-1") and r["mode"] == "prepare"
    finally:
        srv.shutdown()



def test_eval_admission_runs_the_suite_plan_before_consumption(tmp_path, permit_file):
    """suite 清单与 sha 都对, 但语料指针坏了 ⇒ admit 的 plan 预检必须在消耗前拒绝。"""
    sd = JEV / "suites"; name = "s0-planfail-t1"
    good = [json.loads(l) for l in (sd / "s0-compare-v1.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()][0]
    bad = dict(good, text_ref=dict(good["text_ref"], body_sha256="0" * 64))
    raw = (json.dumps(bad, ensure_ascii=False) + "\n").encode()
    (sd / f"{name}.jsonl").write_bytes(raw)
    (sd / f"{name}.manifest.json").write_text(json.dumps({"suite_id": name, "suite_sha256": _sha(sd / f"{name}.jsonl"), "policy": "cpu_smoke.json", "task": "s0_context.v1"}), encoding="utf-8")
    try:
        permit_file.write_text(json.dumps(_eval_permit(suite_id=name, suite_sha256=_sha(sd / f"{name}.jsonl"))))
        p = _run(_env(tmp_path, **{**EVAL_ENV, "SUITE_ID": name}))
        assert p.returncode == 3 and "suite plan failed before consumption" in p.stderr and "0000000000" not in p.stderr.replace("0" * 12, ""), p.stderr
    finally:
        for f in (f"{name}.jsonl", f"{name}.manifest.json"):
            (sd / f).unlink(missing_ok=True)
