# -*- coding: utf-8 -*-
"""蒸馏第二轮的「老师」读数(预注册 tests/data/jev_distill2_prereg.json): 今日 TypeSafe Jev 在
  J3 = 验收 42 条(输入序)第一遍 · R2 = 训练 66 条第二遍 · J4 = 验收 42 条第二遍  —— 按这个顺序读, 每条都存完整分布。
用途: J3/J4 的平均 = 验收条目的软目标(只进交叉拟合, 预测某条时绝不用它自己的读数); R1(第一轮 results/jev_distill_teacher.json)与 R2 的平均 = 训练条目的软目标;
      J3 vs J4、R1 vs R2 = 老师同日复测(描述); J3/J4 vs J1/J2 = 漂移(描述)。判决仍只对 09-23 的 J1/J2(冻结规则)。

★ 计量调用: 硬上限 CAP_ATTEMPTS = 170 次请求尝试(含重试), 跨进程累计(自己的 fsync 账本 + flock), 撞上即停; 计划 150 次 ≈ $0.0075(上限 ≈ $0.0085)。
★ 请求形状、响应校验、不跟随重定向、只记错误类型名 —— 逐字复用第一轮老师 probes/jev_distill_teacher.py(导入, 不改; 其 sha 与 shadow sha 由本轮预注册钉住)。
★ 开跑前核: 本脚本 sha、第一轮老师 sha、shadow sha、题目 sha/端点/模型、验收与训练指针集 sha 与条数 == 预注册; 150 个指针全部按 sha 取到;
  预注册与三个脚本在 HEAD 未改动且 HEAD 已在 oss/master。任一不成立 = 不读密钥、不发请求。已有账本/部分结果/产物时拒绝重开, 只能 --resume。
★ 状态: 每条都读到 = complete; 撞上限 = capped; 熔断(HTTP 401/403, 或连续 3 条没读到 —— 断网/密钥失效时不白烧预算)= aborted;
  其余没读全 = incomplete。只有 complete 不许续跑; 其它状态 --resume 只补没读到的指针, 仍受同一累计上限约束。
★ 产物只有指针、sha、选中值与分布; 不写原文; 密钥只进局部变量。
用法: python3 probes/jev_distill2_teacher.py [--dry-run | --resume]
"""
import argparse, fcntl, hashlib, importlib.util, json, pathlib, subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
PRE = ROOT / "tests/data/jev_distill2_prereg.json"
OUT = ROOT / "results/jev_distill2_teacher.json"
PARTIAL = ROOT / "results/jev_distill2_teacher_partial.jsonl"
LEDGER = ROOT / "results/jev_distill2_teacher_ledger.jsonl"
R1_TEACHER = ROOT / "probes/jev_distill_teacher.py"
CAP_ATTEMPTS = 170
PASSES = ("J3", "R2", "J4")
BREAK_AFTER = 3                                          # 连续这么多条没读到 ⇒ 熔断


class Breaker(Exception):
    pass


def _load(path, name):
    s = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


T1 = _load(R1_TEACHER, "_r1_teacher_for_r2")
T1.CAP_ATTEMPTS = CAP_ATTEMPTS            # 第一轮 call() 在调用时读模块全局的上限; 本轮上限在这里, 账本仍是本轮自己的
SH = T1.SH
sha, now, ptr, body_of, validate, call = T1.sha, T1.now, T1.ptr, T1.body_of, T1.validate, T1.call


def exam_pointers():
    return [{"file": it["text_ref"]["file"], "line_index": it["text_ref"]["line_index"], "line_sha256": it["text_ref"]["line_sha256"],
             "body_sha256": it["text_ref"]["body_sha256"]} for it in T1.acceptance()]


def work_list():
    ex, tr = exam_pointers(), T1.training_pointers()
    return [(p_, p) for p_ in PASSES for p in (tr if p_ == "R2" else ex)], ex, tr


def preflight():
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    a, t = pre["★脚本(冻结)"], pre["★老师(冻结)"]
    errs = []
    for name, path in (("teacher2_sha256", pathlib.Path(__file__)), ("teacher1_sha256", R1_TEACHER), ("shadow_sha256", T1.SHADOW)):
        if sha(path.read_bytes()) != a[name]:
            errs.append(f"{name} != prereg")
    if SH.question_sha() != t["question_sha"] or SH.MODEL != t["model"] or SH.API != t["endpoint"]:
        errs.append("question sha / model / endpoint != prereg")
    work, ex, tr = work_list()
    if len(ex) != 42 or len(tr) != 66 or T1.pointer_set_sha(ex) != t["exam_pointer_set_sha256"] or T1.pointer_set_sha(tr) != t["train_pointer_set_sha256"]:
        errs.append("exam/train pointer sets != prereg")
    if len(work) != t["planned_calls"]:
        errs.append("planned call count != prereg")
    if errs:
        raise SystemExit("preflight refused: " + "; ".join(errs))
    for _, p in work:
        body_of(p)
    return work, {"prereg_sha256": sha(PRE.read_bytes()), "teacher2_sha256": a["teacher2_sha256"], "teacher1_sha256": a["teacher1_sha256"],
                  "shadow_sha256": a["shadow_sha256"]}


def provenance():
    rel = [str(p.relative_to(ROOT)) for p in (PRE, pathlib.Path(__file__), R1_TEACHER, T1.SHADOW)]
    g = lambda *a: subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True)
    head = g("rev-parse", "HEAD").stdout.strip()
    if g("diff", "--quiet", "HEAD", "--", *rel).returncode != 0 or g("ls-files", "--error-unmatch", *rel).returncode != 0:
        raise SystemExit("preflight refused: prereg/scripts not committed as-is at HEAD")
    if g("merge-base", "--is-ancestor", head, "oss/master").returncode != 0:
        raise SystemExit("preflight refused: HEAD is not on oss/master (push the frozen prereg first)")
    return head


def _rows(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.exists() else []


def main(argv=None):
    ap = argparse.ArgumentParser(); g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true"); g.add_argument("--resume", action="store_true"); a = ap.parse_args(argv)
    work, ident = preflight()
    if a.dry_run:
        print(json.dumps({p_: sum(1 for x, _ in work if x == p_) for p_ in PASSES} | {"cap": CAP_ATTEMPTS, "ledger_so_far": len(_rows(LEDGER)),
                                                                                   "question_sha": SH.question_sha(), **ident}, ensure_ascii=False))
        return 0
    prior = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else None
    if not a.resume and (LEDGER.exists() or PARTIAL.exists() or OUT.exists()):
        raise SystemExit("refused: an earlier teacher run left a ledger/partial/output; use --resume (never start over)")
    if a.resume and (not LEDGER.exists() or (prior or {}).get("status") == "complete"):
        raise SystemExit("refused: nothing to resume (no ledger) or the teacher reading is already complete")
    head = provenance()
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    fh = LEDGER.open("a", encoding="utf-8")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise SystemExit("refused: another teacher run holds the ledger lock")
    ledger = {"attempts": len(_rows(LEDGER)), "this_run": 0, "tok_in": 0, "cap_attempts": CAP_ATTEMPTS, "fh": fh}
    started, status, streak = now(), "aborted", 0
    done = {(r["pass"], ptr(r)) for r in _rows(PARTIAL) if r.get("ok")}
    try:
        key = SH._key()
        for pass_, p in work:
            if (pass_, ptr(p)) in done:
                continue
            row = dict(p, **{"pass": pass_}, ok=False, err=None, choice=None, probs=None, at=now())
            resp, err = call(body_of(p), key, ledger, f"{pass_}:{ptr(p)}")
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
            print("  %-2s %s:%d %s  (attempts %d/%d)" % (pass_, p["file"].split("/")[-1], p["line_index"], "ok" if row["ok"] else row["err"],
                                                       ledger["attempts"], CAP_ATTEMPTS))
            streak = 0 if row["ok"] else streak + 1
            if row["err"] in ("HTTP 401", "HTTP 403") or streak >= BREAK_AFTER:
                raise Breaker(row["err"])
        status = "pending"                              # 由 finally 按实读结果定 complete / incomplete
    except RuntimeError as e:
        if str(e) != "BUDGET_EXCEEDED":
            raise
        status = "capped"
    except Breaker:
        status = "aborted"
    finally:
        last = {}
        for r in _rows(PARTIAL):
            last[(r["pass"], ptr(r))] = r
        rows = [last.get((s, ptr(p))) or dict(p, **{"pass": s}, ok=False, err="NOT_ATTEMPTED", choice=None, probs=None) for s, p in work]
        if status == "pending":
            status = "complete" if all(r["ok"] for r in rows) else "incomplete"
        led = {k: v for k, v in ledger.items() if k != "fh"}
        led["attempts_cumulative"] = led.pop("attempts")
        doc = {"block": "JEV_DISTILL2_TEACHER", "status": status, "started": started, "finished": now(), "git_head": head, **ident,
               "model": SH.MODEL, "endpoint": SH.API, "question_sha": SH.question_sha(),
               "★请求形状": "与 J1/J2 及第一轮老师相同: 6 题(含 情绪余温), body = line[:2000]",
               "counts": {s: {"n": sum(1 for r in rows if r["pass"] == s), "ok": sum(1 for r in rows if r["pass"] == s and r["ok"])} for s in PASSES},
               "★账本": led, "★审计线": ["results/" + PARTIAL.name, "results/" + LEDGER.name],
               "★无原文": "只存指针、sha、选中值与分布", "rows": rows}
        OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        fh.close()
        print("status", status, "账本", led, "→", OUT)
    return 0 if status == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
