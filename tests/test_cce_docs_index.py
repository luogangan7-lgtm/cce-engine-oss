#!/usr/bin/env python3
"""docs/ 索引闸 —— 索引必须与文件实际自述一致。

## 为什么必须可执行
这个项目已经**三次**栽在「拿退役组件当现行标准」上。六份架构文档跨 v2/v3/v3.1,
各自在正文里自述状态, 但要打开文件才知道 —— 而一份**散文索引自己会腐烂**
(本项目已确立散文式 caveat 被证伪)。

## 它检查什么
① docs/ 里每份 .md 都必须在索引里(漏登一份就等于没索引)
② 索引说「现行」的, 文件正文**不得**自述已被取代 —— 反之亦然
③ 索引说「已被取代 → X」的, X 必须真实存在, 且不得指向自己
④ 现行文档不得形成「A 取代 B 又被 B 取代」的环
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
INDEX = os.path.join(DOCS, "README.md")

idx_src = open(INDEX, encoding="utf-8").read()
rows = re.findall(r"^\| `([^`]+)` \| ([^|]+) \|", idx_src, re.M)
listed = {f: s.strip() for f, s in rows}

# ── ① 一份都不许漏登 ──────────────────────────────────────────────────
on_disk = {f for f in os.listdir(DOCS) if f.endswith(".md") and f != "README.md"}
missing = on_disk - set(listed)
extra = set(listed) - on_disk
assert not missing, f"★ docs/ 里这些没登进索引: {sorted(missing)} —— 漏一份索引就不可信"
assert not extra, f"★ 索引登了不存在的文件: {sorted(extra)}"

# ── ②③ 状态必须与文件自述一致 ────────────────────────────────────────
SUPERSEDED_MARK = re.compile(r"(已由|已被)\s*`?([\w./-]+\.md)`?\s*(取代|接管)")
for fname, status in listed.items():
    head = "\n".join(open(os.path.join(DOCS, fname), encoding="utf-8").read().splitlines()[:12])
    self_says = SUPERSEDED_MARK.search(head)
    claims_current = "现行" in status
    if claims_current:
        assert not self_says, (
            f"★ 索引说 {fname} 是「现行」, 但文件自己写着被 "
            f"{self_says.group(2)} 取代 —— 二者必有一错")
    else:
        assert self_says, (
            f"★ 索引说 {fname} 已被取代, 但文件正文没有自述 —— "
            "状态只写在索引里, 打开文件的人看不到")
        # 索引声称的后继必须真实存在
        m = re.search(r"→\s*`([^`]+)`", status)
        assert m, f"★ {fname} 标为被取代却没写后继是谁"
        succ = m.group(1)
        assert succ != fname, f"★ {fname} 指向自己"
        assert os.path.exists(os.path.join(DOCS, succ)), \
            f"★ {fname} 声称的后继 {succ} 不存在"

# ── ④ 取代关系不得成环 ───────────────────────────────────────────────
succ_of = {f: re.search(r"→\s*`([^`]+)`", s).group(1)
           for f, s in listed.items() if "现行" not in s}
for start in succ_of:
    seen, cur = {start}, succ_of[start]
    while cur in succ_of:
        assert cur not in seen, f"★ 取代关系成环: {sorted(seen)}"
        seen.add(cur)
        cur = succ_of[cur]

# ── 权威顺序必须写明「冲突时以代码为准」 ──────────────────────────────
assert "以代码为准" in idx_src, \
    "★ 索引必须写明文档与代码冲突时以谁为准 —— 否则下一个人会拿文档当真相源"
assert "cce_doc_reconciliation.json" in idx_src, "★ 必须指出分歧登记在哪"

# ── ★ Kontrolle: 证明这道闸真会响, 不是恒绿 ──────────────────────────
#    无法证明「看得见失败」的看门狗一文不值。
def _check(listed_alt):
    """把上面四条检查抽出来复跑一遍(只跑不依赖磁盘的那几条)。"""
    errs = []
    on = set(on_disk)
    if on - set(listed_alt):
        errs.append("漏登")
    for f, st in listed_alt.items():
        if f not in on:
            errs.append("登了不存在的")
            continue
        h = "\n".join(open(os.path.join(DOCS, f), encoding="utf-8").read().splitlines()[:12])
        says = SUPERSEDED_MARK.search(h)
        if "现行" in st and says:
            errs.append(f"{f} 索引说现行但文件说被取代")
        if "现行" not in st:
            if not says:
                errs.append(f"{f} 索引说被取代但文件没自述")
            m2 = re.search(r"→\s*`([^`]+)`", st)
            if not m2 or not os.path.exists(os.path.join(DOCS, m2.group(1))):
                errs.append(f"{f} 后继不存在")
    return errs

# 反向 1: 漏登一份
assert _check({k: v for k, v in list(listed.items())[1:]}), "★ 漏登没被抓到"
# 反向 2: 把一份已被取代的谎报成现行
_bad = dict(listed); _bad["cce_chain_architecture_v2.md"] = "**现行 · 链路架构**"
assert any("索引说现行但文件说被取代" in e for e in _check(_bad)), "★ 谎报现行没被抓到"
# 反向 3: 后继指向不存在的文件
_bad2 = dict(listed); _bad2["cce_chain_architecture_v2.md"] = "已被取代 → `不存在的文件.md`"
assert any("后继不存在" in e for e in _check(_bad2)), "★ 假后继没被抓到"
# 正向: 真索引必须零错
assert _check(listed) == [], f"★ 基线应为空: {_check(listed)}"

cur = sum(1 for s in listed.values() if "现行" in s)
print(f"test_cce_docs_index: OK (docs/ {len(on_disk)} 份全部登记 · 现行 {cur} 份 · "
      f"被取代 {len(listed)-cur} 份 | 索引状态与文件自述逐份一致 · "
      "后继实存 · 取代关系无环 | 漏登/谎报现行/假后继 三条反向各自见红 | 写明冲突以代码为准)")
