# -*- coding: utf-8 -*-
"""蒸馏的「老师」读数: TypeSafe Jev 在验收 42 条之外的语料行上的逐面选择 + 完整分布(预注册 tests/data/jev_distill_prereg.json)。

★ 会发起计量调用(Jev, 2026-09-23 实测 42 次 ≈ $0.002)。硬上限 CAP_ATTEMPTS = 80 次请求尝试(含重试), **跨进程累计**:
  每次尝试在发请求之前先追加一行到 LEDGER 并 fsync, 上限对 LEDGER 行数判; LEDGER 用 flock 独占, 两个进程不能同时花。
  已有 LEDGER / PARTIAL / OUT 时拒绝开跑; 只有 --resume 能续(沿用累计计数, 跳过已读到的指针), OUT 已是 complete 时 --resume 也拒绝。
  撞上限或中途出错也写 OUT(status = capped / aborted), 账本与已读行不丢。PARTIAL 与 LEDGER 不删, 与 OUT 一起提交当审计线。
★ 开跑前核: 本脚本 sha、probes/s0_jev_shadow.py sha、题目 sha、训练指针集 sha 全部 == 预注册; 76 个指针全部能按 sha 取到;
  预注册与两个脚本在 HEAD 里未改动且 HEAD 已在 oss/master(公开时间戳先于第一次调用)。任一不成立 = 不读密钥、不发请求。
★ 请求形状与 J1/J2(probes/s0_jev_shadow.py)逐字相同: 同一 jev_questions()(6 题, 含 情绪余温)、同 body = line[:2000]、同模型 jev-latest。
★ 两组文本(先 train 后 drift): train = 两份语料里不在验收集(指针与整行 sha 双重排除)的全部非空行(66 条, 按文件内顺序;
  验收集按「提到品牌/型号」选出, 这 66 条恰是其无品牌、约短 3 倍的补集 —— 见预注册 ★混杂);
  drift = 验收集输入序下标 i%4==0 且 i<40 的 10 条(= 复跑条目), 只量 Jev 自 09-23 以来有没有漂, 不进训练。
★ 不跟随重定向(密钥不会被转发); 响应逐面校验(选中值 ∈ 候选, 分布键 ⊆ 候选, 值有限且 ∈[0,1], 和 ≈ 1), 不合格只记错误类型, 不存 API 的任何字符串。
★ 产物只有指针、sha、选中值与分布; 不写原文; 密钥只从 viral-skill-eval/.env 读进局部变量, 不打印、不落盘; 异常只记类型名。
用法: python3 probes/jev_distill_teacher.py [--dry-run | --resume]
"""
import argparse, datetime, fcntl, hashlib, importlib.util, json, math, os, pathlib, subprocess, time, urllib.error, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
PRE = ROOT / "tests/data/jev_distill_prereg.json"
OUT = ROOT / "results/jev_distill_teacher.json"
PARTIAL = ROOT / "results/jev_distill_teacher_partial.jsonl"
LEDGER = ROOT / "results/jev_distill_teacher_ledger.jsonl"
SUITE = ROOT / "experiments/jev/suites/s0-compare-llm-v1.jsonl"
SHADOW = ROOT / "probes/s0_jev_shadow.py"
FILES = ("corpus/reddit_hearingaids_audience_v2.txt", "corpus/reddit_hearingaids_utterances.txt")
CAP_ATTEMPTS = 80
N_TRAIN, N_DRIFT = 66, 10
SUM_TOL = 0.02


def _load(path, name):
    s = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


SH = _load(SHADOW, "_shadow_for_distill")        # jev_questions / question_sha / _key / API / MODEL / BODY_CHARS


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)


_OPENER = urllib.request.build_opener(_NoRedirect)


def sha(s):
    return hashlib.sha256(s if isinstance(s, bytes) else s.encode("utf-8")).hexdigest()


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def acceptance():
    items = [json.loads(l) for l in SUITE.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [it for it in items if "text_ref" in it and not it["item_id"].startswith("rep-")]


def training_pointers():
    """验收集之外的全部非空行: (file, line_index, line_sha256, body_sha256), 文件内顺序。指针与整行 sha 都不得与验收集重合。"""
    acc = acceptance()
    acc_ptr = {(it["text_ref"]["file"], it["text_ref"]["line_index"]) for it in acc}
    acc_sha = {it["text_ref"]["line_sha256"] for it in acc}
    out = []
    for f in FILES:
        for i, line in enumerate((ROOT / f).read_text(encoding="utf-8").split("\n")):
            if line.strip() and (f, i) not in acc_ptr and sha(line) not in acc_sha:
                out.append({"file": f, "line_index": i, "line_sha256": sha(line), "body_sha256": sha(line[:SH.BODY_CHARS])})
    return out


def pointer_set_sha(ptrs):
    return sha(json.dumps([[p["file"], p["line_index"], p["line_sha256"]] for p in ptrs]))


def drift_pointers():
    acc = acceptance()
    return [{"file": it["text_ref"]["file"], "line_index": it["text_ref"]["line_index"], "line_sha256": it["text_ref"]["line_sha256"],
             "body_sha256": it["text_ref"]["body_sha256"]} for i, it in enumerate(acc) if i % 4 == 0 and i < 40]


def body_of(p):
    line = (ROOT / p["file"]).read_text(encoding="utf-8").split("\n")[p["line_index"]]
    if sha(line) != p["line_sha256"] or sha(line[:SH.BODY_CHARS]) != p["body_sha256"]:
        raise SystemExit(f"pointer sha mismatch at {p['file']}:{p['line_index']}")
    return line[:SH.BODY_CHARS]


def ptr(p):
    return "%s:%d" % (p["file"], p["line_index"])


def preflight():
    """不读密钥、不发请求的全部前置。返回 (work, 身份记录)。"""
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    a, t = pre["★分析脚本(冻结)"], pre["★老师(冻结)"]
    errs = []
    if sha(pathlib.Path(__file__).read_bytes()) != a["teacher_sha256"]:
        errs.append("teacher script sha != prereg")
    if sha(SHADOW.read_bytes()) != a["shadow_sha256"]:
        errs.append("shadow module sha != prereg")
    if SH.question_sha() != t["question_sha"] or SH.MODEL != t["model"] or SH.API != t["endpoint"]:
        errs.append("question sha / model / endpoint != prereg")
    tr, dr = training_pointers(), drift_pointers()
    if len(tr) != N_TRAIN or len(dr) != N_DRIFT or pointer_set_sha(tr) != pre["★训练集(冻结)"]["pointer_set_sha256"]:
        errs.append("training/drift pointer set != prereg")
    if errs:
        raise SystemExit("preflight refused: " + "; ".join(errs))
    work = [("train", p) for p in tr] + [("drift", p) for p in dr]
    for _, p in work:
        body_of(p)
    return work, {"prereg_sha256": sha(PRE.read_bytes()), "teacher_script_sha256": a["teacher_sha256"], "shadow_sha256": a["shadow_sha256"]}


def provenance():
    """预注册与两个脚本在 HEAD 里未改动, 且 HEAD 已在公开仓 oss/master 上。"""
    rel = [str(p.relative_to(ROOT)) for p in (PRE, pathlib.Path(__file__), SHADOW)]
    g = lambda *a: subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True)
    head = g("rev-parse", "HEAD").stdout.strip()
    if g("diff", "--quiet", "HEAD", "--", *rel).returncode != 0 or g("ls-files", "--error-unmatch", *rel).returncode != 0:
        raise SystemExit("preflight refused: prereg/scripts not committed as-is at HEAD")
    if g("merge-base", "--is-ancestor", head, "oss/master").returncode != 0:
        raise SystemExit("preflight refused: HEAD is not on oss/master (push the frozen prereg first)")
    return head


def validate(ans):
    """Jev answers → (choice, probs) 或抛 ValueError(只带类型化原因, 不带 API 字符串)。"""
    qs = SH.jev_questions()
    if not isinstance(ans, dict):
        raise ValueError("answers not a dict")
    choice, probs = {}, {}
    for k, q in qs.items():
        a, crit = ans.get(k), set(q["criteria"])
        if not isinstance(a, dict) or a.get("choice") not in crit:
            raise ValueError("choice missing or outside candidates")
        pr = a.get("probabilities")
        if not isinstance(pr, dict) or not pr or not set(pr) <= crit:
            raise ValueError("distribution missing or keys outside candidates")
        vals = [float(v) for v in pr.values() if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if len(vals) != len(pr) or not all(math.isfinite(v) and 0 <= v <= 1 for v in vals) or abs(sum(vals) - 1) > SUM_TOL:
            raise ValueError("distribution values invalid")
        choice[k] = a["choice"]; probs[k] = {c: round(float(v), 6) for c, v in pr.items()}
    return choice, probs


def call(body, key, ledger, where=""):
    """一次 Jev 请求(≤3 次尝试)。每次尝试先把一行追加进 LEDGER(fsync)再发; 累计达 CAP_ATTEMPTS 即抛 BUDGET_EXCEEDED。"""
    payload = json.dumps({"model": SH.MODEL, "state": body, "questions": SH.jev_questions()}, ensure_ascii=False).encode()
    for att in range(3):
        if ledger["attempts"] >= CAP_ATTEMPTS:
            raise RuntimeError("BUDGET_EXCEEDED")
        ledger["attempts"] += 1; ledger["this_run"] += 1
        fh = ledger.get("fh")
        if fh is not None:
            fh.write(json.dumps({"n": ledger["attempts"], "t": now(), "ptr": where, "try": att + 1}) + "\n"); fh.flush(); os.fsync(fh.fileno())
        req = urllib.request.Request(SH.API, data=payload, headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"}, method="POST")
        try:
            with _OPENER.open(req, timeout=60) as r:
                if r.geturl() != SH.API:
                    return None, "URL_CHANGED"
                d = json.load(r)
            u = d.get("usage") if isinstance(d, dict) else None
            t = u.get("input_tokens") if isinstance(u, dict) else None
            ledger["tok_in"] += t if isinstance(t, int) and t >= 0 else 0
            return d, None
        except urllib.error.HTTPError as e:
            if e.code in (429, 529) and att < 2:
                time.sleep(3 * (att + 1)); continue
            return None, "HTTP %d" % e.code
        except Exception as e:  # noqa: BLE001 —— 只记类型名, 不打消息(可能含请求体)
            return None, type(e).__name__
    return None, "RETRY_EXHAUSTED"


def _rows(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.exists() else []


def main(argv=None):
    ap = argparse.ArgumentParser(); g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true"); g.add_argument("--resume", action="store_true"); a = ap.parse_args(argv)
    work, ident = preflight()
    if a.dry_run:
        print(json.dumps({"train": sum(1 for s, _ in work if s == "train"), "drift": sum(1 for s, _ in work if s == "drift"),
                          "question_sha": SH.question_sha(), "cap": CAP_ATTEMPTS, "ledger_so_far": len(_rows(LEDGER)), **ident}, ensure_ascii=False))
        return 0
    prior_out = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else None
    if not a.resume and (LEDGER.exists() or PARTIAL.exists() or OUT.exists()):
        raise SystemExit("refused: an earlier teacher run left a ledger/partial/output; use --resume (never start over)")
    if a.resume and (not LEDGER.exists() or (prior_out or {}).get("status") == "complete"):
        raise SystemExit("refused: nothing to resume (no ledger) or the teacher reading is already complete")
    head = provenance()
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    fh = LEDGER.open("a", encoding="utf-8")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise SystemExit("refused: another teacher run holds the ledger lock")
    ledger = {"attempts": len(_rows(LEDGER)), "this_run": 0, "tok_in": 0, "cap_attempts": CAP_ATTEMPTS, "fh": fh}
    started, status = now(), "aborted"
    done = {(r["split"], ptr(r)) for r in _rows(PARTIAL) if r.get("ok")}
    try:
        key = SH._key()
        for split, p in work:
            if (split, ptr(p)) in done:
                continue
            row = dict(p, split=split, ok=False, err=None, choice=None, probs=None, at=now())
            resp, err = call(body_of(p), key, ledger, ptr(p))
            if err or not isinstance(resp, dict):
                row["err"] = err or "BAD_SHAPE:not a dict"
            else:
                try:
                    ch, pr = validate(resp.get("answers"))
                    row.update(ok=True, choice=ch, probs=pr)
                except (ValueError, TypeError, AttributeError) as e:
                    row["err"] = "BAD_SHAPE:%s" % type(e).__name__
            with PARTIAL.open("a", encoding="utf-8") as pf:
                pf.write(json.dumps(row, ensure_ascii=False) + "\n")
            print("  %-5s %s:%d %s  (attempts %d/%d)" % (split, p["file"].split("/")[-1], p["line_index"], "ok" if row["ok"] else row["err"],
                                                        ledger["attempts"], CAP_ATTEMPTS))
        status = "complete"
    except RuntimeError as e:
        if str(e) != "BUDGET_EXCEEDED":
            raise
        status = "capped"
    finally:
        last = {}
        for r in _rows(PARTIAL):                          # 每个指针取最后一次(续跑只会重读此前没读到的指针)
            last[(r["split"], ptr(r))] = r
        rows = [last.get((s, ptr(p))) or dict(p, split=s, ok=False, err="NOT_ATTEMPTED", choice=None, probs=None) for s, p in work]
        led = {k: v for k, v in ledger.items() if k != "fh"}
        led["attempts_cumulative"] = led.pop("attempts")
        doc = {"block": "JEV_DISTILL_TEACHER", "status": status, "started": started, "finished": now(), "git_head": head, **ident,
               "model": SH.MODEL, "endpoint": SH.API, "question_sha": SH.question_sha(),
               "★请求形状": "与 probes/s0_jev_shadow.py(J1)/s0_retest(J2) 相同: 6 题(含 情绪余温), body = line[:2000]",
               "training_pointer_set_sha256": pointer_set_sha([p for s, p in work if s == "train"]),
               "counts": {s: {"n": sum(1 for r in rows if r["split"] == s), "ok": sum(1 for r in rows if r["split"] == s and r["ok"])} for s in ("train", "drift")},
               "★账本": led, "★审计线": ["results/" + PARTIAL.name, "results/" + LEDGER.name],
               "★无原文": "只存指针、sha、选中值与分布", "rows": rows}
        OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        fh.close()
        print("status", status, "账本", led, "→", OUT)
    return 0 if status == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
