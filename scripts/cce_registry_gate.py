#!/usr/bin/env python3
"""§36/§37 两个注册表的一致性闸。

## 为什么这两个注册表要有闸
库内已确立的权威链是: **capability registry → workflow registry → 实际 workflow/contract
→ GitHub artifact**; 记忆只作背景。既然它们是权威链的头两环, 它们自己就必须被守住,
否则「退役组件当活标准」那类事故会原样复发。

## 三件事
1. **交叉一致**: 能力声明的 entrypoint 必须是登记过的工作流; 工作流声明的 capabilities
   必须是登记过的能力 id。两个注册表不许各说各话。
2. ★ **铁律 21 从散文变成闸**: 此前 workflow_registry 的 rule 字段里写着
   「research workflows cannot issue production complete=true」—— 一句散文, 零强制。
   现在闸会**实查 yml 是否真的调用了 cce_full_run / cce_workflow_manifest**:
     · research 类真能产出 complete   -> 硬红
     · 非 production 非 research 能产出 -> 必须登记在 known_divergences, 未登记即红
   声明与实际能力不符即红 —— 给 research 工作流加上 cce_full_run 会当场被抓。
3. **声称必须有证据**: production_github 状态的能力必须给出 evidence_required,
   且引用的契约文件要真的存在。防的是**无证据声称能力可用**。
"""
from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAP = os.path.join(ROOT, "config", "cce_capability_registry_v1.json")
WF = os.path.join(ROOT, "config", "cce_workflow_registry_v1.json")
EMITS = re.compile(r"cce_full_run|cce_workflow_manifest")


def can_emit_complete(rel: str) -> bool:
    p = os.path.join(ROOT, rel)
    return os.path.exists(p) and bool(EMITS.search(open(p, encoding="utf-8").read()))


def check(cap_path: str = CAP, wf_path: str = WF):
    cap = json.load(open(cap_path, encoding="utf-8"))
    wf = json.load(open(wf_path, encoding="utf-8"))
    errors: list[str] = []
    caps = {c["id"]: c for c in cap["capabilities"]}
    wfs = wf["workflows"]
    fallbacks = set(cap["fallback_policy_values"])

    # ── 1. 交叉一致 ────────────────────────────────────────────────────
    for cid, c in caps.items():
        ep = c.get("entrypoint")
        if ep and ep not in wfs:
            errors.append(f"能力 {cid} 的 entrypoint {ep} 不在 workflow registry 里")
        if c["status"] == "production_github" and not ep:
            errors.append(f"能力 {cid} 标 production_github 却没有 entrypoint")
    for path, v in wfs.items():
        for cid in v.get("capabilities", []):
            if cid not in caps:
                errors.append(f"工作流 {path} 声明的能力 {cid} 不在 capability registry 里")
            elif caps[cid].get("entrypoint") != path:
                errors.append(f"{path} 声明能力 {cid}, 但该能力的 entrypoint 指向 "
                              f"{caps[cid].get('entrypoint')} —— 两个注册表各说各话")

    # ── 2. ★ 铁律 21: 声明 vs 实际能力 ─────────────────────────────────
    div = {d["workflow"]: d for d in wf.get("known_divergences", [])}
    for path, v in wfs.items():
        emits = can_emit_complete(path)
        allowed = v.get("production_complete_allowed")
        if allowed is None:
            errors.append(f"{path}: 缺 production_complete_allowed —— 铁律 21 无从判定")
            continue
        if v.get("★emits_complete_today") != emits:
            errors.append(f"{path}: 登记的 ★emits_complete_today={v.get('★emits_complete_today')} "
                          f"与实查 {emits} 不符")
        if emits and not allowed:
            if v["class"] == "research":
                errors.append(f"★ {path} 是 research 类却**真能产出 complete** —— 铁律 21 硬红")
            elif path not in div:
                errors.append(f"★ {path}({v['class']}) 真能产出 complete 但未登记 known_divergence "
                              "—— 不许悄悄再开一条生产路")
        if v["class"] == "production" and not allowed:
            errors.append(f"{path} 是 production 类却不许产 complete")
    for path, d in div.items():
        if path not in wfs:
            errors.append(f"known_divergence 指向未登记的工作流 {path}")
        elif not can_emit_complete(path):
            errors.append(f"known_divergence {path} 已不再能产出 complete —— 该条目应删除(过期豁免)")
        for k in ("why_still_recorded", "status", "options"):
            if not d.get(k):
                errors.append(f"known_divergence {path} 缺 {k}")

    # ── 3. 声称必须有证据 ──────────────────────────────────────────────
    for cid, c in caps.items():
        if not c.get("evidence_required"):
            errors.append(f"能力 {cid} 没写 evidence_required —— 无证据不得声称能力")
        if c.get("fallback_policy") not in fallbacks:
            errors.append(f"能力 {cid} 的 fallback_policy={c.get('fallback_policy')!r} 不在取值域 "
                          f"{sorted(fallbacks)} —— 防静默兜底")
        for key in ("input_contract", "output_contract"):
            ref = c.get(key)
            if ref and not os.path.exists(os.path.join(ROOT, ref.split("#")[0])):
                errors.append(f"能力 {cid} 的 {key} 指向不存在的 {ref}")
        if c["status"] == "component_only" and not c.get("implementation"):
            errors.append(f"能力 {cid} 标 component_only 必须指出实现文件")
        elif c.get("implementation") and not os.path.exists(os.path.join(ROOT, c["implementation"])):
            errors.append(f"能力 {cid} 的实现 {c['implementation']} 不存在")

    stats = {"capabilities": len(caps), "workflows": len(wfs),
             "can_emit_complete": sum(1 for p in wfs if can_emit_complete(p)),
             "declared_allowed": sum(1 for v in wfs.values() if v.get("production_complete_allowed")),
             "known_divergences": len(div)}
    return (not errors), errors, stats


def main() -> int:
    ok, errors, s = check()
    print("=" * 66)
    print("§36/§37 注册表一致性闸 (权威链头两环)")
    print("=" * 66)
    print(f"能力 {s['capabilities']} · 工作流 {s['workflows']} · "
          f"真能产 complete 的 {s['can_emit_complete']} · 声明允许的 {s['declared_allowed']} · "
          f"已登记分歧 {s['known_divergences']}")
    for e in errors:
        print("  ✗ " + e)
    print()
    print("REGISTRY_GATE_PASS" if ok else "REGISTRY_GATE_FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
