# -*- coding: utf-8 -*-
"""引用证书试点执行器 —— 按 tests/data/citation_certificate_production_prereg.json 跑: 每文本 2 张证书, 判 M1–M4。

★ 会发起调用: (A 2 + B 42) × 2 = 88 次 MiniMax(订阅), 硬上限 88, 每张尝试 1 次(max_retries=1), 失败记 CALL_FAIL 不补。撞上限即停。
★ 协议逐字沿用 r2(PROMPT % (DISC, text) 与 _judge), 投料前把 prompt/_judge sha 与预注册比对, 不符一次 HTTP 都不发。
★ 产物只落 sha16 与统计量: span/object/why 原文一律不落(why 里会带 span)。
★ 生产形状: 每文本 2 张并发; 试点为省墙钟同时跑 3 个文本 —— M3 记的是每文本 max(两张耗时), 与文本间并发无关(并发会略抬单次延迟, 如实标注)。
"""
import hashlib, importlib.util, inspect, json, os, pathlib, statistics, sys, time
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
PROTOCOL = os.environ.get("CCE_CERT_PROTOCOL", "v2")     # v2 = 2026-09-24 试点(已跑, STOP) · v3 = 采集协议 v3(原因码 + 菜单 + 修复重问)
PRE = ROOT / ("tests/data/citation_certificate_production_prereg.json" if PROTOCOL == "v2" else "tests/data/citation_certificate_production_prereg_v3.json")
PRE1 = ROOT / "tests/data/real_corpus_pilot_prereg.json"
OUT = ROOT / ("results/citation_certificate_pilot.json" if PROTOCOL == "v2" else "results/citation_certificate_pilot_v3.json")
PARTIAL = ROOT / ("results/citation_certificate_pilot_partial.jsonl" if PROTOCOL == "v2" else "results/citation_certificate_pilot_v3_partial.jsonl")
ITEM_POOL = 3
P3 = None
if PROTOCOL == "v3":
    _s3 = importlib.util.spec_from_file_location("_p3", ROOT / "probes/citation_certificate_protocol_v3.py"); P3 = importlib.util.module_from_spec(_s3); _s3.loader.exec_module(P3)


def _load(rel, name):
    s = importlib.util.spec_from_file_location(name, ROOT / rel); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def sha16(s): return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def preflight(pre, r2, LQ):
    proto = pre["★★★协议(逐字沿用 r2, 由闸现算比对)"]
    want = sha16(r2.PROMPT % (r2.DISC, "")) if PROTOCOL == "v2" else sha16(P3.prompt_v3(""))
    assert want == proto["prompt_sha(模板, text 置空)"], "★★★ prompt 与预注册不符 —— 未发起任何调用"
    assert sha16(inspect.getsource(r2._judge)) == proto["_judge 源码 sha"], "★★★ _judge 与预注册不符 —— 未发起任何调用"
    assert LQ.P2_BINDING == proto["P2 绑定"], "★★★ P2 绑定版本与预注册不符 —— 未发起任何调用"
    tax = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
    assert any(x.get("hard_discriminant") == r2.DISC for x in tax["knots"]), "★★★ 判别式已不在冻结生产件里 —— 未发起任何调用"


def load_texts(pre):
    mat = pre["★★★试点材料(指针+sha, 冻结)"]; out = []
    for it in mat["A · 归档里 s2 top-1=display 且原文可找回"]["items"]:
        items = json.loads((ROOT / it["text_source"]).read_text(encoding="utf-8")); items = items if isinstance(items, list) else items.get("items")
        t = items[it["item_index"]]["text"]; assert sha16(t) == it["input_sha"], "★★★ 归档文本与预注册 sha 不符 —— 停"
        out.append(("A", it["input_sha"], t))
    cache = {}
    for it in mat["B · real_corpus_pilot 冻结 42 条(top-1 未知)"]["items"]:
        f = it["file"]
        if f not in cache: cache[f] = (ROOT / f).read_text(encoding="utf-8").split("\n")
        line = cache[f][it["line_index"]]; assert hashlib.sha256(line.encode()).hexdigest() == it["sha256"], "★★★ 语料在预注册之后被改过 —— 停"
        out.append(("B", "%s:%d" % (f, it["line_index"]), line))
    return out


def witness_of(obj, text, r2, LQ):
    """只为取 P2 见证集合(sha16): 构造与 _judge 同源的 EvidenceSpan 再过 qualify; 构造失败 ⇒ []。"""
    try:
        ev = []
        for e in obj.get("evidence") or []:
            sup = r2.CONJ.get(str(e.get("supports", "")).strip().upper()); raw_obj = (e.get("object") or "").strip()
            ev.append(LQ.EvidenceSpan(e.get("span") or "", sup, text, about=r2.normalize_about(raw_obj) or None, increment_kind=r2._clean_kind(e.get("increment_kind"))))
        q = LQ.qualify("display", text, evidence=ev, required_conjuncts=[r2.CONJ["A"], r2.CONJ["B"]])
        return sorted(sha16(w) for w in ((q.get("P2") or {}).get("witness") or []))
    except Exception:
        return []


def one_cert(text, r2, LQ, call_model, model, ledger, cap):
    """一张证书。v3: 记原因码(不含文本); MALFORMED 且未撞上限 ⇒ 一次结构化修复重问, 再判。返回里没有任何原文。"""
    def _call(prompt):
        with ledger["lock"]:
            if ledger["calls"] >= cap: return None, {"error": "CAP_HIT"}, 0.0
            ledger["calls"] += 1
        t0 = time.time()
        try: raw, meta = call_model(model, prompt, temperature=0.0, max_retries=1)
        except Exception as ex: raw, meta = "", {"error": type(ex).__name__}
        return raw, meta, round(time.time() - t0, 2)
    prompt = (r2.PROMPT % (r2.DISC, text)) if PROTOCOL == "v2" else P3.prompt_v3(text)
    raw, meta, sec = _call(prompt); calls = 1; repaired = False; codes_first = None
    if (meta or {}).get("error") == "CAP_HIT": return {"outcome": "CAP_HIT", "state": None, "sec": 0.0, "witness": [], "n_evidence": 0, "reason_codes": [], "repaired": False, "calls": 0}
    obj = r2._parse(raw) if raw and raw.strip() else None
    if (meta or {}).get("error") or obj is None:
        codes_first = ["E_JSON"] if not (meta or {}).get("error") else []
        if not ((meta or {}).get("error")) and PROTOCOL == "v3" and raw and raw.strip():
            raw2, meta2, sec2 = _call(P3.repair_prompt(raw[:4000], codes_first))
            if (meta2 or {}).get("error") != "CAP_HIT":   # 撞上限 ⇒ 修复没发, 不计次不标修复
                calls += 1; sec += sec2; repaired = True
                obj = r2._parse(raw2) if raw2 and raw2.strip() and not (meta2 or {}).get("error") else None
        if obj is None: return {"outcome": "CALL_FAIL", "state": None, "sec": sec, "witness": [], "n_evidence": 0, "reason_codes": codes_first or [], "repaired": repaired, "calls": calls}
    if PROTOCOL == "v3":
        codes_first = P3.reason_codes(obj, text) if codes_first is None else codes_first
        if codes_first and calls < 2:
            raw2, meta2, sec2 = _call(P3.repair_prompt(json.dumps(obj, ensure_ascii=False)[:4000], codes_first))
            if (meta2 or {}).get("error") != "CAP_HIT":   # 撞上限 ⇒ 修复没发, 不计次不标修复, 首答按原样判
                calls += 1; sec += sec2; repaired = True
                obj2 = r2._parse(raw2) if raw2 and raw2.strip() and not (meta2 or {}).get("error") else None
                if obj2 is not None: obj = obj2
    t = {"id": "pilot", "arm": "PILOT", "text": text, "推导": {}, "结构": ""}
    oc, why, st = r2._judge(t, obj)
    if oc in (r2.GRANULARITY, r2.DISTINCT): oc = "P2_FAIL"   # 试点无模板声明对象, 两族分不开 ⇒ 合记
    codes_final = P3.reason_codes(obj, text) if PROTOCOL == "v3" else None
    return {"outcome": oc, "state": st, "sec": sec, "witness": witness_of(obj, text, r2, LQ) if oc == r2.UPGRADED else [], "n_evidence": len(obj.get("evidence") or []),
            "reason_codes": codes_final if codes_final is not None else [], "reason_codes_first": codes_first if PROTOCOL == "v3" else None, "repaired": repaired, "calls": calls}


def combine(c1, c2, UP):
    up1, up2 = c1["outcome"] == UP, c2["outcome"] == UP
    inter = sorted(set(c1["witness"]) & set(c2["witness"]))
    fail = "CALL_FAIL" in (c1["outcome"], c2["outcome"]) or "CAP_HIT" in (c1["outcome"], c2["outcome"])
    if fail: label = "CALL_FAIL"
    elif up1 and up2 and inter: label = "CITED_UNVERIFIED"
    elif up1 and up2: label = "BOTH_UPGRADED_NO_COMMON_WITNESS"
    elif up1 != up2: label = "DISAGREE"
    else: label = "BOTH_NOT_UPGRADED"
    return {"决定": label, "可判(两张同类)": (not fail) and (up1 == up2), "升格": label == "CITED_UNVERIFIED",
            "MALFORMED_any": "MALFORMED" in (c1["outcome"], c2["outcome"]), "sec_max": max(c1["sec"], c2["sec"]), "共同见证 sha16": inter}


def evaluate(rows, pre, cp):
    B = [r for r in rows if r["层"] == "B" and r["决定"] != "CALL_FAIL"]; nB = len(B)
    m1 = sum(1 for r in B if r["可判(两张同类)"]); m2 = sum(1 for r in B if r["升格"]); m4 = sum(1 for r in B if r["MALFORMED_any"])
    secs = sorted(r["sec_max"] for r in B); m3 = statistics.median(secs) if secs else None
    calls_fail = sum(1 for r in rows if r["层"] == "B" and r["决定"] == "CALL_FAIL")
    M = {"n_B(去 CALL_FAIL)": nB, "B CALL_FAIL 条数": calls_fail,
         "M1 可判率": {"k": m1, "n": nB, "p": round(m1 / nB, 4) if nB else None, "CP95": [round(x, 4) for x in cp(m1, nB)] if nB else None},
         "M2 升格率": {"k": m2, "n": nB, "p": round(m2 / nB, 4) if nB else None},
         "M3 代价 median(max 两张 s)": m3, "M3 p90": (secs[int(0.9 * (len(secs) - 1))] if secs else None),
         "M4 MALFORMED 率": {"k": m4, "n": nB, "p": round(m4 / nB, 4) if nB else None}}
    p1 = M["M1 可判率"]["p"] or 0; p4 = M["M4 MALFORMED 率"]["p"] or 0
    if p4 > 0.10: v = "STOP"
    elif p1 >= 0.60: v = "ADOPT_SHADOW" if (m3 is not None and m3 <= 45) else "COST_BLOCK"
    else: v = "NEEDS_N3"
    from collections import Counter
    certsB = [c for r in rows if r["层"] == "B" for c in r["certs"]]
    if any(c.get("reason_codes_first") is not None for c in certsB):   # 只有 v3 行才有原因码; v2 产物保持原形
        M["M5 修复(仅 v3)"] = {"证书数": len(certsB), "首答有格式码": sum(1 for c in certsB if c.get("reason_codes_first")), "修复后仍 MALFORMED": sum(1 for c in certsB if c.get("repaired") and c["outcome"] == "MALFORMED"),
                             "首答族分布": dict(Counter(code for c in certsB for code in (c.get("reason_codes_first") or []))), "终态族分布": dict(Counter(code for c in certsB for code in (c.get("reason_codes") or [])))}
    M["B 决定分布"] = dict(Counter(r["决定"] for r in rows if r["层"] == "B")); M["B 单张结局分布"] = dict(Counter(c["outcome"] for r in rows if r["层"] == "B" for c in r["certs"]))
    M["A 层(描述, 不进判决)"] = [{"ptr": r["ptr"], "决定": r["决定"], "outcomes": [c["outcome"] for c in r["certs"]]} for r in rows if r["层"] == "A"]
    return M, v


def main():
    pre = json.loads(PRE.read_text(encoding="utf-8")); psha = sha16(PRE.read_text(encoding="utf-8")); cap = pre["★预算硬上限"]["证书调用"]
    r2 = _load("probes/extractor_counterexample_run_r2.py", "_r2x"); import cce_label_qualification as LQ; preflight(pre, r2, LQ)
    cp = _load("probes/real_corpus_pilot_prereg.py", "_rcp").clopper_pearson
    texts = load_texts(pre); assert len(texts) * 2 * (1 if PROTOCOL == "v2" else 2) == cap, (len(texts), cap)
    r2._load_key(); from exp_crossmodel_desire import call_model; import cce_knot_classify as CK
    import threading; ledger = {"calls": 0, "lock": threading.Lock()}
    if PARTIAL.exists(): PARTIAL.unlink()
    def run_item(item):
        layer, ptr, text = item
        with ThreadPoolExecutor(max_workers=2) as ex: c1, c2 = list(ex.map(lambda _: one_cert(text, r2, LQ, call_model, CK.MEASUREMENT_MODEL, ledger, cap), (0, 1)))
        row = {"层": layer, "ptr": ptr, "text_sha16": sha16(text), "n_chars": len(text), "certs": [c1, c2], **combine(c1, c2, r2.UPGRADED)}
        with ledger["lock"]:
            with PARTIAL.open("a", encoding="utf-8") as fh: fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print("  %s %-52s %s/%s → %s (%.0fs)" % (layer, ptr[-50:], c1["outcome"], c2["outcome"], row["决定"], row["sec_max"])); return row
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=ITEM_POOL) as ex: rows = list(ex.map(run_item, texts))
    M, verdict = evaluate(rows, pre, cp)
    res = {"block": "CITATION_CERTIFICATE_PILOT" + ("" if PROTOCOL == "v2" else "_V3"), "protocol": PROTOCOL, "date": "2026-09-24", "★预注册 sha(投料前冻结)": psha, "model": CK.MEASUREMENT_MODEL,
           "★实际调用": ledger["calls"], "★硬上限": cap, "★墙钟 s": round(time.time() - t0, 1), "★文本间并发": ITEM_POOL,
           "★★★指标": M, "★★★判决(按预注册规则现算)": verdict, "★判决线": pre["★★★决策规则(测量前冻结)"],
           "★怎么读": ["M1 带 CP95; n=42 分辨率有限, 结论句必须带区间。", "③′ 不等于语义正确(MIS-4 类照过); citable_as_confirmed 仍恒 False。", "A 层 n=2 只作描述。", "P2_FAIL 合记 GRANULARITY/DISTINCT(试点无模板声明对象)。"],
           "★隐私": "产物只有指针/sha16/结局/耗时, 无原文 span/object/why。", "rows": rows}
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in M.items() if k.startswith("M") or k.startswith("B ")}, ensure_ascii=False, indent=1)); print("判决:", verdict, "| 调用", ledger["calls"], "/", cap, "→", OUT); return 0


if __name__ == "__main__": sys.exit(main())
