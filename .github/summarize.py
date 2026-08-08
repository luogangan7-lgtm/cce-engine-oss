#!/usr/bin/env python3
import json, os
p = "run/out/manifest.json"
ref = open("run/ref.txt", encoding="utf-8").read().strip() if os.path.exists("run/ref.txt") else "-"
print(f"### CCE 执行清单 · `{ref}`")
if not os.path.exists(p):
    print("\n**manifest 缺失 — 链路未产出**")
    raise SystemExit
m = json.load(open(p, encoding="utf-8"))
st = m.get("stages", {})
chain = m.get("chain", list(st))
print(f"\n- complete: **{m.get('complete')}**  ·  failed_at: `{m.get('failed_at')}`\n")
print("| 段 | 状态 | 秒 | 要点 |")
print("|---|---|---|---|")
for k in chain:
    v = st.get(k, {}) or {}
    body = {kk: vv for kk, vv in v.items() if kk not in ("status", "sec", "file", "detail")}
    s = json.dumps(body, ensure_ascii=False)[:110].replace("|", "/")
    print(f"| {k} | {v.get('status','?')} | {v.get('sec','')} | {s} |")
