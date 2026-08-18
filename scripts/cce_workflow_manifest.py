#!/usr/bin/env python3
"""Build the aggregate audit manifest for a normalized outbound CCE submission."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

# 2026-08-18: 契约里声明的段清单必须与引擎实跑的 manifest.chain 逐位相等。
# 此前无任何断言, 后果实测: outbound_reply 契约声明 6 段、引擎跑 5 段,
# reader_baseline 在 5 个真实 run 里 0 次出现, 而 complete=true 检测不到 ——
# complete 只回答「CHAINS[mode] 这张表里的段跑完没有」, 不回答「这张表对不对」。
CONTRACT = json.loads(
    (Path(__file__).resolve().parents[1] / "config" / "cce_submission_contract_v1.json")
    .read_text(encoding="utf-8"))


def build(normalized: dict[str, Any], artifacts: Path, require_alignment: bool = False) -> dict[str, Any]:
    expected = {row["_meta"]["job_id"]: row for row in normalized.get("items", [])}
    found: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    profile = normalized.get("profile")
    # subject_chain 的 stages 是流程概念名(source_validation 等), 不是引擎 stage_name,
    # 两者不同域 —— 只对出站两档做逐位比对, 否则 subject-aggregate 会永久红。
    expected_stages = (CONTRACT["profiles"][profile]["stages"]
                       if profile in {"outbound_post", "outbound_reply"} else None)
    for path in artifacts.rglob("manifest.json"):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        meta = manifest.get("submission") or {}
        job_id = meta.get("job_id")
        if job_id not in expected:
            errors.append(f"unexpected or missing submission metadata in {path}")
            continue
        if job_id in found:
            errors.append(f"duplicate job artifact {job_id}")
            continue
        item = expected[job_id]
        if manifest.get("text_sha256") != item["_meta"].get("text_sha256"):
            errors.append(f"exact input fingerprint mismatch for {job_id}")
        # 严格列表相等: 顺序也是契约的一部分, 不用集合/子集。
        # optional_stages(reply_alignment) 不并入 —— 它由 reply_loop.py 写进独立文件, 从不进 chain。
        if expected_stages is not None and manifest.get("chain") != expected_stages:
            errors.append(f"contract chain mismatch for {job_id}: "
                          f"ran {manifest.get('chain')} != contract {expected_stages}")
        alignment = None
        alignment_path = path.with_name("reply_alignment.json")
        # 2026-08-13: 对齐算子只作诊断记录, 其 verdict 不计入 errors——与 workflow 层同步
        # (08-10 实测: 同稿重跑 3/8 翻转, 噪声≈θ; s6 口径"不作放行/拦截依据"; 禁布尔 gate)
        # 2026-08-15: 该诊断已改为按需开启(cce-submit.yml with_alignment), 没跑就没有文件,
        # 「缺文件」只有在明确要求跑过时才是错误, 否则是正常的关闭态。
        if alignment_path.exists():
            alignment = json.loads(alignment_path.read_text(encoding="utf-8")).get("verdict") or {}
        elif profile == "outbound_reply" and require_alignment:
            errors.append(f"reply alignment missing for {job_id}")
        measurement_complete = (manifest.get("stages") or {}).get("s1_readout", {}).get("status") == "OK"
        found[job_id] = {"job_id": job_id, "content_id": meta.get("content_id"),
            "profile": meta.get("profile"), "text_sha256": manifest.get("text_sha256"),
            "engine_complete": manifest.get("complete") is True, "failed_at": manifest.get("failed_at"),
            "measurement_complete": measurement_complete,
            "reply_alignment_pass": alignment.get("PASS") if alignment is not None else None,
            "artifact_dir": str(path.parent)}
        if profile == "subject_chain" and not measurement_complete:
            errors.append(f"s1 response measurement incomplete for {job_id}")
        elif profile != "subject_chain" and manifest.get("complete") is not True:
            errors.append(f"engine chain incomplete for {job_id}: {manifest.get('failed_at')}")
    missing = sorted(set(expected) - set(found))
    if missing: errors.append("missing job artifacts: " + ", ".join(missing))
    return {"kind": "cce.workflow_manifest.v1", "schema_version": normalized.get("schema_version"),
        "submission_id": normalized.get("submission_id"), "profile": normalized.get("profile"),
        "complete": not errors and len(found) == len(expected), "items_expected": len(expected),
        "items_completed": len(found), "jobs": [found[key] for key in sorted(found)], "errors": errors}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--normalized", required=True, type=Path)
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--require-alignment", action="store_true",
                        help="对齐诊断本次被要求跑过, 缺 reply_alignment.json 算错误")
    args = parser.parse_args()
    normalized = json.loads(args.normalized.read_text(encoding="utf-8"))
    manifest = build(normalized, args.artifacts, args.require_alignment)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"submission_id": manifest["submission_id"], "complete": manifest["complete"],
                      "items": manifest["items_completed"], "errors": manifest["errors"]}, ensure_ascii=False))
    raise SystemExit(0 if manifest["complete"] else 1)


if __name__ == "__main__": main()
