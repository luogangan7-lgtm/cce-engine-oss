# -*- coding: utf-8 -*-
"""真实语料小批试**结果**的闸。

★★★ 灵敏度: 闸调 build_result() **现算整份产物**再逐键比对 ——
    改了执行器的计算却不重跑, 必须见红。(2026-09-15 的「断言太弱」根本修法)
★★★ 判决必须来自**预注册冻结的拒绝域**, 不是现场重新推导。
★ 隐私: 产物里不许有一个字语料原文, 也不许有模型回填的 span 原文。
"""
import hashlib, importlib.util, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
R = ROOT / "results/real_corpus_pilot.json"
PRE = ROOT / "tests/data/real_corpus_pilot_prereg.json"
RUN = ROOT / "probes/real_corpus_pilot_run.py"


def _res():
    return json.loads(R.read_text(encoding="utf-8")) if R.exists() else None


def _run_mod():
    s = importlib.util.spec_from_file_location("_pilot", RUN)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def test_整份产物必须与build_result现算逐键一致():
    """★★★ 这是灵敏度的主闸: 改了计算不重跑 ⇒ 红。"""
    res = _res()
    if not res:
        return
    m = _run_mod()
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    # ★ env 从产物里取回传 —— 它由 test_max_tokens_两条链必须给同一个值 单独现算核过,
    #   不在这条「整份逐键一致」里重复核(否则这条就变成在核环境而不是核计算)。
    env = [res[x] for x in res if "运行时环境" in x][0]
    got = m.build_result(pre, res["rows"], res["★实际执行数"], res["耗时秒"], res["model"], env)
    for k in got:
        if k in ("耗时秒",):
            continue
        assert got[k] == res[k], (
            "★★★ %s 与 build_result 现算不符 —— 改了执行器却没重跑?\n  档案 %r\n  现算 %r"
            % (k, res[k], got[k]))


def test_判决必须取自预注册的拒绝域_不许现场推导():
    res = _res()
    if not res:
        return
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    J = [pre[x] for x in pre if "主判据(投料前定死)" in x][0]
    table = [v for kk, v in J.items() if "拒绝域按实际 n_ok 查表" in kk][0]
    min_n = [v for kk, v in J.items() if "最低可判 n_ok" in kk][0]
    Rd = res["★★★ 主读数: 真实语料交卷率"]
    k, n_ok = (int(x) for x in Rd["交卷/有效"].split("/"))
    reg = table.get(str(n_ok))
    assert Rd["★实际 n_ok 对应的拒绝域(查表, 非现场推导)"] == reg, (
        "★★★ 结果里的拒绝域不是**按实际 n_ok 查表**得到的 ⇒ 事后改了判据")
    if n_ok < min_n or reg is None:
        want = "INSUFFICIENT_DATA"
    else:
        if k <= reg["k ≤"]:
            want = "TRANSFERS_NOT_LOWER"
        elif reg["k ≥"] is not None and k >= reg["k ≥"]:
            want = "TRANSFERS_NOT_HIGHER"
        else:
            want = "CANNOT_DISTINGUISH"
    assert Rd["★★★判决"] == want, "★ 判决与查表不符: k=%d n_ok=%d 应判 %s" % (k, n_ok, want)


def test_预注册必须逐字节未被改过():
    """★★★ 预注册的生成器是可重跑的脚本 ⇒ 看过结果再重出一版就能换掉判据。
    结果里钉了它的完整 sha256, 这里现算比对。"""
    res = _res()
    if not res:
        return
    assert res["prereg_sha256"] == hashlib.sha256(PRE.read_bytes()).hexdigest(), (
        "★★★ 预注册在投料后被改过 —— 判决作废")


def test_不许有一个字语料原文或模型span():
    res = _res()
    if not res:
        return
    blob = json.dumps(res, ensure_ascii=False)
    for rel in ("corpus/reddit_hearingaids_audience_v2.txt", "corpus/reddit_hearingaids_utterances.txt"):
        for line in (ROOT / rel).read_text(encoding="utf-8").split("\n"):
            if len(line.strip()) >= 25:
                assert line.strip()[:25] not in blob, "★★★ 结果里出现语料原文: %r" % line.strip()[:25]
    for r in res["rows"]:
        for k2, v in r.items():
            assert not (isinstance(v, str) and len(v) > 70 and k2 != "sha256"), (
                "★ 行里有超长字符串, 可能夹带原文: %s=%r" % (k2, v[:60]))
        for kd in r.get("kinds") or []:
            assert set(kd) == {"枚举序号", "命中", "★多重命中", "模型原文 sha16", "模型原文字数"}, (
                "★★★ kinds 的形状变了, 可能把模型文本带回来了: %r" % kd)
            for h in kd["命中"]:
                assert h == "OTHER" or len(h) <= 8, "★ 命中项过长, 可能是模型原文: %r" % h
            assert kd["★多重命中"] == (len(kd["枚举序号"]) > 1), "★ 多重命中标记与序号不一致"
        assert "err" not in r, "★★★ err 正文可能夹带上游响应体, 只许存 err_类型"
    assert "无一字模型自由文本" in res["★隐私"] and "无一字语料原文" in res["★隐私"]


def test_每行必须对得上预注册的输入集指针():
    res = _res()
    if not res:
        return
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    want = {"%s:%d" % (i["file"], i["line_index"]): i["sha256"] for i in pre["★★★ 冻结输入集"]["items"]}
    for r in res["rows"]:
        assert r["ptr"] in want, "★ 出现了预注册之外的输入: %s" % r["ptr"]
        assert r["sha256"] == want[r["ptr"]], "★ %s 的 sha 与预注册不符" % r["ptr"]
    assert len(res["rows"]) == res["★实际执行数"] <= res["★硬上限"]


def test_重试必须是1不是0():
    res = _res()
    if not res:
        return
    assert "max_retries=1" in res["★重试"] and "不是 0" in res["★重试"]
    src = RUN.read_text(encoding="utf-8")
    assert "max_retries=0" not in src, "★★★ 源码里出现 max_retries=0 —— 那等于一次 HTTP 都不发"


def test_判决怎么读必须写明CANNOT_DISTINGUISH不等于相同():
    res = _res()
    if not res:
        return
    v = res["★★★ 判决怎么读"]
    vd = res["★★★ 主读数: 真实语料交卷率"]["★★★判决"]
    if vd == "CANNOT_DISTINGUISH":
        assert "不等于两者相同" in v, "★★★ 分不出被读成了「一样」—— 这是本仓反复犯的那个错"
        # ★★★ 不查硬编码的 0.384 —— 那是 n_ok=42 的功效, 印在任何 n_ok 上都是错的。
        #     改查: 文案里的功效**必须等于冻结表里该 n_ok 那一行**。
        pre = json.loads(PRE.read_text(encoding="utf-8"))
        J = [pre[x] for x in pre if "主判据" in x][0]
        pw = [J[x] for x in J if "功效也按实际 n_ok" in x][0]
        n_ok = int(res["★★★ 主读数: 真实语料交卷率"]["交卷/有效"].split("/")[1])
        row = pw[str(n_ok)]
        for q in ("q=0.0500", "q=0.1000"):
            assert str(row[q]) in v, (
                "★★★ 读法里的功效不是 n_ok=%d 那一行的(%s 应为 %s): %r"
                % (n_ok, q, row[q], v[:200]))
    if vd.startswith("TRANSFERS_NOT"):
        assert "机制未识别" in v, "★★★ 必须限制读法: 长度混淆未消除"
        assert ("高估" in v) or ("低估" in v), "★★★ 必须说明是哪一侧尾部(含义相反)"


def test_代价必须只给下界_且两条区分开():
    res = _res()
    if not res:
        return
    c = res["★★★ 导出的代价下界"]
    if list(c) == ["★不适用"]:
        assert "不成立" in c["★不适用"], "★ 不适用时必须说明为什么"
        return                      # ★ INSUFFICIENT_DATA 分支不给数, 正确
    pure = [v for k in c for v in [c[k]] if "只用**交卷率**" in k][0]
    borrowed = [v for k in c for v in [c[k]] if "借手构" in k][0]
    assert "至少" in pure
    assert "交卷率" in [k for k in c if "只用**交卷率**" in k][0], (
        "★★★ 标签必须写明是哪个量的上界 —— v1 两处用同一标签指两个不同的量")
    assert "0.1333" in borrowed, "★ 借数的那条必须把借的数写出来"
    assert "不是下界" in borrowed and "CI 从未传播" in borrowed, (
        "★★★ 借因子二那条必须标明它**不是界** —— 因子二自己的 CI 没传播进来")
    assert "不可测" in [c[k] for k in c if "为什么只给下界" in k][0]


def test_max_tokens_两条链必须给同一个值():
    """★★★ MODELS[M3].max_tokens 在**导入时**被 exp_v4_* 改写(12000→8000)
    ⇒ 有效值取决于导入图。r2 的链与本轮的链必须给同一个数, 否则两样本不可比。"""
    import subprocess, sys
    def eff(extra):
        code = ("import sys; sys.path.insert(0,'scripts')\n" + extra +
                "\nimport exp_crossmodel_desire as X; print(X.MODELS['M3']['max_tokens'])")
        return subprocess.run([sys.executable, "-c", code], capture_output=True,
                              text=True, cwd=str(ROOT)).stdout.strip()
    r2_chain = eff("import importlib.util as I;"
                   "s=I.spec_from_file_location('_r2','probes/extractor_counterexample_run_r2.py');"
                   "m=I.module_from_spec(s);s.loader.exec_module(m);"
                   "from exp_crossmodel_desire import call_model; import cce_knot_classify")
    ours = eff("from exp_crossmodel_desire import call_model; import cce_knot_classify")
    assert r2_chain == ours != "", (
        "★★★ r2 的链给 %r, 本轮的链给 %r —— 两样本跑在不同 max_tokens 上, **不可比**"
        % (r2_chain, ours))
    res = _res()
    if res:
        env = [res[x] for x in res if "运行时环境" in x][0]
        assert str(env["有效 max_tokens"]) == ours, (
            "★ 产物记的有效 max_tokens %r 与现算 %r 不符" % (env["有效 max_tokens"], ours))


def test_产物的行必须对得上分片文件():
    """★★★ rows 是**无人核对的可信输入** —— 改一行 rows 就能改判决, 而没有任何闸读过分片。
    分片是逐次落盘的, 它是「真的发生过什么」的唯一独立记录。"""
    res = _res()
    if not res:
        return
    P = ROOT / "results/real_corpus_pilot_partial.jsonl"
    # ★ 合成产物(烟测/干跑)没有自己的分片 —— 这一跳必须在存在性检查**之前**,
    #   否则真分片一旦存在, 烟测就会拿合成行去和真分片比对而误红。
    #   (2026-09-17 投料后由烟测自己暴露; 该修法不触碰任何判决数。)
    if res["model"] in ("SMOKE", "DRY_RUN"):
        return
    assert P.exists(), "★★★ 真跑的产物却没有分片文件 %s —— 逐次落盘没生效" % P
    part = {}
    for ln in P.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            r = json.loads(ln)
            part[r["ptr"]] = r
    for r in res["rows"]:
        assert r["ptr"] in part, "★★★ 产物里有分片里没有的行: %s" % r["ptr"]
        assert part[r["ptr"]] == r, (
            "★★★ 产物的行与分片不符 —— rows 被改过: %s\n  分片 %r\n  产物 %r"
            % (r["ptr"], part[r["ptr"]], r))
    assert len(res["rows"]) == len(part), (
        "★ 分片 %d 行 vs 产物 %d 行" % (len(part), len(res["rows"])))


def test_失败构成必须分出风控拦截():
    """★★★ SENSITIVE_BLOCKED 与内容相关 ⇒ 被它拦掉的不是随机样本。
    本轮是第一次把真人语料发出去, 这个风险只在本轮存在。"""
    res = _res()
    if not res:
        return
    t = [res[x] for x in res if "失败构成" in x][0]
    tot = sum(t.values())
    assert tot == res["调用或格式失败"], "★ 失败构成加总与失败数不符: %d vs %d" % (tot, res["调用或格式失败"])
    why = [res[x] for x in res if "为什么要看构成" in x][0]
    assert "不是随机样本" in why and "有偏" in why, "★★★ 必须写明非随机缺失的后果"
    assert "0 次风控" in why, "★ 必须给出手构那边的对照(32 次 0 次风控)"
    src = RUN.read_text(encoding="utf-8")
    assert 'SENSITIVE_BLOCKED' in src and '.get("sensitive")' in src, (
        "★★★ 执行器没有单独识别风控拦截")


def test_鉴别格必须如实留空():
    res = _res()
    if not res:
        return
    v = [res[x] for x in res if "鉴别格: 本轮" in x][0]
    assert v["鉴别格计数"] is None, "★★★ 鉴别格算不了, 不许糊一个数上去"
    assert "人标不出来" in v["★为什么"]


def test_本轮不回答什么必须逐条列出():
    res = _res()
    if not res:
        return
    v = " ".join(res["★★★ 本轮不回答什么"])
    for w in ("570", "整体交卷率", "上界", "r4", "60%", "机制未识别"):
        assert w in v, "★ 「不回答什么」里缺 %r" % w


def test_零调用件与投料件必须分开():
    """★ 预注册生成器不许发调用; 执行器才发。"""
    # ★★★ 不用 grep —— 生成器的**注释里**正当地提到 call_model(在讲 max_retries 那个坑)。
    #     grep 会把「提到」判成「调用」。查 AST 里真实的调用与导入。
    import ast
    tree = ast.parse((ROOT / "probes/real_corpus_pilot_prereg.py").read_text(encoding="utf-8"))
    BAD_CALL = {"call_model", "urlopen", "_load_key", "post", "request", "urlretrieve"}
    BAD_MOD = {"requests", "http", "urllib", "socket", "exp_crossmodel_desire", "httpx"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            nm = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
            assert nm not in BAD_CALL, "★★★ 预注册生成器里**真的调用**了 %r —— 它必须零调用" % nm
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                    else [node.module or ""])
            for mod in mods:
                assert mod.split(".")[0] not in BAD_MOD, (
                    "★★★ 预注册生成器导入了联网模块 %r" % mod)
    run = RUN.read_text(encoding="utf-8")
    assert "--dry-run" in run and "DRY_RUN" in run, "★ 执行器必须有可被闸真跑的 dry-run 通路"


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("结果闸 %d 项全过(产物尚未生成时为空过, 跑完再验)" % n)
