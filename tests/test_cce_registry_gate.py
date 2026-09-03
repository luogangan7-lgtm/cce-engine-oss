#!/usr/bin/env python3
"""§36/§37 两个注册表的一致性闸。

库内已确立的权威链: capability registry → workflow registry → 实际 workflow/contract
→ GitHub artifact。既然这两个注册表是头两环, 它们自己必须被守住 ——
否则「退役组件当活标准」那类事故会原样复发。

★ 本文件同时是**铁律 21 从 FIELD_ONLY 升级为 GATE** 的证据:
  此前 workflow_registry 的 rule 字段里写着「research workflows cannot issue
  production complete=true」—— 一句散文, 零强制。
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cce_registry_gate as rg  # noqa: E402

CAP = json.load(open(rg.CAP, encoding="utf-8"))
WF = json.load(open(rg.WF, encoding="utf-8"))

# ── 正向 ───────────────────────────────────────────────────────────────
ok, errors, s = rg.check()
assert ok, f"基线必须绿: {errors}"
# 2026-09-03: +media_presence_declaration(P3 媒体存在声明闸)
assert s["capabilities"] == 9 and s["workflows"] == 15

# ── 1. §36 补的四个字段逐条落地 ────────────────────────────────────────
for c in CAP["capabilities"]:
    assert c.get("evidence_required"), f"{c['id']} 没写 evidence_required"
    assert c["fallback_policy"] in CAP["fallback_policy_values"]
# 2026-09-03 扩域 +FAIL_CLOSED: 入口闸的语义是**不往下走**, 既有三值都预设「继续走」
assert set(CAP["fallback_policy_values"]) == {
    "WITHHOLD", "SKIP_EXPLICIT", "NOT_IN_PRODUCTION_PATH", "FAIL_CLOSED"}
# ★ 每个取值都必须写明它与别的取值差在哪 —— 否则下一个人会随手挑一个近似的
for _v, _d in CAP["fallback_policy_values"].items():
    assert len(_d) > 10, f"取值 {_v} 缺语义说明"
assert "不往下走" in CAP["fallback_policy_values"]["FAIL_CLOSED"], \
    "★ 扩域必须写明为什么不能复用既有值, 否则扩域就是绕过"
assert "静默兜底" in CAP["★why_these_fields"] and "无证据声称能力" in CAP["★why_these_fields"]
# 跳过的字段必须写明为什么跳过, 不能默默不做
assert "两个真值源" in CAP["★skipped_field"], "★ §36 的 version 字段为何不逐能力挂, 必须写明"
assert "服务多个 profile" in WF["★skipped_field"], "★ §37 的 profile 字段为何不挂, 必须写明"

# ── 2. ★ 铁律 21: 声明 vs 实查能力 ─────────────────────────────────────
prod = [p for p, v in WF["workflows"].items() if v["class"] == "production"]
assert prod == [".github/workflows/cce-submit.yml"]
assert WF["workflows"][prod[0]]["production_complete_allowed"] is True
for p, v in WF["workflows"].items():
    if v["class"] == "research":
        assert v["production_complete_allowed"] is False
        assert not rg.can_emit_complete(p), f"★ {p} 是 research 却真能产 complete —— 铁律 21"
# 2026-09-02 摘除 cce.yml 之后: 只剩唯一生产入口能产 complete
assert sum(1 for p in WF["workflows"] if rg.can_emit_complete(p)) == 1, \
    "★ 实查: 摘除后只有 cce-submit.yml 能产 complete"

# ── 3. ★ 那处分歧已由 owner 裁定摘除, 登记表必须随之清空 ────────────────
assert WF["known_divergences"] == [], \
    "★ 分歧已解决, 条目必须删 —— 闸自带「过期豁免必须清掉」的检查, 留着会红"
assert not rg.can_emit_complete(".github/workflows/cce.yml"), \
    "★ cce.yml 的 cce_full_run 调用已摘除, 不得再能产 complete"
cy = WF["workflows"][".github/workflows/cce.yml"]
assert cy["★emits_complete_today"] is False and cy.get("retired_at") == "2026-09-02"
assert "影响面为零" in cy["retired_note"], "★ 摘除的影响面必须写明"
assert sum(1 for p in WF["workflows"] if rg.can_emit_complete(p)) == 1, \
    "★ 摘除后只剩唯一生产入口能产 complete"

# ★ 闸必须剔掉注释再匹配: 只在注释里提到 cce_full_run 不算「能产」
#   (摘除当天实测出的 bug —— 我自己写的退役注释让闸误判成仍能产)
import tempfile as _tf  # noqa: E402
src = open(os.path.join(ROOT, ".github/workflows/cce.yml"), encoding="utf-8").read()
assert "cce_full_run" in src, "退役注释里确实提到了它 —— 这正是要剔注释的理由"
assert "python scripts/cce_full_run" not in src, "真调用必须已摘除"

# ── 反向 ───────────────────────────────────────────────────────────────
def alt(mut_cap=None, mut_wf=None):
    with tempfile.TemporaryDirectory() as td:
        c, w = json.loads(json.dumps(CAP)), json.loads(json.dumps(WF))
        if mut_cap:
            mut_cap(c)
        if mut_wf:
            mut_wf(w)
        pc, pw = os.path.join(td, "c.json"), os.path.join(td, "w.json")
        json.dump(c, open(pc, "w"), ensure_ascii=False)
        json.dump(w, open(pw, "w"), ensure_ascii=False)
        return rg.check(pc, pw)

# ★ research 工作流被声明成允许产 complete + 谎报实查值 -> 红
ok1, e1, _ = alt(mut_wf=lambda w: w["workflows"][".github/workflows/chain.yml"].update(
    {"★emits_complete_today": True}))
assert not ok1 and any("与实查" in x for x in e1), "★ 登记值与实查不符必须红"

# ★ 「能产 complete 却既不被允许、也不登记」-> 红
#   2026-09-02 摘除 cce.yml 之后, 真实数据里已经没有这种情形了(这正是摘除的目的),
#   所以构造一个: 把唯一生产入口降级成 compatibility 且不许产, 又不登记分歧。
def _hide(w):
    w["workflows"][".github/workflows/cce-submit.yml"].update(
        {"class": "compatibility", "production_complete_allowed": False})
    w["known_divergences"] = []
ok2, e2, _ = alt(mut_wf=_hide)
assert not ok2 and any("不许悄悄再开一条生产路" in x for x in e2), \
    "★ 能产 complete 却不登记必须红"

# ★ 两个注册表各说各话 -> 红
ok3, e3, _ = alt(mut_wf=lambda w: w["workflows"][".github/workflows/reply.yml"].update(
    {"capabilities": ["outbound_post_measurement"]}))
assert not ok3 and any("各说各话" in x for x in e3)

ok4, e4, _ = alt(mut_cap=lambda c: c["capabilities"][0].update(
    {"entrypoint": ".github/workflows/nope.yml"}))
assert not ok4 and any("不在 workflow registry" in x for x in e4)

# ★ 无证据声称能力 -> 红
ok5, e5, _ = alt(mut_cap=lambda c: c["capabilities"][0].update({"evidence_required": []}))
assert not ok5 and any("无证据不得声称能力" in x for x in e5)

# ★ 静默兜底(fallback 取值域外) -> 红
ok6, e6, _ = alt(mut_cap=lambda c: c["capabilities"][0].update({"fallback_policy": "SILENT_DEFAULT"}))
assert not ok6 and any("防静默兜底" in x for x in e6)

# ★ 契约指向不存在的文件 -> 红
ok7, e7, _ = alt(mut_cap=lambda c: c["capabilities"][0].update({"input_contract": "config/nope.json"}))
assert not ok7 and any("不存在" in x for x in e7)

# ★ component_only 不指出实现 -> 红
ok8, e8, _ = alt(mut_cap=lambda c: [x.pop("implementation")
                                    for x in c["capabilities"] if x["id"] == "event_assembly"])
assert not ok8 and any("必须指出实现文件" in x for x in e8)

# ★ 缺 production_complete_allowed -> 红(铁律 21 无从判定)
ok9, e9, _ = alt(mut_wf=lambda w: w["workflows"][".github/workflows/oos.yml"].pop(
    "production_complete_allowed"))
assert not ok9 and any("铁律 21 无从判定" in x for x in e9)

# ★ 过期豁免: 登记的分歧其实已不能产 complete -> 红
ok10, e10, _ = alt(mut_wf=lambda w: w["known_divergences"].append(
    {"workflow": ".github/workflows/oos.yml", "why_still_recorded": "x",
     "status": "s", "options": ["o"]}))
assert not ok10 and any("过期豁免" in x for x in e10), \
    "★ 登记了但其实不需要豁免的条目必须清掉, 否则登记表会变成垃圾场"

print(f"test_cce_registry_gate: OK "
      f"(能力 {s['capabilities']} · 工作流 {s['workflows']} · 真能产 complete {s['can_emit_complete']} "
      f"· 已登记分歧 {s['known_divergences']}(已清空) | §36 四字段 + §37 四字段落地, 跳过的两个各写明理由 | "
      f"★ 铁律 21 由散文升为闸: research 类实查不得能产 complete | 10 条反向各自见红)")
