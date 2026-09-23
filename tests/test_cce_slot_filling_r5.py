# -*- coding: utf-8 -*-
"""r5 预注册与执行器的闸。**本轮尚未投料**, 这些闸守的是「发起前该具备什么」。

★★★ 第一条守的是: **分叉执行器没有把旧闸架空**。
  「分叉执行器后旧闸只守旧文件」是本项目第四次「假保证」。
"""
import difflib, hashlib, importlib.util, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "probes"))
PRE = ROOT / "tests/data/slot_filling_prereg_r5.json"
EXE = ROOT / "probes/slot_filling_run_r5.py"
R4 = ROOT / "probes/slot_filling_run_r4.py"
R4_SHA16 = "832b185e53cad3f6"


def _p():
    return json.loads(PRE.read_text(encoding="utf-8"))


def _m():
    spec = importlib.util.spec_from_file_location("r5exe", EXE)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ───────── 分叉没有架空旧闸 ─────────

def test_r4执行器逐字节未变():
    """★★★ r5 另起一份是对的(改 r4 会让 20 次已付费的读数失去对应物), 但必须同时证明 r4 没被顺手改。"""
    got = hashlib.sha256(R4.read_bytes()).hexdigest()[:16]
    assert got == R4_SHA16, (
        "★★★ r4 执行器变了(%s ≠ %s) —— 它是 20 次已付费调用的读数对应物, 改它等于让那些读数失去对应。"
        % (got, R4_SHA16))


def test_r5的LEGAL从判据层派生_不许手写():
    import cce_claim_frame as CF
    m = _m()
    assert set(CF.PREDICATE_NEG) <= m.LEGAL["predicate"], (
        "★★★ r5 的 LEGAL 缺判据层的否定取值 %r —— **模型填对反而会被判成非法、静默剔出分母**"
        % sorted(set(CF.PREDICATE_NEG) - m.LEGAL["predicate"]))
    src = EXE.read_text(encoding="utf-8")
    assert "PREDICATE_NEG" in src, "★ LEGAL 必须**现算派生**, 不许把取值抄成字面量"


# ───────── 处理物必须被约束 ─────────

def test_两臂提示词哈希与预注册一致_现算():
    assert _m().prompt_sha() == _p()["★★★两臂提示词哈希(测量前冻结)"], (
        "★★★ 提示词与预注册钉的哈希不符 —— 「唯一差异是判据文字」就没有被约束的对象了")


def test_两臂唯一差异是判据文字_diff现算():
    m = _m()
    a = m._STEM % ("", "", "", "", "", m.CRITERION_A)
    b = m._STEM % ("", "", "", "", "", m.CRITERION_B)
    d = [l for l in difflib.unified_diff(a.split("\n"), b.split("\n"), lineterm="")
         if l[:1] in "+-" and not l.startswith(("+++", "---"))]
    assert d, "★ 两臂完全相同 ⇒ 次判据恒为 0"
    assert all(l.startswith("+") for l in d), (
        "★★★ B 臂**删掉或改写**了 A 臂的内容: %r —— 那就不只是「加了判据文字」" % [l for l in d if l.startswith("-")])
    assert any("公开标识" in l for l in d), "★ 新增的那几行里没有附件 A 的条款"


def test_B臂不许含附件A原文里那句与ANX同构的例():
    """★★★ 附件 A 破折号后的例(「复述型号名不产生增量」)与本轮 ANX-3 同构 ⇒ 给了就是开卷。"""
    b = _m().CRITERION_B
    assert "复述型号名不产生增量" not in b, "★★★ B 臂把与 ANX-3 同构的已解范例抄进去了 = 把答案写在卷子上"
    assert "风噪" not in b, "★ 附件 A 的另一半例句也不许进"
    assert "刻意**不给例句**" in EXE.read_text(encoding="utf-8"), "★ 源码里必须写明为什么不给例"


# ───────── 金标与信号量 ─────────

def test_两个金标都被哈希钉死():
    p = _p()["★★★金标哈希(测量前冻结)"]
    g = hashlib.sha256((ROOT / "tests/data/claim_frame_annotations.json").read_bytes()).hexdigest()[:8]
    assert p["tests/data/claim_frame_annotations.json"] == g, "★★★ 冻结金标变了"
    d = json.loads((ROOT / "tests/data/semantic_minimal_pairs.json").read_text(encoding="utf-8"))
    c = hashlib.sha256(json.dumps(d["contract_pairs"], ensure_ascii=False,
                                  sort_keys=True).encode()).hexdigest()[:16]
    assert p["tests/data/semantic_minimal_pairs.json::contract_pairs"] == c, (
        "★★★ ANX 金标变了 —— 它承载本轮**全部**主判据信号")


def test_三个冻结数必须与现搜结果对账():
    """★★★ 评审 MAJOR: 门 14 / p0 / 净增益阈值 是预注册里**手打的常数**,
    而 19 道闸对它们只做源码字符串存在性检查。⇒ 这里逐个与**现搜**对账。
    ★ 另: 本条之前的版本里 `p0 = 2 / 6` **一直硬编码着**(替换锚点没匹配, 我没发现),
      于是「把门改小到 5」这种变异**抓不到** —— 那正是「闸只查字符串不查数」的实例。
    """
    m = _m()
    FZ = _p()["★★★主判据(测量前冻结_confirmatory)"]
    n_fz, p0, gate, base_net = (FZ["★冻结的 n"], FZ["★冻结的 p0"],
                                FZ["★冻结的门"], FZ["★冻结的最佳浅层规则净增益"])
    # ① 鉴别格数现算
    import cce_claim_frame as CF
    D = json.loads((ROOT / "tests/data/claim_frame_annotations.json").read_text(encoding="utf-8"))["★默认槽位"]
    n = sum(1 for it in m.items() if dict(D, **it["gold"]["A"]).get("predicate") == m.TARGET)
    assert n == n_fz, "★★★ 鉴别格现算 %d ≠ 冻结 %d" % (n, n_fz)
    assert n >= 20, "★★★ n=%d 太小 —— n=6 时即使 p0 压到 3/6 门也是满分零余量" % n
    # ② p0 与净增益阈值必须等于**现搜**的结果
    spec = importlib.util.spec_from_file_location("bs", ROOT / "probes/best_shallow_rule_search.py")
    BS = importlib.util.module_from_spec(spec); spec.loader.exec_module(BS)
    rows = BS.cells()
    disc = [x for _, x, g in rows if g == m.TARGET]
    bulk = [x for _, x, g in rows if g == "OF_DECLARED_KIND"]
    fam = max(((sum(1 for x in disc if fn(x)) - sum(1 for x in bulk if fn(x)),
                sum(1 for x in disc if fn(x))) for _d, fn in BS._rules() if any(fn(x) for x in disc)))
    tok, _, _ = BS.search(rows, m.TARGET)
    hit = max(fam[1], int(tok[0]["命中鉴别格"].split("/")[0]))
    assert abs(p0 - hit / n) < 1e-6, (
        "★★★ 冻结的 p0=%.4f ≠ 现搜最高命中率 %d/%d=%.4f —— 手打的常数过期了" % (p0, hit, n, hit / n))
    assert base_net == fam[0], (
        "★★★ 冻结的净增益阈值 %+d ≠ 现搜冻结族最佳 %+d" % (base_net, fam[0]))
    # ③ 门必须显著、且有余量
    pv = m._binom_ge(gate, n, p0)
    assert pv < 0.05, "★★★ 冻结的门 ≥%d/%d 在 p0=%.3f 下 p=%.4f **不显著**" % (gate, n, p0, pv)
    assert m._binom_ge(gate - 1, n, p0) >= 0.05, (
        "★★★ 门 ≥%d 比必要的更严(≥%d 就已显著) —— 白白牺牲 power" % (gate, gate - 1))
    assert n - gate >= 5, "★★★ 门没有余量(%d) —— n=1 + 重测一致率 60%% 下一次噪声就翻转" % (n - gate)


# ───────── 主判据的三个前置条件 ─────────

def test_主判据必须有三个前置条件_缺一个就有退化能穿过():
    m = _m()
    r = m.selfcheck()
    gold = r["① 两臂=金标"]
    assert "**超过" in gold["主判据结论"], "★★★ 连金标臂都过不了门 ⇒ 判据**永假**"
    for bad in ("② 两臂=零基线(不读文本)", "③ 两臂=最佳单token浅层规则",
                "⑤ 两臂=枚举外取值", "⑥ 两臂=全 UNSPECIFIED",
                "⑦ 两臂=一刀切(A支全填RESTATES)",
                "⑧ ★★★两臂=纯正则(评审用来穿过七条降级的那个)"):
        assert "**超过" not in (r[bad]["主判据结论"] or ""), "★★★ 退化态「%s」**穿过了主判据**" % bad
    assert r["⑦ 两臂=一刀切(A支全填RESTATES)"]["三个前置条件"]["② 净增益 > 最佳浅层规则的净增益"] is False, (
        "★★★ 一刀切必须被**前置条件②**挡住 —— 它的鉴别格是满分, 只有净增益拆穿它")
    # ★★★ 2026-09-15 投料前评审实测: 一条**族外**零语义正则(不含量词/时段 ⇒ RESTATES)
    #   曾拿鉴别格 19/24 并穿过全部三个前置条件(p=3.8e-5)。它现在必须被挡。
    q = [k for k in r if "族外量词规则" in k]
    assert q, "★★★ 缺「族外量词规则」那一态 —— 那是本轮 BLOCKING 的回归测试"
    assert "**超过" not in (r[q[0]]["主判据结论"] or ""), (
        "★★★ 那条零语义正则又穿过去了: %r" % r[q[0]])
    assert r[q[0]]["三个前置条件"]["② 净增益 > 最佳浅层规则的净增益"] is False, (
        "★★★ 它必须被**净增益**挡住 —— 它的鉴别格与多数类格**分开看都过**, 只有净增益拆穿它")
    assert r["⑤ 两臂=枚举外取值"]["三个前置条件"]["③ 端到端可用过半"] is False, (
        "★★★ 枚举外取值必须被**前置条件③**挡住")


def test_桩自检结果由执行器现跑_不许手写():
    p = _p()
    k = [x for x in p if "零调用桩自检" in x][0]
    live = _m().selfcheck()
    assert set(p[k]) == set(live), "★★★ 桩自检状态集不符: %r vs %r" % (sorted(p[k]), sorted(live))
    for name, v in live.items():
        a = p[k][name]
        for f in ("B 鉴别格", "B 多数类格", "净增益", "单侧p", "主判据结论"):
            assert a.get(f) == v.get(f), "★★★ 「%s」的 %s 档案 %r vs 现跑 %r" % (name, f, a.get(f), v.get(f))


def test_桩自检抓到的三个漏洞必须留档():
    p = _p()
    k = [x for x in p if "桩自检抓到的漏洞" in x][0]
    v = json.dumps(p[k], ensure_ascii=False)
    assert "一刀切" in v and "0/42" in v, "★ 没写明一刀切那条"
    assert "端到端" in v, "★ 没写明枚举外取值那条"
    assert "五类成立条件" in v and "仍是解释" in v, "★ 没写明分母混了两个取值那条"
    assert "q=0.90 的好模型" in v and "全是退化填充" in v, (
        "★★★ 必须写明**噪声态才暴露的那条** —— 原八态全是退化填充, "
        "「真会做但有噪声的模型」从来没测过")


# ───────── 库内硬规则 ─────────

def test_声明了调用预算就必须带判据准入结果_且逐条回应被拦项():
    p = _p()
    k = [x for x in p if "判据准入结果" in x][0]
    v = p[k]
    assert v["工具"].endswith("cce_criterion_preflight.py")
    assert v["明细"], "★ 缺明细"
    r = [x for x in v if "我对被拦" in x]
    assert r, "★★★ 准入拦下了条目却没有逐条回应"
    body = json.dumps(v[r[0]], ensure_ascii=False)
    assert "退化检测" in body and "descriptive" in body, "★ 回应没说清方向/结论权限"


def test_预注册必须钉硬上限_零重试_失败也计数_停止规则():
    b = _p()["★★★预算"]
    assert b["硬上限"] == 68
    assert "计入预算" in b["★失败也计数"] and "不进分母" in b["★失败也计数"]
    assert "撞硬上限即停" in b["★停止规则"] and "哈希" in b["★停止规则"]
    src = EXE.read_text(encoding="utf-8")
    assert "if n >= CAP" in src, "★ 执行器没按硬上限停"
    assert "max_retries=ATTEMPTS" in src and "ATTEMPTS = 1" in src, (
        "★★★ 零重试的正确写法是 ATTEMPTS=1(一次尝试、零重试) —— "
        "call_model 是 `for attempt in range(max_retries)`, 写 0 **一次 HTTP 都不发**")


def test_执行器在预注册未READY时拒发():
    src = EXE.read_text(encoding="utf-8")
    assert 'assert st.startswith("**READY**")' in src, "★★★ 执行器没有 READY 门 —— 草案状态也能投料"
    st = _p()["★★★status"]
    ALLOWED = ("**BLOCKED_ON_CORPUS**", "**DRAFT_V3**", "**READY**", "**DONE**")
    assert st.startswith(ALLOWED), "★ status 取值不在允许集合里: %r" % st[:40]
    # ★★★ 评审 MINOR 指出的悖论: 原版断言「不许是 READY」⇒ 真要投料时这道闸必红,
    #   「闸全绿再投料」这个状态在本仓**根本不存在**。
    #   ⇒ 改为: READY 必须**写明谁批准、依据哪几轮评审**, 而不是禁止 READY。
    if st.startswith("**READY**"):
        assert "评审" in st and ("owner" in st or "授权" in st), (
            "★★★ status=READY 必须写明**谁批准的、依据哪几轮评审** —— "
            "否则 READY 就是一个没人负责的开关: %r" % st)


def test_评审结论与下一版前提必须留档():
    """★★★ 不许把「修了四条工程 bug」读成「可以投料了」。决定性的那条是对照集, 没修。"""
    p = _p()
    k = [x for x in p if "投料前评审的结论" in x][0]
    v = p[k]
    body = json.dumps(v, ensure_ascii=False)
    assert "5/6" in body and "门在任何 n 下都不可达" in body, "★ 没写清决定性理由"
    assert "净 0" in body and "伪影" in body, (
        "★★★ 必须写明那条规则在**真实证书**上净增益是 0 ⇒ 它是手构对照集的伪影")
    assert "定义句" in body and "泛泛提及" in body, "★ 没写清真实形态与我造的形态的差"
    assert "外部锚点" in body, "★ 没写明这轮买到的方法论进展"
    nxt = [x for x in v if "仍未处理" in x][0]
    assert len(v[nxt]) >= 8, "★ 下一版前提少于 8 条"
    assert any("照真实形态重造对照集" in i for i in v[nxt]), "★ 第一条前提必须是重造对照集"
    assert any("n 必须 ≥12" in i for i in v[nxt]), "★ 必须写明 n 的下限"


def test_不得据此说与已知局限都在_且覆盖关键误读():
    p = _p()
    ns = json.dumps(p["★★★不得据此说"], ensure_ascii=False)
    for must in ("照抄", "r4 的历史读数", "接进生产", "聚合"):
        assert must in ns, "★ 「不得据此说」漏了 %r 这个方向" % must
    lim = json.dumps(p["★★★已知局限(测量前写下)"], ensure_ascii=False)
    for must in ("n=1", "更长", "下界", "看过 best_shallow_rule_search 结果之后"):
        assert must in lim, "★ 已知局限漏了 %r" % must


def test_交错发起而不是按臂分块():
    p = json.dumps(_p(), ensure_ascii=False)
    assert "交错" in p and "共线" in p, "★ 没写明为什么必须交错"
    assert "for it in its for arm in ARMS" in EXE.read_text(encoding="utf-8"), (
        "★★★ 执行器实际是按臂分块的 ⇒ 「臂」与「执行时间」完全共线")

def test_门必须用冻结值判_不许运行时现算():
    """★★★ 评审 BLOCKING: 原版 `gate_sig = (p < 0.05)` 是现算的 ⇒ n 一动门就跟着动,
    声称 confirmatory 却没锁分析自由度。必须用预注册里冻结的那个整数。"""
    src = EXE.read_text(encoding="utf-8")
    assert "gate_sig = (k >= gate)" in src, (
        "★★★ 主判据的显著性门是**现算**的 —— 掉一条样本就换一个门")
    assert 'FZ = PREREG["★★★主判据(测量前冻结_confirmatory)"]' in src and 'FZ["★冻结的 p0"]' in src, (
        "★ p0 必须从预注册读, 不许在执行器里现算或硬编码")
    assert "if n != n_fz:" in src and "不是**「模型未达成」" in src, (
        "★★★ 鉴别格数与冻结值不符时必须**不计算主判据**, 且写明那不是「未达成」")


def test_power必须测量前算出来并写进预注册():
    """★★★ 评审 BLOCKING: r5-v2 全程没算过 power, 最可能的结局是「未达成」且一条降级都不响。"""
    FZ = _p()["★★★主判据(测量前冻结_confirmatory)"]
    k = [x for x in FZ if "power(联合" in x]
    assert k, "★★★ 预注册没有**联合** power —— 上一版只算①的 power 并当成结论的 power, 被判 BLOCKING"
    pw = FZ[k[0]]
    assert len(pw) >= 5, "★ power 表太短, 看不出拐点"
    assert float(pw["q=0.75"]) >= 0.8, "★★★ 连每格 0.75 的模型都没有 0.8 的功效, 门太严"
    how = [FZ[x] for x in FZ if "power 是联合的" in x]
    assert how, "★★★ 必须写明这是**联合** power 而不是单条"
    assert "不等于模型不行" in how[0] and "0.069" in how[0], (
        "★★★ 必须写明: ①只算 0.817 而联合只有 0.069 那次是 BLOCKING; "
        "以及低于 q=0.75 的「未达成」不等于模型不行")


def test_硬上限必须等于items数_否则跑不完():
    m = _m()
    b = _p()["★★★预算"]
    assert m.CAP == b["硬上限"] == len(m.items()), (
        "★★★ CAP=%d · 预注册硬上限=%s · items=%d —— 三者必须一致, "
        "否则要么跑不完(尾部条目静默丢失)要么超预算" % (m.CAP, b["硬上限"], len(m.items())))
    assert len(m.ARMS) == 1, "★ A 臂已砍, 只应剩一条臂: %r" % list(m.ARMS)

# ───────── 根本修法: 必须有闸**真的执行 main()** ─────────

def test_源码里不许有未定义的自由名():
    """★★★ 2026-09-15 投料前评审(四个维度独立报到): 我把 RETRIES 改名成 ATTEMPTS 时**漏了一行**,
    而那行在 `res = {...}` 字面量里、在 judge 的 try/except **之前** ⇒
    **68 次全部打完之后才 NameError, 结果文件一个字节都写不出**。
    19 道闸当时**全绿** —— 因为没有一道闸执行过 main()。与 r3「跑完 16 次后必 KeyError」同型。
    """
    import ast, builtins
    tree = ast.parse(EXE.read_text(encoding="utf-8"))
    loads = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    bound = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            bound.add(n.id)
        elif isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            bound.add(n.name)
        elif isinstance(n, ast.arg):
            bound.add(n.arg)
        elif isinstance(n, ast.alias):
            bound.add((n.asname or n.name).split(".")[0])
    free = sorted(loads - bound - set(dir(builtins)) - {"__file__", "e"})
    assert not free, "★★★ 执行器里有未定义的自由名 %r —— 它们会在**运行到那一行时**才炸" % free


def test_main必须能零调用干跑到落盘():
    """★★★ 评审给的根本修法: **monkeypatch 掉模型入口, 真的跑一遍 main()**, 断言产物落盘。

    ★ 只静态查名字不够 —— 键缺失、类型错、分母为零都只有跑起来才暴露。
    ★★ 本闸**零调用**: call_model 被替换成返回金标 JSON 的桩, _load_key 被替换成空操作。
    """
    import json as _j, tempfile, types, sys as _s
    m = _m()
    calls = {"n": 0}

    def fake_call(model, prompt, temperature=0.0, max_retries=1):
        calls["n"] += 1
        # 桩: 按提示词里的文本找回该 item 的金标, 返回合法 JSON
        for it in m.items():
            if it["text"] in prompt:
                D = m.GOLD["★默认槽位"]
                return _j.dumps({"片段一": dict(D, **it["gold"]["A"]),
                                 "片段二": dict(D, **it["gold"]["B"])}, ensure_ascii=False), {"error": None}
        return "{}", {"error": None}

    m._load_key = lambda: None
    # ★ 只替换 call_model 这一个名字, 其余属性从真模块转发 —— 否则 main() 里别的 import 会挂
    import importlib
    real = importlib.import_module("exp_crossmodel_desire")
    fake_mod = types.ModuleType("exp_crossmodel_desire")
    for a in dir(real):
        setattr(fake_mod, a, getattr(real, a))
    fake_mod.call_model = fake_call
    old = _s.modules.get("exp_crossmodel_desire")
    _s.modules["exp_crossmodel_desire"] = fake_mod
    with tempfile.TemporaryDirectory() as td:
        m.OUT = pathlib.Path(td) / "r5_dryrun.json"
        m.PREREG = dict(m.PREREG, **{"★★★status": "**READY** (干跑)"})
        try:
            m.main()
        finally:
            if old is not None:
                _s.modules["exp_crossmodel_desire"] = old
            else:
                _s.modules.pop("exp_crossmodel_desire", None)
        assert m.OUT.exists(), "★★★ main() 跑完了但**产物没落盘** —— 真投料时 68 次会全部蒸发"
        r = _j.loads(m.OUT.read_text(encoding="utf-8"))
    assert calls["n"] == len(m.items()), "★ 干跑应恰好走 %d 条, 实际 %d" % (len(m.items()), calls["n"])
    for must in ("rows", "★★★五臂对照(四条零调用 + 一条模型臂 · 同一批 items · 同一套打分)",
                 "★★★主判据: B 臂鉴别格 vs 最佳浅层规则", "★★★判读降级"):
        assert must in r, "★★★ 产物缺关键键 %r" % must
    assert len(r["rows"]) == len(m.items())
    assert "**超过" in r["★★★主判据: B 臂鉴别格 vs 最佳浅层规则"]["★结论"], (
        "★★★ 桩喂的是**金标**, 主判据却没过 ⇒ 判据**永假**")


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("r5 预注册与执行器闸 %d 项全过" % n)
