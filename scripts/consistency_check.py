#!/usr/bin/env python3
"""配置↔代码一致性自检 — 堵住「规则写在配置里、代码里从没人用」这一类洞。

2026-08-09 建立。当天连续抓到同族缺陷四例:
  1. annotation_protocol.annotator_qualification 定义了, run_gates 从没跑(grep=0)
  2. knots[display].cost_tier_note 校准了, G-K2 预测侧没接(观察侧却在用 followed_up)
  3. FACT_TMPL 抽取 asked_question, observed_tier_from_facts 不计分
  4. COST_TIER / s2 的 taxonomy 版本号是硬编码副本, 与 config 漂移
共同点: 配置声明的东西在代码里引用数为 0, 或代码另存了一份会漂的副本。人工 review 抓不住。

检查项
  C1 字段引用: 分类学每个结字段 / annotation_protocol 每个键, 代码里必须有引用
  C2 内部版本一致: taxonomy.version 与 annotation_protocol.version
  C3 硬编码版本号: 代码里出现 taxonomy 语境下的版本字面量且 != 真值
  C4 键集合副本: 同一字面量里出现 >=4 个九结键(自测夹具需显式豁免)

退出码非 0 = 有 ERROR。WARN 不阻断。
"""
import json, re, os, sys, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAXO = json.load(open(os.path.join(ROOT, "config/knot_taxonomy.json"), encoding="utf-8"))
KEYS = [k["key"] for k in TAXO["knots"]]
VER = TAXO["version"]
SRC_FILES = sorted(glob.glob(f"{ROOT}/scripts/*.py") + glob.glob(f"{ROOT}/accuracy/*.py"))
SRC = {f: open(f, encoding="utf-8").read() for f in SRC_FILES}
ALL = "\n".join(SRC.values())
# 显式豁免: 自测夹具里的键集合不是权威副本
EXEMPT_BLOCKS = {"cce_align_v2.py": "CASES"}
# 纯描述性字段, 供人读不供代码用
DESCRIPTIVE = {"name", "source", "evidence_level", "internal_examples", "typical_codes",
               "definition_of_knot", "identity_criterion", "frozen_at", "status",
               "gate_record", "anchor_source", "_order_note"}

err, warn = [], []

# ── C1 字段引用 ──
fields = set()
for k in TAXO["knots"]:
    fields |= set(k.keys())
for f in sorted(fields - DESCRIPTIVE):
    if f"\"{f}\"" not in ALL and f"'{f}'" not in ALL and f".{f}" not in ALL:
        err.append(f"C1 分类学字段 knots[].{f} 在代码中引用数为 0 —— 死规则")
proto = TAXO.get("annotation_protocol") or {}
for f in sorted(set(proto) - DESCRIPTIVE - {"version"}):
    hits = sum(1 for s in SRC.values() if f in s)
    if hits == 0:
        err.append(f"C1 annotation_protocol.{f} 在代码中引用数为 0 —— 死规则")

# ── C2 内部版本一致 ──
pv = proto.get("version")
if pv and pv != VER:
    err.append(f"C2 annotation_protocol.version={pv} 与 taxonomy.version={VER} 不一致")

# ── C3 硬编码版本号 ──
for f, s in SRC.items():
    for m in re.finditer(r'["\']((?:\d+\.){2}\d+)["\']', s):
        v = m.group(1)
        ctx = s[max(0, m.start() - 70):m.start() + 25].replace("\n", " ")
        if v != VER and re.search(r'taxonom|TAXO', ctx, re.I) and "PINNED" not in ctx:
            ln = s[:m.start()].count("\n") + 1
            err.append(f"C3 {os.path.basename(f)}:{ln} taxonomy 语境下硬编码 '{v}' != {VER}")

# ── C4 键集合副本 ──
for f, s in SRC.items():
    base = os.path.basename(f)
    for m in re.finditer(r'[\{\[][^{}\[\]]{20,600}?[\}\]]', s, re.S):
        blk = m.group(0)
        n = sum(1 for k in KEYS if f'"{k}"' in blk or f"'{k}'" in blk)
        if n < 4 or "TAXO" in blk:
            continue
        ln = s[:m.start()].count("\n") + 1
        tag = EXEMPT_BLOCKS.get(base)
        if tag and re.search(rf"^\s*{tag}\s*=", s, re.M):
            warn.append(f"C4 {base}:{ln} 键集合副本({n}/9) 已豁免(自测夹具 {tag})")
        else:
            err.append(f"C4 {base}:{ln} 九结键硬编码副本({n}/9), 应改为从 config 读")

print(f"配置↔代码一致性自检 · taxonomy {VER} · 扫描 {len(SRC)} 个源文件")
for w in warn:
    print(f"  WARN  {w}")
for e in err:
    print(f"  ERROR {e}")
print(f"\n{'FAIL' if err else 'PASS'} · {len(err)} error / {len(warn)} warn")
sys.exit(1 if err else 0)
