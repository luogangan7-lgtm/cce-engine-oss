#!/usr/bin/env python3
"""§42 四条独立 Ledger 的**准入闸**。

## 为什么重点是闸而不是四张表
§42 原文用「**必须**分开」——它要防的不是「四张表没建好」, 是**把它们合并**:
  · 铁律 9: Activation != Distribution —— 内容能激活谁, 不等于平台会送给谁
  · 库内铁律: 平台互动指标(触达/点赞/评论)属于**不同真值域**, 无法替代商业真值
实测四条账里只有 content 有数据, 另外三条**没有数据源**。
给不存在的数据建三张空表是脚手架; 但**准入规则现在就该生效** ——
等数据真来的那天, 合并已经被闸挡住了。

## 两条硬约束(来自库内已确立的铁律, 不是本模块新拍的)
· distribution 只收**人工后台读数**: 平台侧指标查阅走人工后台, **不做自动化抓取**。
  第三方平台 API 是平台可随时关闭的水管, 不能作为地基。
· outcome 只收**自有资产链**上的结果: 自有站 → UTM → 落地页 → 独立分析 →
  自有潜客库 → 成交。平台互动指标不得入账。
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(ROOT, "config", "cce_ledgers_v1.json")

# 平台互动指标 —— 它们是**分发侧**的量, 不是商业真值
PLATFORM_METRICS = {"impression", "impressions", "view", "views", "watch_time", "completion",
                    "rewatch", "like", "likes", "upvote", "upvotes", "comment", "comments",
                    "save", "share", "shares", "follow", "followers", "reach", "曝光", "浏览"}
# 自有资产链上的结果
OWNED_OUTCOMES = {"lead", "purchase", "repeat_purchase", "deal", "signup", "utm_click",
                  "landing_view", "form_submit"}


# 状态层的量: 由仪器**测**出来的心理状态读数, 不是被**观察**到的行为。
# 铁律 4 State != Behavior —— 夹带一个 owned key 就能把状态塞进 outcome 账,
# 2026-09-03 实测确有此洞(admit('outcome', {'deal':1,'knots':{...}}) 曾放行)。
STATE_KEYS = {"knots", "intensity", "weight", "mass", "quadrant", "families",
              "desire_vec", "emotion_vec", "action_vec", "appraisal", "composition",
              "drive_brake", "levers_present"}


class LedgerAdmissionError(ValueError):
    """记录进错了账。★ typed —— 上层可精确捕获, 但捕获它不等于允许入账。"""


def load(path: str = SPEC) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def admit(ledger: str, record: dict, path: str = SPEC) -> dict:
    """把一条记录放进某个账。违反准入规则即抛。"""
    spec = load(path)
    if ledger not in spec["ledgers"]:
        raise LedgerAdmissionError(f"没有名为 {ledger!r} 的账; 四条是 {sorted(spec['ledgers'])}")
    L = spec["ledgers"][ledger]
    keys = {str(k).lower() for k in record}

    # ── distribution: 只收人工后台读数 ──────────────────────────────────
    if ledger == "distribution":
        prov = (record.get("provenance") or {})
        if prov.get("method") != "manual_backend_read":
            raise LedgerAdmissionError(
                "distribution 只收**人工后台读数**(provenance.method=manual_backend_read) —— "
                "平台侧指标不做自动化抓取; 第三方 API 是平台可随时关闭的水管, 不能作为地基。"
                f" 实际 method={prov.get('method')!r}")
        if not prov.get("backend_ref"):
            raise LedgerAdmissionError("distribution 记录必须带 provenance.backend_ref(后台出处)")
        if record.get("creates_identified_subjects"):
            raise LedgerAdmissionError(
                "平台曝光总数**不得**直接用于创建 identified reached subjects —— 缺抽样框")

    # ── outcome: 平台互动指标不得冒充商业结果 ──────────────────────────
    if ledger == "outcome":
        bad = keys & PLATFORM_METRICS
        if bad:
            raise LedgerAdmissionError(
                f"outcome 里出现平台互动指标 {sorted(bad)} —— 它们属于**不同真值域**, "
                "无法替代商业真值。唯一可靠真值链: 自有站 → UTM → 落地页 → 独立分析 → "
                "自有潜客库 → 成交。这类指标应进 distribution。")
        if not (keys & OWNED_OUTCOMES):
            raise LedgerAdmissionError(
                f"outcome 记录必须含至少一项自有资产链结果 {sorted(OWNED_OUTCOMES)}")
        if record.get("simulated") or (record.get("provenance") or {}).get("method") == "llm":
            raise LedgerAdmissionError("实际行为与商业结果**不可由 LLM 模拟**")

    # ── 铁律 4: State != Behavior —— 状态读数不得进 outcome / distribution ──
    #    ★ 光靠「必须含 owned key」拦不住: 带上一个 owned key 就能夹带(实测放行过)。
    if ledger in ("outcome", "distribution"):
        bad = keys & STATE_KEYS
        if bad:
            raise LedgerAdmissionError(
                f"{ledger} 里出现状态层读数 {sorted(bad)} —— 铁律 4: State != Behavior。"
                "状态是仪器**测**出来的, 行为与分发是**观察**到的; 前者进 content 账。"
                "★ 带一个 owned key 就夹带进来, 正是这条闸补上的洞。")

    # ── content / population: 不得混入分发或商业量 ──────────────────────
    if ledger in ("content", "population"):
        bad = keys & (PLATFORM_METRICS | OWNED_OUTCOMES)
        if bad:
            raise LedgerAdmissionError(
                f"{ledger} 里出现 {sorted(bad)} —— 那是 distribution/outcome 的量。"
                "铁律 9: Activation != Distribution。跨账连接只能经**显式 Attribution**。")

    if L["status"] == "DECLARED_EMPTY":
        # 允许写入(数据真来了就该写), 但必须显式承认这会改变账的状态
        if not record.get("acknowledges_first_entry"):
            raise LedgerAdmissionError(
                f"{ledger} 当前标 DECLARED_EMPTY({L['why']})。"
                "写入第一条记录前必须显式 acknowledges_first_entry=True, "
                "并同步把 config/cce_ledgers_v1.json 的 status 改掉 —— "
                "否则账里有数据而声明说它是空的。")
    return {"ledger": ledger, "admitted": True, "record_keys": sorted(record)}


def attribute(from_ledger: str, to_ledger: str, *, evidence: list | None = None,
              path: str = SPEC) -> dict:
    """跨账连接的**唯一**合法入口。禁止隐式合并。"""
    spec = load(path)
    pair = {(m["from"], m["to"]): m for m in spec["forbidden_merges"]}
    m = pair.get((from_ledger, to_ledger))
    if not evidence:
        raise LedgerAdmissionError(
            f"{from_ledger} → {to_ledger} 的连接必须带 evidence —— "
            "无证据的跨账连接就是隐式合并" + (f"; 且 {m['why']}" if m else ""))
    return {"kind": "cce.attribution.v1", "from": from_ledger, "to": to_ledger,
            "evidence": evidence, "assertion": "derived",
            "★caveat": (m["why"] if m else "跨账连接是推断, 不是观测") +
                       " —— 本连接是 Attribution, 不得把两账合并成一账。"}


def status(path: str = SPEC) -> dict:
    spec = load(path)
    return {k: {"status": v["status"], "why": v.get("why")} for k, v in spec["ledgers"].items()}


def main() -> int:
    spec = load()
    print("=" * 66)
    print("§42 四条独立 Ledger")
    print("=" * 66)
    for k, v in spec["ledgers"].items():
        mark = "✓" if v["status"] == "POPULATED" else "·"
        print(f"  {mark} {k:<13} {v['status']:<16} {v['question']}")
        if v.get("why"):
            print(f"      {v['why'][:78]}")
    print()
    print(f"  分离规则: {spec['separation_rule']}")
    print(f"  禁止合并: {len(spec['forbidden_merges'])} 对")
    print()
    print(spec["★declared_empty_is_not_a_gap"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
