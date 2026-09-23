# -*- coding: utf-8 -*-
"""真实语料小批试**预注册 v2** 的闸。零调用。

★★★ 必须在投料**之前**绿。守四件事:
    ① 判据事前**可达**且**按实际 n_ok 查表**(v1 的 BLOCKING 就在这)
    ② 判据**冻结**: 输入集/提示词/判别式/交卷定义/拒绝域, 改一个见红
    ③ 产物里**没有一个字**语料原文
    ④ 评审打回的九条, **每条都有一道对应的闸**, 不是改完就算

★★★ 每个数都**现算**。
"""
import hashlib, importlib.util, json, pathlib, re, statistics
from math import comb

ROOT = pathlib.Path(__file__).resolve().parents[1]
P = ROOT / "tests/data/real_corpus_pilot_prereg.json"
GEN = ROOT / "probes/real_corpus_pilot_prereg.py"
RUN = ROOT / "probes/real_corpus_pilot_run.py"


def _pre():
    return json.loads(P.read_text(encoding="utf-8")) if P.exists() else None


def _gen():
    s = importlib.util.spec_from_file_location("_gen", GEN)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def _k(d, frag):
    ks = [x for x in d if frag in x]
    assert len(ks) == 1, "★ 片段 %r 命中 %d 个键(应为 1)" % (frag, len(ks))
    return d[ks[0]]


# ── A: 拒绝域必须按实际 n_ok 查表, 且有 INSUFFICIENT_DATA 出口 ─────────
def test_A_拒绝域必须是整张表且逐行现算一致():
    pre = _pre()
    if not pre:
        return
    g = _gen()
    J = _k(pre, "主判据(投料前定死)")
    base = _k(J, "底数用模板级")
    K2, N2 = base["k_unit(= 平均率 × 单元数)"], base["单元数"]
    N1 = _k(pre, "冻结输入集")["条数"]
    table = _k(J, "拒绝域按实际 n_ok 查表")
    assert set(table) == {str(n) for n in range(N1 + 1)}, "★★★ 表必须覆盖每一个可能的 n_ok"
    p0 = K2 / N2
    for n in range(N1 + 1):
        R = [k for k in range(n + 1) if g.fisher_p(k, n - k, K2, N2 - K2) < 0.05]
        if not R:
            assert table[str(n)] is None, "★ n_ok=%d 应无拒绝域" % n
            continue
        lo = max([k for k in R if k / n < p0], default=-1)
        hi = min([k for k in R if k / n > p0], default=n + 1)
        want = {"k ≤": lo, "k ≥": hi if hi <= n else None}
        assert table[str(n)] == want, (
            "★★★ n_ok=%d 的拒绝域与现算不符: 档案 %r vs 现算 %r" % (n, table[str(n)], want))


def test_A_全部调用失败不许被判成显著不同():
    """★★★ v1 的 BLOCKING: n_ok=0 时 k=0 ≤ 5 ⇒ 自信判 TRANSFERS_NOT。"""
    pre = _pre()
    if not pre:
        return
    J = _k(pre, "主判据(投料前定死)")
    min_n = _k(J, "最低可判 n_ok(= **下尾可达**")
    table = _k(J, "拒绝域按实际 n_ok 查表")
    # ★★★ 门槛必须是**下尾可达**的那个 —— 用「任意一侧非空」会让 4≤n_ok≤12 整段在
    #     预期方向上事前不可达却印 CANNOT_DISTINGUISH(r5-v1 死因搬到小 n_ok 分支)
    for n in range(0, min_n):
        r = table[str(n)]
        assert r is None or r["k ≤"] < 0, (
            "★★★ n_ok=%d < 最低 %d 却有可达的**下尾**: %r" % (n, min_n, r))
    assert table[str(min_n)]["k ≤"] >= 0, "★ 门槛处下尾必须可达"
    v = _k(J, "n_ok 低于它时的判决")
    assert "INSUFFICIENT_DATA" in v and "不是** TRANSFERS_NOT" in v and "不是** CANNOT_DISTINGUISH" in v
    assert "先验不可达" in _k(J, "为什么门槛不能用「任意一侧非空」")
    # ★ 执行器里也必须真有这条出口
    src = RUN.read_text(encoding="utf-8")
    assert "INSUFFICIENT_DATA" in src and "n_ok < min_n" in src, "★★★ 执行器没有这条出口"


# ── I: 底数必须是模板级(独立单元), 不是合并 ────────────────────────────
def test_I_底数必须按模板级现算_且伪重复的证据要在():
    pre = _pre()
    if not pre:
        return
    g = _gen()
    m = g._r2()
    got, K2, N2 = g.template_level_baseline(m)
    J = _k(pre, "主判据(投料前定死)")
    assert _k(J, "底数用模板级") == got, "★ 模板级底数与现算不符"
    assert "%d/%d" % (K2, N2) in J["零假设"], "★ 零假设没用模板级底数"
    # ★★★ 断言**结构化字段**, 不从散文里抠数(抠数的正则漏了第二个数, 已由闸自己暴露)
    b = _k(J, "底数用模板级")
    st, fl = b["两轮都有效且一致的模板数"], b["两轮都有效但翻转的模板数"]
    assert st > 2 * fl, (
        "★★★ 一致 %d / 翻转 %d —— 若一致的不再远多于翻转的, 「伪重复」这个理由不成立, 判据要重写" % (st, fl))
    # ★ 合并率必须留着但标明不用于判决
    assert "不用于判决" in [x for x in _k(J, "底数用模板级") if "合并率" in x][0]


def test_I_功效必须现算_且必须承认比v1弱():
    pre = _pre()
    if not pre:
        return
    g = _gen()
    J = _k(pre, "主判据(投料前定死)")
    base = _k(J, "底数用模板级")
    K2, N2 = base["k_unit(= 平均率 × 单元数)"], base["单元数"]
    N1 = _k(pre, "冻结输入集")["条数"]
    R = [k for k in range(N1 + 1) if g.fisher_p(k, N1 - k, K2, N2 - K2) < 0.05]
    pw = _k(J, "★功效(n_ok = %d 时" % N1)
    for key, want in pw.items():
        q = float(key.split("=")[1])
        got = round(sum(comb(N1, k) * q ** k * (1 - q) ** (N1 - k) for k in R), 4)
        assert abs(got - want) < 1e-9, "★ 功效 %s 档案 %r vs 现算 %r" % (key, want, got)
    assert pw["q=0.0500"] >= 0.8, "★★★ 连 q=0.05 都到不了 0.8 功效 ⇒ 事前不可达, 不许投料"
    assert pw["q=%.4f" % (K2 / N2)] <= 0.05, "★ 零假设点上的第一类错误超了"
    honest = _k(J, "功效的老实话")
    assert "很可能的结局" in honest and "不携带信息" in honest, (
        "★★★ 必须写明 CANNOT_DISTINGUISH 很可能发生且基本不携带信息")
    assert "这不是退步" in _k(J, "比 v1 弱了多少"), "★ 必须解释为什么功效比 v1 低"


# ── C: 交卷判定只有一个定义 ───────────────────────────────────────────
def test_功效表必须逐n_ok现算一致():
    """★★★ 功效是按 n_ok 冻成表的; 只核 n=42 那一行等于没核。"""
    pre = _pre()
    if not pre:
        return
    g = _gen()
    J = _k(pre, "主判据(投料前定死)")
    b = _k(J, "底数用模板级")
    K2, N2 = b["k_unit(= 平均率 × 单元数)"], b["单元数"]
    N1 = _k(pre, "冻结输入集")["条数"]
    pw = _k(J, "功效也按实际 n_ok 查表")
    for n in range(N1 + 1):
        R = [k for k in range(n + 1) if g.fisher_p(k, n - k, K2, N2 - K2) < 0.05]
        if not R:
            assert pw[str(n)] is None
            continue
        for key, want in pw[str(n)].items():
            q = float(key.split("=")[1])
            got = round(sum(comb(n, k) * q ** k * (1 - q) ** (n - k) for k in R), 4)
            assert abs(got - want) < 1e-9, "★ n_ok=%d 的功效 %s: 档案 %r vs 现算 %r" % (n, key, want, got)


def test_P2_模型臂必须冻结_且max_tokens不许被当成可断言的冻结项():
    pre = _pre()
    if not pre:
        return
    g = _gen()
    m = _k(pre, "冻结模型臂")
    got = g._models_entry_by_ast(m["MEASUREMENT_MODEL"])
    assert got["model"] == m["model 字符串"] and got["key_env"] == m["key_env"]
    note = _k(m, "max_tokens 这个数不可信")
    assert "导入时" in note and "8000" in note, "★★★ 必须写明它在导入时被改写"
    assert "预注册**不冻这个数**" in note, "★ 冻源码值会让预检误报"
    # ★ 执行器不许拿它去断言
    src = RUN.read_text(encoding="utf-8")
    assert '"max_tokens"' not in src.split("def preflight")[1].split("return {")[0], (
        "★★★ preflight 又把 max_tokens 当冻结项断言了 —— 源码值从不生效, 会误报")


def test_P3_零假设必须钉在两份具名产物上():
    """★ r5-v2 的死因就是底数来源。不钉死就能事后换掉。"""
    pre = _pre()
    if not pre:
        return
    g = _gen()
    pin = _k(pre, "零假设钉在这两份产物上")["sha256"]
    assert set(pin) == set(g.HAND), "★ 钉的产物与底数来源不符"
    for rel, want in pin.items():
        assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == want, (
            "★★★ 底数产物 %s 已被改过" % rel)
    assert "r5-v2 正是死在底数来源上" in _k(_k(pre, "零假设钉在这两份产物上"), "为什么")
    src = RUN.read_text(encoding="utf-8")
    assert "零假设钉在这两份产物上" in src, "★★★ 执行器没在调用前核底数产物"


def test_实际size必须披露_不许只写名义alpha():
    pre = _pre()
    if not pre:
        return
    g = _gen()
    J = _k(pre, "主判据(投料前定死)")
    pw = _k(J, "★功效(n_ok = %d 时" % _k(pre, "冻结输入集")["条数"])
    b = _k(J, "底数用模板级")
    p0 = round(b["k_unit(= 平均率 × 单元数)"] / b["单元数"], 4)
    note = _k(J, "实际 size 远小于名义")
    assert str(pw["q=%.4f" % p0]) in note, "★ 实际 size 与功效表那一格不符"
    assert "反保守" in note, "★★★ 必须写明「提功效的改法都是反保守的」"


def test_C_交卷判定只有一个定义_且等价性用它现算():
    pre = _pre()
    if not pre:
        return
    g = _gen()
    m = g._r2()
    mism = 0
    for rel in g.HAND:
        for r in json.loads((ROOT / rel).read_text(encoding="utf-8"))["rows"]:
            if not r.get("调用成功"):
                continue
            if g.submitted(r.get("模型原样")) != (r.get("outcome") in m.ISSUED):
                mism += 1
    assert mism == 0, "★★★ 两个口径不等价(%d 行) ⇒ 对照不成立" % mism
    d = _k(pre, "冻结交卷定义")
    assert "不一致的行数 = 0" in _k(d, "同口径的机械证明")
    assert "is True" in d["定义"] and "严格布尔" in d["定义"]
    # ★★★ 执行器必须 import 它, 不许自己再写一个
    src = RUN.read_text(encoding="utf-8")
    assert "g.submitted(obj)" in src, "★★★ 执行器没用预注册那个唯一定义"
    assert 'is True' not in src.split("def build_result")[0].replace("g.submitted", ""), \
        "★ 执行器里还有另一处自写的交卷判定"


# ── D: 立即落盘 + 计数强制 str ────────────────────────────────────────
def test_D_必须逐次落盘_且计数不许拿模型给的东西当键():
    src = RUN.read_text(encoding="utf-8")
    assert "PARTIAL" in src and "fh.write" in src, "★★★ 没有逐次落盘 ⇒ 写盘前任何异常都丢掉全部调用"
    assert "PARTIAL.open(\"a\"" in src, "★ 必须是追加写"
    # ★★★ 不查源码字样, **真的喂进去跑一遍** —— 查字样是 grep 不是闸
    g = importlib.util.spec_from_file_location("_run", RUN)
    mm = importlib.util.module_from_spec(g); g.loader.exec_module(mm)
    E = ["具体型号", "数据", "使用细节", "纠错", "结构化经验"]
    rows = [{"调用成功": True, "kinds": [mm.classify_kind(x, E)]}
            for x in (["具体型号"], {"a": 1}, "数据和使用细节", None, 42, "随便写的")]
    t = mm._kind_tally(rows)          # 不抛 = D 修好了
    assert isinstance(t, dict) and "逐项(多重命中会重复计入)" in t
    assert t["多重命中的证据条数"] == 1, "★ 「数据和使用细节」应被记成多重命中: %r" % t
    assert mm.classify_kind({"a": 1}, E)["命中"] == ["OTHER"], "★ 非字符串必须安全落到 OTHER"
    assert mm.classify_kind("数据和使用细节", E)["命中"] == ["数据", "使用细节"], (
        "★★★ 只取第一个命中会把信息悄悄丢掉")


# ── E: 产物不含模型自由文本 ───────────────────────────────────────────
def test_E_枚举必须从冻结生产件抠出_产物只存序号与sha():
    pre = _pre()
    if not pre:
        return
    g = _gen()
    m = g._r2()
    want = [x.strip() for x in re.search(r"新信息增量\*\*\(([^)]*)\)", m.DISC).group(1).split("/") if x.strip()]
    d = _k(pre, "increment_kind 枚举")
    assert d["枚举"] == want, "★ 枚举与判别式现算不符: %r vs %r" % (d["枚举"], want)
    assert "不存文本" in d["★产物只存什么"]
    src = RUN.read_text(encoding="utf-8")
    assert '"kinds": [classify_kind' in src, "★ 必须经 classify_kind 落地"
    assert "increment_kind\"]" not in src.replace('e.get("increment_kind")', ""), "★ 有裸写 increment_kind 的路径"


# ── F/G: 上限有效 + 执行前重验 ────────────────────────────────────────
def test_F_硬上限必须等于实际条数_且可被真跑到():
    pre = _pre()
    if not pre:
        return
    inp = _k(pre, "冻结输入集")
    assert inp["硬上限"] == inp["条数"] == len(inp["items"]), (
        "★ 上限 %r != 条数 %r ⇒ 那条保护永不触发" % (inp["硬上限"], inp["条数"]))
    assert "--limit" in RUN.read_text(encoding="utf-8"), "★ 必须能在 dry-run 里走一次上限分支"


def test_G_执行前必须重验提示词与判别式():
    pre = _pre()
    if not pre:
        return
    g = _gen()
    m = g._r2()
    f = _k(pre, "冻结提示词与判别式")
    # ★★★ 必须 hash **真发出去的串**(m.PROMPT), 不是源码字面量 —— 两者因转义而不同,
    #     而真串的 sha16 = 7a8f9417 正是本仓 r3 记录里引用的那个。
    assert f["PROMPT sha256"] == hashlib.sha256(m.PROMPT.encode()).hexdigest(), "★★★ 提示词变了"
    lit = re.search(r'PROMPT = """(.*?)"""',
                    (ROOT / "probes/extractor_counterexample_run_r2.py").read_text(encoding="utf-8"),
                    re.S).group(1)
    assert hashlib.sha256(lit.encode()).hexdigest() != f["PROMPT sha256"], (
        "★ 源码字面量与真串的 sha 竟然相同 —— 那说明转义情况变了, 这条守护要重新想")
    assert f["PROMPT sha256"].startswith("7a8f9417"), (
        "★★★ 与本仓 r3 记录里引用的提示词 sha 对不上: %s" % f["PROMPT sha256"][:16])
    assert f["判别式 sha256"] == hashlib.sha256(m.DISC.encode()).hexdigest(), "★★★ 判别式变了"
    assert f["max_retries"] == 1
    src = RUN.read_text(encoding="utf-8")
    assert "def preflight" in src and "未发起任何调用" in src, "★★★ 执行器没有调用前重验"
    assert src.index("preflight(pre, m)") < src.index("for it, line in pairs"), (
        "★★★ 重验必须在循环之前")


# ── B: 判别式来源 ─────────────────────────────────────────────────────
def test_B_判别式必须能在冻结生产件里找到():
    pre = _pre()
    if not pre:
        return
    g = _gen()
    m = g._r2()
    tax = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
    knots = tax["knots"] if isinstance(tax, dict) else tax
    hit = [x for x in knots if isinstance(x, dict) and x.get("hard_discriminant") == m.DISC]
    assert len(hit) == 1, "★★★ 判别式在冻结生产件里找不到唯一对应"
    assert "逐字节比对通过" in _k(_k(pre, "冻结提示词与判别式"), "判别式来源")


# ── H: 长度混淆必须量化披露 ───────────────────────────────────────────
def test_H_长度混淆必须现算且限制结论():
    pre = _pre()
    if not pre:
        return
    tpl = json.loads((ROOT / "tests/data/extractor_counterexample_templates_r2.json")
                     .read_text(encoding="utf-8"))["templates"]
    tl = [len(t["text"]) for t in tpl]
    cl = [i["n_chars"] for i in _k(pre, "冻结输入集")["items"]]
    d = _k(pre, "已知混淆")
    assert d["中位数之比"] == round(statistics.median(cl) / statistics.median(tl), 2), "★ 比值与现算不符"
    assert d["比最长模板还长的语料条数"] == "%d/%d" % (sum(1 for x in cl if x > max(tl)), len(cl))
    assert d["中位数之比"] >= 2.0, "★ 若长度差不再显著, 这条混淆声明要重写"
    lim = _k(d, "对结论的限制")
    assert "不得读成" in lim and "机制未识别" in lim, "★★★ 必须限制 TRANSFERS_NOT 的读法"
    # ★ 执行器的判决解释里也必须带这条
    assert "机制未识别" in RUN.read_text(encoding="utf-8"), "★ 判决解释里没带混淆限制"


# ── 通用 ──────────────────────────────────────────────────────────────
def test_输入集必须逐条对得上语料现算():
    pre = _pre()
    if not pre:
        return
    inp = _k(pre, "冻结输入集")
    cache = {}
    for it in inp["items"]:
        f = it["file"]
        if f not in cache:
            cache[f] = (ROOT / f).read_text(encoding="utf-8").split("\n")
        line = cache[f][it["line_index"]]
        assert hashlib.sha256(line.encode()).hexdigest() == it["sha256"], "★★★ 语料被改过"
        assert len(line) == it["n_chars"]
    assert "全取" in inp["★取法"] and "不抽样" in inp["★取法"]


def test_产物里不许有一个字语料原文():
    pre = _pre()
    if not pre:
        return
    blob = json.dumps(pre, ensure_ascii=False)
    for rel in _gen().CORPUS:
        for l in (ROOT / rel).read_text(encoding="utf-8").split("\n"):
            if len(l.strip()) >= 25:
                assert l.strip()[:25] not in blob, "★★★ 预注册里出现语料原文: %r" % l.strip()[:25]


def test_九条打回必须逐条留档():
    pre = _pre()
    if not pre:
        return
    v = _k(pre, "v1 被零调用对抗评审打回")
    # ★★★ 查**值**不查键名 —— 键名里本来就有那句话, 只改值会漏网(变异 R2 实测漏过一次)
    note = _k(v, "我没有只修存活的那 4 条")
    assert "逐条自核" in note and "全部属实" in note, (
        "★★★ 必须写明未验证的那批也自核了且属实 —— 否则下次会以为「存活的才算数」: %r" % note)
    import re as _re
    nums = [int(x) for x in _re.findall(r"\d+", note)]
    assert 9 in nums, "★ 必须写明自核了几条: %r" % note
    items = _k(v, "逐条")
    assert len(items) == 9, "★ 应有 9 条, 实为 %d" % len(items)
    for lbl in ("A ", "B ", "C ", "D ", "E ", "F ", "G ", "H ", "I "):
        assert any(x.startswith(lbl) for x in items), "★ 缺 %r" % lbl


def test_必须写明这一轮换掉了上一次给owner的说法():
    pre = _pre()
    if not pre:
        return
    k = [x for x in pre if "这一轮不是「把 ~570 次的外推换成实测」" in x]
    assert k, "★★★ 更正被删了"
    v = pre[k[0]]
    assert "上一份汇报" in _k(v, "★为什么要更正")
    keys = list(pre)
    assert keys.index(k[0]) < keys.index([x for x in pre if "主判据" in x][0]), "★ 更正必须排在主判据之前"


def test_C2_鉴别格必须声明为_测不了_而不是测不准():
    """★★★ v1 把事前枚举按**鉴别格数**列, 读起来像会去数它 —— 但执行器没有金标, 根本算不出。
    那是在预注册一个测不了的量。"""
    pre = _pre()
    if not pre:
        return
    g = _gen()
    v = _k(pre, "鉴别格产出率: 本轮**根本测不了**")
    assert "人从语料里标不出来" in _k(v, "为什么是测不了")
    assert "已删掉那个假枚举" in _k(v, "v1 在这里做错了什么"), "★ 必须写明 v1 错在哪"
    # ★★★ 事前枚举必须是按**交卷数**列的, 且逐行现算
    N1 = _k(pre, "冻结输入集")["条数"]
    enum = _k(v, "事前枚举(按**交卷数**")
    for label, row in enum.items():
        assert "**交卷**" in label, "★ 枚举标签必须写明是交卷数: %r" % label
        k = int(label.split(" ")[1].split("/")[0])
        lo, hi = g.clopper_pearson(k, N1)
        assert [round(lo, 4), round(hi, 4)] == row["交卷率 CP95"], "★ %s 的 CP95 与现算不符" % label
        want = "下界为 0, 上不封顶" if lo == 0 else round(hi / lo, 1)
        assert row["★区间跨度(倍)"] == want, "★ %s 跨度与现算不符" % label
        # ★ (b): 标签必须写明是**哪个量**的上界
        lbl = [x for x in row if "代价下界" in x][0]
        assert "交卷率上界" in lbl, "★ 标签没写明是哪个量: %r" % lbl
    assert "更正我自己的一句过度断言" in _k(v, "★★★不得当点估计引用")
    assert "不是下界" in _k(v, "★另一条要用手构因子二")
    # ★ 执行器必须真的不算鉴别格
    src = RUN.read_text(encoding="utf-8")
    assert '"鉴别格计数": None' in src, "★★★ 执行器必须如实把鉴别格留空, 不许糊一个数上去"


def test_a_两侧尾部不许印同一个判决():
    """★★★ k 低 = 外推高估; k 高 = 外推低估。含义相反, 印同一个词会误导。"""
    src = RUN.read_text(encoding="utf-8")
    assert "TRANSFERS_NOT_LOWER" in src and "TRANSFERS_NOT_HIGHER" in src, (
        "★★★ 两侧尾部仍印同一个判决")
    # ★★★ 不 grep 措辞 —— 真跑 build_result 两侧各一次, 比对解释文本确实不同且各自带方向
    import importlib.util as _I, json as _j
    sp = _I.spec_from_file_location("_run_tails", RUN)
    mm = _I.module_from_spec(sp); sp.loader.exec_module(mm)
    pre = _pre()
    if not pre:
        return
    items = _k(pre, "冻结输入集")["items"]
    def mk(n_ok, k):
        out = []
        for i in range(n_ok):
            it = items[i]
            out.append({"ptr": "%s:%d" % (it["file"], it["line_index"]), "sha256": it["sha256"],
                        "n_chars": it["n_chars"], "调用成功": True, "交卷": i < k,
                        "n_evidence": 0, "A_支": 0, "B_支": 0, "kinds": [], "span_逐字": [],
                        "why_not_字数": 0, "finish_reason": "stop"})
        return out
    env = {"有效 max_tokens": 8000, "源码声明": 12000}
    lo_res = mm.build_result(pre, mk(42, 2), 42, 1.0, "T", env)
    hi_res = mm.build_result(pre, mk(42, 30), 42, 1.0, "T", env)
    assert lo_res["★★★ 主读数: 真实语料交卷率"]["★★★判决"] == "TRANSFERS_NOT_LOWER"
    assert hi_res["★★★ 主读数: 真实语料交卷率"]["★★★判决"] == "TRANSFERS_NOT_HIGHER"
    a, b = lo_res["★★★ 判决怎么读"], hi_res["★★★ 判决怎么读"]
    assert a != b, "★★★ 两侧尾部印了同一段解释, 但含义相反"
    assert "高估" in a and "低估" in b, "★ 两侧必须各自写清方向: %r / %r" % (a[:60], b[:60])
    assert "机制未识别" in a and "机制未识别" in b, "★ 两侧都要带混淆限制"
    assert "不得就此说「比 ~570 次更贵」" in a, (
        "★★★ 低尾不许做**总代价**断言 —— 那需要因子二, 本轮没测")


def test_d_子总体与更长混在一起必须披露():
    pre = _pre()
    if not pre:
        return
    import statistics as st
    g = _gen()
    bs = importlib.util.spec_from_file_location("_cb", ROOT / "probes/corpus_balance_audit.py")
    cb = importlib.util.module_from_spec(bs); bs.loader.exec_module(cb)
    br, nb = [], []
    for rel in g.CORPUS:
        for l in (ROOT / rel).read_text(encoding="utf-8").split("\n"):
            if l.strip():
                (br if cb.BRANDS.search(l) else nb).append(len(l))
    ratio = st.median(br) / max(1, st.median(nb))
    v = _k(_k(pre, "冻结输入集"), "但「最有利」与「更长」混在一起")
    assert "%.1f 倍" % ratio in v, "★ 长度比与现算不符, 应为 %.1f" % ratio
    assert "分不开" in v and "不得说是因为「有对象」" in v, "★★★ 必须限制上界成因的读法"


def test_子总体是上界_且上界多松没测这件事要写明():
    pre = _pre()
    if not pre:
        return
    inp = _k(pre, "冻结输入集")
    assert "最有利" in _k(inp, "这是个上界不是总体率")
    assert "没有测" in _k(inp, "上界有多松")


def test_首次外发真实语料必须披露且带量():
    pre = _pre()
    if not pre:
        return
    g = _gen()
    v = _k(pre, "首次把真实语料送到外部模型")
    assert "第一次" in _k(v, "★事实")
    tot = sum(i["n_chars"] for i in _k(pre, "冻结输入集")["items"])
    assert str(tot) in _k(v, "★范围"), "★ 必须写明实际外发多少字符, 不能只说「不发整份」"


def test_不得做的事必须点名已否决与已知混淆():
    pre = _pre()
    if not pre:
        return
    blob = " ".join(_k(pre, "不得做的事"))
    for w in ("看过结果再改", "r4", "60%", "子总体", "机制未识别", "硬上限"):
        assert w in blob, "★ 「不得做」里缺 %r" % w


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("预注册 v2 闸 %d 项全过" % n)
