# -*- coding: utf-8 -*-
"""固定模型文件清单 · 下载计划 · 资产核验 · decider_config 严格读取。

- 源锁 locks/model.source.lock.json: revision 钉死 + HF 元数据锚点(LFS sha256 / git blob sha1 / size) —— 供应链锚点, 本机只读元数据。
- 资产锁 locks/model.assets.lock.json: 由 GitHub prepare 在 runner 上**下载并自算**后生成; 状态不是 READY 一律拒绝。
- 下载(download_bundle)只在 GitHub 守卫通过后执行; 延迟 import huggingface_hub。缓存命中也必须 verify_bundle。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .contracts import JevError, canonical, file_sha256, sha256
from .execution_guard import require

HERE = Path(__file__).resolve().parent
LOCKS = HERE / "locks"
SOURCE_LOCK = LOCKS / "model.source.lock.json"
ASSETS_LOCK = LOCKS / "model.assets.lock.json"
ASSETS_SCHEMA = "cce.jev.model-assets.v1"
REQUIRED_CONFIG_KEYS = ("temperature", "version", "isolated_levels", "max_options", "schema_first", "neutralize_none")


def load_json(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def source_lock(path=SOURCE_LOCK) -> dict:
    s = load_json(path)
    for k in ("repo_id", "revision", "model_version", "files", "execution_location", "remote_inference_allowed"):
        if k not in s:
            raise JevError("DEPENDENCY_LOCK_INVALID", f"source lock missing {k}")
    if s["execution_location"] != "github_hosted_actions_only" or s["remote_inference_allowed"] is not False:
        raise JevError("DEPENDENCY_LOCK_INVALID", "source lock execution boundary altered")
    return s


def assets_lock(path=ASSETS_LOCK) -> dict:
    return load_json(path)


def plan_download(src: dict, max_bytes: int) -> dict:
    """先算下载计划; 放不进上限就失败, 不下载一半再扩容。"""
    files = src["files"]
    total = sum(int(f["size"]) for f in files.values())
    if total > max_bytes:
        raise JevError("BUDGET_EXCEEDED", f"planned download {total} bytes > cap {max_bytes}")
    return {"total_bytes": total, "files": sorted(files), "revision": src["revision"], "repo_id": src["repo_id"]}


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _anchor_ok(path: Path, spec: dict) -> bool:
    kind, value = spec["anchor"]["kind"], spec["anchor"]["value"]
    if kind == "lfs_sha256":
        return file_sha256(path) == value
    if kind == "git_blob_sha1":
        return git_blob_sha1(path.read_bytes()) == value
    raise JevError("DEPENDENCY_LOCK_INVALID", f"unknown anchor kind {kind!r}")


def verify_bundle(bundle_dir, lock: dict, src: dict | None = None) -> dict:
    """严格: 缺件 / 多件 / 大小或 sha256 不符 / 锁未 READY ⇒ MODEL_BUNDLE_INVALID。不自动换资产、不删掉重下。"""
    if lock.get("schema") != ASSETS_SCHEMA or lock.get("status") != "READY" or not lock.get("files"):
        raise JevError("MODEL_BUNDLE_INVALID", f"assets lock status {lock.get('status')!r} (need READY with files)")
    if src is not None and (lock.get("revision") != src["revision"] or lock.get("repo_id") != src["repo_id"]):
        raise JevError("MODEL_VERSION_MISMATCH", "assets lock revision/repo != source lock")
    d = Path(bundle_dir)
    if not d.is_dir():
        raise JevError("MODEL_BUNDLE_INVALID", f"bundle dir {d} missing")
    present = {p.name for p in d.iterdir() if p.is_file() and not p.name.startswith(".")}
    subdirs = [p.name for p in d.iterdir() if p.is_dir() and not p.name.startswith(".")]
    expected = set(lock["files"])
    if subdirs:
        raise JevError("MODEL_BUNDLE_INVALID", f"unexpected subdirectories {sorted(subdirs)}")
    if expected - present:
        raise JevError("MODEL_BUNDLE_INVALID", f"missing files {sorted(expected - present)}")
    if present - expected:
        raise JevError("MODEL_BUNDLE_INVALID", f"extra files {sorted(present - expected)}")
    for name, spec in lock["files"].items():
        p = d / name
        if p.stat().st_size != int(spec["size"]):
            raise JevError("MODEL_BUNDLE_INVALID", f"{name}: size {p.stat().st_size} != {spec['size']}")
        if file_sha256(p) != spec["sha256"]:
            raise JevError("MODEL_BUNDLE_INVALID", f"{name}: sha256 mismatch (corrupt or substituted)")
    return {"verified_files": sorted(expected), "bundle_sha256": sha256(canonical(lock["files"])), "revision": lock["revision"]}


def read_decider_config(bundle_dir, src: dict) -> dict:
    """上游缺 decider_config.json 会被 except 吞掉回默认温度 —— 这里先严格读, 缺/错一律失败。"""
    p = Path(bundle_dir) / "decider_config.json"
    if not p.is_file():
        raise JevError("MODEL_BUNDLE_INVALID", "decider_config.json missing (no default temperature allowed)")
    cfg = json.loads(p.read_text(encoding="utf-8"))
    for k in REQUIRED_CONFIG_KEYS:
        if k not in cfg:
            raise JevError("MODEL_BUNDLE_INVALID", f"decider_config.json missing {k}")
    if not isinstance(cfg["temperature"], (int, float)) or isinstance(cfg["temperature"], bool) or cfg["temperature"] <= 0:
        raise JevError("MODEL_BUNDLE_INVALID", f"temperature {cfg['temperature']!r}")
    if cfg["version"] != src["model_version"]:
        raise JevError("MODEL_VERSION_MISMATCH", f"decider_config version {cfg['version']!r} != lock {src['model_version']!r}")
    for k in ("isolated_levels", "schema_first", "neutralize_none"):
        if not isinstance(cfg[k], bool):
            raise JevError("MODEL_BUNDLE_INVALID", f"{k} must be bool")
    if cfg["schema_first"]:
        raise JevError("RUNTIME_UNSUPPORTED", "schema_first layout not part of this contract (state-first only)")
    return {k: cfg[k] for k in REQUIRED_CONFIG_KEYS} | {"temperature": float(cfg["temperature"])}


def download_bundle(src: dict, dest, ledger, env: dict, receipt: dict, expect_workflow: str = "cce-jev-prepare.yml") -> dict:
    """仅 GitHub 托管 runner: 按清单逐文件下载同一 revision, 预约字节, 核对元数据锚点, 返回资产锁提案(状态 READY 由核验决定)。"""
    require(env, receipt, expect_workflow)
    plan = plan_download(src, ledger.b.max_download_bytes)
    from huggingface_hub import hf_hub_download   # 延迟 import, 守卫之后
    d = Path(dest); d.mkdir(parents=True, exist_ok=True)
    files, anchors = {}, {}
    for name in plan["files"]:
        spec = src["files"][name]
        ledger.reserve_download(int(spec["size"]), name)
        got = Path(hf_hub_download(repo_id=src["repo_id"], filename=name, revision=src["revision"], local_dir=str(d)))
        if got.resolve().parent != d.resolve() or got.name != name:
            raise JevError("MODEL_BUNDLE_INVALID", f"{name}: downloaded to unexpected path {got}")
        size = got.stat().st_size
        if size != int(spec["size"]):
            raise JevError("MODEL_BUNDLE_INVALID", f"{name}: size {size} != metadata {spec['size']}")
        anchors[name] = _anchor_ok(got, spec)
        if not anchors[name]:
            raise JevError("MODEL_BUNDLE_INVALID", f"{name}: content does not match HF metadata anchor")
        files[name] = {"size": size, "sha256": file_sha256(got)}
    return {"schema": ASSETS_SCHEMA, "status": "READY", "repo_id": src["repo_id"], "revision": src["revision"],
            "model_version": src["model_version"], "files": files, "anchor_check": anchors,
            "total_bytes": sum(f["size"] for f in files.values()), "generated_by": "cce-jev-prepare.yml on github-hosted runner"}
