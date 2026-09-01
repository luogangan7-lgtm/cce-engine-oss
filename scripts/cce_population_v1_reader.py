#!/usr/bin/env python3
"""冻结的 v1 Population artifact 只读适配器。

P1 的边界: 冻结件一个字节都不改 —— 它是「当时实际发生过什么」的证据, 重写字段等于重写历史。
所以 v1 artifact 不迁移, 只在**读取时**映射成内存里的 canonical v2 对象。

单向。禁止 v2 -> v1: 反向存在就等于旧 wire contract 重新成为活跃输出能力。
"""
from __future__ import annotations

from typing import Any

V1_KIND = "cce.population_subject.v1"
V2_KIND = "cce.population_subject.v2"

# 只读映射表; 与 config/ontology_legacy_exceptions_v1.json 的 token_map 同源
_FIELD_MAP = {
    "segment_mixture": "mode_mixture",
    "segmentation": "mode_partition",
    "segment_id": "mode_id",
    "segment_basis": "mode_basis",
    "within_segment_mean_js": "within_mode_mean_js",
    "min_segment_size": "min_mode_size",
}


class UnsupportedSchemaVersion(Exception):
    """缺 kind 或 kind 不认识时抛出 —— 绝不猜版本。"""


def _rename(node: Any) -> Any:
    if isinstance(node, dict):
        return {_FIELD_MAP.get(k, k): _rename(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_rename(item) for item in node]
    return node


def adapt_v1_to_v2_in_memory(raw: dict[str, Any]) -> dict[str, Any]:
    out = _rename(raw)
    out["kind"] = V2_KIND
    out["read_via"] = {
        "adapter": "cce_population_v1_reader",
        "source_kind": V1_KIND,
        "direction": "v1_to_v2_read_only",
        "note": "内存对象; 源冻结件未被修改",
    }
    return out


def read_population_artifact(raw: dict[str, Any]) -> dict[str, Any]:
    """按 kind 分派。缺 kind 不猜, 直接抛。"""
    if not isinstance(raw, dict):
        raise UnsupportedSchemaVersion("population artifact must be an object")
    kind = raw.get("kind")
    if kind == V2_KIND:
        return raw
    if kind == V1_KIND:
        return adapt_v1_to_v2_in_memory(raw)
    raise UnsupportedSchemaVersion(f"unsupported population artifact kind: {kind!r}")


if __name__ == "__main__":
    import json
    import sys
    print(json.dumps(read_population_artifact(json.load(open(sys.argv[1]))), ensure_ascii=False, indent=2))
