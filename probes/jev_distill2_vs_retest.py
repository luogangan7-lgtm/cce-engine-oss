# -*- coding: utf-8 -*-
"""s0 读者蒸馏第二轮(预注册 tests/data/jev_distill2_prereg.json, 冻结于任何第二轮老师读数与特征之前)。零 API、零模型: 只读已存读数与归档特征。

特征(两模型都用 = 变体 C; 单腿失败时按预注册退到存活的那个模型):
  z_l = 每个模型在该 (帖, 面) 上选项字母 logits 的候选内 log-softmax, 两模型拼接 —— 每次拟合按该次训练行逐维标准化;
  z_h = 6 块隐状态跨度坐标(模型 × {0.5 深度块, 0.75 深度块, final}, 见 experiments/jev/hidden_export.py) —— 每块按该次训练行去均值,
        再整体缩放到训练总方差 = 1(块内不逐维缩放 ⇒ 头只依赖内积, 与在全局标准化的 2560 维状态上做岭等价)。
头(逐面多项逻辑回归, 严格凸): logit = z_l·W_lᵀ + z_h·W_hᵀ + b + δ·[训练帖];
  目标 = Σ w_i·CE(τ_i, p_i)/Σ w_i + λ_l/2‖W_l‖² + λ_h/2‖W_h‖² + λ_b/2(‖b‖² + ‖δ‖²), λ_b = 1e-3(截距也罚 ⇒ 缺类/单例类也有有限唯一解);
  验收帖 w = 1, 训练帖 w = w_T(w_T = 0 时训练帖整个不进该次拟合); CE 走 log-softmax, 不加任何 epsilon; L-BFGS-B 零初始化;
  收敛 = 解处梯度无穷范数 ≤ GRAD_TOL, 任何一次不收敛计数上报(主读者 > 0 = 前置不成立)。读出 = 概率首个最大。
读者(全部过冻结判据、全部报告, 不挑):
  P  主: 外层 = 验收 42 帖留一帖(训练 = 其余 41 帖 + 66 训练帖); 内层 = 那 41 帖按位置 mod 7 七折(训练帖始终在训练侧), 平均每帖 Brier 选配置,
        网格 λ_l × λ_h × w_T = 126, 并列(差 < 1e-9)取更大 λ_h → 更大 λ_l → 更大 w_T; 选中后在外层训练集上重拟合。目标 q_E = mean(J3, J4), q_T = mean(R1, R2)。
  S1 只字母(去掉 z_h; 网格 λ_l × w_T = 18)。S2 = P 但验收目标 = J1 独热。S3 = 纯迁移: 只用 66 训练帖(分组 7 折选 λ_l × λ_h), 42 帖只作考场。
控制: 置换闸(5 种子, 全嵌套 P) · 植入老师功效(锐度匹配的平滑独热, 全嵌套 P, 非退化条件) · 学习曲线(众数配置) · 稳健性(软 CE 选择)。
判决 = 冻结 probes/jev_decider_vs_retest.py 的 load_arms()/determinism()/analyse() 原样调用(sha 核), 对 09-23 的 J1/J2。产物只有指针、计数、统计量。
用法: python3 probes/jev_distill2_vs_retest.py <run_dir>          (run_dir 含 <model_key>/{report.json, predictions.jsonl, hidden_coords.jsonl, hidden_basis_meta.json})
"""
import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")                      # 单线程 BLAS: 逐次拟合确定、并行只在进程级

import collections, concurrent.futures as cf, hashlib, importlib.util, json, math, pathlib, sys

import numpy as np
from scipy.optimize import minimize

ROOT = pathlib.Path(__file__).resolve().parents[1]
PRE = ROOT / "tests/data/jev_distill2_prereg.json"
TEACHER1 = ROOT / "results/jev_distill_teacher.json"
TEACHER2 = ROOT / "results/jev_distill2_teacher.json"
SUITE = ROOT / "experiments/jev/suites/s0-distill2-v1.jsonl"
EXAM_SUITE = ROOT / "experiments/jev/suites/s0-compare-llm-v1.jsonl"
TRAIN_SUITE = ROOT / "experiments/jev/suites/s0-distill-train-v1.jsonl"
FROZEN = ROOT / "probes/jev_decider_vs_retest.py"
CAND_WRAPPER = ROOT / "probes/jev_candidate_vs_retest.py"
ARCH_EXAM, ARCH_TRAIN = ROOT / "archive/36316049972", ROOT / "archive/36325037233"
MODELS = ("qwen3-4b-2507", "qwen3.5-4b")
LAM_L = (1e-4, 1e-3, 1e-2, 1e-1, 1.0, 10.0)
LAM_H = (1e-5, 1e-4, 1e-3, 1e-2, 1e-1, 1.0, 10.0)
W_T = (0.0, 0.3, 1.0)
LAM_B, GRAD_TOL, N_INNER = 1e-3, 1e-5, 7
PERM_SEEDS, LC_SIZES, LC_SEEDS = 5, (10, 20, 30), 10
IDENTITY_KEYS = ("adapter_sha256", "runtime_lock_sha256", "tokenizer_sha256", "task_contract", "source_lock_sha256", "assets_lock_sha256", "model_key")
WORKERS = max(1, (os.cpu_count() or 2) - 1)


def sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode("utf-8")).hexdigest()


def _jsonl(p):
    return [json.loads(l) for l in pathlib.Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def _ptr(ref):
    return "%s:%d" % (ref["file"], ref["line_index"])


def out_path(tag):
    return ROOT / f"results/jev_distill2_{tag}_vs_retest.json"


SUMMARY = ROOT / "results/jev_distill2_summary.json"


def load_frozen(pre):
    if sha(FROZEN.read_bytes()) != pre["★脚本(冻结)"]["frozen_rule_sha256"]:
        raise SystemExit("冻结的对比脚本被改过: sha 与预注册不符, 拒绝出任何判决")
    s = importlib.util.spec_from_file_location("_frozen_cmp_d2", FROZEN); m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m


# ───────────────────────── 头(严格凸, 确定性) ─────────────────────────
def _lse(Z):
    m = Z.max(axis=1, keepdims=True)
    return m + np.log(np.exp(Z - m).sum(axis=1, keepdims=True))


def fit(Z, n_l, dom, Y, w, lam_l, lam_h):
    """Z: n×D(前 n_l 列字母, 其余隐状态), dom: n(0/1), Y: n×K 目标(行和 1), w: n 权重。返回 ((W, b, d), 解处梯度无穷范数)。
    无损变量替换(只为速度, 目标函数与最优解不变):
      ① s = λ^(-1/2)(按列组), Z̃ = Z·s, W̃ = W/s ⇒ 罚项 = ½‖W̃‖²; 最优 W̃ 在 Z̃ 的行空间里 ⇒ Z̃ = U S Vᵀ, W̃ = β Vᵀ, X = U S, logit = X βᵀ, 罚项 ½‖β‖²;
      ② Böhning 预条件: T = (½·XᵀΩX + I)^(-1/2)(Ω = 归一化权重), β = γ T —— 约化问题的曲率上界变成单位阵, L-BFGS 迭代从上千次降到几十次。
    零初始化; 收敛判据 = 解处(γ 空间)梯度无穷范数。"""
    n, D = Z.shape; K = Y.shape[1]
    sc = np.concatenate([np.full(n_l, lam_l ** -0.5), np.full(D - n_l, lam_h ** -0.5)])
    U, S, Vt = np.linalg.svd(Z * sc, full_matrices=False)
    r = int((S > 1e-12 * S[0]).sum()) if S.size and S[0] > 0 else 0
    X = U[:, :r] * S[:r]
    ws = w / w.sum()
    ev, Q = np.linalg.eigh(0.5 * (X * ws[:, None]).T @ X + np.eye(r))
    T = (Q * ev ** -0.5) @ Q.T
    XT = X @ T

    def f(t):
        Gm = t[:K * r].reshape(K, r); b = t[K * r:K * r + K]; d = t[K * r + K:]
        B = Gm @ T
        L = XT @ Gm.T + b + dom[:, None] * d
        logP = L - _lse(L)
        loss = -(ws[:, None] * Y * logP).sum() + 0.5 * (B * B).sum() + 0.5 * LAM_B * (b @ b + d @ d)
        G = (np.exp(logP) - Y) * ws[:, None]
        return loss, np.concatenate([(G.T @ XT + B @ T).ravel(), G.sum(axis=0) + LAM_B * b, (G * dom[:, None]).sum(axis=0) + LAM_B * d])
    res = minimize(f, np.zeros(K * r + 2 * K), jac=True, method="L-BFGS-B", options={"maxiter": 10000, "gtol": 1e-9, "ftol": 1e-15, "maxcor": 20})
    g = float(np.abs(f(res.x)[1]).max())
    W = ((res.x[:K * r].reshape(K, r) @ T) @ Vt[:r]) * sc
    return (W, res.x[K * r:K * r + K], res.x[K * r + K:]), g


def predict(params, Z, dom):
    W, b, d = params
    L = Z @ W.T + b + dom[:, None] * d
    return np.exp(L - _lse(L))


class Prep:
    """只用该次训练行: 字母列逐维标准化; 每个隐状态块去均值后整体缩放到总方差 1。"""
    def __init__(self, XL, XH, use_h):
        self.mu_l, self.sd_l = XL.mean(axis=0), XL.std(axis=0)
        self.sd_l[self.sd_l == 0] = 1.0
        self.use_h = use_h
        self.blocks = []
        if use_h:
            for B in XH:
                mu = B.mean(axis=0); tv = float(((B - mu) ** 2).sum(axis=1).mean())
                self.blocks.append((mu, math.sqrt(tv) if tv > 0 else 1.0))

    def __call__(self, XL, XH):
        parts = [(XL - self.mu_l) / self.sd_l]
        if self.use_h:
            parts += [(B - mu) / s for B, (mu, s) in zip(XH, self.blocks)]
        return np.concatenate(parts, axis=1)


# ───────────────────────── 一个面的数据 ─────────────────────────
class Facet:
    """rows: 帖索引 0..n_E-1 = 验收帖(输入序), n_E.. = 训练帖; rep: 复跑行特征(与基帖同索引)。"""
    def __init__(self, XL, XH, YE, YJ1, YT, rep_XL, rep_XH, rep_of, groups_T, groups_E=None):
        self.XL, self.XH = XL, XH                       # XL: N×L, XH: [N×r_b]
        self.YE, self.YJ1, self.YT = YE, YJ1, YT        # 42×K, 42×K, 66×K
        self.rep_XL, self.rep_XH, self.rep_of = rep_XL, rep_XH, rep_of
        self.nE, self.nT = YE.shape[0], YT.shape[0]
        self.groups_T = groups_T
        self.groups_E = groups_E or [str(i) for i in range(self.nE)]      # 预注册的验收集近重复组: 留出时整组留出, 内层整组分折

    def group_of(self, i):
        return [j for j in range(self.nE) if self.groups_E[j] == self.groups_E[i]]


def fit_rows(F, tr, Y, w, dom, cfg, use_h):
    """在池化行 tr(0..nE-1 = 验收帖, nE.. = 训练帖)上拟合。返回 (prep, params, 梯度范数)。"""
    XL = F.XL[tr]; XH = [B[tr] for B in F.XH]
    prep = Prep(XL, XH, use_h)
    params, g = fit(prep(XL, XH), F.XL.shape[1], dom, Y, w, cfg[0], cfg[1])
    return prep, params, g


def pred_rows(F, prep, params, rows, dom):
    return predict(params, prep(F.XL[rows], [B[rows] for B in F.XH]), dom)


def pred_rep(F, prep, params, js):
    if not js:
        return []
    return list(predict(params, prep(F.rep_XL[js], [B[js] for B in F.rep_XH]), np.zeros(len(js))))


def pooled(F, exam_tr, cfg, YE, YT):
    """池化训练集: exam_tr 验收帖(w = 1) ∪ 全部训练帖(w = w_T; w_T = 0 时不进)。"""
    w_T = cfg[2]
    tr = list(exam_tr) + (list(range(F.nE, F.nE + F.nT)) if w_T > 0 else [])
    Y = np.vstack([YE[list(exam_tr)]] + ([YT] if w_T > 0 else []))
    w = np.array([1.0] * len(exam_tr) + [w_T] * (len(tr) - len(exam_tr)))
    return tr, Y, w, (np.asarray(tr) >= F.nE).astype(float)


def _brier(P, Y):
    return float(((P - Y) ** 2).sum(axis=1).mean())


def _ce(P, Y):
    return float(-(Y * np.log(np.clip(P, 1e-300, None))).sum(axis=1).mean())


TIE_TOL = 1e-6                                          # 高于实测求解分辨率(内层 Brier 约 1e-7)


def _pick(scores):
    """scores: {cfg: 值} → argmin, 并列(差 < TIE_TOL)取更大 λ_h → 更大 λ_l → 更大 w_T。"""
    best = min(scores.values())
    return max((c for c, v in scores.items() if v - best < TIE_TOL), key=lambda c: (c[1], c[0], c[2]))


def grid(reader):
    """配置网格(选择与顺序无关: _pick 显式定并列)。S1 不用隐状态(λ_h 占位), S3 不用 w_T。"""
    if reader == "S1":
        return [(l, LAM_H[-1], w) for l in LAM_L for w in W_T]
    if reader == "S3":
        return [(l, h, 1.0) for l in LAM_L for h in LAM_H]
    return [(l, h, w) for l in LAM_L for h in LAM_H for w in W_T]


def inner_folds(F, others):
    """其余验收帖按组(组首次出现的次序)mod 7 分 7 折; 同组(近重复)永不拆开。"""
    ug = list(dict.fromkeys(F.groups_E[j] for j in others))
    return [f for f in ([j for j in others if ug.index(F.groups_E[j]) % N_INNER == k] for k in range(N_INNER)) if f]


def outer_fold(F, i, reader, YE, YT, crit="brier"):
    """验收帖 i 留出(连同它的近重复组): 内层在其余验收帖上按组七折选配置(训练帖始终在训练侧), 再在其余帖(+训练帖)上重拟合, 预测帖 i 与其复跑行。"""
    use_h = reader != "S1"
    others = [j for j in range(F.nE) if j not in F.group_of(i)]
    folds = inner_folds(F, others)
    score, worst = {}, 0.0
    for cfg in grid(reader):
        Ps, Ys = [], []
        for held in folds:
            tr, Y, w, dom = pooled(F, [j for j in others if j not in held], cfg, YE, YT)
            prep, params, g = fit_rows(F, tr, Y, w, dom, cfg, use_h)
            worst = max(worst, g)
            Ps.append(pred_rows(F, prep, params, held, np.zeros(len(held)))); Ys.append(YE[held])
        Ps, Ys = np.vstack(Ps), np.vstack(Ys)
        score[cfg] = _brier(Ps, Ys) if crit == "brier" else _ce(Ps, Ys)
    cfg = _pick(score)
    vals = sorted(score.values())
    tr, Y, w, dom = pooled(F, others, cfg, YE, YT)
    prep, params, g = fit_rows(F, tr, Y, w, dom, cfg, use_h)
    reps = [j for j, b in enumerate(F.rep_of) if b == i]
    p = pred_rows(F, prep, params, [i], np.zeros(1))[0]
    return {"i": i, "cfg": cfg, "p": p.tolist(), "rep": {j: r.tolist() for j, r in zip(reps, pred_rep(F, prep, params, reps))}, "grad": max(worst, g),
            "margin": float(vals[1] - vals[0]) if len(vals) > 1 else None}


def transfer(F, YT):
    """S3 纯迁移: 只用 66 训练帖(无领域列), 分组七折选 λ_l × λ_h, 全量重拟合后预测 42 帖与复跑行。"""
    ug = list(dict.fromkeys(F.groups_T))
    folds = [[j for j in range(F.nT) if ug.index(F.groups_T[j]) % N_INNER == k] for k in range(N_INNER)]
    score, worst = {}, 0.0
    for cfg in grid("S3"):
        Ps, Ys = [], []
        for held in folds:
            keep = [j for j in range(F.nT) if j not in held]
            prep, params, g = fit_rows(F, [F.nE + j for j in keep], YT[keep], np.ones(len(keep)), np.zeros(len(keep)), cfg, True)
            worst = max(worst, g)
            Ps.append(pred_rows(F, prep, params, [F.nE + j for j in held], np.zeros(len(held)))); Ys.append(YT[held])
        score[cfg] = _brier(np.vstack(Ps), np.vstack(Ys))
    cfg = _pick(score)
    prep, params, g = fit_rows(F, list(range(F.nE, F.nE + F.nT)), YT, np.ones(F.nT), np.zeros(F.nT), cfg, True)
    P = pred_rows(F, prep, params, list(range(F.nE)), np.zeros(F.nE))
    R = pred_rep(F, prep, params, list(range(len(F.rep_of))))
    return {"cfg": cfg, "p": [x.tolist() for x in P], "rep": {j: r.tolist() for j, r in enumerate(R)}, "grad": max(worst, g)}


def fit_all(F, cfg, YE, YT, use_h=True):
    """在全部 42 帖(+训练帖, 按 w_T)上拟合 cfg, 返回 108 帖的概率(植入老师用)。"""
    tr, Y, w, dom = pooled(F, list(range(F.nE)), cfg, YE, YT)
    prep, params, _ = fit_rows(F, tr, Y, w, dom, cfg, use_h)
    rows = list(range(F.nE + F.nT))
    return pred_rows(F, prep, params, rows, (np.asarray(rows) >= F.nE).astype(float))


# ───────────────────────── 并行(进程级; 每次拟合零初始化 ⇒ 结果与调度顺序无关) ─────────────────────────
_W = {}


def _init(facets):
    _W["F"] = facets


def _job(args):
    tag, kind, f, i, reader, crit, tgt = args
    F = _W["F"][f]
    YE, YT = (F.YE, F.YT) if tgt is None else tgt
    return tag, f, (outer_fold(F, i, reader, YE, YT, crit) if kind == "outer" else transfer(F, YT))


def run_jobs(facets, jobs):
    """jobs: (标签, outer|transfer, 面, 帖, 读者, 准则, 目标覆盖) → {(标签, 面): {帖: 结果}}(transfer 的帖 = -1)。"""
    out = collections.defaultdict(dict)
    if WORKERS <= 1:                                   # 串行(测试用; 结果与并行逐位相同)
        _init(facets)
        results = map(_job, jobs)
    else:                                              # spawn: 子进程按 __main__ 重新导入本脚本, 网格常量取模块默认值
        ex = cf.ProcessPoolExecutor(max_workers=WORKERS, initializer=_init, initargs=(facets,))
        results = ex.map(_job, jobs, chunksize=1)
    for tag, f, r in results:
        out[(tag, f)][r.get("i", -1)] = r
    if WORKERS > 1:
        ex.shutdown()
    return out


# ───────────────────────── 数据装载与前置 ─────────────────────────
def load_leg(run_dir, key):
    d = pathlib.Path(run_dir) / key
    rep = json.loads((d / "report.json").read_text(encoding="utf-8"))
    preds = {(r["item_id"], r["question_id"]): r for r in _jsonl(d / "predictions.jsonl")}
    coords = {(r["item_id"], r["question_id"]): r for r in _jsonl(d / "hidden_coords.jsonl")}
    meta = json.loads((d / "hidden_basis_meta.json").read_text(encoding="utf-8"))
    prov = {"report_sha256": sha((d / "report.json").read_bytes()), "predictions_sha256": sha((d / "predictions.jsonl").read_bytes()),
            "coords_sha256": sha((d / "hidden_coords.jsonl").read_bytes()), "run_id": ((rep.get("identities") or {}).get("run") or {}).get("GITHUB_RUN_ID"),
            "execution_commit": (rep.get("identities") or {}).get("cce_execution_commit")}
    return rep, preds, coords, meta, prov


def _identity_errors(key, rep):
    """与候选对比同一身份核对(probes/jev_candidate_vs_retest.identity_errors, sha 由预注册钉住): 仓库/修订/字母/线程/精度/prompt spec/温度 == 源锁。"""
    s_ = importlib.util.spec_from_file_location("_cand_wrapper_d2", CAND_WRAPPER); m = importlib.util.module_from_spec(s_); s_.loader.exec_module(m)
    return m.identity_errors(key, rep)


def leg_errors(key, rep, preds, coords, meta, prov, pre, run_dir):
    e = []
    ids = rep.get("identities") or {}
    e += _identity_errors(key, rep)
    if ids.get("adapter_sha256") != pre["★脚本(冻结)"]["adapter_sha256"]:
        e.append(f"{key}: adapter sha (experiments/jev/*.py) != the frozen adapter")
    plan = ((rep.get("hidden_export") or {}).get("plan") or {})
    want_blocks = pre["★GitHub(冻结)"]["隐状态块号"][key]
    if plan.get("blocks") != want_blocks or ((ids.get("backend_effective") or {}).get("hidden_export") or {}).get("blocks") != want_blocks:
        e.append(f"{key}: hidden export blocks {plan.get('blocks')} != registered {want_blocks}")
    keys_want = sorted([f"b{k}" for k in want_blocks] + ["final"])
    if any(sorted(r["blocks"]) != keys_want for r in coords.values()):
        e.append(f"{key}: coordinate block keys != {keys_want}")
    for b, v in (meta.get("blocks") or {}).items():
        if v.get("n_main") != 108 or not 1 <= v.get("rank", 0) <= 107:
            e.append(f"{key}: span meta {b} n_main {v.get('n_main')} / rank {v.get('rank')}"); break
    main_ids = {it["item_id"] for it in _jsonl(SUITE) if "text_ref" in it and not it["item_id"].startswith("rep-")}
    worst = max((blk["resid"] for (iid, _q), r in coords.items() if iid in main_ids for blk in r["blocks"].values()), default=0.0)
    if worst > 1e-6:
        e.append(f"{key}: a main row lies outside its own span (resid {worst:.3g})")
    src = ROOT / f"experiments/jev/models/{key}/model.source.lock.json"; ast = ROOT / f"experiments/jev/models/{key}/model.assets.lock.json"
    if rep.get("execution_status") != "SUCCEEDED" or rep.get("coverage_status") != "COMPLETE":
        e.append(f"{key}: run not SUCCEEDED/COMPLETE")
    if rep.get("suite_sha256") != sha(SUITE.read_bytes()) or (rep.get("suite_manifest") or {}).get("prereg_sha256") != sha(PRE.read_bytes()):
        e.append(f"{key}: suite sha or executed manifest prereg sha != current")
    if ids.get("model_key") != key or ids.get("source_lock_sha256") != sha(src.read_bytes()) or ids.get("assets_lock_sha256") != sha(ast.read_bytes()):
        e.append(f"{key}: report identity != current locks")
    if ids.get("permit_id") != pre["★GitHub(冻结)"]["permit_id"] or str(prov["run_id"]) != pathlib.Path(run_dir).name:
        e.append(f"{key}: permit id or run id does not match the prereg / archive directory")
    if len(preds) != pre["★GitHub(冻结)"]["rows_per_leg"] or set(coords) != set(preds):
        e.append(f"{key}: {len(preds)} prediction rows / {len(coords)} coordinate rows")
    if meta.get("coords_sha256") != prov["coords_sha256"]:
        e.append(f"{key}: hidden coordinate file sha != its meta")
    blocks = {tuple(sorted(r["blocks"])) for r in coords.values()}
    if len(blocks) != 1 or len(next(iter(blocks))) != 3:
        e.append(f"{key}: coordinate blocks per row not uniform ×3: {sorted(blocks)[:3]}")
    for arch in (ARCH_EXAM, ARCH_TRAIN):                  # 同一 prompt ⇒ 同一 token 行 ⇒ 行 sha 必须与归档逐行相等
        for (iid, q), r in {(r["item_id"], r["question_id"]): r for r in _jsonl(arch / key / "predictions.jsonl")}.items():
            mine = preds.get((iid, q))
            if mine is None or mine["identities"]["row_sha256"] != r["identities"]["row_sha256"]:
                e.append(f"{key}: row {iid}/{q} missing or row_sha256 != archive {arch.name}"); break
    return e


def teacher_rows(pre):
    """→ ({pass: {ptr: row}}, 错误)。R1 = 第一轮 train 行; J3/R2/J4 = 第二轮。"""
    e = []
    t1 = json.loads(TEACHER1.read_text(encoding="utf-8")); t2 = json.loads(TEACHER2.read_text(encoding="utf-8"))
    fz = pre["★老师(冻结)"]
    if t2.get("status") not in ("complete", "capped") or t2.get("prereg_sha256") != sha(PRE.read_bytes()) or \
            t2.get("teacher2_sha256") != pre["★脚本(冻结)"]["teacher2_sha256"] or t2.get("question_sha") != fz["question_sha"]:
        e.append("第二轮老师读数不是在当前预注册/冻结脚本下完成的(status/prereg/sha/question)")
    out = {"R1": {_ptr(r): r for r in t1["rows"] if r["split"] == "train" and r.get("ok")}}
    for p in ("J3", "R2", "J4"):
        out[p] = {_ptr(r): r for r in t2["rows"] if r["pass"] == p and r.get("ok")}
    return out, e


def target(reads, ptr_, facet, cand):
    vs = [np.array([float(r["probs"][facet].get(c, 0.0)) for c in cand]) for r in (x.get(ptr_) for x in reads) if r and facet in (r.get("probs") or {})]
    vs = [v / v.sum() for v in vs if v.sum() > 0]
    return (sum(vs) / len(vs)) if vs else None


def logsoftmax(v):
    v = np.asarray(v, dtype=float)
    return v - (v.max() + np.log(np.exp(v - v.max()).sum()))


def build(pre, X_, legs, teach):
    """→ ({面: Facet}, 元信息, 错误)。"""
    e = []
    facets = pre["★面"]["模型读"]
    ex_items = [it for it in _jsonl(EXAM_SUITE) if "text_ref" in it and not it["item_id"].startswith("rep-")]
    rep_items = [it for it in _jsonl(EXAM_SUITE) if it["item_id"].startswith("rep-")]
    tr_items = _jsonl(TRAIN_SUITE)
    j1 = X_.load_arms()["J1"]
    grp = {iid: str(g) for g, ids in enumerate(pre["★训练集(冻结)"]["留一分组(近重复)"]) for iid in ids}
    egrp = {p_: "g%d" % g for g, ps in enumerate(pre["★验收集(冻结)"]["近重复分组"]) for p_ in ps}
    models = [m for m in MODELS if m in legs]
    out, row_sha = {}, {}
    for f in facets:
        cand = legs[models[0]][0][(ex_items[0]["item_id"], f)]["candidate_ids"]
        inv = {X_.RT.norm(c, X_.FACETS[f]): c for c in cand}
        if len(inv) != len(cand):
            e.append(f"{f}: normalised candidates not unique"); continue

        def feats(iid):
            L, H = [], []
            for m in models:
                p, c = legs[m][0][(iid, f)], legs[m][1][(iid, f)]
                if p["candidate_ids"] != cand:
                    raise ValueError(f"{m}/{iid}/{f}: candidate order differs")
                L.append(logsoftmax(p["raw_candidate_logits"]))
                H += [np.array(c["blocks"][k]["c"], dtype=float) for k in sorted(c["blocks"])]
            return np.concatenate(L), H
        try:
            rows = [feats(it["item_id"]) for it in ex_items] + [feats(it["item_id"]) for it in tr_items]
            reps = [feats(it["item_id"]) for it in rep_items]
        except (KeyError, ValueError) as err:
            e.append(f"{f}: {type(err).__name__}: {err}"); continue
        XL = np.array([r[0] for r in rows]); XH = [np.array([r[1][b] for r in rows]) for b in range(len(rows[0][1]))]
        rXL = np.array([r[0] for r in reps]); rXH = [np.array([r[1][b] for r in reps]) for b in range(len(reps[0][1]))]
        YE, YT, YJ = [], [], []
        for it in ex_items:
            t = target([teach["J3"], teach["J4"]], _ptr(it["text_ref"]), f, cand)
            lab = inv.get(X_.RT.norm((j1.get(_ptr(it["text_ref"])) or {}).get(f), X_.FACETS[f]))
            if t is None or lab is None:
                e.append(f"{f}: exam post {it['item_id']} has no usable J3/J4 read or J1 label"); break
            YE.append(t); YJ.append(np.array([1.0 if c == lab else 0.0 for c in cand]))
        for it in tr_items:
            t = target([teach["R1"], teach["R2"]], _ptr(it["text_ref"]), f, cand)
            if t is None:
                e.append(f"{f}: training post {it['item_id']} has no usable R1/R2 read"); break
            YT.append(t)
        if len(YE) != len(ex_items) or len(YT) != len(tr_items):
            continue
        base = {it["item_id"]: k for k, it in enumerate(ex_items)}
        out[f] = Facet(XL, XH, np.array(YE), np.array(YJ), np.array(YT), rXL, rXH, [base[it["item_id"][4:]] for it in rep_items],
                       [grp.get(it["item_id"], it["item_id"]) for it in tr_items],
                       [egrp.get(_ptr(it["text_ref"]), str(k)) for k, it in enumerate(ex_items)])
        out[f].cand = cand
        for it in ex_items + rep_items:
            row_sha[(it["item_id"], f)] = "|".join(legs[m][0][(it["item_id"], f)]["identities"]["row_sha256"] for m in models)
    info = {"models": models, "ex_items": ex_items, "rep_items": rep_items, "tr_items": tr_items, "row_sha": row_sha}
    return out, info, e


# ───────────────────────── 读者 → 冻结判决 ─────────────────────────
def verdict(reader_rows, info, pre, X_, check_det=True):
    """reader_rows: {面: {帖索引: (p, {复跑索引: p})}} → (冻结 analyse 结果, 同 run 复跑块)。复跑行用真实行 sha(两模型拼接)。"""
    ev_items = _jsonl(EXAM_SUITE)
    ptr_of = {it["item_id"]: _ptr(it["text_ref"]) for it in ev_items if "text_ref" in it}
    preds = []
    for f, rows in reader_rows.items():
        cand = info["cand"][f]
        for i, (p, reps) in rows.items():
            iid = info["ex_items"][i]["item_id"]
            for rid, pp in [(iid, p)] + [(info["rep_items"][j]["item_id"], q) for j, q in reps.items()]:
                preds.append({"item_id": rid, "question_id": f, "candidate_ids": cand, "probabilities": [float(x) for x in pp],
                              "selected_candidate": cand[int(np.argmax(pp))], "identities": {"row_sha256": info["row_sha"][(rid, f)]}})
    within = None
    if check_det:
        within, _ = X_.determinism(preds, ev_items, ptr_of, [], pre["★确定性(前置)"]["tol_abs_dp"], expected_pairs=10 * len(reader_rows))
    D, P = {}, {}
    for r in preds:
        if not r["item_id"].startswith("rep-"):
            D.setdefault(ptr_of[r["item_id"]], {})[r["question_id"]] = r["selected_candidate"]
            P.setdefault(ptr_of[r["item_id"]], {})[r["question_id"]] = dict(zip(r["candidate_ids"], r["probabilities"]))
    return X_.analyse(D, P, X_.load_arms(), pre, within), within


def d_vs(labels, ref, info, f, X_):
    """labels: 42 个候选(验收输入序) → 与 ref({ptr: {面: 标签}})归一化后不同的条数。"""
    fk = X_.FACETS[f]
    return sum(X_.RT.norm(l, fk) != X_.RT.norm((ref.get(_ptr(it["text_ref"])) or {}).get(f), fk) for l, it in zip(labels, info["ex_items"]))


def modal(sel):
    c = collections.Counter(sel)
    top = max(c.values())
    return max((k for k, v in c.items() if v == top), key=lambda k: (k[1], k[0], k[2]))


def rows_of(got, F, transfer_=False):
    if transfer_:
        t = got[-1]
        return {i: (np.array(t["p"][i]), {int(j): np.array(v) for j, v in t["rep"].items() if F.rep_of[int(j)] == i}) for i in range(F.nE)}, [tuple(t["cfg"])], t["grad"]
    return ({i: (np.array(got[i]["p"]), {int(j): np.array(v) for j, v in got[i]["rep"].items()}) for i in range(F.nE)},
            [tuple(got[i]["cfg"]) for i in range(F.nE)], max(got[i]["grad"] for i in range(F.nE)))


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    run_dir = pathlib.Path(argv[0])
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    X_ = load_frozen(pre)
    for t in ("P", "S1", "S2", "S3"):
        out_path(t).unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)
    errs, legs, prov = [], {}, {}
    if sha(pathlib.Path(__file__).read_bytes()) != pre["★脚本(冻结)"]["analysis2_sha256"]:
        errs.append("analysis script sha != prereg (看数据后的改动必须登记; 仍出判决, 但带此标记)")
    failed_legs = []                                   # 单腿预案只覆盖「GitHub 上那条腿没成功/没有产物」; 身份、行 sha 等不符一律是前置不成立
    for m in MODELS:
        rp = run_dir / m / "report.json"
        rep = json.loads(rp.read_text(encoding="utf-8")) if rp.is_file() else None
        if rep is None or rep.get("execution_status") != "SUCCEEDED" or rep.get("coverage_status") != "COMPLETE":
            failed_legs.append(m); continue
        missing = [n for n in ("predictions.jsonl", "hidden_coords.jsonl", "hidden_basis_meta.json") if not (run_dir / m / n).is_file()]
        if missing:
            errs.append(f"{m}: files missing {missing}"); continue
        rep, preds, coords, meta, pv = load_leg(run_dir, m)
        e = leg_errors(m, rep, preds, coords, meta, pv, pre, run_dir)
        prov[m] = pv
        errs += e
        if not e:
            legs[m] = (preds, coords, rep)
    if not legs and not errs:
        errs.append("no usable leg")
    contingency = f"single leg (pre-registered contingency): {sorted(legs)}; failed on GitHub: {failed_legs}" if failed_legs and legs else None
    if failed_legs and not legs:
        errs.append(f"both legs failed on GitHub: {failed_legs}")
    teach, te = teacher_rows(pre); errs += te
    facets, info, be = build(pre, X_, legs, teach) if legs else ({}, {}, []); errs += be
    fl = pre["★面"]["模型读"]
    fatal = [x for x in errs if not x.startswith("analysis script sha")]
    res = {"block": "JEV_DISTILL2", "★前置错误": errs, "★单腿预案": contingency, "★输入溯源": prov, "prereg_sha256": sha(PRE.read_bytes()),
           "analysis_script_sha256": sha(pathlib.Path(__file__).read_bytes()), "analysis_script_sha256_at_freeze": pre["★脚本(冻结)"]["analysis2_sha256"],
           "frozen_rule_sha256": sha(FROZEN.read_bytes()), "teacher2_sha256": sha(TEACHER2.read_bytes()) if TEACHER2.is_file() else None,
           "★不得据此说": pre["★★★不得据此说"]}
    if fatal or len(facets) != len(fl):
        SUMMARY.write_text(json.dumps(res | {"overall": "前置不成立(执行错误, 不出判决)"}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(json.dumps(errs, ensure_ascii=False, indent=1)); return 1
    info["cand"] = {f: F.cand for f, F in facets.items()}
    J = X_.load_arms()
    head = pre["★头条检查(预注册)"]["面"]
    # ---- 第一批(并行): 读者 P / S1 / S2 / S3, 置换闸 5 种子, 软 CE 稳健性
    perms = {(s, f): (np.random.default_rng([20260928, s, k]).permutation(42), np.random.default_rng([20260929, s, k]).permutation(66))
             for s in range(PERM_SEEDS) for k, f in enumerate(fl)}
    jobs = [(rd, "outer", f, i, rd, "brier", (facets[f].YJ1, facets[f].YT) if rd == "S2" else None) for rd in ("P", "S1", "S2") for f in fl for i in range(42)]
    jobs += [("S3", "transfer", f, -1, "S3", "brier", None) for f in fl]
    jobs += [(f"perm{s}", "outer", f, i, "P", "brier", (facets[f].YE[perms[(s, f)][0]], facets[f].YT[perms[(s, f)][1]]))
             for s in range(PERM_SEEDS) for f in fl for i in range(42)]
    jobs += [("ce", "outer", f, i, "P", "ce", None) for f in fl for i in range(42)]
    R = run_jobs(facets, jobs)
    readers = {}
    for rd in ("P", "S1", "S2", "S3"):
        rows, sel, grad = {}, {}, 0.0
        for f in fl:
            rows[f], sel[f], g = rows_of(R[(rd, f)], facets[f], transfer_=(rd == "S3"))
            grad = max(grad, g)
        margin = {f: min((x.get("margin") for x in R[(rd, f)].values() if x.get("margin") is not None), default=None) for f in fl}
        an, within = verdict(rows, info, pre, X_)
        readers[rd] = {"rows": rows, "sel": sel, "grad": grad, "an": an, "within": within, "nonconverged": grad > GRAD_TOL, "margin": margin}
    P_ = readers["P"]
    d0 = {f: P_["an"]["per_facet"][f]["zero_baseline"]["J1"]["d0_constant_majority"] for f in fl}
    perm_res = {}
    for f in fl:
        ds = []
        for s in range(PERM_SEEDS):
            pe = perms[(s, f)][0]
            labs = [facets[f].cand[int(np.argmax(R[(f"perm{s}", f)][i]["p"]))] for i in range(42)]
            J1p = {_ptr(info["ex_items"][i]["text_ref"]): J["J1"].get(_ptr(info["ex_items"][pe[i]]["text_ref"])) or {} for i in range(42)}
            ds.append(d_vs(labs, J1p, info, f, X_))
        perm_res[f] = {"d_perm_vs_permuted_J1": ds, "median": float(np.median(ds)), "d0": d0[f], "leak_suspected": float(np.median(ds)) < d0[f] - 2}
    leak = any(v["leak_suspected"] for v in perm_res.values())
    res["★置换闸"] = perm_res
    rows_ce = {f: rows_of(R[("ce", f)], facets[f])[0] for f in fl}
    an_ce, _ = verdict(rows_ce, info, pre, X_)
    res["★稳健性(软CE选择, 描述)"] = {"verdict_changes": sorted(f for f in fl if an_ce["verdicts"][f] != P_["an"]["verdicts"][f]), "verdicts": an_ce["verdicts"],
                                   "d": {f: [an_ce["per_facet"][f]["pairs"][f"D~{j}"]["d"] for j in ("J1", "J2")] for f in fl}}
    # ---- 第二批(并行): 植入老师 —— 从最强正则一端起, 取第一个「有效且与真实标签不同」的配置在全部帖上拟合 → argmax = 植入标签
    #      (小 λ 会把真实标签插值出来 ⇒ 植入老师 = 真标签, 检查就不是功效了); 目标 = 锐度匹配的平滑独热; 再跑完整嵌套 P 看能否学回
    planted, pl_jobs = {}, []
    for f in fl:
        F = facets[f]; K = len(F.cand); pick = None
        jl = [inv_lab for inv_lab in (int(np.argmax(y)) for y in F.YJ1)]
        qe = [int(np.argmax(y)) for y in F.YE]
        for cfg in sorted(grid("P"), key=lambda c: (-c[1], -c[0], -c[2])):
            lab = np.array([int(np.argmax(p)) for p in fit_all(F, cfg, F.YE, F.YT)])
            maj = collections.Counter(lab[:42].tolist()).most_common(1)[0][1]
            dj1 = int(sum(a != b for a, b in zip(lab[:42], jl))); dqe = int(sum(a != b for a, b in zip(lab[:42], qe)))
            if maj < 38 and (42 - maj) >= d0[f] - 3 and dj1 > 0 and dqe > 0:
                pick = (cfg, lab, maj, dj1, dqe); break
        if pick is None:
            planted[f] = None; continue
        m = float(np.concatenate([F.YE.max(axis=1), F.YT.max(axis=1)]).mean())
        eps = (1 - m) / (1 - 1 / K)
        T = (1 - eps) * np.eye(K)[pick[1]] + eps / K
        planted[f] = pick + (eps,)
        pl_jobs += [("planted", "outer", f, i, "P", "brier", (T[:42], T[42:])) for i in range(42)]
    PL = run_jobs(facets, pl_jobs) if pl_jobs else {}
    power = {}
    for f in fl:
        if planted[f] is None:
            power[f] = {"valid": False, "ok": False, "note": "网格里没有有效且与真实标签不同的植入老师 ⇒ 功效未确立"}; continue
        cfg, lab, maj, dj1, dqe, eps = planted[f]
        rec = [int(np.argmax(PL[("planted", f)][i]["p"])) for i in range(42)]
        d_pl = int(sum(r != l for r, l in zip(rec, lab[:42])))
        power[f] = {"planted_cfg": list(cfg), "eps": round(eps, 6), "d_planted": d_pl, "planted_majority": maj, "d0_planted": 42 - maj, "valid": True,
                    "ok": d_pl <= 4, "in_sample_d(planted, J1)": dj1, "in_sample_d(planted, argmax q_E)": dqe}
    res["★植入老师功效"] = power
    # ---- 学习曲线(众数配置; 描述; 顺序计算)
    lc = {}
    for f in fl:
        F = facets[f]; cfg = modal(P_["sel"][f]); per = {}
        for n in LC_SIZES + (41,):
            ds = []
            for s in (range(LC_SEEDS) if n < 41 else [0]):
                labs = []
                for i in range(42):
                    others = [j for j in range(42) if j not in F.group_of(i)]
                    sub = others if n == 41 else sorted(np.random.default_rng([7, s, i, n]).choice(others, min(n, len(others)), replace=False).tolist())
                    tr, Y, w, dom = pooled(F, sub, cfg, F.YE, F.YT)
                    prep, params, _ = fit_rows(F, tr, Y, w, dom, cfg, True)
                    labs.append(F.cand[int(np.argmax(pred_rows(F, prep, params, [i], np.zeros(1))[0]))])
                ds.append(d_vs(labs, J["J1"], info, f, X_))
            per[str(n)] = {"mean_d_vs_J1": float(np.mean(ds)), "d": ds}
        lc[f] = per
    data_limited = lc[head]["41"]["mean_d_vs_J1"] <= lc[head]["20"]["mean_d_vs_J1"] - 2
    res["★学习曲线(描述)"] = {"per_facet": lc, "data_limited_flag": data_limited}
    # ---- 描述: 老师复测/漂移、J3 读者、分歧类型、McNemar、跨 run 字母 logits、预登记的不可学条数
    desc = {}
    for f in fl:
        fk = X_.FACETS[f]
        def top(reads, it, f=f, fk=fk):
            r = reads.get(_ptr(it["text_ref"]))
            return None if not r else X_.RT.norm(r["choice"].get(f), fk)
        def jr(arm, f=f, fk=fk):
            return lambda it: X_.RT.norm((J[arm].get(_ptr(it["text_ref"])) or {}).get(f), fk)
        def d(a, b, items):
            return sum(1 for it in items if a(it) is not None and b(it) is not None and a(it) != b(it))
        ex, tr_ = info["ex_items"], info["tr_items"]
        j3, j4 = (lambda it: top(teach["J3"], it)), (lambda it: top(teach["J4"], it))
        desc[f] = {"d(J3,J4)": d(j3, j4, ex), "d(R1,R2)": d(lambda it: top(teach["R1"], it), lambda it: top(teach["R2"], it), tr_),
                   "d(J3,J1)": d(j3, jr("J1"), ex), "d(J3,J2)": d(j3, jr("J2"), ex), "d(J4,J1)": d(j4, jr("J1"), ex), "d(J4,J2)": d(j4, jr("J2"), ex),
                   "d(J1,J2)": d(jr("J1"), jr("J2"), ex)}
    res["★老师复测与漂移(描述)"] = desc
    j3rows = {f: {i: (facets[f].YE[i], {}) for i in range(42)} for f in fl}
    an_j3, _ = verdict(j3rows, info, pre, X_, check_det=False)
    res["★q_E 读者(漂移底, 描述)"] = {"verdicts": an_j3["verdicts"], "d": {f: [an_j3["per_facet"][f]["pairs"][f"D~{j}"]["d"] for j in ("J1", "J2")] for f in fl}}
    unl = {}
    for f in fl:
        F = facets[f]; n = 0
        for i, it in enumerate(info["ex_items"]):
            k = int(np.argmax(F.YJ1[i]))
            n += (np.delete(np.vstack([F.YE, F.YT]), i, axis=0)[:, k].sum() < 0.5)
        unl[f] = int(n)
    res["★留一不可学条数(J1 类在其余 107 帖软质量 < 0.5)"] = unl
    split, mc = {}, {}
    def lab_of(rd, f, i):
        return X_.RT.norm(facets[f].cand[int(np.argmax(readers[rd]["rows"][f][i][0]))], X_.FACETS[f])
    for rd in readers:
        split[rd] = {}
        for f in fl:
            a = c = 0
            for i, it in enumerate(info["ex_items"]):
                s_, j = lab_of(rd, f, i), X_.RT.norm((J["J1"].get(_ptr(it["text_ref"])) or {}).get(f), X_.FACETS[f])
                if s_ != j:
                    a += "未知" in (s_, j); c += "未知" not in (s_, j)
            split[rd][f] = {"abstain_convention": a, "concrete_choice": c}
    for other in ("S1", "S2", "S3"):
        mc[other] = {}
        for f in fl:
            b = c = 0
            for i, it in enumerate(info["ex_items"]):
                j = X_.RT.norm((J["J1"].get(_ptr(it["text_ref"])) or {}).get(f), X_.FACETS[f])
                pok, ook = lab_of("P", f, i) == j, lab_of(other, f, i) == j
                b += pok and not ook; c += ook and not pok
            mc[other][f] = {"P_only_right": b, "other_only_right": c, "p_exact": X_.mcnemar_exact(b, c)}
    res["★分歧类型(对 J1, 描述)"] = split
    res["★McNemar(P vs 其他, 对 J1, 描述)"] = mc
    xr = {}
    for m, (preds, _c, _r) in legs.items():
        dmax = 0.0
        for arch in (ARCH_EXAM, ARCH_TRAIN):
            for r in _jsonl(arch / m / "predictions.jsonl"):
                mine = preds[(r["item_id"], r["question_id"])]
                dmax = max(dmax, max(abs(a - b) for a, b in zip(mine["raw_candidate_logits"], r["raw_candidate_logits"])))
        xr[m] = {"max_abs_letter_logit_delta_vs_archives": float("%.3g" % dmax)}
    res["★跨 run 字母 logits(描述)"] = xr
    # ---- 判决文件(置换闸疑泄漏 ⇒ 任何读者都不出判决; 读者自身不收敛或复跑不过 ⇒ 该读者不出判决)
    docs = {}
    th = pre["★★★判决规则(测量前冻结)"]["数值"]["replaceable_max_d"]
    for rd, r in readers.items():
        an = r["an"]
        if leak or r["nonconverged"] or not (r["within"] or {}).get("pass"):
            an = {"n_items": None, "per_facet": {}, "verdicts": {k: None for k in fl},
                  "overall": "前置不成立(" + ("置换闸: 疑泄漏" if leak else "拟合不收敛或同 run 复跑不过") + ", 不出判决)"}
        else:
            for f in fl:
                an["per_facet"][f]["selected_cfg_hist"] = {str(list(k)): v for k, v in collections.Counter(r["sel"][f]).items()}
                an["per_facet"][f]["inner_cv_top2_margin_min"] = r["margin"].get(f)
                if rd == "P":
                    an["per_facet"][f]["★功效标记"] = "头能学回植入老师" if power[f]["ok"] else ("植入老师功效未确立" if not power[f]["valid"] else "头无分辨力")
        pf = (an.get("per_facet") or {}).get(head)
        hd = None
        if pf:
            dd = {j: pf["pairs"][f"D~{j}"]["d"] for j in ("J1", "J2")}
            hd = {"facet": head, "d": dd, "max_d": max(dd.values()), "threshold": th + 1,
                  "result": "不能判可替代 ⇒ 不是完整替代" if max(dd.values()) >= th + 1 else "头条检查通过(仅说明该面未被排除, 不是判决)"}
        docs[rd] = {"block": "JEV_DISTILL2_READER", "reader": rd, "★前置错误": errs, "★单腿预案": contingency, "★同 run 复跑": r["within"],
                    "max_grad_inf_norm": r["grad"], "nonconverged": r["nonconverged"], **an, "★头条检查": hd, "models": sorted(legs),
                    "prereg_sha256": res["prereg_sha256"], "analysis_script_sha256": res["analysis_script_sha256"],
                    "frozen_rule_sha256": res["frozen_rule_sha256"], "★不得据此说": pre["★★★不得据此说"]}
        out_path(rd).write_text(json.dumps(docs[rd], ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    # ---- 预测核对与决策图(预注册)
    def dR(rd, f, j="J1"):
        return ((docs[rd].get("per_facet") or {}).get(f) or {}).get("pairs", {}).get(f"D~{j}", {}).get("d")
    pr = pre["★预测(先写, 看数据前)"]
    pv = docs["P"]
    preds_ = {
        "Q1_P_d_vs_J1_inside_80pct": {f: bool(dR("P", f) is not None and pr["Q1_区间"][f][0] <= dR("P", f) <= pr["Q1_区间"][f][1]) for f in fl},
        "Q2_P_headline_max_d_ge_5": bool(pv["★头条检查"] and pv["★头条检查"]["max_d"] >= 5),
        "Q3_P_replaceable_any_facet": any(v == "可替代" for v in pv["verdicts"].values()),
        "Q4_P_beats_S1_by_2_on_3_facets": sum(1 for f in fl if None not in (dR("P", f), dR("S1", f)) and dR("S1", f) - dR("P", f) >= 2) >= 3,
        "Q5_S1_within_2_of_round1_XC_on_4_facets": sum(1 for f in fl if dR("S1", f) is not None and abs(dR("S1", f) - pr["Q5_第一轮XC_d_vs_J1"][f]) <= 2) >= 4,
        "Q6_drift_small": all(desc[f]["d(J3,J1)"] <= (3 if f == "资源状态" else 1) for f in fl),
        "Q7_power_valid_ok_on_3": sum(1 for f in fl if power[f]["ok"]) >= 3,
        "Q8_permutation_gate_passes": not leak}
    hv, md = pv["verdicts"].get(head), (pv["★头条检查"] or {}).get("max_d")
    sp = split["P"][head]
    if hv is None:
        outcome = "不出判决(前置不成立)"
    elif hv == "可替代" and power[head]["ok"]:
        outcome = "A: 探索性正面结果 —— 须在新帖上复现"
    elif not power[head]["ok"]:
        outcome = "U: 功效未确立或头学不回植入老师 —— 不可解释, 不据此给下一步建议"
    elif data_limited:
        outcome = "C: 数据受限(学习曲线仍在降) —— 下一步是更多已授权同分布帖子, 不是更多学生工程"
    elif md >= 10:
        outcome = "B: 这两个 4B 模型状态的线性读出复现不了 Jev 的 触发事件 —— 关闭这条学生线"
    elif 5 <= md <= 9:
        outcome = "D: 差一点 —— " + ("放弃型分歧 ≥ 50%: 唯一有理由的第三轮 = 约定 prompt" if sp["abstain_convention"] >= sp["concrete_choice"] else "具体型分歧为主: 约定 prompt 无理由")
    else:
        outcome = "其他(见各面判决)"
    res.update({"readers": {rd: {"overall": d_["overall"], "verdicts": d_["verdicts"], "headline": d_["★头条检查"],
                                 "d": {f: [dR(rd, f, "J1"), dR(rd, f, "J2")] for f in fl}, "nonconverged": d_["nonconverged"]} for rd, d_ in docs.items()},
                "★预测核对": preds_, "★决策图": outcome, "★置换闸通过": not leak})
    SUMMARY.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("readers", "★决策图", "★置换闸通过")}, ensure_ascii=False, indent=1, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
