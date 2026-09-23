# -*- coding: utf-8 -*-
"""真实语料小批试 · 执行器 v2。**会发起真实模型调用。**

★★★ 判据全部来自冻结的 tests/data/real_corpus_pilot_prereg.json, 本文件**不定义任何判据**。
★★★ v1 被零调用对抗评审打回的九条, 与执行器相关的六条在这里逐条设防:
  A 拒绝域**按实际 n_ok 查表**(不再拿 n=42 的门槛套在 n_ok 上), 并有 INSUFFICIENT_DATA 出口
  C 交卷判定 **import 预注册那个唯一的 submitted()**, 不另写
  D 每次调用后**立即落盘** ⇒ 之后任何异常都不会丢掉已花的调用; 计数前强制 str()
  E 产物只存「命中冻结枚举第几项 + sha」, **不存模型自由文本**
  F 硬上限 = 预注册里的 cap(= 实际条数), 且 dry-run 会真的走一次上限分支
  G **第一次调用之前**重验 PROMPT 与判别式的 sha, 不符即停

★ 隐私: 产物里不写一个字的语料原文、模型 span、模型自由文本。
"""
import argparse, hashlib, importlib.util, json, pathlib, re, sys, time

ROOT = pathlib.Path(__file__).resolve().parents[1]
PRE = ROOT / "tests/data/real_corpus_pilot_prereg.json"
OUT = ROOT / "results/real_corpus_pilot.json"
PARTIAL = ROOT / "results/real_corpus_pilot_partial.jsonl"   # ★ D: 逐次落盘


def _gen():
    s = importlib.util.spec_from_file_location("_gen", ROOT / "probes/real_corpus_pilot_prereg.py")
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def _r2():
    s = importlib.util.spec_from_file_location("_r2", ROOT / "probes/extractor_counterexample_run_r2.py")
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def _k(d, frag):
    ks = [x for x in d if frag in x]
    assert len(ks) == 1, "★ 片段 %r 在预注册里命中 %d 个键 —— 有人加了同名键" % (frag, len(ks))
    return d[ks[0]]


def preflight(pre, m):
    """★★★ G: 第一次调用**之前**把所有冻结件重验一遍。不符就停, 一次 HTTP 都不发。"""
    f = _k(pre, "冻结提示词与判别式")
    # ★★★ 评审二轮: v2 hash 的是**源码字面量**(带转义), 不是真发出去的串 —— 两者 sha 不同。
    #     现在 hash m.PROMPT 本身, sha16 = 7a8f9417, 与本仓 r3 记录一致。
    got_p = hashlib.sha256(m.PROMPT.encode()).hexdigest()
    assert got_p == f["PROMPT sha256"], (
        "★★★ 提示词与预注册不符 —— 对照不成立, **未发起任何调用**\n  预注册 %s\n  现算 %s"
        % (f["PROMPT sha256"], got_p))
    got_d = hashlib.sha256(m.DISC.encode()).hexdigest()
    assert got_d == f["判别式 sha256"], (
        "★★★ 判别式与预注册不符 —— **未发起任何调用**")
    assert f["max_retries"] == 1, "★★★ max_retries 必须是 1 —— 0 等于一次 HTTP 都不发"
    assert f["temperature"] == 0.0, "★★★ temperature 必须是 0.0(r2/r3 用的就是它)"
    # 判别式必须仍能在冻结生产件里找到
    tax = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
    knots = tax["knots"] if isinstance(tax, dict) else tax
    assert any(isinstance(x, dict) and x.get("hard_discriminant") == m.DISC for x in knots), (
        "★★★ 判别式在冻结生产件里找不到了 —— **未发起任何调用**")

    # ★★★ P3: 零假设钉在两份具名产物上 —— 底数被换掉是 r5-v2 的死因
    for rel, want in _k(pre, "零假设钉在这两份产物上")["sha256"].items():
        got = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
        assert got == want, (
            "★★★ 底数产物 %s 在预注册之后被改过 ⇒ 零假设不再是冻结的那个 —— **未发起任何调用**" % rel)

    # ★★★ P2: 模型臂也要验 —— 整个对照就是关于它的
    mf = _k(pre, "冻结模型臂")
    sys.path.insert(0, str(ROOT / "scripts"))
    import cce_knot_classify as _CK
    import exp_crossmodel_desire as _XM
    assert _CK.MEASUREMENT_MODEL == mf["MEASUREMENT_MODEL"], (
        "★★★ 测量模型臂变了(%s → %s) ⇒ 与 r2/r3 的对照不成立 —— **未发起任何调用**"
        % (mf["MEASUREMENT_MODEL"], _CK.MEASUREMENT_MODEL))
    cfg = _XM.MODELS[_CK.MEASUREMENT_MODEL]
    for kk, want in (("model", mf["model 字符串"]), ("key_env", mf["key_env"])):
        assert cfg[kk] == want, (
            "★★★ 模型臂配置 %s 变了(%r → %r) —— **未发起任何调用**" % (kk, want, cfg[kk]))
    # ★★★ max_tokens **不与预注册比** —— 它在导入时被别的模块改写, 源码值从不生效。
    #     这里只把**有效值**记下来, 由闸去核「r2 的链与本轮的链给同一个数」。
    return {"有效 max_tokens": cfg["max_tokens"], "源码声明": mf["max_tokens"]}


def load_lines(pre):
    cache, out = {}, []
    for it in _k(pre, "冻结输入集")["items"]:
        f = it["file"]
        if f not in cache:
            cache[f] = (ROOT / f).read_text(encoding="utf-8").split("\n")
        line = cache[f][it["line_index"]]
        assert hashlib.sha256(line.encode()).hexdigest() == it["sha256"], (
            "★★★ 语料在预注册之后被改过: %s:%d —— **未发起任何调用**" % (f, it["line_index"]))
        out.append((it, line))
    return out


def classify_kind(raw_kind, enum):
    """★★★ E: 只回「命中哪几项 / OTHER」+ sha。**绝不把模型文本带回产物**。

    ★ 记**全部**命中而不是第一个: 提示词虽写了「只写其中一种」, 但模型不守是常态
      (r2 实测过它多给证据)。只取第一个会把「数据和使用细节」悄悄记成「数据」。
    """
    s = raw_kind if isinstance(raw_kind, str) else json.dumps(raw_kind, ensure_ascii=False)
    idx = [i for i, e in enumerate(enum) if e in s]
    return {"枚举序号": idx,
            "命中": [enum[i] for i in idx] if idx else ["OTHER"],
            "★多重命中": len(idx) > 1,
            "模型原文 sha16": hashlib.sha256(s.encode()).hexdigest()[:16],
            "模型原文字数": len(s)}


def build_result(pre, rows, n_exec, elapsed, model, env=None):
    """★ 计算与产物构造全在这里 —— 闸现算整份逐键比对。"""
    from math import comb
    g = _gen()

    def cp(k, n, alpha=0.05):
        def F(p): return sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))
        def G(p): return sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(0, k + 1))
        def bis(f, t):
            lo, hi = 0.0, 1.0
            for _ in range(100):
                mid = (lo + hi) / 2
                if f(mid) < t: lo = mid
                else: hi = mid
            return (lo + hi) / 2
        return (0.0 if k == 0 else bis(F, alpha / 2)), (1.0 if k == n else bis(lambda p: -G(p), -alpha / 2))

    J = _k(pre, "主判据(投料前定死)")
    base = _k(J, "底数用模板级")
    K2, N2 = base["k_unit(= 平均率 × 单元数)"], base["单元数"]
    table = _k(J, "拒绝域按实际 n_ok 查表")
    power_by_n = _k(J, "功效也按实际 n_ok 查表")
    min_n = _k(J, "最低可判 n_ok")

    ok = [r for r in rows if r["调用成功"]]
    n_ok = len(ok)
    k = sum(1 for r in ok if r["交卷"] is True)
    pw_row = power_by_n.get(str(n_ok)) or {}

    # ★★★ A: 按**实际 n_ok** 查表, 不用 n=42 的门槛
    reg = table.get(str(n_ok))
    if n_ok < min_n or reg is None:
        verdict = "INSUFFICIENT_DATA"
        in_reject = None
    else:
        lo_k, hi_k = reg["k ≤"], reg["k ≥"]
        # ★★★ (a) 的修法: 两侧尾部**含义相反**, 不许印同一个词。
        #     k 低 = 真实语料更难交卷(外推**高估**了); k 高 = 更容易交卷(外推**低估**了)。
        if k <= lo_k:
            verdict, in_reject = "TRANSFERS_NOT_LOWER", True
        elif hi_k is not None and k >= hi_k:
            verdict, in_reject = "TRANSFERS_NOT_HIGHER", True
        else:
            verdict, in_reject = "CANNOT_DISTINGUISH", False

    lo, hi = cp(k, n_ok) if n_ok else (0.0, 1.0)
    p = g.fisher_p(k, n_ok - k, K2, N2 - K2) if n_ok else None
    F2 = 2 / 15

    # ★ H 的描述性辅助: 按长度三分位看交卷率(不参与判决)
    by_len = {}
    if ok:
        srt = sorted(ok, key=lambda r: r["n_chars"])
        t = max(1, len(srt) // 3)
        for name, chunk in (("短(下三分位)", srt[:t]), ("中", srt[t:2 * t]), ("长(上三分位)", srt[2 * t:])):
            if chunk:
                by_len[name] = "%d/%d · 字符中位 %d" % (
                    sum(1 for r in chunk if r["交卷"] is True), len(chunk),
                    sorted(r["n_chars"] for r in chunk)[len(chunk) // 2])

    return {
        "block": "REAL_CORPUS_PILOT_RESULT",
        "version": 2,
        "date": "2026-09-17",
        "prereg": str(PRE.relative_to(ROOT)),
        "prereg_sha256": hashlib.sha256(PRE.read_bytes()).hexdigest(),
        "model": model,
        "★实际执行数": n_exec,
        "★硬上限": _k(pre, "冻结输入集")["硬上限"],
        "★重试": "max_retries=1(**不是 0**)",
        "★★★ 运行时环境(有效值, 非源码值)": env,
        "调用或格式失败": n_exec - n_ok,
        "★★★ 失败构成(非随机缺失的检查)": _err_tally(rows),
        "★★★ 为什么要看构成": "SENSITIVE_BLOCKED 是 MiniMax 的内容风控, 它**与文本内容相关** ⇒ "
            "被它拦掉的不是随机样本。若它占比高, n_ok 就是**有偏**的子集, "
            "交卷率读数要按「在未被风控拦下的段落中」来限定。手构模板从未触发过它(r2/r3 共 32 次, 0 次风控)。",

        "★★★ 主读数: 真实语料交卷率": {
            "交卷/有效": "%d/%d" % (k, n_ok),
            "率": round(k / n_ok, 4) if n_ok else None,
            "CP95": [round(lo, 4), round(hi, 4)],
            "手构模板级底数": "%d/%d = %.4f" % (K2, N2, K2 / N2),
            "Fisher 两侧 p": round(p, 6) if p is not None else None,
            "★实际 n_ok 对应的拒绝域(查表, 非现场推导)": reg,
            "★最低可判 n_ok": min_n,
            "★★★判决": verdict,
        },
        "★★★ 判决怎么读": (
            {"INSUFFICIENT_DATA":
                "有效调用只有 %d 次, 低于事前定的最低 %s ⇒ **什么都没测到**。"
                "★ v1 会在这里把它判成 TRANSFERS_NOT。" % (n_ok, min_n),
             "TRANSFERS_NOT_LOWER":
                "真实语料的交卷率**显著更低** ⇒ 手构模板上的外推在**因子一**上**高估**了产出。"
                "★★★ **不得就此说「比 ~570 次更贵」** —— 那是**总代价**断言, 需要因子二, "
                "而因子二本轮**没测**(同一份产物下面就写着鉴别格算不了)。能说的只有因子一。"
                "★★★ **不得读成「因为是真实语料」** —— 长度中位数差 3 倍、结构与话题同时变了, "
                "**机制未识别**(见预注册的已知混淆)。",
             "TRANSFERS_NOT_HIGHER":
                "真实语料的交卷率**显著更高** ⇒ 手构模板上的外推**低估**了产出 ⇒ "
                "因子一比预想的好, 但**因子二仍未测**, 所以总代价仍未定。"
                "★★★ 同样**不得读成「因为是真实语料」** —— 混淆未消除, 机制未识别。",
             "CANNOT_DISTINGUISH":
                "**这批数据分不出**, **不等于两者相同**。"
                "★ 在**本次实际的 n_ok=%d** 上, 功效 q=0.05 时 %s、q=0.10 时 %s "
                "⇒ 分不出**大概率只是样本小**。"
                "★★★ 这两个数取自预注册里**按 n_ok 冻结的功效表**那一行, "
                "不是 n_ok=42 的数(v2 曾把 42 的功效硬编码进任何 n_ok 的读法里)。"
                % (n_ok, pw_row.get("q=0.0500"), pw_row.get("q=0.1000"))}[verdict]),

        "★★★ 导出的代价下界": {"★不适用": "判决是 INSUFFICIENT_DATA ⇒ 交卷率没测到, "
                                         "任何由它导出的界都**不成立**, 这里不给数。"} if verdict == "INSUFFICIENT_DATA" else {
            "代价下界(只用**交卷率**的 CP95 上界, 不借任何别的数)":
                ("鉴别格 ≤ 交卷 ⇒ 买 24 格**至少**需 %.0f 次" % (24 / hi)) if hi > 0 else "∞",
            "借手构因子二的**点算**(**不是下界**)":
                ("24/(%.4f × %.4f) ≈ %.0f 次 —— 借了手构的 2/15, "
                 "而**因子二自己的 CI 从未传播进来** ⇒ 这只是一个点算, **不是下界**。" % (hi, F2, 24 / (hi * F2)))
                if hi > 0 else "∞",
            "★为什么只给下界": "n=%d 上产出率不可测(预注册事前声明), 只有上界是可信的。" % n_ok,
        },

        "★★★ 鉴别格: 本轮**没有算, 也算不了**": {
            "★为什么": "真实语料没有金标, 而 RESTATES_IDENTIFIER 的定义含「声称这是增量」"
                       "(A 支属性) ⇒ 人标不出来。**这一项在预注册里就声明过测不了**, 这里如实为空。",
            "鉴别格计数": None,
            "★退而能给的": "交卷率是它的上界 ⇒ 只有**代价下界**, 没有产出率。",
        },
        "★★★ 描述性: 模型自填 increment_kind 命中冻结枚举的分布(不参与任何判决)": {
            "分布": _kind_tally(ok),
            "★这不是鉴别格": "kind 是模型**自填**的, 不是人标的金标 ⇒ 它不能用来数鉴别格。",
            "★产物里没有模型文本": "只存枚举序号与 sha16。",
        },

        "★★★ 描述性: 按长度三分位的交卷率(不参与判决)": by_len,
        "★★★ 怎么读这三个数": "若长度是主因, 三分位间应有梯度。**它不参与判决**, "
                              "n 也太小, 只作为下一轮的线索。",

        "★★★ 本轮不回答什么": [
            "**不回答**「花 ~570 次值不值」—— 那需要因子二, 本轮测不了(预注册事前声明)。",
            "**不回答**语料整体交卷率 —— 本轮只跑含品牌子总体, 那是**上界**, 且上界有多松没测。",
            "**不回答**为什么不迁移 —— 长度混淆未消除, **机制未识别**。",
            "**不得**与 r4 历史读数直接比(r3 实测同一仪器重测一致率仅 60%)。",
        ],
        "★隐私": "产物里只有指针与结构化事实, **无一字语料原文、无一字模型 span、无一字模型自由文本**。",
        "耗时秒": round(elapsed, 1),
        "rows": rows,
    }


def _err_tally(rows):
    t = {}
    for r in rows:
        if not r["调用成功"]:
            t[r["err_类型"]] = t.get(r["err_类型"], 0) + 1
    return dict(sorted(t.items()))


def _kind_tally(ok):
    t, multi = {}, 0
    for r in ok:
        for kd in r.get("kinds") or []:
            multi += 1 if kd.get("★多重命中") else 0
            for h in (kd.get("命中") or ["OTHER"]):
                key = str(h)                   # ★ D: 强制 str, 绝不拿模型给的东西当键
                t[key] = t.get(key, 0) + 1
    return {"逐项(多重命中会重复计入)": dict(sorted(t.items())), "多重命中的证据条数": multi}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="dry-run 用: 只跑前 N 条以走一次上限分支")
    args = ap.parse_args(argv)

    g, m = _gen(), _r2()
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    assert pre["★★★status"].startswith("**READY**"), "★ 预注册未就绪"
    envinfo = preflight(pre, m)                          # ★ G: 调用前重验
    pairs = load_lines(pre)
    frozen_cap = _k(pre, "冻结输入集")["硬上限"]
    # ★★★ 评审二轮: --limit 原本在真跑时也生效 ⇒ 可静默覆盖冻结上限, 而产物照印 42。
    assert args.limit is None or args.dry_run, "★★★ --limit 只许配 --dry-run 使用"
    cap = args.limit if (args.limit is not None and args.dry_run) else frozen_cap
    enum = _k(pre, "increment_kind 枚举")["枚举"]

    if args.dry_run:
        model_name = "DRY_RUN"
        def call(_mdl, _p, temperature=0.0, max_retries=1):
            assert max_retries == 1
            return ('{"supported": true, "evidence": [{"span":"x","supports":"A",'
                    '"increment_kind":["具体型号"]}], "why_not": null}'), {}
    else:
        m._load_key()
        sys.path.insert(0, str(ROOT / "scripts"))
        from exp_crossmodel_desire import call_model as call
        import cce_knot_classify as CK
        model_name = CK.MEASUREMENT_MODEL
        # ★★★ 评审二轮: 原来这里 unlink() —— 那会销毁**上一轮已花调用的唯一记录**,
        #     而且上限是按进程计的 ⇒ 重跑一次就又花 42 次。改成**续跑**: 读已有行, 跳过已做的。

    done = {}
    if not args.dry_run and PARTIAL.exists():
        for ln in PARTIAL.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                r = json.loads(ln)
                done[r["ptr"]] = r
        print("★ 续跑: 已有 %d 行, 跳过它们(上限按**累计**算, 不是按进程)" % len(done))

    rows, n, t0 = list(done.values()), len(done), time.time()
    for it, line in pairs:
        ptr = "%s:%d" % (it["file"], it["line_index"])
        if ptr in done:
            continue
        if n >= cap:
            print("★★★ 撞硬上限 %d —— 停" % cap)
            break
        n += 1
        raw, meta = call(model_name, m.PROMPT % (m.DISC, line), temperature=0.0, max_retries=1)
        err = (meta or {}).get("error")
        obj = m._parse(raw) if raw and raw.strip() else None
        base = {"ptr": ptr, "sha256": it["sha256"], "n_chars": it["n_chars"]}
        if err or obj is None:
            # ★ 隐私: call_model 的 last_err 里夹着上游响应体 r.text[:300] ⇒ **只留类型, 不留正文**
            # ★★★ 风控拦截要单独记: 真人语料触发内容审查的概率远高于手写模板, 而那种丢失
            #     **与内容相关、不是随机的** ⇒ 会系统性偏掉 n_ok。它本身就是一个读数。
            if (meta or {}).get("sensitive"):
                et = "SENSITIVE_BLOCKED"
            elif err:
                et = "CALL_ERROR"
            else:
                et = "UNPARSEABLE"
            row = dict(base, **{"调用成功": False, "交卷": None, "err_类型": et,
                                "finish_reason": (meta or {}).get("finish_reason")})
        else:
            ev = obj.get("evidence") or []
            ev = ev if isinstance(ev, list) else []
            row = dict(base, **{
                "调用成功": True,
                "交卷": g.submitted(obj),                 # ★ C: 唯一的定义
                "n_evidence": len(ev),
                "A_支": sum(1 for e in ev if isinstance(e, dict) and e.get("supports") == "A"),
                "B_支": sum(1 for e in ev if isinstance(e, dict) and e.get("supports") == "B"),
                "kinds": [classify_kind(e.get("increment_kind"), enum) for e in ev
                          if isinstance(e, dict) and e.get("supports") == "A"
                          and e.get("increment_kind") is not None],
                "span_逐字": [bool(isinstance(e, dict) and isinstance(e.get("span"), str)
                                   and e["span"] in line) for e in ev],
                "why_not_字数": len(obj.get("why_not") or "") if isinstance(obj.get("why_not"), str) else 0,
                "finish_reason": (meta or {}).get("finish_reason"),
            })
        rows.append(row)
        if not args.dry_run:                              # ★★★ D: 立即落盘
            with PARTIAL.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print("  %-52s 交卷=%-5s" % (row["ptr"], row.get("交卷")))

    res = build_result(pre, rows, n, time.time() - t0, model_name, envinfo)
    R = res["★★★ 主读数: 真实语料交卷率"]
    if args.dry_run:
        print("\n[dry-run] main() 真跑完(n=%d), 未写盘。判决 = %s" % (n, R["★★★判决"]))
        return 0
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n交卷 %s · 率 %s · CP95 %s" % (R["交卷/有效"], R["率"], R["CP95"]))
    print("拒绝域(n_ok=%s) %r · Fisher p = %s" % (R["交卷/有效"].split("/")[1],
                                                 R["★实际 n_ok 对应的拒绝域(查表, 非现场推导)"],
                                                 R["Fisher 两侧 p"]))
    print("判决 %s" % R["★★★判决"])
    print("→", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
