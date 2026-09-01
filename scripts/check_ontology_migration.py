#!/usr/bin/env python3
"""P1 本体迁移闸。

原验收标准是「旧名在生产路径 grep 命中 == 0」。那条标准写错了，实测不可达：
它把五种本质不同的情况混成了一个文本搜索结果 ——
  1. 仍在使用的旧本体            ← 只有这一类是真违规
  2. 冻结证据里的历史字段        ← 永远不能改，改了就是改历史
  3. 必须保留的黑名单哨兵        ← 删掉反而降低安全性
  4. 与本体无关的同名符号        ← 文本跨度切分和人群分群同名异义
  5. 被测量语料自己的英文单词    ← 真人写的 "susceptible individuals"，是 payload 不是本体

本闸的判据因此不是「搜不到旧名」，而是
    「搜到的每一处旧名都有唯一、明确、可审计的合法类别」。
grep 在这里只是 inventory，不是 verdict。

退出码非 0 = P1 不通过。
"""
from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, "config", "ontology_legacy_exceptions_v1.json")
# 登记表自身必须写出旧名才能履行职责，故不自查；它没有可执行语义。
SELF_EXEMPT = {
    os.path.relpath(REGISTRY, ROOT),
    os.path.relpath(os.path.abspath(__file__), ROOT),
}

SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules", "results"}
TEXTUAL = (".py", ".json", ".md", ".yml", ".yaml")


def load_registry(path: str = REGISTRY) -> dict:
    with open(path, encoding="utf-8") as fh:
        reg = json.load(fh)
    for entry in reg.get("entries", []):
        loc = entry.get("path", "")
        if any(ch in loc for ch in "*?[") or loc.endswith("/"):
            raise ValueError(
                f"登记表禁止通配/整目录豁免（会退化成 blanket exemption）: {loc!r}"
            )
        if entry.get("class") not in reg["allowed_classes"]:
            raise ValueError(f"未知豁免类别: {entry.get('class')!r} @ {loc}")
    return reg


def surface_of(rel: str, surfaces: dict) -> str:
    """最长前缀优先: tests/data/ 必须先于 tests/ 命中。"""
    best = ("EVIDENCE", -1)
    for name, prefixes in surfaces.items():
        for p in prefixes:
            if rel.startswith(p) and len(p) > best[1]:
                best = (name, len(p))
    return best[0]


def _unused_surface_of(rel: str, surfaces: dict) -> str:
    for name, prefixes in surfaces.items():
        if any(rel.startswith(p) for p in prefixes):
            return name
    return "EVIDENCE"


def _json_tokens(text: str, values: bool) -> list[tuple[int, str]]:
    """返回 (行号, 待扫描片段)。values=False 时只取 object key。"""
    out = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for m in re.finditer(r'"((?:[^"\\]|\\.)*)"\s*(:?)', line):
            is_key = m.group(2) == ":"
            if is_key or values:
                out.append((lineno, m.group(1)))
    return out


def scan_file(path: str, rel: str, surface: str, mode: str, tokens: list[str]):
    """产出 (行号, 旧名) 列表。"""
    try:
        text = open(path, encoding="utf-8").read()
    except (UnicodeDecodeError, OSError):
        return []
    pattern = re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(map(re.escape, tokens)) + r")(?![A-Za-z0-9_])")
    hits = []
    if mode == "python_source_text":
        for lineno, line in enumerate(text.splitlines(), 1):
            hits += [(lineno, m.group(1)) for m in pattern.finditer(line)]
    elif mode in ("json_keys_only", "json_keys_and_values"):
        for lineno, frag in _json_tokens(text, values=(mode == "json_keys_and_values")):
            hits += [(lineno, m.group(1)) for m in pattern.finditer(frag)]
    elif mode == "inventory_only":
        for lineno, line in enumerate(text.splitlines(), 1):
            hits += [(lineno, m.group(1)) for m in pattern.finditer(line)]
    return hits


def main(argv: list[str]) -> int:
    reg = load_registry()
    tokens = sorted(reg["token_map"], key=len, reverse=True)
    surfaces = reg["surfaces"]
    scan_mode = reg["surface_scan_mode"]
    registered = {(e["path"], e["token"]): e for e in reg["entries"]}

    active: list[str] = []          # 真违规：活跃旧本体依赖
    unclassified: list[str] = []    # 真违规：未登记的旧名出现
    undeclared_code: list[str] = [] # 真违规：EVIDENCE 面上出现可执行代码
    inventory: dict[str, int] = {}
    used_entries: set[tuple[str, str]] = set()

    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in sorted(filenames):
            if not fn.endswith(TEXTUAL):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, ROOT)
            if rel in SELF_EXEMPT:
                continue
            surface = surface_of(rel, surfaces)
            if surface == "EVIDENCE" and fn.endswith(".py"):
                undeclared_code.append(rel)
                continue
            mode = scan_mode[surface]
            for lineno, tok in scan_file(path, rel, surface, mode, tokens):
                inventory[surface] = inventory.get(surface, 0) + 1
                entry = registered.get((rel, tok))
                if entry:
                    used_entries.add((rel, tok))
                    continue
                if surface == "DOCUMENTATION":
                    # 文档默认按历史文档处理，但仍进 inventory 计数
                    continue
                if surface in ("EVIDENCE", "EVIDENCE_DATA"):
                    unclassified.append(f"{rel}:{lineno}  {tok}  [EVIDENCE 里的 object key 必须登记]")
                else:
                    active.append(f"{rel}:{lineno}  {tok} -> {reg['token_map'][tok]}")

    stale = sorted(set(registered) - used_entries)

    print("=" * 68)
    print("P1 本体迁移闸  (旧 gate「grep==0」已作废，见 docstring)")
    print("=" * 68)
    print(f"遗留出现 inventory（不是判据，只是清单）: {inventory or '无'}")
    print()
    ok = True
    for label, rows in (
        ("active_legacy_dependency  活跃旧本体依赖", active),
        ("unclassified_occurrence   未登记的旧名出现", unclassified),
        ("undeclared_code_surface   未声明面上的可执行代码", undeclared_code),
        ("stale_registry_entry      登记了但已不存在的豁免", [f"{p}  {t}" for p, t in stale]),
    ):
        n = len(rows)
        print(f"{'✓' if n == 0 else '✗'} {label}: {n}")
        for r in rows[:200]:
            print(f"      {r}")
        if n > 200:
            print(f"      … 另有 {n - 200} 条")
        if n:
            ok = False
    print()
    print("P1_PASS" if ok else "P1_FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
