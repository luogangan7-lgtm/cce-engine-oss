#!/usr/bin/env python3
import json, os
p = "run/out/manifest.json"
# ★ 2026-09-28 (诊断 #27): 此前读 run/ref.txt —— 那是 s8 的「上一篇正文」, 不是运行标识, 标题栏会印出整篇上一帖。
ref = open("run/ref_tag", encoding="utf-8").read().strip() if os.path.exists("run/ref_tag") else "-"
print(f"### CCE 执行清单 · `{ref}`")
if not os.path.exists(p):
    print("\n**manifest 缺失 — 链路未产出**")
    raise SystemExit
m = json.load(open(p, encoding="utf-8"))
st = m.get("stages", {})
chain = m.get("chain", list(st))
print(f"\n- complete: **{m.get('complete')}**  ·  failed_at: `{m.get('failed_at')}`\n")
# ★ 2026-09-28 (诊断 #8): 先给出口闸的结论。此前只有下面那张逐段表, 每段截 110 字 —— 扣发的读数照样显示,
#   usable/withheld 台账反被截掉; 看摘要的人读到的正是不许引用的东西。
q = st.get("qualified_readout") or {}
if q:
    print(f"**可引用(usable)** {q.get('usable_count', 0)}: " + (", ".join(f"`{k}`" for k in q.get("usable_keys") or []) or "无"))
    print(f"\n**扣发(withheld)** {q.get('withheld_count', 0)} —— 不是弱证据, 是没有读数:\n")
    for k, why in (q.get("withheld") or {}).items():
        print(f"- `{k}`: {str(why)[:160]}")
    if q.get("s0_read_backend"):
        print(f"\ns0 读出后端: `{q['s0_read_backend']}`")
    print("\n下表是各段原始产出的开头, **不是可引用读数**; 引用以上方 usable 为准。\n")
print("| 段 | 状态 | 秒 | 要点 |")
print("|---|---|---|---|")
for k in chain:
    v = st.get(k, {}) or {}
    body = {kk: vv for kk, vv in v.items() if kk not in ("status", "sec", "file", "detail")}
    s = json.dumps(body, ensure_ascii=False)[:110].replace("|", "/")
    print(f"| {k} | {v.get('status','?')} | {v.get('sec','')} | {s} |")
