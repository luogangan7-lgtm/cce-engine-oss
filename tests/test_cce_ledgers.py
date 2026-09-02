#!/usr/bin/env python3
"""§42 四条独立 Ledger 的准入闸。

§42 原文是「**必须**分开」——它要防的不是「四张表没建好」, 是**把它们合并**。
所以这里测的是闸: 每条禁止的合并都必须构造一个输入, 确认它真的被拦。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from cce_ledger import (  # noqa: E402
    LedgerAdmissionError, admit, attribute, load, status,
)

SPEC = load()

# ── 1. 四条账齐全, 且状态如实 ──────────────────────────────────────────
assert set(SPEC["ledgers"]) == {"content", "population", "distribution", "outcome"}
st = status()
assert st["content"]["status"] == "POPULATED"
for k in ("population", "distribution", "outcome"):
    assert st[k]["status"] == "DECLARED_EMPTY" and st[k]["why"], \
        f"★ {k} 标空必须写明为什么 —— 「没数据源」和「忘了建」不是一回事"
assert "不是欠账" in SPEC["★declared_empty_is_not_a_gap"]

# ── 2. ★ distribution 只收人工后台读数 ─────────────────────────────────
ok = {"platform": "reddit", "impressions": 1200, "acknowledges_first_entry": True,
      "provenance": {"method": "manual_backend_read", "backend_ref": "reddit insights 截图 0902"}}
assert admit("distribution", ok)["admitted"]

for bad, want in (
    ({**ok, "provenance": {"method": "api_scrape", "backend_ref": "x"}}, "不做自动化抓取"),
    ({**ok, "provenance": {"method": "manual_backend_read"}}, "backend_ref"),
    ({**ok, "creates_identified_subjects": True}, "缺抽样框"),
):
    try:
        admit("distribution", bad)
    except LedgerAdmissionError as e:
        assert want in str(e), f"{want} 的报错不对: {e}"
    else:
        raise AssertionError(f"★ 反向失败: distribution 收下了不该收的({want})")

# ── 3. ★ 平台互动指标不得冒充商业结果 ──────────────────────────────────
good_out = {"lead": 3, "acknowledges_first_entry": True,
            "provenance": {"method": "own_site_analytics"}}
assert admit("outcome", good_out)["admitted"]
for bad, want in (
    ({"upvotes": 40, "lead": 1, "acknowledges_first_entry": True}, "不同真值域"),
    ({"comments": 12, "purchase": 1, "acknowledges_first_entry": True}, "不同真值域"),
    ({"acknowledges_first_entry": True}, "自有资产链"),
    ({**good_out, "simulated": True}, "不可由 LLM 模拟"),
    ({**good_out, "provenance": {"method": "llm"}}, "不可由 LLM 模拟"),
):
    try:
        admit("outcome", bad)
    except LedgerAdmissionError as e:
        assert want in str(e), f"{want} 的报错不对: {e}"
    else:
        raise AssertionError(f"★ 反向失败: outcome 收下了不该收的({want})")

# ── 4. content / population 不得混入分发或商业量 ───────────────────────
assert admit("content", {"knots": {"reward": 0.5}, "instrument_hash": "h"})["admitted"]
for led in ("content", "population"):
    for bad in ({"knots": {}, "impressions": 900}, {"knots": {}, "purchase": 2}):
        try:
            admit(led, {**bad, "acknowledges_first_entry": True})
        except LedgerAdmissionError as e:
            assert "Activation != Distribution" in str(e)
        else:
            raise AssertionError(f"★ 反向失败: {led} 混进了分发/商业量")

# ── 5. ★ DECLARED_EMPTY 的账写第一条必须显式承认 ───────────────────────
try:
    admit("outcome", {"lead": 1, "provenance": {"method": "own_site_analytics"}})
except LedgerAdmissionError as e:
    assert "DECLARED_EMPTY" in str(e) and "status 改掉" in str(e), \
        "★ 必须提示同步改 status —— 否则账里有数据而声明说它是空的"
else:
    raise AssertionError("★ 反向失败: 往声明为空的账里静默写入了第一条")

# ── 6. 跨账连接只能经显式 Attribution, 且必须带证据 ────────────────────
for f, t in [(m["from"], m["to"]) for m in SPEC["forbidden_merges"]]:
    try:
        attribute(f, t)
    except LedgerAdmissionError as e:
        assert "隐式合并" in str(e)
    else:
        raise AssertionError(f"★ 反向失败: {f}→{t} 无证据也能连接")
a = attribute("content", "outcome", evidence=["utm:abc", "deal:2026-09"])
assert a["kind"] == "cce.attribution.v1" and a["assertion"] == "derived"
assert "不得把两账合并成一账" in a["★caveat"]

# ── 7. 不存在的账要报错, 不能静默建一个 ────────────────────────────────
try:
    admit("engagement", {"x": 1})
except LedgerAdmissionError as e:
    assert "四条是" in str(e)
else:
    raise AssertionError("★ 反向失败: 凭空多出一条账")

# ── 8. 四对禁止合并都写了理由 ──────────────────────────────────────────
assert len(SPEC["forbidden_merges"]) == 4
for m in SPEC["forbidden_merges"]:
    assert m.get("why"), f"{m['from']}→{m['to']} 没写为什么禁止"
assert any("Activation != Distribution" in m["why"] for m in SPEC["forbidden_merges"])
assert any("不同真值域" in m["why"] for m in SPEC["forbidden_merges"])

# ── 9. 两条硬约束的出处必须写明是库内既有铁律, 不是本模块新拍 ───────────
d = SPEC["ledgers"]["distribution"]
assert "不做自动化抓取" in d["★admission_rule"] and "水管" in d["★admission_rule"]
o = SPEC["ledgers"]["outcome"]
assert "自有站内容 → UTM 标记 → 落地页 → 独立分析 → 自有潜客库 → 成交" in o["★truth_chain"]

print(f"test_cce_ledgers: OK "
      f"(四条账齐全 · content POPULATED / 三条 DECLARED_EMPTY 且各自写明原因 | "
      f"distribution 拒自动化抓取·拒无后台出处·拒凭曝光造 subject | "
      f"outcome 拒平台指标冒充商业真值·拒 LLM 模拟 | "
      f"content/population 拒混入分发商业量 | 空账首写须显式承认 | "
      f"4 对禁止合并各自见红, 跨账只能走 Attribution)")
