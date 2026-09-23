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
# ★★ 2026-09-07 补 C1 的盲区: 此前只管 knots[].* 与 annotation_protocol.*,
#   **另外 17 个顶层键一个都不管**。knot_taxonomy 的首次消融(probes/knot_taxonomy_ablation.py)
#   实测出 9 条零消费者的顶层键 —— 全部落在这个盲区里。
#   ⇒ 新增顶层键必须**要么被代码引用, 要么在下面具名登记为纯文档**。
#   ★ 登记不是豁免: 它把「这是文档」变成一句**写下来的、可被反驳的声明**,
#     而不是靠没人检查而默认成立。
TOPLEVEL_DOC_ONLY = {
    # 变更日志 —— 纯文档, 零引用, 不进 prompt(消融实测 L1/L2 皆 0/8)
    "changelog_1_1_0", "changelog_1_1_1", "changelog_1_2_0", "changelog_1_3_0",
    "changelog_1_3_1", "changelog_1_3_1_b", "changelog_2026_09_05_atoms_a1a2",
    "changelog_2026_09_07_acceptance_rerun",
    "changelog_2026_09_07_gk3_revoked",
    "changelog_2026_09_07_qualification_is_a_coin_flip",
    "changelog_2026_09_07_repeatability_external_belong",   # ★ 这条闸昨天刚建, 今天就抓到了我自己新加的键
    # 占位槽 —— 「等数据到了再填」, 机制未接线。★ 不是死规则, 是**未来的接口**,
    #   删了等于把「这里还缺东西」这件事也删了(同 sesoi 那类诚实性载荷)。
    "extra_appraisal_slots", "extension_slots_pending_data",
    # ★ 修订说明 —— 它**是**文档(记录「旧 PASS 的资格前提为何被撤销」),
    #   但**同时**有一道断言其内容的闸 tests/test_cce_qualification_premise_revised.py
    #   (钉住两个方向: 数字不许被说成假的 · 不许再说「资格考生效」)。
    #   ⇒ 登记为文档 + 有闸守着, 两者都成立, 都写下来。
    "★qualification_premise_of_the_2026-09-07_PASS_is_revised",
}

# ★★★ 2026-09-08 加第三档 GATED_DOC。
#   C1 原本只有两档: 「被 scripts/accuracy 引用」或「具名登记为纯文档」。
#   ⇒ 一个**只被 tests/ 里的闸引用**的字段会被判成死规则 —— 而它其实**有消费者, 就是那道闸**。
#   ★ 但不能简单把 tests/ 加进 SRC_FILES: 那样「为了让闸绿而写一个只提字段名的闸」也会通过。
#   ⇒ 要求更强: 引用它的测试文件必须**同时含 assert**, 且**报出是哪个文件**, 让「谁在守这个字段」可追溯。
#   ★★ 这比「登记为纯文档」**强**: 登记只是一句声明, 闸是**可执行的**。
TEST_FILES = sorted(glob.glob(f"{ROOT}/tests/test_*.py"))


def _gated_by(field):
    """返回**断言了该字段**的测试文件名; 只提名字不断言的不算。"""
    out = []
    for t in TEST_FILES:
        src = open(t, encoding="utf-8").read()
        if field in src and "assert" in src:
            out.append(os.path.basename(t))
    return out
_top_desc = DESCRIPTIVE | TOPLEVEL_DOC_ONLY | {"knots", "version", "annotation_protocol"}
for f in sorted(set(TAXO) - _top_desc):
    if f'"{f}"' not in ALL and f"'{f}'" not in ALL and f".{f}" not in ALL:
        gates = _gated_by(f)
        if gates:
            warn.append(f"C1 顶层键 {f} 无生产代码引用, 但**被闸守着**(GATED_DOC): {gates}")
            continue
        err.append(f"C1 分类学**顶层**键 {f} 在代码中引用数为 0 —— "
                   f"死规则。若它确实是纯文档, 请具名登记进 TOPLEVEL_DOC_ONLY "
                   f"(登记 = 写下一句可被反驳的声明, 不是豁免); "
                   f"★ **或给它写一道断言其内容的闸** —— 那比登记更强")

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
