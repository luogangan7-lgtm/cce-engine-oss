# -*- coding: utf-8 -*-
"""固定模型文件清单 · 下载计划 · 资产核验 · decider_config 严格读取。

- 源锁 locks/model.source.lock.json: revision 钉死 + HF 元数据锚点(LFS sha256 / git blob sha1 / size) —— 供应链锚点, 本机只读元数据。
- 资产锁 locks/model.assets.lock.json: 由 GitHub prepare 在 runner 上**下载并自算**后生成; 状态不是 READY 一律拒绝。
- 下载(download_bundle)只在 GitHub 守卫通过后执行; 延迟 import huggingface_hub。缓存命中也必须 verify_bundle。
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

from .contracts import JevError, canonical, file_sha256, sha256
from .execution_guard import require

HERE = Path(__file__).resolve().parent
LOCKS = HERE / "locks"
SOURCE_LOCK = LOCKS / "model.source.lock.json"
ASSETS_LOCK = LOCKS / "model.assets.lock.json"
ASSETS_SCHEMA = "cce.jev.model-assets.v1"
REQUIRED_CONFIG_KEYS = ("temperature", "version", "isolated_levels", "max_options", "schema_first", "neutralize_none")
# ★ 2026-09-27 多模型: Decider 的锁留在 locks/(键 decider-2b, 逐字节不动); 新候选各占 models/<key>/。
MODELS = HERE / "models"
LEGACY_KEY = "decider-2b"
MODEL_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{2,40}$")
REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}/[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")   # 段首必须字母数字: 拒 ../x、.git 之类
REV_RE = re.compile(r"^[0-9a-f]{40}$")
FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
HF_BASE = "https://huggingface.co"          # 取件与 admit 的可达性检查用同一个主机; 不读环境变量


def model_paths(key=None) -> tuple:
    """模型键 → (源锁, 资产锁) 路径。None / decider-2b = 旧位置; 其它键必须已在 models/ 下登记源锁。"""
    if key in (None, LEGACY_KEY):
        return SOURCE_LOCK, ASSETS_LOCK
    if not isinstance(key, str) or not MODEL_KEY_RE.fullmatch(key) or ".." in key:
        raise JevError("INPUT_INVALID", f"model key {key!r}")
    d = MODELS / key
    if not (d / "model.source.lock.json").is_file():
        raise JevError("DEPENDENCY_LOCK_INVALID", f"model {key} has no source lock under models/")
    return d / "model.source.lock.json", d / "model.assets.lock.json"


def load_json(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def source_lock(path=SOURCE_LOCK) -> dict:
    s = load_json(path)
    for k in ("repo_id", "revision", "model_version", "files", "execution_location", "remote_inference_allowed"):
        if k not in s:
            raise JevError("DEPENDENCY_LOCK_INVALID", f"source lock missing {k}")
    if s["execution_location"] != "github_hosted_actions_only" or s["remote_inference_allowed"] is not False:
        raise JevError("DEPENDENCY_LOCK_INVALID", "source lock execution boundary altered")
    if s.get("backend", "decider") not in ("decider", "hf_choice"):
        raise JevError("DEPENDENCY_LOCK_INVALID", f"unknown backend {s.get('backend')!r}")
    if s.get("backend") == "hf_choice":
        if not REPO_RE.fullmatch(s["repo_id"]) or not REV_RE.fullmatch(s["revision"]) or not all(FILE_RE.fullmatch(n) for n in s["files"]):
            raise JevError("DEPENDENCY_LOCK_INVALID", "hf_choice source lock: repo / revision / file names must be plain pinned identifiers")
        for k in ("load_class", "expected_class", "storage_dtype", "compute_dtype", "threads", "temperature", "letters", "user_head", "user_tail", "answer_suffix", "prompt_spec"):
            if k not in (s.get("backend_config") or {}):
                raise JevError("DEPENDENCY_LOCK_INVALID", f"hf_choice source lock missing backend_config.{k}")
    return s


def assets_lock(path=ASSETS_LOCK) -> dict:
    """资产锁; 尚未 prepare 的新模型没有该文件 ⇒ 空表(调用方按「不是 READY」拒绝)。"""
    p = Path(path)
    return load_json(p) if p.is_file() else {}


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


def _http_get_verified(url: str, dest: Path, spec: dict, name: str, ledger=None, sleep=time.sleep, opener=None, attempts: int = 5) -> str:
    """流式下载一个固定修订的文件, 边下边算 sha256 与 git blob sha1; 大小与 HF 元数据锚点都对上才落盘, 否则整文件重试(≤5 次, 10/30/60/120 s)。
    内容寻址: 完整性来自锚点比对, 与下载客户端无关 ⇒ 只用标准库。每次尝试都先向账本预约整文件字节(重试也计入上限);
    任何未成功的尝试都删掉 .part。锚点不符 / 超出固定大小 = 内容错, 立刻失败不重试。"""
    import http.client
    import urllib.request
    size = int(spec["size"])
    part = dest / (name + ".part")
    last = None
    for i in range(attempts):
        if ledger is not None:
            ledger.reserve_download(size, name if i == 0 else f"{name} (retry {i})")
        h256, h1, n = hashlib.sha256(), hashlib.sha1(b"blob %d\0" % size), 0
        done = False
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "cce-jev-fetch/1"})
            with (opener or urllib.request.urlopen)(req, timeout=60) as r, open(part, "wb") as fh:
                for chunk in iter(lambda: r.read(1 << 20), b""):
                    n += len(chunk)
                    if n > size:
                        raise JevError("MODEL_BUNDLE_INVALID", f"{name}: more bytes than the pinned size {size}")
                    h256.update(chunk); h1.update(chunk); fh.write(chunk)
            if n != size:
                raise OSError(f"short read {n}/{size}")
            kind, value = spec["anchor"]["kind"], spec["anchor"]["value"]
            got = h256.hexdigest() if kind == "lfs_sha256" else h1.hexdigest() if kind == "git_blob_sha1" else None
            if got != value:
                raise JevError("MODEL_BUNDLE_INVALID", f"{name}: content does not match HF metadata anchor")
            part.replace(dest / name)
            done = True
            return h256.hexdigest()
        except (OSError, http.client.HTTPException) as e:     # 网络/截断/分块读残: 整文件重来; 不续传拼接
            last = e
            if i + 1 < attempts:
                sleep((10, 30, 60, 120)[min(i, 3)])
        finally:
            if not done:
                part.unlink(missing_ok=True)
    raise JevError("MODEL_BUNDLE_INVALID", f"{name}: download failed after {attempts} attempts ({type(last).__name__})")


def fetch_bundle_http(src: dict, dest, ledger, env: dict, receipt: dict, expect_workflow: str, sleep=time.sleep, opener=None) -> dict:
    """hf_choice 模型: 仅 GitHub 托管 runner, 按源锁逐文件取同一固定修订(https://huggingface.co/<repo>/resolve/<rev>/<file>),
    预约字节 → 流式核锚点 → 落盘; 返回资产锁提案。prepare 与 eval 都走它(eval 之后再对已提交的 READY 资产锁逐字节核)。"""
    require(env, receipt, expect_workflow)
    if src.get("backend") != "hf_choice":
        raise JevError("DEPENDENCY_LOCK_INVALID", "fetch_bundle_http is only for hf_choice models")
    plan = plan_download(src, ledger.b.max_download_bytes)
    from urllib.parse import quote
    d = Path(dest); d.mkdir(parents=True, exist_ok=True)
    files, anchors = {}, {}
    for name in plan["files"]:
        spec = src["files"][name]
        url = "%s/%s/resolve/%s/%s" % (HF_BASE, src["repo_id"], src["revision"], quote(name))
        sha = _http_get_verified(url, d, spec, name, ledger=ledger, sleep=sleep, opener=opener)
        files[name] = {"size": int(spec["size"]), "sha256": sha}
        anchors[name] = True
    return {"schema": ASSETS_SCHEMA, "status": "READY", "repo_id": src["repo_id"], "revision": src["revision"],
            "model_version": src["model_version"], "files": files, "anchor_check": anchors,
            "total_bytes": sum(f["size"] for f in files.values()), "generated_by": f"{expect_workflow} on github-hosted runner"}
