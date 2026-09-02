#!/usr/bin/env python3
"""链路符合性核对: §48 最简总图的 15 段 × §44 八阶段的验收 gate。

## 为什么是一个脚本而不是一份文档
本项目反复栽在同一个根因上: **结论写进记录 ≠ 结论进了执行队列**。
一份「链路对照表」文档写完当天就开始腐烂, 没人知道它哪一行已经不成立了。
所以这里把对照做成可执行的: 每一段声明它的实现文件与测试文件, 文件没了就红;
每个 Phase 声明它的验收 gate 是哪条命令, 命令红了就红。

## 它不声称什么
它**不**证明每段的语义正确, 只证明:
  ① 声明的实现与测试文件确实存在
  ② 声明的 gate 命令确实退出 0
  ③ 没有 Phase 靠「标 DONE」而没有可跑的 gate
语义正确性由各自的反向测试负责, 不由本文件负责。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP = os.path.join(ROOT, "config", "cce_chain_conformance.json")


def _exists(rel: str) -> bool:
    return os.path.exists(os.path.join(ROOT, rel))


def check(run_gates: bool = True) -> tuple[bool, list[str], dict]:
    """run_gates=False: 只校验对照表结构, 不真去跑八条 gate。

    只给**结构类**反向测试用 —— 那些测试断言的是「表本身写得对不对」,
    跑 gate 对它们没有信息量, 却让一次断言变成 72 次子进程测试(实测 109 秒)。
    正向核对与「gate 红了整表要红」那一条仍然真跑。
    """
    spec = json.load(open(MAP, encoding="utf-8"))
    errors: list[str] = []

    stages = spec["chain_stages"]
    for row in stages:
        for key in ("implemented_in", "tested_by"):
            for rel in row[key]:
                if not _exists(rel):
                    errors.append(f"链路第 {row['n']} 段「{row['stage']}」的 {key} 缺文件: {rel}")
        if not row["implemented_in"]:
            errors.append(f"链路第 {row['n']} 段「{row['stage']}」没有实现文件")
        if not row["tested_by"]:
            errors.append(f"链路第 {row['n']} 段「{row['stage']}」没有测试")

    gate_results = {}
    for ph in spec["phases"]:
        pid = ph["phase"]
        if ph["status"] in ("NOT_STARTED", "BLOCKED"):
            if ph.get("gate_command"):
                errors.append(f"{pid} 标 {ph['status']} 却带着 gate 命令 —— 二选一")
            gate_results[pid] = ph["status"]
            continue
        cmd = ph.get("gate_command")
        if not cmd:
            errors.append(f"{pid} 标 {ph['status']} 却没有可跑的 gate —— "
                          "标 DONE 而没有 gate 就是「感觉差不多了」")
            gate_results[pid] = "NO_GATE"
            continue
        if not ph["status"].startswith("DONE") and not ph.get("why"):
            errors.append(f"{pid} 不是 DONE 却没写 why —— "
                          "「还差什么」必须写出来, 不能只留一个状态词")
        if not run_gates:
            gate_results[pid] = "SKIPPED"
            continue
        proc = subprocess.run(cmd, shell=True, cwd=ROOT, capture_output=True,
                              env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        gate_results[pid] = "PASS" if proc.returncode == 0 else "FAIL"
        if proc.returncode != 0:
            tail = (proc.stdout or proc.stderr).decode("utf-8", "replace").strip().splitlines()[-3:]
            errors.append(f"{pid} 的验收 gate 红了: {cmd}\n      " + "\n      ".join(tail))

    stats = {
        "chain_total": len(stages),
        "chain_implemented": sum(1 for r in stages if r["implemented_in"]),
        "chain_tested": sum(1 for r in stages if r["tested_by"]),
        "phases": gate_results,
        "phases_pass": sum(1 for v in gate_results.values() if v == "PASS"),
        "phases_done": sum(1 for ph in spec["phases"] if ph["status"].startswith("DONE")),
        "phases_total": len(gate_results),
    }
    return (not errors), errors, stats


def main() -> int:
    ok, errors, stats = check()
    spec = json.load(open(MAP, encoding="utf-8"))
    print("=" * 70)
    print("CCE 链路符合性核对  (§48 最简总图 × §44 八阶段验收 gate)")
    print("=" * 70)
    print(f"链路 {stats['chain_implemented']}/{stats['chain_total']} 已实现 · "
          f"{stats['chain_tested']}/{stats['chain_total']} 已测")
    print()
    for row in spec["chain_stages"]:
        mark = "✓" if row["implemented_in"] and row["tested_by"] else "✗"
        print(f"  {mark} {row['n']:2d}. {row['stage']:<26} {row['implemented_in'][0] if row['implemented_in'] else '—'}")
    print()
    print(f"Phase gate {stats['phases_pass']}/{stats['phases_total']} 通过 "
          f"({stats['phases_done']}/{stats['phases_total']} 内容已建)")
    for ph in spec["phases"]:
        v = stats["phases"][ph["phase"]]
        # ★ gate 过 ≠ 这个 Phase 做完了。P3 只交付了 gate、P4 只交付了判据 ——
        #   用同一个 ✓ 显示会把「闸绿」读成「内容做完了」, 那正是本项目栽过的那类假绿。
        done = ph["status"].startswith("DONE")
        measured_fail = (ph.get("measured_verdict") or {}).get("verdict") == "FAIL"
        mark = ("✓" if done else "✗" if measured_fail else "◐") if v == "PASS" else \
               {"FAIL": "✗", "NOT_STARTED": "·", "BLOCKED": "⊘", "NO_GATE": "✗"}[v]
        print(f"  {mark} {ph['phase']:<28} {ph['status']:<30} gate={v}")
        mv = ph.get("measured_verdict")
        if mv:
            print(f"        └─ 实测判定 {mv['verdict']}: 过 {mv['passed']} / 不过 {mv['failed']}")
        if not done and ph.get("why"):
            print(f"        └─ {ph['why']}")
    if errors:
        print()
        for e in errors:
            print("  ✗ " + e)
    print()
    print("CHAIN_CONFORMANCE_PASS" if ok else "CHAIN_CONFORMANCE_FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
