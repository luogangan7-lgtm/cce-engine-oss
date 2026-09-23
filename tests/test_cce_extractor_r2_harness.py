# -*- coding: utf-8 -*-
"""r2 **执行器**闸 —— 上一版最大的漏洞就是没有这个文件。

★★★ 2026-09-14 独立评审的原话(已复核属实): 上一版的 10 项设计自检
「只读 templates_r2.json 与 prereg_r2.json 两个 JSON …… 全仓没有任何测试覆盖执行器。
 所以『r2 设计自检全绿』是**假保证**: 绿灯和协议有没有落到代码里完全无关,
 正好会让人以为可以投料。」

本文件核的是**代码**: 冻结的提示词、规范化的边界、三层记账的可达性,
以及用 r1 **已付费的真实输出**回放(库内铁律: 自检样本必须经由真实采集流程产出,
不是手填好再喂给判据)。
"""
import hashlib, importlib.util, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
P = ROOT / "tests/data/extractor_counterexample_prereg_r2.json"
T2 = ROOT / "tests/data/extractor_counterexample_templates_r2.json"
T1 = ROOT / "tests/data/extractor_counterexample_templates.json"
R1 = ROOT / "results/extractor_counterexample.json"


def _mod():
    spec = importlib.util.spec_from_file_location(
        "r2run", ROOT / "probes/extractor_counterexample_run_r2.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _tpl(p):
    return {t["id"]: t for t in json.loads(p.read_text(encoding="utf-8"))["templates"]}


def test_运行时提示词与预注册冻结的那份逐字相同():
    """★ 「提示词里不许泄露比较规则」这条规则, 必须有一个**被约束的对象**。"""
    d = json.loads(P.read_text(encoding="utf-8"))
    frozen = d["★★★prompt(逐字冻结)"]
    live = _mod().PROMPT
    assert live == frozen["text"], (
        "★★★ 运行时提示词与预注册冻结的不一致 —— 冻结就失效了\n"
        "  冻结 sha %s\n  运行 sha %s"
        % (frozen["sha256_8"], hashlib.sha256(live.encode()).hexdigest()[:8]))
    assert hashlib.sha256(live.encode()).hexdigest()[:8] == frozen["sha256_8"]


def test_提示词没有泄露比较规则():
    d = json.loads(P.read_text(encoding="utf-8"))
    live = _mod().PROMPT
    for bad in d["★★★prompt(逐字冻结)"]["★不许出现的话(泄露比较规则)"]:
        assert bad not in live, "★★★ 提示词泄露了比较规则: %r" % bad
    assert "不要为了凑成一致" not in live and "凑成一致" not in live, (
        "★ r1 那句反向暗示又回来了 —— 反向暗示同样是把答案递给被测方")


def test_提示词没有把增量种类列成选项菜单():
    """★ r1 把 INCREMENT_KINDS 原样列成菜单 ⇒ 该闸期望与实际同源, 恒真。"""
    import cce_label_qualification as LQ
    m = _mod()
    menu = "|".join(LQ.INCREMENT_KINDS)
    assert menu not in m.PROMPT, "★★★ 五类又被列成选项菜单了(%r) ⇒ kind 闸恒真" % menu
    # ★ 模板本身不含那五个词; 它们**只**经由判别式原文在渲染时进入上下文
    #   —— 那是被核验的合同, 必须给它看。核渲染后的那一份。
    assert not any(k in m.PROMPT for k in LQ.INCREMENT_KINDS), (
        "★ 提示词模板**自己**含增量种类词 ⇒ 又把菜单递给了被测方")
    rendered = m.PROMPT % (m.DISC, "some text")
    hits = [k for k in LQ.INCREMENT_KINDS if k in rendered]
    assert len(hits) == len(LQ.INCREMENT_KINDS), (
        "★ 渲染后五个词应当全在(经由判别式原文), 现只有 %r —— 判别式没完整传进去" % hits)
    assert m.DISC == json.loads(T2.read_text(encoding="utf-8"))[
        [k for k in json.loads(T2.read_text(encoding="utf-8")) if k.startswith("★合同原文")][0]], (
        "★ 执行器用的判别式与模板档案里冻结的那份不是同一份")


def test_规范化只做三件事_边界已反向验证():
    N = _mod().normalize_about
    assert N("the loaner ReSound Nexia (personally worn)") == N("the loaner ReSound Nexia"), (
        "★ r1 的实测拦点没被消除: 两半写了同一个名字, 只因尾部括注被判成两个对象")
    for a, b, what in [("Oticon More 1", "Oticon More", "别名归并"),
                       ("Battery on the Oticon More 1", "the Oticon More 1", "子串包含"),
                       ("hearing aids", "hearing aid", "词干还原"),
                       ("Phonak Audeo Sphere", "something far simpler", "语义相似")]:
        assert N(a) != N(b), "★★★ 规范化越界做了%s ⇒ 它变成了「放松 P2」" % what


def test_规范化不放松对象错配臂():
    N = _mod().normalize_about
    for t in _tpl(T2).values():
        if t["arm"] != "对象错配阴性":
            continue
        for pre in ("", "the ", "my ", "that ", "The "):
            assert N(pre + t["about_P"]) != N(pre + t["about_Q"]), (
                "★★★ %s 的两个对象在规范化后被归成一个 —— 那一格就没了" % t["id"])


def _cert(t, pa, pb, kind="数据"):
    return {"supported": True, "evidence": [
        {"span": pa[0], "supports": "A", "object": pa[1], "increment_kind": kind},
        {"span": pb[0], "supports": "B", "object": pb[1], "increment_kind": None}]}


def test_结局分类法每一格都可达():
    """★★★ 非空性自检。前两次栽的都是「某一支结构上恒真或恒假」, 这里逐格验。"""
    m = _mod()
    T = _tpl(T2)
    P1 = T["POS-1"]
    ok = (("The Oticon More 1 gives me about 14 hours on a charge", "The Oticon More 1"),
          ("The Oticon More 1 has been mine since last spring", "The Oticon More 1"))
    g = lambda t, c: m._judge(t, c)[0]

    assert g(P1, _cert(P1, *ok)) == m.UPGRADED, "★ 对照结构上通不过 ⇒ 又是 DEGENERATE"
    assert g(P1, {"supported": False, "why_not": "x"}) == m.REFUSED_OTHER
    assert g(P1, _cert(P1, (ok[0][0], "电池续航"), ok[1])) == m.MALFORMED
    assert g(P1, _cert(P1, *ok, kind="型号")) == m.MALFORMED, "★ kind 枚举外应判 MALFORMED"
    # ★ 附件 A: 只复述型号名 ⇒ COVERAGE_FAIL。必须在**原样**上算,
    #   吃了规范化的红利就会变成 UPGRADED, 从而**伪造**出终局判决。
    assert g(P1, _cert(P1, ("The Oticon More 1", "The Oticon More 1"), ok[1], kind="具体型号")) \
        == m.COVERAGE_FAIL, "★★★ 规范化又把附件 A 那道闸打穿了"
    # supports 全填 A ⇒ missing 分支可达
    assert g(P1, {"supported": True, "evidence": [
        {"span": ok[0][0], "supports": "A", "object": ok[0][1], "increment_kind": "数据"},
        {"span": ok[1][0], "supports": "A", "object": ok[1][1], "increment_kind": "数据"}]}) \
        == m.COVERAGE_FAIL
    # ★ r1 的死因形态(逐字方面名词)必须被认成 GRANULARITY, 不能混进 DISTINCT
    assert g(P1, _cert(P1, (ok[0][0], "a charge"), ok[1])) == m.GRANULARITY, (
        "★★★ r1 同因的通道故障被混成了「真·不同对象」⇒ 降级条件 D1 会失灵")
    m1 = T["MIS-1"]
    honest = _cert(m1, ("gets 16 hours on a charge with streaming", "Phonak Audeo Sphere"),
                   ("I wear something far simpler myself", "something far simpler"))
    lying = _cert(m1, ("gets 16 hours on a charge with streaming", "Phonak Audeo Sphere"),
                  ("I wear something far simpler myself", "Phonak Audeo Sphere"))
    assert g(m1, honest) == m.DISTINCT, "★ 错配臂诚实作答应判 DISTINCT"
    assert g(m1, lying) == m.UPGRADED, "★ 撒谎凑成一致就是一次错误升格见证"
    # 承重臂: 缺P 上的错误升格**必须可达**
    n1 = T["NEGP-1"]
    assert g(n1, _cert(n1, ("wearing hearing aids for a good while now", "hearing aids"),
                       ("I've been wearing hearing aids", "hearing aids"),
                       kind="使用细节")) == m.UPGRADED, (
        "★★★ 缺P阴性上的错误升格结构上不可能 ⇒ 本轮承重的那一臂是死的")


def test_拒答的读法_命名对了与没命名对分得开():
    """★★★ 在阴性上**正确拒答就是期望行为**。r1 把它压成「未交卷」并触发降级,
    那条规则要求模型在 12 条构造阴性上主动断言 display 成立 >=4 次才算可读 ——
    而 r1 先验是 1/12 ⇒ **把最好的结局判成了不可读**。已撤销并留档。"""
    m = _mod()
    T = _tpl(T2)
    q1 = T["NEGQ-1"]
    assert m._judge(q1, {"supported": False,
                         "why_not": "从未 owned or tried, 不满足自己已拥有或已经历"})[0] \
        == m.REFUSED_RIGHT
    assert m._judge(q1, {"supported": False, "why_not": "没有具体型号和数据"})[0] == m.REFUSED_OTHER
    assert m._judge(q1, {"supported": False})[0] == m.REFUSED_OTHER
    d = json.loads(P.read_text(encoding="utf-8"))
    rm = d["★★★决策规则(测量前冻结)"]["★★★被撤销的那条降级规则(留档)"]
    assert "1/12" in rm["★为什么撤"] and "零调用" in rm["★撤销时点"], (
        "★ 撤销一条冻结规则必须写明理由与**撤销时点是零调用** —— 否则读起来像看着结果改判据")


def test_规范化不许抹平物主标记():
    """★ 第二轮评审抓到: 原表含 my/his/their ⇒「my X」与「his X」被抹成同一个对象,
    而 Q 支要的正是**自己的** —— 那等于用规范化把被测的那一支抹掉了。"""
    N = _mod().normalize_about
    for a, b in [("my Oticon More 1", "his Oticon More 1"), ("my aids", "their aids"),
                 ("that pair", "this pair")]:
        assert N(a) != N(b), "★★★ 规范化抹平了 %r / %r 的区别" % (a, b)
    assert N("the Oticon More 1") == N("Oticon More 1") == "Oticon More 1"


def test_从零重写有可机器核的不变量():
    """★ 原来的闸只 grep 档案里「从零重写」那句声明 —— 可机器证伪的假声明。
    真不变量: r1 模型**实际选中的 span** 一个都不得逐字存活在 r2 对照文本里。"""
    if not R1.exists():
        return
    T2d, T1d = _tpl(T2), _tpl(T1)
    alive = []
    for row in json.loads(R1.read_text(encoding="utf-8"))["rows"]:
        mo = row["模型原样"]
        if not (isinstance(mo, dict) and mo.get("supported")) or row["arm"] != "正证据对照":
            continue
        for k in ("increment", "owned_or_experienced"):
            sp = (mo.get(k) or {}).get("span")
            if sp and sp in T2d[row["id"]]["text"]:
                alive.append((row["id"], k, sp[:50]))
    assert not alive, (
        "★★★ r1 模型的作答仍逐字存活在 r2 对照文本里: %r\n"
        "  —— 那正是被评审点名的坏做法(拿受试者上一轮的作答改考题)" % alive)


def test_每条阴性都声明了构造规则说哪一支失败():
    for t in _tpl(T2).values():
        if t["arm"] == "正证据对照":
            continue
        v = t.get("★构造规则声明失败的那一支")
        assert v in ("P", "Q", "SAME_OBJECT"), "★ %s 没声明失败支" % t["id"]


def test_型号名重复不再与臂身份共线():
    """★ 原设计里「型号名出现两次」与臂身份 4/4 vs 0/12 完全共线 ⇒
    一个纯句法启发式(找重复字符串)能拿满分而不做任何语义判断。"""
    T = _tpl(T2)
    def twice(t):
        n = t.get("★可共享的逐字对象名") or t.get("about_P") or t.get("about") or ""
        return bool(n) and t["text"].count(n) >= 2
    neg_twice = [k for k, t in T.items() if t["arm"] != "正证据对照" and twice(t)]
    assert neg_twice, (
        "★★★ 没有任何阴性含重复型号名 ⇒ 「找重复字符串」这个纯句法策略能拿到 "
        "4/4 对照 + 0/12 阴性, 看起来完美却没做任何语义判断")


def test_p_challenge分母不含失败调用():
    src = (ROOT / "probes/extractor_counterexample_run_r2.py").read_text(encoding="utf-8")
    assert 'pred(r) and r["调用成功"]' in src, (
        "★ _tally 没有过滤失败调用 —— 失败会被算成「完成测试的阴性」")


def _rows(*spec):
    """合成 rows: (臂, 结局, 条数) —— 用来**真跑** summarize(), 不 grep 源码。"""
    m = _mod()
    out = []
    for arm, oc, k in spec:
        for _ in range(k):
            out.append({"arm": arm, "outcome": oc, "Z": 1 if oc == m.UPGRADED else 0,
                        "调用成功": True})
    return out


def test_降级是行为闸_不是源码grep():
    """★★★ 第三次「假保证」: 独立审计把仓镜像出去, 把四条降级改成 no-op、
    把 p_challenge 分母篡改成含 MALFORMED, **27 道闸一道都没响** ——
    守这块的三道全是 `assert <字面量> in src`。
    grep 证明的是「这行字还在」, 不是「这个行为还对」。这里改成**真跑 summarize()**。"""
    m = _mod()
    S = m.summarize                       # 记账全在这一个函数里, 变异它必然被下面抓到

    # D1 粒度失配过半 ⇒ 与 r1 同因的仪器伪影
    r = S(_rows(("正证据对照", m.UPGRADED, 4), ("缺P阴性", m.GRANULARITY, 3),
                ("缺P阴性", m.DISTINCT, 1)))
    assert any(x.startswith("D1") for x in r["降级"]), "★★★ D1 没响"

    # D2 格式层失效
    r = S(_rows(("正证据对照", m.UPGRADED, 4), ("缺P阴性", m.MALFORMED, 3),
                ("缺P阴性", m.DISTINCT, 1)))
    assert any(x.startswith("D2") for x in r["降级"]), "★★★ D2 没响"

    # D3 无差别拒答
    r = S(_rows(("正证据对照", m.UPGRADED, 4), ("缺P阴性", m.REFUSED_OTHER, 3),
                ("缺P阴性", m.REFUSED_RIGHT, 1), ("否定Q阴性", m.DISTINCT, 1)))
    assert any(x.startswith("D3") for x in r["降级"]), "★★★ D3 没响"

    # D4 零裁决
    r = S(_rows(("正证据对照", m.UPGRADED, 4), ("缺P阴性", m.REFUSED_RIGHT, 12)))
    assert any(x.startswith("D4") for x in r["降级"]), "★★★ D4 没响"

    # ★★★ D5: 对照死在格式/粒度层 ⇒ **不计为**第二次退化。
    #   没有它, 一次仪器故障会去触发「这条路不可行」的终局结论。
    r = S(_rows(("正证据对照", m.MALFORMED, 4), ("缺P阴性", m.REFUSED_RIGHT, 12)))
    assert r["verdict"] == "DEGENERATE_ON_CONTROLS"
    d5 = [x for x in r["降级"] if x.startswith("D5")]
    assert d5 and "不计为" in d5[0] and "终局" in d5[0], (
        "★★★ 对照整批死在格式层却不挂 D5 ⇒ 会把仪器故障读成路线终局结论")

    # ★ D6: 逐臂零裁决也要报 —— 合计非零会掩盖承重臂的零
    r = S(_rows(("正证据对照", m.UPGRADED, 4), ("缺P阴性", m.REFUSED_RIGHT, 4),
                ("否定Q阴性", m.REFUSED_RIGHT, 4), ("对象错配阴性", m.DISTINCT, 4)))
    d6 = [x for x in r["降级"] if x.startswith("D6")]
    assert any("缺P阴性" in x for x in d6), (
        "★★★ 承重臂一次没被裁决过却不报 ⇒ 合计 0/4 会被读成「干净」")

    # ★ 一个各方面健康、且承重臂真被裁决过的轮次: verdict 可单独读
    r = S(_rows(("正证据对照", m.UPGRADED, 4), ("缺P阴性", m.DISTINCT, 4),
                ("否定Q阴性", m.DISTINCT, 4), ("对象错配阴性", m.DISTINCT, 4)))
    assert not r["降级"] and r["最终判读"] == "NO_COUNTEREXAMPLE_IN_THIS_SUITE", (
        "★ 降级条件过紧: 一个健康轮次也被降级, 那降级就成了万能台阶 —— 实际: %r" % r["降级"])


def test_p_challenge分母是被裁决过的_行为核():
    """r1 的 0/12 里实际只有 1 次被资格层裁决过。分母必须是**被裁决过的**。"""
    m = _mod()
    r = m.summarize(_rows(("正证据对照", m.UPGRADED, 4),
                          ("缺P阴性", m.REFUSED_RIGHT, 3), ("缺P阴性", m.UPGRADED, 1)))
    assert r["逐臂"]["缺P阴性"]["★p_challenge(分母=被裁决过的)"] == "1/1", (
        "★★★ 分母把拒答也算进去了 —— 实际 %r"
        % r["逐臂"]["缺P阴性"]["★p_challenge(分母=被裁决过的)"])
    # MALFORMED **不得**进分母(它是格式失败, 不是资格层裁决)
    r2 = m.summarize(_rows(("正证据对照", m.UPGRADED, 4),
                           ("缺P阴性", m.MALFORMED, 3), ("缺P阴性", m.UPGRADED, 1)))
    assert r2["逐臂"]["缺P阴性"]["★p_challenge(分母=被裁决过的)"] == "1/1", (
        "★★★ MALFORMED 被算进了 p_challenge 分母 —— 那个 0 说的就成了形式不是语义")


def test_产物必须自带怎么读():
    """★ r1 的产物带过「怎么读这个判决」, r2 初版丢了。
    半年后只读结果文件、不读预注册的人, 拿到的就是那份文件。"""
    src = (ROOT / "probes/extractor_counterexample_run_r2.py").read_text(encoding="utf-8")
    for k in ("★★★不得据此说", "★★★已知局限", "★★★承重臂是哪一臂", "★★★拒答怎么读",
              "★★★结局分类法"):
        assert k in src and "res = {" in src, "★★★ 产物没带 %s ⇒ 未来读者读不到" % k
    assert src.index("★★★最终判读") < src.index("★★★verdict(原始"), (
        "★ 最终判读必须排在原始 verdict **前面** —— 顺序就是读法")


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("r2 执行器闸 %d 项全过 —— ★这一次绿灯**确实**和协议落没落到代码里有关" % n)
