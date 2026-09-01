#!/usr/bin/env python3
"""铁律 20 的可执行形式: 新模态增加 Parser, 不应修改 CCE Core。

## 为什么需要一条闸
铁律 20 是一句话, 一句话拦不住任何东西。§44.9 给 P3 定的验收 gate 是
「新增 Parser 后 CCE Core 文件 diff = 0」, 反向测试是「故意在 Core 里改一行,
CI 必须拦」—— 那就得先能机器判定「哪些文件是 Core」。

## 判据
Core = **改了它就换仪器**的文件。这与 instrument_hash 的判据同源:
      「改它之后, 已采集的原始 draw 还能不能用」。
Parser/Ingest = 把外部素材变成 CCE 能吃的输入; 它换了, 已采集的 draw 照样有效。

## 闸怎么判
Core 文件的 sha256 钉在 config/cce_core_manifest.json 里。
  · hash 与钉住的不同, 且 instrument_generation 没有跟着变 -> **红**
    (这就是「静默换仪器」, 正是 instrument_id 当初要防的事)
  · 有意换代时, 同时更新 pin 与 instrument_generation -> 绿
  · Parser 层怎么加、加多少个 -> 完全不影响本闸
Core 清单本身也钉住: 从清单里**删掉**一个 Core 文件同样是红,
否则「把文件移出 Core」就成了绕过闸的办法。
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "config", "cce_core_manifest.json")


def sha256_of(rel: str) -> str:
    with open(os.path.join(ROOT, rel), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:16]


def current_core_hashes(core_files: list[str]) -> dict[str, str]:
    return {rel: sha256_of(rel) for rel in sorted(core_files)}


def check(manifest_path: str = MANIFEST) -> tuple[bool, list[str], dict]:
    man = json.load(open(manifest_path, encoding="utf-8"))
    errors: list[str] = []
    pinned = man["core_files"]
    missing = [rel for rel in pinned if not os.path.exists(os.path.join(ROOT, rel))]
    for rel in missing:
        errors.append(f"Core 文件不存在: {rel} —— 把文件移出 Core 不是绕过闸的办法")
    live = {rel: sha256_of(rel) for rel in pinned if rel not in missing}
    drifted = {rel: (pinned[rel], live[rel]) for rel in live if pinned[rel] != live[rel]}
    if drifted:
        errors.append(
            f"CCE Core 有 {len(drifted)} 个文件与钉住的 hash 不同, "
            f"而 instrument_generation 仍是 {man['instrument_generation']} —— "
            "这是**静默换仪器**。有意换代请同时更新 pin 与 instrument_generation。")
        for rel, (was, now) in sorted(drifted.items()):
            errors.append(f"    {rel}: pinned {was} != live {now}")
    # Parser 层允许自由增删, 但不许把 Core 文件也塞进 Parser 清单蒙混
    overlap = sorted(set(pinned) & set(man.get("parser_plane", [])))
    if overlap:
        errors.append(f"同一文件同时被声明为 Core 与 Parser: {overlap}")
    return (not errors), errors, {"core_n": len(pinned), "drifted": sorted(drifted),
                                  "parser_n": len(man.get("parser_plane", [])),
                                  "instrument_generation": man["instrument_generation"]}


def main() -> int:
    ok, errors, info = check()
    print("=" * 60)
    print("铁律 20 闸: 新增 Parser 不得修改 CCE Core")
    print("=" * 60)
    print(f"Core 文件 {info['core_n']} 个 · Parser 层 {info['parser_n']} 个 · "
          f"instrument_generation = {info['instrument_generation']}")
    for e in errors:
        print("  ✗ " + e)
    print("CORE_BOUNDARY_PASS" if ok else "CORE_BOUNDARY_FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
