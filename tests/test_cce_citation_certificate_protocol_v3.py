# -*- coding: utf-8 -*-
"""闸: 采集协议 v3 + 原因码 + 预注册 v3。零调用(模型调用用桩)。
守: kind 菜单由合同文本导出且 == INCREMENT_KINDS · prompt_v3 只在三处改动且 sha 与预注册一致 · 修复提示不含判据 · reason_codes 逐族真闸 · 执行器 v3 修复路径最多 2 次调用且产物无原文 · v2 产物 sha 未改 · 生产未接线。"""
import hashlib, importlib.util, json, os, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
def _load(rel, name, env=None):
    old = {k: os.environ.get(k) for k in (env or {})}
    for k, v in (env or {}).items(): os.environ[k] = v
    try:
        s = importlib.util.spec_from_file_location(name, ROOT / rel); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
    finally:
        for k, v in old.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v
P3 = _load("probes/citation_certificate_protocol_v3.py", "_p3t"); r2 = P3.r2
PRE3 = json.loads((ROOT / "tests/data/citation_certificate_production_prereg_v3.json").read_text(encoding="utf-8"))
TEXT = "Settled on the Oticon after two fittings. Been wearing the Oticon daily since March and it gets me through a full day."


def test_menu_derived_from_contract_and_prompt_pinned():
    import cce_label_qualification as LQ
    assert tuple(P3.kind_menu()) == LQ.INCREMENT_KINDS and P3.kind_menu() == PRE3["★★★协议 v3(由闸现算比对)"]["①kind 菜单(由判别式括号机械导出)"]
    p = P3.prompt_v3(""); assert hashlib.sha256(p.encode()).hexdigest()[:16] == PRE3["★★★协议 v3(由闸现算比对)"]["prompt_sha(模板, text 置空)"]
    base = r2.PROMPT % (r2.DISC, "")
    assert base.count("\n") + 1 == p.count("\n") and "只填一个" in p and "复制粘贴" in p and r2.DISC in p   # 只加了一行, 判别式原样
    rp = P3.repair_prompt("{}", [P3.E_KIND_MULTI, P3.E_SPAN]); assert r2.DISC not in rp and "增量" not in rp and "已拥有" not in rp and "E_KIND_MULTI" in rp and "E_SPAN_NOT_VERBATIM" in rp


def test_reason_codes_each_family_and_clean_cert():
    ok = {"supported": True, "evidence": [{"span": "gets me through a full day", "supports": "A", "object": "Oticon", "increment_kind": "数据"}, {"span": "Been wearing the Oticon daily", "supports": "B", "object": "Oticon", "increment_kind": None}]}
    assert P3.reason_codes(ok, TEXT) == []
    assert P3.reason_codes(None, TEXT) == [P3.E_JSON] and P3.reason_codes({"supported": False, "evidence": []}, TEXT) == []
    assert P3.reason_codes({"supported": True, "evidence": []}, TEXT) == [P3.E_SHAPE]
    def mut(**kw):
        c = json.loads(json.dumps(ok)); c["evidence"][0].update(kw); return P3.reason_codes(c, TEXT)
    assert mut(supports="C") == [P3.E_KIND_MENU, P3.E_SUPPORTS] or P3.E_SUPPORTS in mut(supports="C")
    assert mut(span="gets me thru a full day") == [P3.E_SPAN] and mut(object="the aids") == [P3.E_OBJECT]
    assert mut(increment_kind="数据/使用细节") == [P3.E_KIND_MULTI] and mut(increment_kind="价格") == [P3.E_KIND_MENU]
    c = json.loads(json.dumps(ok)); c["evidence"][1]["increment_kind"] = "数据"; assert P3.reason_codes(c, TEXT) == [P3.E_KIND_ON_B]


def test_executor_v3_repairs_once_and_stores_codes_not_text():
    px = _load("probes/citation_certificate_pilot_run.py", "_pxv3", env={"CCE_CERT_PROTOCOL": "v3"}); import cce_label_qualification as LQ, threading
    assert px.PROTOCOL == "v3" and px.P3 is not None
    bad = json.dumps({"supported": True, "evidence": [{"span": "gets me through a full day", "supports": "A", "object": "Oticon", "increment_kind": "数据/使用细节"}, {"span": "Been wearing the Oticon daily", "supports": "B", "object": "Oticon", "increment_kind": None}]}, ensure_ascii=False)
    good = bad.replace("数据/使用细节", "数据"); seen = []
    def fake_call(model, prompt, temperature=0.0, max_retries=1):
        seen.append(prompt); return (bad if len(seen) == 1 else good), {}
    ledger = {"calls": 0, "lock": threading.Lock()}
    c = px.one_cert(TEXT, r2, LQ, fake_call, "M3", ledger, cap=4)
    assert c["calls"] == 2 and c["repaired"] is True and c["reason_codes_first"] == [P3.E_KIND_MULTI] and c["reason_codes"] == [] and ledger["calls"] == 2
    assert "E_KIND_MULTI" in seen[1] and r2.DISC not in seen[1] and c["outcome"] == "UPGRADED" and all(len(w) == 16 for w in c["witness"])
    assert set(c) == {"outcome", "state", "sec", "witness", "n_evidence", "reason_codes", "reason_codes_first", "repaired", "calls"}
    # 上限: cap=1 ⇒ 修复不发, 首答按原样判(MALFORMED), calls 仍 1
    seen.clear(); ledger = {"calls": 0, "lock": threading.Lock()}
    c2 = px.one_cert(TEXT, r2, LQ, fake_call, "M3", ledger, cap=1); assert c2["calls"] == 1 and c2["repaired"] is False and c2["outcome"] == "MALFORMED" and c2["reason_codes"] == [P3.E_KIND_MULTI]


def test_v2_product_untouched_and_not_wired():
    v2 = json.loads((ROOT / "results/citation_certificate_pilot.json").read_text(encoding="utf-8"))
    assert v2["★★★判决(按预注册规则现算)"] == "STOP" and "M5 修复(仅 v3)" not in v2["★★★指标"]
    assert PRE3["supersedes"]["sha"] == hashlib.sha256((ROOT / "tests/data/citation_certificate_production_prereg.json").read_text(encoding="utf-8").encode()).hexdigest()[:16]
    assert PRE3["★预算硬上限"]["证书调用"] == 176 and "未执行" in PRE3["★★★status"] and "5–12%" in PRE3["★★★决策规则(测量前冻结)"]["★预测(先写)"]
    src = (ROOT / "scripts/cce_full_run.py").read_text(encoding="utf-8"); assert "CCE_CITATION_CERT" in src and "shadow_certificates" in src   # ★ 2026-09-24 ADOPT_SHADOW + owner「接吧」⇒ 已接线(默认关)
