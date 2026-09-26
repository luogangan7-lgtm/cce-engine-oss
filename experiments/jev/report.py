# -*- coding: utf-8 -*-
"""覆盖闸 · 公开安全摘要 · 上传白名单 · manifest.sha256。

覆盖完整 = 预期集合每个 item×question 恰有一个终态; 失败项留在分母。它不证明结果正确。
报告 artifact 在公开仓可被登录用户下载 ⇒ 不放原文、权重、tokenizer、秘密。"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from .contracts import FINAL_STATUSES, JevError, file_sha256

FORBIDDEN_EXT = {".safetensors", ".gguf", ".pt", ".pth", ".bin", ".ckpt", ".msgpack", ".h5", ".onnx", ".tflite", ".pkl", ".npz", ".npy"}
FORBIDDEN_NAMES = {"tokenizer.json", "tokenizer.model", "vocab.json", "merges.txt", "spiece.model", "vocab.txt", "model.safetensors.index.json"}
TEXT_EXT = {".json", ".jsonl", ".md", ".txt", ".log", ".csv", ".sha256", ".yml", ".yaml"}
SECRET_RE = re.compile(r"(apikey_[A-Za-z0-9]{8,}|sk-[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|hf_[A-Za-z0-9]{20,}|"
                       r"-----BEGIN [A-Z ]*PRIVATE KEY-----|Bearer [A-Za-z0-9._-]{20,}|AKIA[0-9A-Z]{16})")


def coverage(expected: list, results: list) -> dict:
    """expected: [{item_id, question_id, status}], results: [{item_id, question_id, status}] 终态。多/少/重复/非法状态 ⇒ COVERAGE_MISMATCH。"""
    exp_keys = [(e["item_id"], e["question_id"]) for e in expected]
    if len(set(exp_keys)) != len(exp_keys):
        raise JevError("COVERAGE_MISMATCH", "duplicate keys in expected set")
    got = Counter((r["item_id"], r["question_id"]) for r in results)
    missing = [k for k in exp_keys if got.get(k, 0) == 0]
    dup = [k for k, c in got.items() if c > 1]
    extra = [k for k in got if k not in set(exp_keys)]
    bad = [r for r in results if r.get("status") not in FINAL_STATUSES]
    if missing or dup or extra or bad:
        raise JevError("COVERAGE_MISMATCH", f"missing={missing} duplicate={dup} extra={extra} bad_status={[r.get('status') for r in bad]}")
    counts = Counter(r["status"] for r in results)
    return {"expected": len(exp_keys), "final": len(results), "by_status": dict(sorted(counts.items())), "coverage_status": "COMPLETE"}


LEAK_WINDOW = 24


def _json_strings(o, out):
    if isinstance(o, str):
        out.append(o)
    elif isinstance(o, dict):
        for k, v in o.items():
            out.append(str(k)); _json_strings(v, out)
    elif isinstance(o, list):
        for v in o:
            _json_strings(v, out)


def _surface(p: Path) -> str:
    """文件的可读表面: 原始文本 + (JSON/JSONL 时)解码后的全部字符串 —— 转义过的原文也要抓到。"""
    raw = p.read_text(encoding="utf-8", errors="replace")
    parts = [raw]
    try:
        docs = [json.loads(raw)] if p.suffix == ".json" else [json.loads(l) for l in raw.splitlines() if l.strip()] if p.suffix == ".jsonl" else []
        for d in docs:
            _json_strings(d, parts)
    except ValueError:
        pass
    return "\n".join(parts)


def text_leaks(surface: str, forbidden_texts, window: int = LEAK_WINDOW) -> int:
    """任一输入文本的任一长度 window 的连续片段出现在 surface 里的次数(不返回片段本身 —— 报告泄漏不许复述泄漏)。"""
    if not forbidden_texts:
        return 0
    shingles = {surface[i:i + window] for i in range(max(0, len(surface) - window + 1))}
    hits = 0
    for t in forbidden_texts:
        t = " ".join(str(t).split())
        for i in range(0, max(0, len(t) - window + 1)):
            w = t[i:i + window]
            if w.strip() and not w.replace(" ", "").isdigit() and w in shingles:
                hits += 1
                break
    return hits


def check_upload(root, paths, max_total_bytes: int, forbidden_texts=()) -> list:
    """上传前白名单: 目录不越界 · 禁模型扩展名/tokenizer 资产 · 总大小 · 文本内无秘密 · 无输入原文(24 字符窗)。返回相对路径。"""
    root = Path(root).resolve()
    rel, total = [], 0
    for p in paths:
        p = Path(p).resolve()
        if root not in p.parents and p != root:
            raise JevError("OUTPUT_INVALID", f"{p} escapes report root {root}")
        if not p.is_file():
            raise JevError("OUTPUT_INVALID", f"{p} is not a regular file")
        if p.suffix.lower() in FORBIDDEN_EXT or p.name in FORBIDDEN_NAMES:
            raise JevError("OUTPUT_INVALID", f"{p.name}: model/tokenizer asset must not be uploaded")
        total += p.stat().st_size
        if total > max_total_bytes:
            raise JevError("OUTPUT_INVALID", f"report exceeds {max_total_bytes} bytes")
        if p.suffix.lower() in TEXT_EXT:
            m = SECRET_RE.search(p.read_text(encoding="utf-8", errors="replace"))
            if m:
                raise JevError("OUTPUT_INVALID", f"{p.name}: secret-shaped token ({m.group(0)[:6]}…)")
            n = text_leaks(" ".join(_surface(p).split()), forbidden_texts)
            if n:
                raise JevError("OUTPUT_INVALID", f"{p.name}: contains verbatim input text from {n} item(s)")
        rel.append(str(p.relative_to(root)))
    return rel


def write_manifest_sha256(out_dir) -> Path:
    d = Path(out_dir)
    lines = [f"{file_sha256(p)}  {p.name}" for p in sorted(d.iterdir()) if p.is_file() and p.name != "manifest.sha256"]
    (d / "manifest.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return d / "manifest.sha256"


def summary_md(report: dict) -> str:
    L = [f"# CCE Decider candidate evaluation ({report.get('suite_id', '?')})", "",
         f"- execution_status: **{report['execution_status']}**",
         f"- coverage_status: **{report['coverage_status']}**",
         f"- semantic_acceptance: **{report['semantic_acceptance']}**",
         f"- production_eligible: {report['production_eligible']}",
         f"- backend / model_version: {report['backend']} / {report['model_version']}", ""]
    cov = report.get("coverage") or {}
    if cov:
        L += ["| status | n |", "|---|---:|"] + [f"| {k} | {v} |" for k, v in cov.get("by_status", {}).items()] + [""]
    t = report.get("timing") or {}
    if t:
        L += ["## timing (s)", ""] + [f"- {k}: {v}" for k, v in t.items()] + [""]
    if report.get("failures"):
        L += ["## failures", ""] + [f"- `{f.get('code')}`: {f.get('detail', '')[:300]}" for f in report["failures"]] + [""]
    L += ["_Infrastructure success and business acceptance are reported separately; items without gold are REVIEW_REQUIRED and never count as accuracy._", ""]
    return "\n".join(L)


def public_result(row: dict) -> dict:
    """预测行的公开形式: 无原文, 只有 item/question/候选标签/分布/哈希。"""
    return {k: v for k, v in row.items() if k not in ("state", "text")}


def dump_json(path, obj) -> None:
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
