#!/usr/bin/env python3
"""文档 ↔ 代码 核对闸。

本项目反复栽在「结论写进记录 != 结论进了执行队列」。一份不可执行的对照表自己就会腐烂,
所以做成可跑的: **每条 GATE 声明都必须指向真实存在的文件 + 证据串 + 会跑过的测试**。
声明不到的东西不许标 GATE —— 这条闸的存在就是为了让「有闸」这句话本身不能撒谎。

三档: GATE(有可执行检查) / FIELD_ONLY(有字段但无强制) / PROSE_ONLY(只有一句话)。
FIELD_ONLY 与 PROSE_ONLY **都不构成保护** —— 本项目已确立散文式 caveat 被证伪。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(ROOT, "config", "cce_doc_reconciliation.json")
KINDS = {"GATE", "FIELD_ONLY", "PROSE_ONLY"}
VERDICTS = {"文档过时", "代码欠账", "位置不同+代码欠账", "异名等价", "符合"}


def check(spec_path: str = SPEC, run_tests: bool = True):
    spec = json.load(open(spec_path, encoding="utf-8"))
    errors: list[str] = []
    laws = spec["iron_laws"]
    if len(laws) != 25:
        errors.append(f"§43 是 25 条铁律, 对照表只有 {len(laws)} 条")

    seen_tests = set()
    for n, v in sorted(laws.items(), key=lambda kv: int(kv[0])):
        if v["kind"] not in KINDS:
            errors.append(f"铁律{n}: 未知档位 {v['kind']}")
            continue
        if v["kind"] != "GATE":
            if v["kind"] == "FIELD_ONLY" and not v.get("note"):
                errors.append(f"铁律{n}: 标 FIELD_ONLY 必须写明「有字段但什么都不会因它失败」")
            if v.get("file") or v.get("test"):
                errors.append(f"铁律{n}: 非 GATE 却挂着 file/test —— 二选一")
            continue
        # ★ GATE 声明必须可验证
        for key in ("file", "evidence", "test"):
            if not v.get(key):
                errors.append(f"铁律{n}: 标 GATE 却没写 {key}")
        f, ev, t = v.get("file"), v.get("evidence"), v.get("test")
        if f and not os.path.exists(os.path.join(ROOT, f)):
            errors.append(f"铁律{n}: 声明的 {f} 不存在")
        elif f and ev and ev not in open(os.path.join(ROOT, f), encoding="utf-8").read():
            errors.append(f"铁律{n}: {f} 里找不到证据串 {ev!r} —— 「有闸」这句话是假的")
        if t and not os.path.exists(os.path.join(ROOT, t)):
            errors.append(f"铁律{n}: 声明的测试 {t} 不存在")
        elif t:
            seen_tests.add(t)

    if run_tests:
        for t in sorted(seen_tests):
            r = subprocess.run([sys.executable, t], cwd=ROOT, capture_output=True,
                               env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            if r.returncode != 0:
                errors.append(f"GATE 声明引用的测试红了: {t}")

    for d in spec["section_divergences"]:
        # 判「符合」的必须给出让它成立的那道闸, 否则「符合」就是自称
        if d["verdict"] == "符合":
            g = d.get("gate") or {}
            for key in ("file", "test"):
                if not g.get(key) or not os.path.exists(os.path.join(ROOT, g[key])):
                    errors.append(f"{d['section']}: 判「符合」必须给出真实存在的 gate.{key}")
        if d["verdict"] not in VERDICTS:
            errors.append(f"{d['section']}: 未知判定 {d['verdict']}")
        if not d.get("note"):
            errors.append(f"{d['section']}: 判定必须带 note 说明为什么")

    if "不得把本次结果当成全文" not in spec.get("★not_covered", ""):
        errors.append("必须写明本次未覆盖哪些章节 —— 上次就是把一节当成了全集")

    # ── §45 矩阵 ──────────────────────────────────────────────────────
    m45 = spec.get("section_45_matrix")
    if not m45:
        errors.append("缺 §45 矩阵核对")
    else:
        n = sum(v["declared"] for k, v in m45.items() if isinstance(v, dict) and "declared" in v)
        if n != 37:
            errors.append(f"§45 是 37 项, 核对表只覆盖 {n} 项")
        for k, v in m45.items():
            if not isinstance(v, dict) or "verdict" not in v:
                continue
            if v["verdict"] == "文档过时" and not v.get("actual"):
                errors.append(f"§45 {k} 判「文档过时」必须给出 actual 分布")
            if v["verdict"] == "文档属实" and v.get("verified") != v.get("declared"):
                errors.append(f"§45 {k} 判「属实」但 verified != declared")
        if "命中 != 实现" not in m45.get("★method", ""):
            errors.append("§45 必须写明核对方法(命中 != 实现), 否则下次还会拿 grep 命中当证据")

    # ── §1–§35 ────────────────────────────────────────────────────────
    s135 = spec.get("sections_1_35")
    if not s135:
        errors.append("缺 §1–§35 核对")
    else:
        if not s135.get("not_machine_checkable", {}).get("why"):
            errors.append("§1–§35 里不可机器核的部分必须写明为什么, 不能只列节号")
        if "不得" not in s135.get("not_machine_checkable", {}).get("★do_not_claim", ""):
            errors.append("必须写明: 没核 != 有问题, 也 != 全核完了")
        for sec, blk in s135.get("checked", {}).items():
            if not blk.get("why_checkable"):
                errors.append(f"{sec} 必须写明它为什么可核(是存在性声明而非定义)")
            for f in blk.get("findings", []):
                if not f.get("evidence") and not f.get("note"):
                    errors.append(f"{sec} 的判定「{f['claim'][:20]}」既无 evidence 也无 note")

    s = spec["iron_law_summary"]
    live = {k: sum(1 for v in laws.values() if v["kind"] == k) for k in KINDS}
    for k in KINDS:
        if s.get(k) != live[k]:
            errors.append(f"summary 的 {k}={s.get(k)} 与实际 {live[k]} 不符")
    return (not errors), errors, live


def main() -> int:
    ok, errors, live = check()
    print("=" * 66)
    print("文档 ↔ 代码 核对")
    print("=" * 66)
    print(f"§43 铁律 25 条: GATE {live['GATE']} · FIELD_ONLY {live['FIELD_ONLY']} "
          f"· PROSE_ONLY {live['PROSE_ONLY']}")
    print(f"⇒ **{live['FIELD_ONLY'] + live['PROSE_ONLY']}/25 条铁律没有任何东西会因违反它而变红**")
    spec = json.load(open(SPEC, encoding="utf-8"))
    print()
    for d in spec["section_divergences"]:
        print(f"  {d['verdict']:<16} {d['section']}")
    for e in errors:
        print("  ✗ " + e)
    print()
    print("DOC_RECONCILE_PASS" if ok else "DOC_RECONCILE_FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
