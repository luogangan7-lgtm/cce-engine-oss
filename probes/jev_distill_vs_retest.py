# -*- coding: utf-8 -*-
"""s0 读者蒸馏测试(预注册 tests/data/jev_distill_prereg.json, 冻结于任何老师读数与训练特征之前)。零 API(只读已存读数)。

两族学生, 各三个变体(A = Qwen3-4B-2507, B = Qwen3.5-4B, C = 两者拼接), 六个读者全部报告, 不挑:
  T(迁移): 老师 = 今日 TypeSafe Jev 在验收集之外 66 条文本上的完整分布(软目标); 头在这 66 条上训, 在验收 42 条上判。
  X(交叉拟合): 验收 42 条按输入序 i % 7 分 7 折; 每折的头只用另外 6 折的 J1 标签(独热)训, 只预测本折 —— 每条的预测都不来自见过它标签的头。
特征: 每个模型在该 (文本, 面) 上的选项字母 logits 做候选内 log-softmax(行内去偏移, 消掉长度带来的整行平移), 多模型拼接;
      每次拟合只用该次训练行的均值/标准差标准化。
头: 逐面多项逻辑回归, L2 只罚 W; λ ∈ LAMBDAS, 在该次训练行上留一交叉熵选(并列取更大); L-BFGS-B 求解(零初始化, 确定性); 读出 = 头概率的首个最大。
功效前置(逐族 × 变体 × 面): 把目标换成「自老师」(该变体模型自己的候选分布, C 取两模型平均), 走完全相同的训练协议再预测考场;
      若头的读出与自老师首选在 42 条上改判 > replaceable_max_d ⇒ 这套头连能表示的老师都学不回来 ⇒ 该面打「头无分辨力」标记:
      判决仍按冻结规则一字不改, 但不许把该面结果解释成「Jev 的读法从这些特征学不到」。
判据: 冻结的 probes/jev_decider_vs_retest.py 的 load_arms()/determinism()/analyse() 原样调用(sha 核), 数值规则逐字相同。
产物只有指针、标签计数、统计量、系数; 无原文。
用法: python3 probes/jev_distill_vs_retest.py <train_run_dir> <eval_run_dir>   (两者各含 <model_key>/{report.json,predictions.jsonl})
"""
import collections, hashlib, importlib.util, json, math, pathlib, sys

import numpy as np
from scipy.optimize import minimize

ROOT = pathlib.Path(__file__).resolve().parents[1]
PRE = ROOT / "tests/data/jev_distill_prereg.json"
TEACHER = ROOT / "results/jev_distill_teacher.json"
TRAIN_SUITE = ROOT / "experiments/jev/suites/s0-distill-train-v1.jsonl"
EVAL_SUITE = ROOT / "experiments/jev/suites/s0-compare-llm-v1.jsonl"
FROZEN = ROOT / "probes/jev_decider_vs_retest.py"
SUMMARY = ROOT / "results/jev_distill_summary.json"
VARIANTS = {"A": ("qwen3-4b-2507",), "B": ("qwen3.5-4b",), "C": ("qwen3-4b-2507", "qwen3.5-4b")}
FAMILIES = ("T", "X")
LAMBDAS = (1e-4, 1e-3, 1e-2, 1e-1, 1.0, 10.0)
N_FOLDS = 7
IDENTITY_KEYS = ("adapter_sha256", "runtime_lock_sha256", "tokenizer_sha256", "task_contract", "source_lock_sha256", "assets_lock_sha256", "model_key")
VOLATILE_EFFECTIVE = ("load_s",)                                  # backend_effective 里唯一随次数变的字段(加载耗时)
TEACHER_STATUS_OK = ("complete", "capped")


def sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode("utf-8")).hexdigest()


def out_path(tag):
    return ROOT / f"results/jev_distill_{tag}_vs_retest.json"


def load_frozen(pre):
    if sha(FROZEN.read_bytes()) != pre["★分析脚本(冻结)"]["sha256"]:
        raise SystemExit("冻结的对比脚本被改过: sha 与预注册不符, 拒绝出任何判决")
    s = importlib.util.spec_from_file_location("_frozen_cmp_d", FROZEN); m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m


def _jsonl(p):
    return [json.loads(l) for l in pathlib.Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def _ptr(ref):
    return "%s:%d" % (ref["file"], ref["line_index"])


# ───────────────────────── 头(numpy + L-BFGS-B, 确定性) ─────────────────────────
def softmax(Z):
    Z = Z - Z.max(axis=1, keepdims=True)
    E = np.exp(Z)
    return E / E.sum(axis=1, keepdims=True)


def fit(X, Y, lam):
    """X 已标准化; Y 软目标(行和 1)。返回 (W, b)。目标 = 平均交叉熵 + λ/2·‖W‖²。"""
    n, d = X.shape; K = Y.shape[1]

    def f(theta):
        W = theta[:K * d].reshape(K, d); b = theta[K * d:]
        P = softmax(X @ W.T + b)
        loss = -(Y * np.log(P + 1e-300)).sum() / n + 0.5 * lam * (W * W).sum()
        G = (P - Y) / n
        return loss, np.concatenate([(G.T @ X + lam * W).ravel(), G.sum(axis=0)])
    r = minimize(f, np.zeros(K * d + K), jac=True, method="L-BFGS-B", options={"maxiter": 5000, "gtol": 1e-10, "ftol": 1e-15})
    return r.x[:K * d].reshape(K, d), r.x[K * d:]


def ce(P, Y):
    return float(-(Y * np.log(P + 1e-12)).sum(axis=1).mean())


def train_head(X, Y, groups=None):
    """标准化(只用这些训练行) → 留一(组)选 λ → 全量拟合。groups: 预注册的近重复行同组留出。返回可预测的头与选择记录。"""
    def std(Xa):
        mu, sd = Xa.mean(axis=0), Xa.std(axis=0)
        sd[sd == 0] = 1.0
        return mu, sd
    g = np.arange(len(X)) if groups is None else np.asarray(groups)
    scores = {}
    for lam in LAMBDAS:
        losses = []
        for gi in dict.fromkeys(g.tolist()):
            m = g != gi
            mu, sd = std(X[m])
            W, b = fit((X[m] - mu) / sd, Y[m], lam)
            P = softmax(((X[~m] - mu) / sd) @ W.T + b)
            losses += [ce(P[j:j + 1], Y[~m][j:j + 1]) for j in range(len(P))]
        scores[lam] = float(np.mean(losses))
    best = min(scores.values())
    lam = max(l for l, s in scores.items() if s - best < 1e-12)
    mu, sd = std(X)
    W, b = fit((X - mu) / sd, Y, lam)
    return {"lambda": lam, "loo_ce": {repr(k): round(v, 8) for k, v in scores.items()}, "mu": mu, "sd": sd, "W": W, "b": b}


def predict(head, X):
    return softmax(((X - head["mu"]) / head["sd"]) @ head["W"].T + head["b"])


def logsoftmax(v):
    v = np.asarray(v, dtype=float)
    return v - (v.max() + np.log(np.exp(v - v.max()).sum()))


# ───────────────────────── 数据 ─────────────────────────
def load_run(run_dir, key):
    d = pathlib.Path(run_dir) / key
    rep = json.loads((d / "report.json").read_text(encoding="utf-8"))
    pf = next(p for p in d.iterdir() if p.name.endswith("predictions.jsonl"))
    rows = {(r["item_id"], r["question_id"]): r for r in _jsonl(pf)}
    return rep, rows, {"report_sha256": sha((d / "report.json").read_bytes()), "predictions_sha256": sha(pf.read_bytes()),
                       "run_id": ((rep.get("identities") or {}).get("run") or {}).get("GITHUB_RUN_ID"),
                       "execution_commit": (rep.get("identities") or {}).get("cce_execution_commit")}


def run_errors(rep, rows, key, suite_path, n_rows, prereg_sha=None):
    src_p = ROOT / f"experiments/jev/models/{key}/model.source.lock.json"; ast_p = ROOT / f"experiments/jev/models/{key}/model.assets.lock.json"
    ids = rep.get("identities") or {}
    e = []
    if rep.get("execution_status") != "SUCCEEDED" or rep.get("coverage_status") != "COMPLETE":
        e.append(f"{key}: run not SUCCEEDED/COMPLETE")
    if rep.get("suite_sha256") != sha(suite_path.read_bytes()):
        e.append(f"{key}: report suite sha != {suite_path.name}")
    if ids.get("model_key") != key or ids.get("source_lock_sha256") != sha(src_p.read_bytes()) or ids.get("assets_lock_sha256") != (sha(ast_p.read_bytes()) if ast_p.is_file() else None):
        e.append(f"{key}: report identity != current locks")
    if prereg_sha is not None and (rep.get("suite_manifest") or {}).get("prereg_sha256") != prereg_sha:
        e.append(f"{key}: training run's executed manifest does not carry the current prereg sha")
    if len(rows) != n_rows:
        e.append(f"{key}: {len(rows)} prediction rows != {n_rows}")
    return e


def comparability_errors(rep_t, rep_e, rows_t, rows_e, key):
    """训练特征与考场特征必须出自同一构建: 适配器/运行时/tokenizer/任务/锁/有效配置逐项相等, 候选顺序与题目集 sha 逐面相等。"""
    it, ie = rep_t.get("identities") or {}, rep_e.get("identities") or {}
    e = [f"{key}: identities.{k} train {it.get(k)!r} != eval {ie.get(k)!r}" for k in IDENTITY_KEYS if it.get(k) != ie.get(k)]
    bt, be = it.get("backend_effective") or {}, ie.get("backend_effective") or {}
    e += [f"{key}: backend_effective.{k} differs between train and eval" for k in sorted(set(bt) | set(be)) if k not in VOLATILE_EFFECTIVE and bt.get(k) != be.get(k)]
    if not bt:
        e.append(f"{key}: training report has no backend_effective")
    for facet in {q for _, q in rows_e}:
        ct = {tuple(r["candidate_ids"]) for (_, q), r in rows_t.items() if q == facet}
        ce_ = {tuple(r["candidate_ids"]) for (_, q), r in rows_e.items() if q == facet}
        if len(ct) != 1 or ct != ce_:
            e.append(f"{key}: {facet} candidate order differs between/within runs")
    qt = {r.get("questions_sha256") for r in rows_t.values()}; qe = {r.get("questions_sha256") for (i, _), r in rows_e.items() if not i.startswith("smoke")}
    if len(qt) != 1 or qt != qe:
        e.append(f"{key}: questions_sha256 differs between train and eval main rows")
    return e


def feats(rows_by_model, models, item_id, facet):
    """(x, cand) 或 (None, 原因)。每个模型: 候选内 log-softmax; 多模型拼接; 候选与 logits 长度逐模型核。"""
    parts, cand = [], None
    for m in models:
        r = rows_by_model[m].get((item_id, facet))
        if r is None:
            return None, f"{m} missing row {item_id}/{facet}"
        c = list(r["candidate_ids"])
        if cand is None:
            cand = c
        if c != cand or len(r["raw_candidate_logits"]) != len(c):
            return None, f"{m} candidates/logits inconsistent at {item_id}/{facet}"
        parts.append(logsoftmax(r["raw_candidate_logits"]))
    return np.concatenate(parts), cand


def self_teacher(x, models, K):
    """该变体模型自己的候选分布(多模型取平均)。"""
    ps = [np.exp(x[i * K:(i + 1) * K]) for i in range(len(models))]
    p = sum(ps) / len(ps)
    return p / p.sum()


def teacher_target(row, cand, facet):
    """老师软目标 + 校验记录。分布键必须 ⊆ 候选, 值有限非负且和≈1; 否则返回 None 与原因。"""
    if not row or not row.get("ok"):
        return None, "teacher row not ok"
    pr = (row.get("probs") or {}).get(facet)
    if not isinstance(pr, dict) or not pr:
        return None, "teacher distribution missing"
    vals = list(pr.values())
    if set(pr) - set(cand) or not all(isinstance(v, (int, float)) and math.isfinite(v) and v >= 0 for v in vals) or abs(sum(vals) - 1) > 0.02:                      # 与老师脚本 SUM_TOL 相同
        return None, "teacher distribution invalid (keys/values/sum)"
    y = np.array([float(pr.get(c, 0.0)) for c in cand])
    return y / y.sum(), None


# ───────────────────────── 一个读者(族 × 变体) ─────────────────────────
def analyse_reader(family, variant, train_dir, eval_dir, pre, X_):
    models = VARIANTS[variant]
    ev_items = _jsonl(EVAL_SUITE)
    ev_main = [it for it in ev_items if "text_ref" in it and not it["item_id"].startswith("rep-")]
    ptr_of = {it["item_id"]: _ptr(it["text_ref"]) for it in ev_items if "text_ref" in it}
    facets = pre["★面"]["模型读"]
    th = pre["★★★判决规则(测量前冻结)"]["数值"]["replaceable_max_d"]
    errs, prov, ev_rows, reps = [], {}, {}, {}
    for m in models:
        rep_e, ev_rows[m], prov[f"eval:{m}"] = load_run(eval_dir, m)
        reps[m] = rep_e
        errs += run_errors(rep_e, ev_rows[m], m, EVAL_SUITE, pre["★考场(冻结)"]["rows_per_model"])
        if prov[f"eval:{m}"]["run_id"] != pre["★考场(冻结)"]["run"]:
            errs.append(f"{m}: eval report is not from the pre-registered run {pre['★考场(冻结)']['run']}")
    tr_rows, teacher, teacher_doc = {}, {}, None
    if family == "T":
        teacher_doc = json.loads(TEACHER.read_text(encoding="utf-8"))
        fr = pre["★老师(冻结)"]
        if teacher_doc.get("question_sha") != fr["question_sha"] or teacher_doc.get("model") != fr["model"]:
            errs.append("老师请求形状/模型与预注册不符")
        if teacher_doc.get("prereg_sha256") != sha(PRE.read_bytes()) or teacher_doc.get("teacher_script_sha256") != pre["★分析脚本(冻结)"]["teacher_sha256"]:
            errs.append("老师读数不是在当前预注册与冻结的老师脚本下取得的")
        if teacher_doc.get("training_pointer_set_sha256") != pre["★训练集(冻结)"]["pointer_set_sha256"]:
            errs.append("训练指针集 sha 与预注册不符")
        if teacher_doc.get("status") not in TEACHER_STATUS_OK:
            errs.append(f"老师读数状态 {teacher_doc.get('status')!r} 不可用(只收 complete/capped)")
        teacher = {_ptr(r): r for r in teacher_doc["rows"] if r["split"] == "train"}
        tr_items = _jsonl(TRAIN_SUITE)
        if sha(json.dumps([[it["text_ref"]["file"], it["text_ref"]["line_index"], it["text_ref"]["line_sha256"]] for it in tr_items])) != pre["★训练集(冻结)"]["pointer_set_sha256"]:
            errs.append("训练 suite 与预注册指针集不符")
        if {_ptr(it["text_ref"]) for it in tr_items} & {_ptr(it["text_ref"]) for it in ev_main} or \
                {it["text_ref"]["line_sha256"] for it in tr_items} & {it["text_ref"]["line_sha256"] for it in ev_main}:
            errs.append("训练集与验收集有重合")
        for m in models:
            rep_t, tr_rows[m], prov[f"train:{m}"] = load_run(train_dir, m)
            errs += run_errors(rep_t, tr_rows[m], m, TRAIN_SUITE, len(tr_items) * len(facets), prereg_sha=sha(PRE.read_bytes()))
            errs += comparability_errors(rep_t, reps[m], tr_rows[m], ev_rows[m], m)
    j1 = X_.load_arms()["J1"]
    heads, preds, power = {}, [], {}
    for facet in (facets if not errs else []):
        # ---- 考场特征(全部行: 主条目、复跑、smoke)
        ev_x = {}
        for (iid, q) in sorted(ev_rows[models[0]]):
            if q != facet:
                continue
            x, cand_or_err = feats(ev_rows, models, iid, facet)
            if x is None:
                errs.append(cand_or_err); break
            ev_x[iid] = (x, cand_or_err)
        if errs:
            break
        cand = next(iter(ev_x.values()))[1]
        K = len(cand)
        # ---- 训练集合: 每个「预测单元」一组(训练 X, 目标 Y, 自老师 Ys, 要预测的考场 item_ids)
        units = []
        if family == "T":
            Xt, Yt, St, Gt = [], [], [], []
            grp = {iid: gi for gi, ids in enumerate(pre["★训练集(冻结)"]["留一分组(近重复)"]) for iid in ids}
            for it in tr_items:
                x, c = feats(tr_rows, models, it["item_id"], facet)
                if x is None:
                    errs.append(c); break
                if c != cand:
                    errs.append(f"{facet}: training candidate order != eval"); break
                y, why = teacher_target(teacher.get(_ptr(it["text_ref"])), cand, facet)
                if y is None:
                    if why != "teacher row not ok":
                        errs.append(f"{facet}: {why} at {it['item_id']}"); break
                    continue
                Xt.append(x); Yt.append(y); St.append(self_teacher(x, models, K)); Gt.append(grp.get(it["item_id"], it["item_id"]))
            if errs:
                break
            if len(Xt) < pre["★训练集(冻结)"]["min_n_train"]:
                errs.append(f"{facet}: {len(Xt)} usable training rows < min_n_train"); break
            units.append((np.array(Xt), np.array(Yt), np.array(St), sorted(ev_x), [str(x) for x in Gt]))
        else:
            order = [it["item_id"] for it in ev_main]
            fold = {iid: i % N_FOLDS for i, iid in enumerate(order)}
            for k in range(N_FOLDS):
                tr_ids = [iid for iid in order if fold[iid] != k]
                Xt = np.array([ev_x[iid][0] for iid in tr_ids])
                if any(ptr_of[iid] not in j1 for iid in tr_ids):
                    errs.append(f"{facet}: J1 has no reading for a training item in fold {k}"); break
                inv = {X_.RT.norm(c, X_.FACETS[facet]): c for c in cand}          # 归一化标签 → 唯一对应的候选(未知 ↔ 未提及)
                lab = [inv.get(X_.RT.norm(j1[ptr_of[iid]].get(facet), X_.FACETS[facet])) for iid in tr_ids]
                if len(inv) != len(cand) or None in lab:
                    errs.append(f"{facet}: normalised J1 label has no unique candidate in fold {k}"); break
                Yt = np.array([[1.0 if c == l else 0.0 for c in cand] for l in lab])
                St = np.array([self_teacher(x, models, K) for x in Xt])
                held = [iid for iid in ev_x if (iid[4:] if iid.startswith("rep-") else iid) in fold and fold[iid[4:] if iid.startswith("rep-") else iid] == k]
                units.append((Xt, Yt, St, held, None))
            if errs:
                break
        # ---- 拟合、预测、功效前置
        dself, lam_used = 0, []
        head_rec = []
        for Xt, Yt, St, held, groups in units:
            h = train_head(Xt, Yt, groups); hs = train_head(Xt, St, groups)
            lam_used.append(h["lambda"])
            head_rec.append({"n_train": int(len(Xt)), "lambda": h["lambda"], "loo_ce": h["loo_ce"], "self_lambda": hs["lambda"],
                             "W": np.round(h["W"], 8).tolist(), "b": np.round(h["b"], 8).tolist()})
            for iid in held:
                x = ev_x[iid][0][None, :]
                p = predict(h, x)[0]; ps = predict(hs, x)[0]; st = self_teacher(ev_x[iid][0], models, K)
                pl = [float(v) for v in p]
                if iid in ptr_of and not iid.startswith("rep-"):
                    dself += int(np.argmax(ps)) != int(np.argmax(st))
                base = ev_rows[models[0]][(iid, facet)]
                preds.append({"item_id": iid, "question_id": facet, "candidate_ids": cand, "probabilities": pl, "selected_candidate": cand[pl.index(max(pl))],
                              "questions_sha256": base.get("questions_sha256"),
                              "identities": {"row_sha256": sha("|".join(ev_rows[m][(iid, facet)]["identities"]["row_sha256"] for m in models))}})
        power[facet] = {"d_self_teacher": dself, "ok": dself <= th}
        heads[facet] = {"units": head_rec, "lambdas": lam_used}
        if family == "T":
            Xt = units[0][0]; mu, sd = Xt.mean(axis=0), Xt.std(axis=0); sd[sd == 0] = 1.0
            Xe = np.array([ev_x[iid][0] for iid in (it["item_id"] for it in ev_main)])
            heads[facet]["train_teacher_argmax"] = dict(collections.Counter(cand[int(np.argmax(y))] for y in units[0][1]))
            heads[facet]["★特征偏移(描述)"] = {"smd_eval_vs_train_per_dim": np.round((Xe.mean(axis=0) - mu) / sd, 4).tolist(),
                                          "max_abs_smd": round(float(np.abs((Xe.mean(axis=0) - mu) / sd).max()), 4)}
    within = {"pass": False}
    if not errs:
        within, _cross = X_.determinism(preds, ev_items, ptr_of, [], pre["★确定性(前置)"]["tol_abs_dp"], expected_pairs=10 * len(facets))
    if errs or not within.get("pass"):
        res = {"n_items": None, "per_facet": {}, "情绪余温_structural": None, "verdicts": {k: None for k in facets}, "overall": "前置不成立(执行错误, 不出判决)"}
    else:
        D, P = {}, {}
        for r in preds:
            if r["item_id"] in ptr_of and not r["item_id"].startswith("rep-"):
                D.setdefault(ptr_of[r["item_id"]], {})[r["question_id"]] = r["selected_candidate"]
                P.setdefault(ptr_of[r["item_id"]], {})[r["question_id"]] = dict(zip(r["candidate_ids"], r["probabilities"]))
        res = X_.analyse(D, P, X_.load_arms(), pre, within)
        for k in facets:                                           # 判决一字不改(冻结规则); 功效只决定能不能把它解释成「学不会」
            res["per_facet"][k]["★功效标记"] = "头能学回自老师" if power[k]["ok"] else "头无分辨力: 不得把本面结果解释成 Jev 读法学不到"
    head = None
    pf = (res.get("per_facet") or {}).get(pre["★头条检查(预注册)"]["面"])
    if pf:
        d = {j: pf["pairs"][f"D~{j}"]["d"] for j in ("J1", "J2")}
        head = {"facet": pre["★头条检查(预注册)"]["面"], "d": d, "max_d": max(d.values()), "threshold": th + 1,
                "result": "不能判可替代 ⇒ 不是完整替代" if max(d.values()) >= th + 1 else "头条检查通过(仅说明该面未被排除, 不是判决)"}
    return {"block": "JEV_DISTILL_VS_RETEST", "reader": family + variant, "family": family, "variant": variant, "models": list(models),
            "★前置错误": errs, "★同 run 复跑": within, **res, "★头条检查": head, "★功效前置(自老师)": power, "★头": heads,
            "★输入溯源": prov, "prereg_sha256": sha(PRE.read_bytes()), "teacher_sha256": sha(TEACHER.read_bytes()) if family == "T" and TEACHER.is_file() else None,
            "analysis_script_sha256": sha(pathlib.Path(__file__).read_bytes()), "analysis_script_sha256_at_freeze": pre["★分析脚本(冻结)"]["distill_sha256"],
            "frozen_rule_sha256": sha(FROZEN.read_bytes()), "★不得据此说": pre["★★★不得据此说"]}


def drift(pre, X_):
    """描述量(不进训练、不进判决): 今日老师在 10 条复跑条目上与 09-23 的 J1/J2 比; 同一批上 J1~J2 作噪声底。"""
    doc = json.loads(TEACHER.read_text(encoding="utf-8"))
    arms = X_.load_arms()
    per = {j: collections.Counter() for j in ("J1", "J2")}; base = collections.Counter(); n = missing = 0
    for r in doc["rows"]:
        if r["split"] != "drift" or not r.get("ok"):
            continue
        p = _ptr(r)
        if p not in arms["J1"] or p not in arms["J2"]:
            missing += 1; continue
        n += 1
        for f in pre["★面"]["模型读"]:
            t = X_.RT.norm(r["choice"].get(f), X_.FACETS[f])
            for j in ("J1", "J2"):
                per[j][f] += t != X_.RT.norm(arms[j][p].get(f), X_.FACETS[f])
            base[f] += X_.RT.norm(arms["J1"][p].get(f), X_.FACETS[f]) != X_.RT.norm(arms["J2"][p].get(f), X_.FACETS[f])
    flag = None if n < 10 else any(v >= pre["★老师(冻结)"]["drift_flag_min_d_of_10"] for v in per["J1"].values())
    return {"n": n, "missing_in_J": missing, "d_vs_J1": dict(per["J1"]), "d_vs_J2": dict(per["J2"]), "J1_vs_J2_same_items": dict(base), "flag": flag}


def shift(pre, X_):
    """描述量: 训练集老师首选分布 vs 验收 42 条 J1 分布(逐面)。"""
    doc = json.loads(TEACHER.read_text(encoding="utf-8")); j1 = X_.load_arms()["J1"]
    out = {}
    for f in pre["★面"]["模型读"]:
        t = collections.Counter(X_.RT.norm(r["choice"].get(f), X_.FACETS[f]) for r in doc["rows"] if r["split"] == "train" and r.get("ok"))
        a = collections.Counter(X_.RT.norm(v.get(f), X_.FACETS[f]) for v in j1.values())
        out[f] = {"teacher_train": dict(t), "J1_acceptance": dict(a)}
    return out


def score_predictions(pre, docs):
    """预注册预测的机器核对。"""
    zs = pre["★零样本基线(冻结)"]
    out = {}
    for tag, d in docs.items():
        pf = d.get("per_facet") or {}
        if not pf:
            out[tag] = None; continue
        better = [f for f in pre["★面"]["模型读"] if all(pf[f]["pairs"][f"D~{j}"]["d"] < min(zs[m][f][j] for m in zs) for j in ("J1", "J2"))]
        out[tag] = {"headline_ge_5": (d["★头条检查"] or {}).get("max_d", 0) >= 5, "overall_replaceable": d["overall"].startswith("5 个可读面上换成"),
                    "facets_better_than_best_zero_shot_both_rounds": better}
    return out


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    train_dir, eval_dir = argv[0], argv[1]
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    X_ = load_frozen(pre)
    for fam in FAMILIES:
        for v in VARIANTS:
            out_path(fam + v).unlink(missing_ok=True)
    docs = {}
    for fam in FAMILIES:
        for v in VARIANTS:
            try:
                doc = analyse_reader(fam, v, train_dir, eval_dir, pre, X_)
            except Exception as e:  # noqa: BLE001 —— 一个读者崩了也要落「前置不成立」, 不让其余读者缺席
                doc = {"block": "JEV_DISTILL_VS_RETEST", "reader": fam + v, "★前置错误": [f"crashed: {type(e).__name__}"],
                       "verdicts": {k: None for k in pre["★面"]["模型读"]}, "overall": "前置不成立(执行错误, 不出判决)", "★头条检查": None}
            docs[fam + v] = doc
    extra = {"★老师漂移(描述, 不进判决)": drift(pre, X_), "★分布偏移(描述)": shift(pre, X_)} if TEACHER.is_file() else {}
    for tag, doc in docs.items():
        doc.update(extra)
        out_path(tag).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    summary = {"block": "JEV_DISTILL_SUMMARY", "prereg_sha256": sha(PRE.read_bytes()), **extra, "★预测核对": score_predictions(pre, docs),
               "readers": {t: {"overall": d["overall"], "verdicts": d["verdicts"], "headline": d["★头条检查"], "errors": d["★前置错误"],
                               "power": d.get("★功效前置(自老师)")} for t, d in docs.items()}}
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(summary["readers"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
