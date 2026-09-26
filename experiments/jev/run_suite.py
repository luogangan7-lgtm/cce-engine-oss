# -*- coding: utf-8 -*-
"""一进程一次加载, 固定 suite 批量执行, 产出最小报告集(§12.1)。

推理前固定预期集合(item×question) → 计划题行(只需 tokenizer) → 一次加载 → 逐行执行 → 校验输出 → 覆盖闸 → 语义断言(预设 gold, 不由模型改)。
执行成功与业务通过分开报告; 任何失败也写出报告(不合成空成功)。产物无原文, 只有 sha 与候选标签。
不写回生产: 只写 reports/<run-id>/ 下的文件。"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .budget import Ledger
from .compile_context import build_request, item_text, load_task, load_taxonomy, unknown_candidate
from .contracts import ExecutionBudget, JevError, REPORT_SCHEMA, sha256, validate_row
from .plan_work import prepare, rows_json
from .report import check_upload, coverage, dump_json, summary_md, write_manifest_sha256

HERE = Path(__file__).resolve().parent
SUITES = HERE / "suites"
SUITE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,40}$")
PRODUCTION_FORBIDDEN = ("s0_context.json", "manifest.json", "cce_population", "usable", "population")


def load_suite(suite_id: str, suites_dir=SUITES):
    if not SUITE_ID_RE.match(suite_id or ""):
        raise JevError("INPUT_INVALID", f"suite_id {suite_id!r}")
    p, mp = Path(suites_dir) / f"{suite_id}.jsonl", Path(suites_dir) / f"{suite_id}.manifest.json"
    if not p.is_file() or not mp.is_file():
        raise JevError("INPUT_INVALID", f"suite {suite_id} not registered")
    raw = p.read_bytes()
    manifest = json.loads(mp.read_text(encoding="utf-8"))
    if manifest.get("suite_sha256") != sha256(raw):
        raise JevError("INPUT_INVALID", f"suite {suite_id}: sha256 differs from manifest (suite files are reviewed, not editable at run time)")
    items = [json.loads(l) for l in raw.decode("utf-8").splitlines() if l.strip()]
    seen = set()
    for it in items:
        for k in ("item_id", "expected"):
            if k not in it:
                raise JevError("INPUT_INVALID", f"suite item missing {k}")
        if ("text" in it) == ("text_ref" in it):
            raise JevError("INPUT_INVALID", f"suite item {it['item_id']!r}: exactly one of text / text_ref")
        if it["item_id"] in seen:
            raise JevError("INPUT_INVALID", f"duplicate item_id {it['item_id']}")
        seen.add(it["item_id"])
    return items, manifest


def expected_set(compiled: list) -> list:
    """推理前固定: 每个 item 的每个面一行; 声明/不可观测已是终态, 模型题 NOT_RUN。"""
    rows = []
    for req, prov in compiled:
        for facet, pv in prov.items():
            st = {"DECLARED": "DECLARED", "UNOBSERVABLE": "UNOBSERVABLE", "STRUCTURAL_COLD_READ": "STRUCTURAL_COLD_READ"}.get(pv["provenance"], "NOT_RUN")
            rows.append({"item_id": req.item_id, "question_id": facet, "provenance": pv["provenance"], "status": st,
                         "value": pv["value"], "readable": pv["readable"]})
    return rows


def suite_task(manifest: dict, taxonomy: dict):
    """清单里的任务合同; 缺省 = v1(task=None, 行为与 v1 逐字相同)。"""
    tid = manifest.get("task", "s0_context.v1")
    return tid, (None if tid == "s0_context.v1" else load_task(tid, taxonomy))


def suite_texts(items) -> list:
    """全部条目的有效文本(内存里, 只供泄漏扫描用; 绝不写盘)。"""
    return [item_text(it)[0] for it in items]


def _check_policy(items, compiled, policy, suite_id=None, task_id=None):
    if suite_id is not None and "suite_ids" in policy and suite_id not in policy["suite_ids"]:
        raise JevError("PERMIT_NOT_APPROVED", f"policy {policy.get('policy_id')} does not cover suite {suite_id}")
    if task_id is not None and policy.get("task", "s0_context.v1") != task_id:
        raise JevError("PERMIT_NOT_APPROVED", f"policy task {policy.get('task', 's0_context.v1')} != suite task {task_id}")
    nq = sum(len(req.questions) for req, _ in compiled)
    if len(items) > int(policy["max_items"]):
        raise JevError("BUDGET_EXCEEDED", f"{len(items)} items > policy max_items {policy['max_items']}")
    if nq > int(policy["max_questions"]):
        raise JevError("BUDGET_EXCEEDED", f"{nq} model questions > policy max_questions {policy['max_questions']}")


def run(suite_id: str, out_dir, policy: dict, cfg: dict, identities: dict, backend_factory, tok_factory, upstream_factory,
        taxonomy: dict | None = None, suites_dir=SUITES, clock=time.monotonic) -> dict:
    out = Path(out_dir)
    if "reports" not in out.parts:
        raise JevError("OUTPUT_INVALID", f"out_dir {out} must live under a reports/ directory (never production paths)")
    out.mkdir(parents=True, exist_ok=True)
    report = {"schema": REPORT_SCHEMA, "mode": "shadow_eval", "backend": "decider", "model_version": identities.get("model_version", "unknown"),
              "suite_id": suite_id, "execution_status": "NOT_RUN", "coverage_status": "NOT_ESTABLISHED",
              "semantic_acceptance": "NOT_ESTABLISHED", "production_eligible": False, "results": [], "failures": [],
              "identities": identities, "timing": {}, "budget": None, "plan": None}
    ledger, rows_out, expected, semantic, texts = None, [], [], [], []
    t = report["timing"]
    T0 = clock()
    try:
        items, manifest = load_suite(suite_id, suites_dir)
        report["suite_sha256"] = manifest["suite_sha256"]
        report["suite_manifest"] = {k: manifest.get(k) for k in ("task", "policy", "prereg_sha256", "items", "model_questions")}
        tax = taxonomy or load_taxonomy()
        task_id, task = suite_task(manifest, tax)
        texts = suite_texts(items)
        compiled = [build_request(it, tax, task) for it in items]
        _check_policy(items, compiled, policy, suite_id, task_id)
        expected = expected_set(compiled)
        dump_json(out / "expected_items.json", {"suite_id": suite_id, "fixed_before_inference": True, "rows": expected})
        budget = ExecutionBudget.from_policy(policy)
        ledger = Ledger(budget, clock)
        t0 = clock(); tok = tok_factory(); t["tokenizer_load_s"] = round(clock() - t0, 3)
        up = upstream_factory()
        t0 = clock(); plans = [prepare(req, tok, up, cfg, budget) for req, _ in compiled]; t["render_tokenize_s"] = round(clock() - t0, 3)
        report["plan"] = [p.summary() | {"rows_detail": rows_json(p)} for p in plans]
        total_rows = sum(len(p.rows) for p in plans)
        if total_rows > budget.max_rows or sum(r.padded_len for p in plans for r in p.rows) > budget.max_padded_tokens:
            raise JevError("BUDGET_EXCEEDED", f"planned {total_rows} rows / padded tokens exceed policy before model load")
        t0 = clock(); backend = backend_factory(ledger); t["model_load_s"] = round(clock() - t0, 3)
        report["identities"] = identities | {"backend_effective": backend.identities()}
        first = None
        t0 = clock()
        for req, prov in compiled:
            plan = next(p for p in plans if p.item_id == req.item_id)
            rows = backend.evaluate(plan, up)
            if first is None and rows:
                first = rows[0].timing.get("forward_s"); t["first_forward_s"] = first
            qmap = {q.question_id: q for q in req.questions}
            for r in rows:
                validate_row(r, qmap[r.question_id])
                unk = unknown_candidate(qmap[r.question_id])
                r.semantic_status = "SEMANTIC_UNKNOWN" if r.selected_candidate == unk else "OK"
                rows_out.append(r.to_json() | {"status": r.semantic_status, "input_sha256": plan.input_sha256, "questions_sha256": plan.questions_sha256})
        t["all_forwards_s"] = round(clock() - t0, 3)
        t["remaining_forwards_s"] = round(t["all_forwards_s"] - (first or 0.0), 3)
        # 终态表: 模型行 + 声明/不可观测
        final = [{"item_id": e["item_id"], "question_id": e["question_id"], "status": e["status"]} for e in expected if e["status"] != "NOT_RUN"]
        final += [{"item_id": r["item_id"], "question_id": r["question_id"], "status": r["status"]} for r in rows_out]
        report["coverage"] = coverage(expected, final)
        report["coverage_status"] = report["coverage"]["coverage_status"]
        if backend.forwards_observed != ledger.forwards:
            raise JevError("RESOURCE_EXCEEDED", f"observed forwards {backend.forwards_observed} != reserved {ledger.forwards}")
        # 语义断言: gold 来自 suite(预先人工审定), 不由模型改; 未知不重试
        by_item = {it["item_id"]: it for it in items}
        for r in rows_out:
            acc = by_item[r["item_id"]]["expected"].get(r["question_id"])
            if acc is None:
                semantic.append({"item_id": r["item_id"], "question_id": r["question_id"], "asserted": False, "status": "REVIEW_REQUIRED"})
            else:
                ok = r["selected_candidate"] in acc
                semantic.append({"item_id": r["item_id"], "question_id": r["question_id"], "asserted": True, "accepted": acc,
                                 "selected": r["selected_candidate"], "pass": ok})
        asserted = [s for s in semantic if s["asserted"]]
        report["semantic_acceptance"] = ("NOT_ESTABLISHED" if not asserted else "PASSED" if all(s["pass"] for s in asserted) else "FAILED")
        report["execution_status"] = "SUCCEEDED"
        if report["semantic_acceptance"] == "FAILED":
            report["failures"].append({"code": "SEMANTIC_CHECK_FAILED", "detail": f"{sum(not s['pass'] for s in asserted)}/{len(asserted)} asserted questions outside accepted set"})
    except JevError as e:
        report["execution_status"] = "FAILED"
        report["failures"].append({"code": e.code, "detail": e.detail})
    except Exception as e:                      # 不合成成功; 只记类型名 —— str(e) 可能带输入原文, 公仓报告/日志不许出现
        report["execution_status"] = "FAILED"
        report["failures"].append({"code": "UNHANDLED_EXCEPTION", "type": type(e).__name__, "detail": "message withheld (may contain input text)"})
    finally:
        t["wall_s"] = round(clock() - T0, 3)
        try:
            import resource
            t["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss   # Linux: KiB
        except (ImportError, OSError):
            t["peak_rss_kib"] = "unavailable"
        done = {(r["item_id"], r["question_id"]) for r in rows_out}
        report["results"] = ([{"item_id": e["item_id"], "question_id": e["question_id"], "status": e["status"], "provenance": e["provenance"], "value": e["value"]}
                              for e in expected if e["status"] != "NOT_RUN"]
                             + rows_out
                             + [{"item_id": e["item_id"], "question_id": e["question_id"], "status": "NOT_RUN", "provenance": e["provenance"]}
                                for e in expected if e["status"] == "NOT_RUN" and (e["item_id"], e["question_id"]) not in done])
        report["semantic"] = semantic
        report["budget"] = ledger.snapshot() if ledger else None
        with open(out / "predictions.jsonl", "w", encoding="utf-8") as fh:
            for r in rows_out:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        (out / "s0_candidates.jsonl").write_bytes((out / "predictions.jsonl").read_bytes())
        if ledger:
            ledger.write_jsonl(out / "resource_ledger.jsonl")
        else:
            (out / "resource_ledger.jsonl").write_text("", encoding="utf-8")
        dump_json(out / "execution_receipt.json", {"suite_id": suite_id, "execution_status": report["execution_status"],
                                                   "identities": report["identities"], "budget": report["budget"], "timing": t,
                                                   "forwards_observed": getattr(locals().get("backend"), "forwards_observed", 0)})
        dump_json(out / "report.json", report)
        (out / "summary.md").write_text(summary_md(report), encoding="utf-8")
        write_manifest_sha256(out)
        check_upload(out, [p for p in out.iterdir() if p.is_file()], int(policy.get("report_max_bytes", 20 * 1024 * 1024)), forbidden_texts=texts)
    return report
