# -*- coding: utf-8 -*-
"""多模型登记(models/<key>/)与 hf_choice 取件器的纯测试(零网络: 假 opener)。
守: 键名/路径 · 旧 Decider 位置不动 · hf_choice 源锁的固定标识与必填 backend_config · 流式取件的锚点核/超长/截断重试/锚点不符不重试 · 守卫在任何取件之前。"""
import hashlib
import io
import json
from pathlib import Path

import pytest

from experiments.jev import strict_assets as SA
from experiments.jev.budget import Ledger
from experiments.jev.contracts import ExecutionBudget, JevError

JEV = Path(__file__).resolve().parents[1]
ENV = {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted", "GITHUB_REPOSITORY": "luogangan7-lgtm/cce-engine-oss",
       "GITHUB_WORKFLOW_REF": "luogangan7-lgtm/cce-engine-oss/.github/workflows/cce-jev-llm-prepare.yml@refs/heads/master",
       "GITHUB_RUN_ID": "7", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": "b" * 40}
REC = {"schema": "cce.jev.admission-receipt.v1", "permit_id": "p", "repository": ENV["GITHUB_REPOSITORY"], "execution_commit": "b" * 40,
       "run_id": "7", "workflow_id": "cce-jev-llm-prepare.yml"}


def test_model_paths_keep_decider_in_place_and_validate_keys():
    assert SA.model_paths(None) == SA.model_paths("decider-2b") == (SA.SOURCE_LOCK, SA.ASSETS_LOCK)
    sp, ap = SA.model_paths("qwen3.5-4b")
    assert sp == JEV / "models" / "qwen3.5-4b" / "model.source.lock.json" and ap.name == "model.assets.lock.json"
    for bad in ("../locks", "Qwen", "a", "x/y", "qwen..4b"):
        with pytest.raises(JevError):
            SA.model_paths(bad)
    with pytest.raises(JevError) as e:
        SA.model_paths("not-registered-model")
    assert e.value.code == "DEPENDENCY_LOCK_INVALID"


@pytest.mark.parametrize("key,repo,rev", [("qwen3-4b-2507", "Qwen/Qwen3-4B-Instruct-2507", "cdbee75f17c01a7cc42f958dc650907174af0554"),
                                          ("qwen3.5-4b", "Qwen/Qwen3.5-4B", "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a")])
def test_candidate_source_locks_are_pinned_hf_choice(key, repo, rev):
    src = SA.source_lock(SA.model_paths(key)[0])
    assert src["backend"] == "hf_choice" and src["repo_id"] == repo and src["revision"] == rev
    bc = src["backend_config"]
    assert bc["storage_dtype"] == "bfloat16" and bc["compute_dtype"] == "float32" and bc["threads"] == 3 and bc["temperature"] == 1.0
    assert bc["letters"] == "ABCDEFGH" and bc["prompt_spec"] == "cce.jev.hf_choice.prompt.v1"
    assert src["planned_download_bytes"] == sum(f["size"] for f in src["files"].values())
    assert any(n.endswith(".safetensors") and f["anchor"]["kind"] == "lfs_sha256" for n, f in src["files"].items())
    assert "tokenizer.json" in src["files"] and src["files"]["tokenizer.json"]["anchor"]["kind"] == "lfs_sha256"
    if key == "qwen3.5-4b":         # 默认思考: 关掉后渲染串必须以空思考块结尾
        assert bc["chat_template_kwargs"] == {"enable_thinking": False} and bc["answer_suffix"].endswith("<think>\n\n</think>\n\n")


def test_hf_choice_source_lock_rejects_unpinned_or_incomplete(tmp_path):
    base = json.loads(SA.model_paths("qwen3-4b-2507")[0].read_text(encoding="utf-8"))
    for mut in (lambda d: d.update(revision="main"), lambda d: d.update(repo_id="../x"), lambda d: d["files"].update({"../evil": {"size": 1, "anchor": {"kind": "git_blob_sha1", "value": "0"}}}),
                lambda d: d["backend_config"].pop("answer_suffix"), lambda d: d.update(backend="vllm"), lambda d: d.update(remote_inference_allowed=True)):
        d = json.loads(json.dumps(base)); mut(d)
        f = tmp_path / "s.json"; f.write_text(json.dumps(d), encoding="utf-8")
        with pytest.raises(JevError) as e:
            SA.source_lock(f)
        assert e.value.code == "DEPENDENCY_LOCK_INVALID"


def _src(files):
    return {"backend": "hf_choice", "repo_id": "Org/Model", "revision": "c" * 40, "model_version": "m@c", "files": files}


def _spec(data: bytes, kind="lfs_sha256"):
    v = hashlib.sha256(data).hexdigest() if kind == "lfs_sha256" else hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
    return {"size": len(data), "anchor": {"kind": kind, "value": v}}


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _opener(bodies):
    calls = []

    def op(req, timeout=60):
        calls.append(req.full_url)
        b = bodies[len(calls) - 1]
        if isinstance(b, Exception):
            raise b
        return _Resp(b)
    return op, calls


def _ledger(cap=10 ** 6):
    return Ledger(ExecutionBudget(max_forwards=0, max_rows=0, max_padded_tokens=0, max_row_tokens=0, deadline_s=60, max_download_bytes=cap))


def test_fetch_verifies_anchors_and_writes_proposal(tmp_path):
    w, cfgb = b"\x01" * 3000, b'{"a": 1}'
    src = _src({"model.safetensors": _spec(w), "config.json": _spec(cfgb, "git_blob_sha1")})
    op, calls = _opener([cfgb, w])                                  # plan 按文件名排序: config.json 先
    prop = SA.fetch_bundle_http(src, tmp_path / "b", _ledger(), ENV, REC, "cce-jev-llm-prepare.yml", sleep=lambda s: None, opener=op)
    assert calls == ["https://huggingface.co/Org/Model/resolve/" + "c" * 40 + "/config.json", "https://huggingface.co/Org/Model/resolve/" + "c" * 40 + "/model.safetensors"]
    assert prop["status"] == "READY" and prop["files"]["model.safetensors"]["sha256"] == hashlib.sha256(w).hexdigest() and prop["total_bytes"] == 3008
    assert SA.verify_bundle(tmp_path / "b", prop, src)["verified_files"] == ["config.json", "model.safetensors"]
    assert not list((tmp_path / "b").glob("*.part"))


def test_fetch_retries_short_reads_but_never_accepts_wrong_bytes(tmp_path):
    w = b"\x02" * 100
    src = _src({"w.safetensors": _spec(w)})
    op, calls = _opener([w[:50], OSError("reset"), w])               # 截断 → 断线 → 成功: 三次整文件重取
    SA.fetch_bundle_http(src, tmp_path / "b", _ledger(), ENV, REC, "cce-jev-llm-prepare.yml", sleep=lambda s: None, opener=op)
    assert len(calls) == 3
    op, calls = _opener([b"\x03" * 100])                             # 同样大小但内容不符: 立刻失败, 不重试
    with pytest.raises(JevError) as e:
        SA.fetch_bundle_http(src, tmp_path / "c", _ledger(), ENV, REC, "cce-jev-llm-prepare.yml", sleep=lambda s: None, opener=op)
    assert e.value.code == "MODEL_BUNDLE_INVALID" and len(calls) == 1 and not list((tmp_path / "c").iterdir())
    op, calls = _opener([w + b"x"])                                  # 多出字节: 立刻失败
    with pytest.raises(JevError):
        SA.fetch_bundle_http(src, tmp_path / "d", _ledger(), ENV, REC, "cce-jev-llm-prepare.yml", sleep=lambda s: None, opener=op)
    op, calls = _opener([OSError("x")] * 3)
    with pytest.raises(JevError) as e:
        SA.fetch_bundle_http(src, tmp_path / "e", _ledger(), ENV, REC, "cce-jev-llm-prepare.yml", sleep=lambda s: None, opener=op)
    assert "after 3 attempts" in e.value.detail


def test_fetch_is_guarded_and_budgeted_before_any_request(tmp_path):
    src = _src({"w.safetensors": _spec(b"z" * 10)})
    op, calls = _opener([b"z" * 10])
    with pytest.raises(JevError) as e:
        SA.fetch_bundle_http(src, tmp_path / "b", _ledger(), {}, REC, "cce-jev-llm-prepare.yml", opener=op)
    assert e.value.code == "EXECUTION_LOCATION_FORBIDDEN" and not calls
    with pytest.raises(JevError) as e:
        SA.fetch_bundle_http(src, tmp_path / "b", _ledger(cap=5), ENV, REC, "cce-jev-llm-prepare.yml", opener=op)
    assert e.value.code == "BUDGET_EXCEEDED" and not calls
    with pytest.raises(JevError):
        SA.fetch_bundle_http(dict(src, backend="decider"), tmp_path / "b", _ledger(), ENV, REC, "cce-jev-llm-prepare.yml", opener=op)
