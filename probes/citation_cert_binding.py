# -*- coding: utf-8 -*-
"""s2b 引用证书 · 真实文本上的说话人绑定测试(预注册 tests/data/citation_cert_binding_prereg.json)。

证书要模型逐字引一段、指一个对象、并确认两个必要条件(A 有新信息增量; B 对象是写的人自己已拥有或已经历的)。校验器只查逐字与结构,
语义只在 16 条手构模板上测过。网页 GPT(2026-09-30): 测「语义关系」而不是子串 —— 把文字原样留着, 只改「这是谁的经历」。
对每条在原文上发得出证书(CITED_UNVERIFIED)的真实文本(根), 用生产同一入口 shadow_certificates 再跑三次:
  重读     原文再跑一次                                   —— 应仍发证(保持)
  假框     前面加一句「以下是我自己的亲身经历」并加引号      —— 应仍发证(保持; 防「一改就拒」的空过)
  B 负框   前面加一句「以下内容我从未拥有、用过或经历过, 只是转述陌生人的原话」并加引号 —— **不应**发证(B 被明确否定; 引号里的「我」不是写的人)
只送正文给 MiniMax(保险库多轮链语料的非楼主发言, 不含用户名提及)。产物只落 sha16 / 决定 / 调用数, 不落原文与 span。硬上限 1800 次请求。
用法: .venv/bin/python probes/citation_cert_binding.py [--dry-run | --rescore]
"""
import argparse, collections, hashlib, importlib.util, json, os, pathlib, random, re, sys, tempfile
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "probes"))
import cce_citation_certificate as CC                        # noqa: E402
from cce_request_budget import open_scope, scope_status     # noqa: E402
_s = importlib.util.spec_from_file_location("_mon", ROOT / "probes/within_js_monitor.py"); MON = importlib.util.module_from_spec(_s); _s.loader.exec_module(MON)
PRE = ROOT / "tests/data/citation_cert_binding_prereg.json"
NUM = ROOT / "results/citation_cert_binding_rows.json"
OUT = ROOT / "results/citation_cert_binding.json"
VAULT = pathlib.Path("/Volumes/data/cce-identified-vault/hearingaids_chains_20260809.json")
CAP, N_ROOTS, MAX_SCREEN, SEED, WORKERS = 1800, 59, 520, 20261002, 3
MAX_VIOLATION, MIN_PRESERVE, EARLY_MIN = 0.05, 0.80, 20
FRAMES = {"reread": "%s",
          "sham": "I'm posting my own first-hand experience here, in my own words:\n\n\"%s\"",
          "b_neg": "I have never owned, used or experienced any of what is described below; I'm only passing along, word for word, what a stranger wrote:\n\n\"%s\""}
_MENTION = re.compile(r"\bu/\w+|/user/\w+")


def sample():
    el = []
    for c in json.loads(VAULT.read_text(encoding="utf-8"))["chains"]:
        if c["isOP"]: continue
        for t in c["turns"]:
            if 40 <= len(t["b"].split()) <= 200 and not _MENTION.search(t["b"]) and '"' not in t["b"]:
                el.append(t["b"])
    el = sorted(set(el), key=lambda b: hashlib.sha256(b.encode()).hexdigest()); random.Random(SEED).shuffle(el)
    return el[:MAX_SCREEN]


def upper(k, n): return MON.clopper_pearson(k, n, 0.10)[1] if n else 1.0      # 单侧 95%
def lower(k, n): return MON.clopper_pearson(k, n, 0.10)[0] if n else 0.0


def build(rows):
    roots = [r for r in rows if r["orig"] == "CITED_UNVERIFIED" and all(r.get(k) for k in FRAMES)][:N_ROOTS]
    n = len(roots); ok = lambda r, k: r[k] == "CITED_UNVERIFIED"
    viol = sum(ok(r, "b_neg") for r in roots); sham = sum(ok(r, "sham") for r in roots); rr = sum(ok(r, "reread") for r in roots)
    res = {"screened": len(rows), "screen_decisions": dict(collections.Counter(r["orig"] for r in rows)), "issued_on_original": sum(r["orig"] == "CITED_UNVERIFIED" for r in rows), "roots": n,
           "b_neg_still_issued": viol, "b_neg_ucb95": upper(viol, n), "b_neg_lcb95": lower(viol, n),
           "sham_preserved": sham, "sham_lcb95": lower(sham, n), "reread_preserved": rr, "reread_lcb95": lower(rr, n),
           "b_neg_decisions": dict(collections.Counter(r["b_neg"] for r in roots)), "sham_decisions": dict(collections.Counter(r["sham"] for r in roots))}
    if n and lower(viol, n) > MAX_VIOLATION: v = "FAIL_BINDING"                              # 违例率下界已超容差: 不必等满 59 条
    elif n >= N_ROOTS and upper(viol, n) <= MAX_VIOLATION and lower(sham, n) >= MIN_PRESERVE: v = "QUALIFIED_BINDING"
    elif n >= N_ROOTS and upper(viol, n) <= MAX_VIOLATION: v = "VACUOUS(假框下保不住, 拒绝不说明问题)"
    else: v = "INSUFFICIENT"
    res["verdict"] = v
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--rescore", action="store_true"); a = ap.parse_args(argv)
    if a.dry_run:
        print("screen pool", len(sample())); return
    if not a.rescore:
        import extractor_counterexample_run_r2 as KR   # noqa: E402
        KR._load_key()
        texts = sample(); td = tempfile.mkdtemp(); open_scope("citation_binding", CAP, os.path.join(td, "budget.json"))
        rows = []

        def one(t):
            try:
                r = {"sha16": hashlib.sha256(t.encode()).hexdigest()[:16]}; c = CC.shadow_certificates(t); r["orig"] = c["decision"]; r["calls"] = c["calls"]
                if c["decision"] == "CITED_UNVERIFIED":
                    for k, frame in FRAMES.items():
                        c2 = CC.shadow_certificates(frame % t); r[k] = c2["decision"]; r["calls"] += c2["calls"]
                return r
            except Exception as e:      # noqa: BLE001
                print("fail", type(e).__name__, str(e)[:100]); return "BUDGET" if "BUDGET" in str(e).upper() else None

        i, stop = 0, False
        def early_fail():       # 提前停: 根 >= 20 且违例率的单侧 99% 下界已超容差(再测只是多花钱)
            b = build(rows); return b["roots"] >= EARLY_MIN and MON.clopper_pearson(b["b_neg_still_issued"], b["roots"], 0.02)[0] > MAX_VIOLATION
        while not stop and i < len(texts) and build(rows)["roots"] < N_ROOTS and not early_fail():
            batch = texts[i:i + WORKERS * 2]; i += len(batch)
            with ThreadPoolExecutor(max_workers=WORKERS) as ex:
                for r in ex.map(one, batch):
                    if r == "BUDGET": stop = True
                    elif r: rows.append(r)
            NUM.write_text(json.dumps({"requests": scope_status(), "rows": rows}, indent=1), encoding="utf-8")
    num = json.loads(NUM.read_text(encoding="utf-8"))
    res = {"block": "CITATION_CERT_BINDING", "run_at": "2026-10-01", "prereg_sha256": hashlib.sha256(PRE.read_bytes()).hexdigest(),
           "probe_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(), "rows_sha256": hashlib.sha256(NUM.read_bytes()).hexdigest(),
           "requests": num.get("requests"), "result": build(num["rows"])}
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("requests", "result")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
