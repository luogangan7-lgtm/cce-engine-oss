#!/usr/bin/env python3
"""机制登记表 —— §44 Phase 6 的「candidate → preregister → test → replicate → reject」。

## 为什么要有它
本仓库已经产出过十几条机制结论(词面不变性失败、稀释而非长度、mixed-content
interference…), 但它们**只以散文形态躺在 4416 行架构文档的 33 个小节里**。
后果实测: 2026-09-01 owner 问「CCE 到哪一步了」, 我只能靠 grep 逐条重新推导 ——
**已确立的东西不可查询, 等于每次都要重新确立一遍。**

## 登记的硬判据(§44.9 事先写好的验收 gate)
> 每条 mechanism 记录都能追到 evidence_refs, 且至少一次 replication
> 反向: 造一条无 evidence 的 mechanism, 注册必须被拒

所以 `register()` 不是写入函数, 是**闸**:
- `evidence_refs` 为空 → 拒
- 引用的文件不存在 → 拒(防止指向想象中的 artifact)
- `status=ESTABLISHED` 但 `replications < 1` → 拒
- `preregistered=True` 但拿不出前登记冻结件 → 拒

## 为什么 status 是四档而不是布尔
`REJECTED` 必须能被登记 —— 否则下一个 agent 会重做已被否决的实验(本项目实际发生过,
库里有 21 条 rejected 记录正是为此)。**被否决的机制和被确立的机制同样值钱。**
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, "config", "mechanism_registry.json")

STATUS = ("CANDIDATE", "TESTED", "ESTABLISHED", "REJECTED")
REQUIRED = ("id", "claim", "status", "evidence_refs")


def _load():
    if not os.path.exists(REGISTRY):
        return {"schema": "cce.mechanism.v1", "mechanisms": []}
    with open(REGISTRY, encoding="utf-8") as f:
        return json.load(f)


def validate(m, existing_ids=()):
    """返回 issue 列表。空 = 可登记。**这是闸, 不是建议。**"""
    issues = []
    for k in REQUIRED:
        if not str(m.get(k, "")).strip():
            issues.append(f"缺必填字段 `{k}`")
    if m.get("status") and m["status"] not in STATUS:
        issues.append(f"status 必须是 {STATUS} 之一, 实得 {m['status']!r}")
    if m.get("id") in existing_ids:
        issues.append(f"id `{m['id']}` 已存在 —— 改用 supersedes 而非重复登记")

    refs = m.get("evidence_refs") or []
    if not refs:
        issues.append("evidence_refs 为空 —— 没有证据的机制不得登记(§44.9 反向测试正是这条)")
    for r in refs:
        if not os.path.exists(os.path.join(ROOT, r)):
            issues.append(f"evidence_ref 指向不存在的文件: {r} —— 不得引用想象中的 artifact")

    if m.get("status") == "ESTABLISHED":
        if len(m.get("replications") or []) < 1:
            issues.append("status=ESTABLISHED 需至少一次 replication(§44.9 验收 gate)")
        for r in m.get("replications") or []:
            if not os.path.exists(os.path.join(ROOT, r)):
                issues.append(f"replication 指向不存在的文件: {r}")

    if m.get("preregistered") and not m.get("prereg_ref"):
        issues.append("声称 preregistered 却没给 prereg_ref —— 事后声称前登记是最坏的一种")
    if m.get("prereg_ref") and not os.path.exists(os.path.join(ROOT, m["prereg_ref"])):
        issues.append(f"prereg_ref 指向不存在的文件: {m['prereg_ref']}")
    return issues


def register(m):
    reg = _load()
    issues = validate(m, {x["id"] for x in reg["mechanisms"]})
    if issues:
        return issues
    reg["mechanisms"].append(m)
    os.makedirs(os.path.dirname(REGISTRY), exist_ok=True)
    with open(REGISTRY, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=1)
    return []


def audit():
    """全表复核 —— 引用的文件可能在登记之后被删。"""
    reg = _load()
    bad = []
    for m in reg["mechanisms"]:
        iss = validate(m, ())
        iss = [i for i in iss if "已存在" not in i]
        if iss:
            bad.append((m.get("id", "?"), iss))
    return reg, bad


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "audit"
    if cmd == "register":
        errs = register(json.load(open(sys.argv[2], encoding="utf-8")))
        if errs:
            print("❌ 拒绝登记:")
            for e in errs:
                print(f"  - {e}")
            sys.exit(1)
        print("✔ 已登记")
    else:
        reg, bad = audit()
        by = {}
        for m in reg["mechanisms"]:
            by.setdefault(m["status"], []).append(m)
        print(f"机制登记表 · {len(reg['mechanisms'])} 条")
        for s in STATUS:
            for m in by.get(s, []):
                print(f"  [{s:12s}] {m['id']:28s} {m['claim'][:52]}")
        if bad:
            print("\n❌ 复核失败(证据文件已不存在?):")
            for i, iss in bad:
                print(f"  {i}: {iss}")
            sys.exit(1)
