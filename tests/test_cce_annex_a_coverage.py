# -*- coding: utf-8 -*-
"""合同条款对照(附件 A 可观察性)的闸。

★★★ 本文件守的第一件事**不是**读数好不好, 而是: **补这两对没有动到任何冻结件**。
  r4 花了 20 次真实调用, 它的三臂对照(金标/零基线/模型)建立在
  tests/data/claim_frame_annotations.json(sha8 5a018edd) 与 pairs 那 10 对之上。
  往里加用例 = **事后改已付费那一轮的基准**。
"""
import difflib, hashlib, importlib.util, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
PAIRS = ROOT / "tests/data/semantic_minimal_pairs.json"
GOLD = ROOT / "tests/data/claim_frame_annotations.json"
RES = ROOT / "results/annex_a_coverage.json"
PROBE = ROOT / "probes/annex_a_coverage.py"

# ★ r4 预注册(tests/data/slot_filling_prereg_r4.json)钉死的金标哈希
R4_GOLD_SHA8 = "5a018edd"
# ★ 补 contract_pairs **之前** pairs 那 10 对的内容哈希(规范化 JSON, 2026-09-15 记)
PAIRS10_SHA16 = "cd9a06844cc6226d"
# ★★★ 2026-09-15 补(280-agent 评审抓到): ANX 两对的 frames 是**它们自己的金标**,
#   而在此之前**全仓没有任何哈希钉死它** —— 我在 r5 草案里写「ANX 2 对的标注已冻结且已被闸把住」,
#   **那句话当时是假的**。这是本项目第五次「假保证」, 与 r4 预注册记下的
#   「改金标一格, 原来的 14 道闸一道都没响」是**同型**。
# ★ 2026-09-15 第三次更新: contract_pairs 由 2 对扩到 **6 对**(ANX-3..6), 并把 ANX-2/4/6 的 pos
#   改成系动词句以压低 token 规则的净增益。**这次调整是在看过 best_shallow_rule_search 结果之后做的**,
#   方向是**让实验更难**(让浅层规则更差), 已在数据里逐条登记。
# ★★★ 2026-09-15 第四次: contract_pairs **整体重造为 24 对**(v1 的 6 对已撤回并留档)。
#   原因: v1 全是「X is Y」教科书式定义句, 与真实证书的复述形态不符 ⇒ 句法共线 ⇒ 门不可达。
# ★★★ 2026-09-15 第五次: 按体检器逐轴对齐(量词/时段/词数), 把 2026-09-15 投料前评审抓到的
#   那条族外零语义正则由「鉴别格 19/24 · 穿过全部前置条件」压到「净增益 −2 · 被挡」。
CONTRACT_PAIRS_SHA16 = "d73477daaac7ce09"


def _d():
    return json.loads(PAIRS.read_text(encoding="utf-8"))


def _res():
    return json.loads(RES.read_text(encoding="utf-8")) if RES.exists() else None


# ───────────────────────── 冻结件不许被碰 ─────────────────────────

def test_r4的金标一个字节都没动():
    got = hashlib.sha256(GOLD.read_bytes()).hexdigest()[:8]
    assert got == R4_GOLD_SHA8, (
        "★★★ 金标 sha8 %s ≠ r4 钉的 %s —— **r4 的对照基准被事后改了**。"
        "补对照对必须走 contract_pairs(自带 frames), 不许往冻结金标里加条目。" % (got, R4_GOLD_SHA8))


def test_那10对语义关系一个字都没动():
    h = hashlib.sha256(json.dumps(_d()["pairs"], ensure_ascii=False,
                                  sort_keys=True).encode()).hexdigest()[:16]
    assert h == PAIRS10_SHA16, (
        "★★★ pairs 那 10 对变了(%s ≠ %s) —— 上界读数 4/10 → 0/10 与 r4 的三臂对照**都建立在它上面**。"
        "要改必须先说清楚那些已付费的读数怎么办。" % (h, PAIRS10_SHA16))


def test_ANX金标被哈希钉死_而不是口头声称():
    """★★★ 我在 r5 草案里写过「ANX 2 对的标注已冻结且已被闸把住」—— **那句话当时是假的**。
    ANX 的六槽位正确答案全在 contract_pairs[*].frames 里, 而在本条之前**没有任何哈希断言碰过它**。
    ⇒ 测量后改一格金标, 一道闸都不会响。这是第五次「假保证」。"""
    h = hashlib.sha256(json.dumps(_d()["contract_pairs"], ensure_ascii=False,
                                  sort_keys=True).encode()).hexdigest()[:16]
    assert h == CONTRACT_PAIRS_SHA16, (
        "★★★ contract_pairs 变了(%s ≠ %s)。它承载 ANX 两对的**金标**与**文本**; "
        "任何改动都必须同时重跑 results/annex_a_coverage.json 与 results/shallow_cue_arm.json, "
        "并在这里更新哈希**且说明为什么允许改**。" % (h, CONTRACT_PAIRS_SHA16))


def test_v1对照集的撤回必须留档_不许悄悄换掉():
    """★★★ 2026-09-15: contract_pairs 由 6 对**整体重造为 24 对**。
    v1 那 6 对**全部**是「X is Y」教科书式定义句, 与真实证书的复述形态不符 ⇒ 句法共线 ⇒ 门不可达。
    ★ 换掉可以, **但不许悄悄换** —— 历史读数(annex_a_coverage / shallow_cue_arm)建立在它们上面。"""
    d = _d()
    k = [x for x in d if "contract_pairs_v1" in x and "已撤回" in x]
    assert k, "★★★ v1 的 6 对被换掉了却没留档"
    v = d[k[0]]
    assert len(v["pairs"]) == 6, "★ 撤回档案里应有原样的 6 对"
    why = v["★为什么撤回"]
    assert "定义句" in why and "净 +5" in why and "净 0" in why, (
        "★★★ 撤回理由必须带**两个实测数**: 冻结族在 v1 上净 +5 vs 在**真实证书**上净 0")
    assert "不删除" in json.dumps(v, ensure_ascii=False)


def test_新对照集必须分调整集与留出集():
    """★★★ 「我造对照集 → 搜索器找线索 → 我再改」没有停止规则 ⇒ 必须留出一批不迭代的。"""
    cp = _d()["contract_pairs"]
    g = {}
    for p in cp:
        g[p["★分组"]] = g.get(p["★分组"], 0) + 1
    assert set(g) == {"调整集", "留出集"}, "★ 分组缺失: %r" % g
    assert g["留出集"] >= 6, "★ 留出集太小(%d), 定 p0 时没有统计意义" % g["留出集"]
    body = _d()["★★★contract_pairs 是什么_为什么不并进 pairs"]
    assert "留出集只搜一次" in body and "调整集确实被拟合了" in body, (
        "★★★ 必须写明**留出集 p0 高于调整集** —— 那是拟合发生过的证据, 也是 p0 取留出集那个的理由")
    assert "锚点来自**真实证书**" in body and "没有停止规则" in body


def test_上界探针不读contract_pairs_所以上界读数不受影响():
    """★ 这是「不受影响」的**机械证明**, 不是口头保证。"""
    src = (ROOT / "probes/claim_frame_upper_bound.py").read_text(encoding="utf-8")
    assert "contract_pairs" not in src, (
        "★★★ 上界探针一旦读了 contract_pairs, 上界读数的分母就会变 ⇒ r4 的对照基准跟着变")
    # ★★★ 2026-09-17 修(三项决策调研抓到的灵敏度缺口):
    #   原写法读的是**存盘的 results JSON**, 不是现算 ⇒ 若判据层被改而**没重跑探针**, 这道闸不会响。
    #   实测: 在镜像上把 NOT_OF_DECLARED_KIND 升为合同档, 重跑探针 → 4 红; **不重跑 → 只有 3 红**,
    #   少的那一条正是这里。⇒ 改成**现算比对**(照 test_产物由探针现算_不许手写 的写法)。
    ub = ROOT / "results/claim_frame_upper_bound.json"
    if ub.exists():
        spec2 = importlib.util.spec_from_file_location(
            "ubprobe", ROOT / "probes/claim_frame_upper_bound.py")
        ubm = importlib.util.module_from_spec(spec2)
        import io, contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            spec2.loader.exec_module(ubm)
        t = json.loads(ub.read_text(encoding="utf-8"))["★★★合计"]
        assert t["只用合同明文"] == "4/10" and t["明文+解释"] == "0/10", (
            "★★★ 上界读数变了: %r —— 它应当**逐字不变**" % t)
        # ★ 现算一遍判据层在这 10 对上的行为, 与存盘值比 —— 存盘值过期时立刻红
        import cce_claim_frame as _CF
        ann = json.loads((ROOT / "tests/data/claim_frame_annotations.json").read_text(encoding="utf-8"))
        D = ann["★默认槽位"]
        pr = {p_["id"]: p_ for p_ in _d()["pairs"]}
        leak = {"只用合同明文": 0, "明文+解释": 0}
        for pid, e in ann["annotations"].items():
            fr = []
            for key, conj in (("A", _CF.CONJ_P), ("B", _CF.CONJ_Q)):
                kw = dict(D, **e["frames"]["neg"][key])
                src = pr[pid]["neg"]
                fr.append(_CF.ClaimFrame(
                    src[key][0], conj, object=src[key][1],
                    predicate=kw["predicate"], speaker=kw["speaker"], polarity=kw["polarity"],
                    time=kw["time"], citation=kw["citation"], possession=kw["possession"],
                    increment_kind=(src[key][2] if key == "A" else None)))
            for tier, ui in (("只用合同明文", False), ("明文+解释", True)):
                leak[tier] += bool(_CF.allow_label(fr, use_interpretation=ui)["allow"])
        n = len(ann["annotations"])
        for tier in leak:
            assert t[tier] == "%d/%d" % (leak[tier], n), (
                "★★★ 存盘的上界 %s=%s 与**现算** %d/%d 不符 —— "
                "判据层被改过而探针没重跑。这道闸以前读存盘值, 就是在这里失灵的。"
                % (tier, t[tier], leak[tier], n))


# ───────────────────────── 对照对本身合规 ─────────────────────────

def test_两对结构合规_且差异最小():
    cp = _d()["contract_pairs"]
    assert len(cp) >= 2, "★ 一对只测得到一种复述形态"
    for p in cp:
        for side in ("pos", "neg"):
            t = p[side]["text"]
            for k in ("A", "B"):
                sp, ob = p[side][k][0], p[side][k][1]
                assert sp in t, "★%s.%s.%s span 非逐字" % (p["id"], side, k)
                assert ob in t, "★%s.%s.%s object 非逐字" % (p["id"], side, k)
        a, b = p["pos"]["text"].split(), p["neg"]["text"].split()
        ops = [o for o in difflib.SequenceMatcher(None, a, b).get_opcodes() if o[0] != "equal"]
        w = sum(max(o[2] - o[1], o[4] - o[3]) for o in ops)
        assert len(ops) <= 2 and w <= 6, (
            "★★★ %s 差异过大(%d 区 %d 词) —— 放行与否就不能归因于「增量是否成立」" % (p["id"], len(ops), w))


def test_标注差异只有predicate一格():
    """★★★ 若两版标注差了不止一格, 拦住 neg 的可能是**别的槽位**, 这两对就测不到附件 A。"""
    for p in _d()["contract_pairs"]:
        f = p["frames"]
        assert f["pos"]["B"] == f["neg"]["B"], "★ %s 的 Q 支标注两版应完全相同" % p["id"]
        diff = {k for k in set(f["pos"]["A"]) | set(f["neg"]["A"])
                if f["pos"]["A"].get(k) != f["neg"]["A"].get(k)}
        assert diff == {"predicate"}, "★★★ %s A 支标注差异应只有 predicate, 实为 %r" % (p["id"], diff)
        assert f["neg"]["A"]["predicate"] == "RESTATES_IDENTIFIER", (
            "★ %s neg 版应标 RESTATES_IDENTIFIER(附件 A 那一条)" % p["id"])


def test_依据必须标合同明文_因为附件A已升():
    for p in _d()["contract_pairs"]:
        assert p["依据"] == "**合同明文**", (
            "★ %s: 附件 A 已于 2026-09-14 升为合同, 依据不该再标解释" % p["id"])
        assert "附件 A" in p["推导"] or "公开标识" in p["推导"], "★ %s 推导没说清依据" % p["id"]
        assert [x for x in p if "验证器为什么看不见" in x], "★ %s 没写验证器为什么看不见" % p["id"]


# ───────────────────────── 读数与灵敏度 ─────────────────────────

def test_结果由冻结判据现算_不许手写():
    r = _res()
    if not r:
        return
    import importlib.util, sys
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("annexcov", PROBE)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    import cce_claim_frame as CF
    _rows, tot = m.run(_d()["contract_pairs"], CF)
    assert r["★★★合计"] == tot, "★★★ 档案合计 %r 与现算 %r 不符" % (r["★★★合计"], tot)


def test_两档必须相同_否则判据没把附件A当合同():
    r = _res()
    if not r:
        return
    t = r["★★★合计"]
    assert t["只用合同明文_错误放行"] == t["明文+解释_错误放行"], (
        "★★★ 两档不同 ⇒ 拦住它的其实是**解释档**规则, 附件 A 并没有被当成合同明文: %r" % t)
    assert t["只用合同明文_错误放行"].startswith("0/"), "★ 附件 A 已升合同, 明文档就该拦住: %r" % t


def test_对照必须有效_否则测不出东西():
    r = _res()
    if not r:
        return
    t = r["★★★合计"]
    n = t["明文+解释_对照有效"].split("/")[1]
    assert t["明文+解释_对照有效"] == "%s/%s" % (n, n), (
        "★★★ pos 版被误拦 ⇒ 这两对什么都测不出, 0 漏是**一刀切**换来的: %r" % t)


def test_现有资格层对照基线必须在():
    """★ 没有基线就不知道这两对是不是**本来就好过** —— 那样 0/2 是白给的。"""
    r = _res()
    if not r:
        return
    b = r["★对照基线(现有资格层_形式验证)"]
    n = len(_d()["contract_pairs"])      # ★ 现算, 不许硬编码分母(2026-09-15 已因此过期两次)
    assert b["错误放行"] == "%d/%d" % (n, n), (
        "★★★ 现有资格层必须**全漏** —— 漏不满说明形式验证已经拦得住一部分, "
        "新判据在那几对上的 0 **不构成增量**: %r (n=%d)" % (b, n))
    assert b["对照有效"] == "%d/%d" % (n, n), "★ 对照必须全有效, 否则那几对什么都测不出: %r" % b


def test_变异实测必须现跑_且全部被抓到():
    r = _res()
    if not r:
        return
    k = [x for x in r if "镜像变异实测" in x][0]
    assert "现跑" in k, "★ 变异结论必须现跑 —— 手写的会在判据变化后悄悄过期"
    mut = r[k]
    assert len(mut) >= 3, "★ 变异太少"
    # ★★★ 闸**自己重跑一遍**变异 —— 只查档案里写着「被抓到」等于信任手写结论
    import importlib.util, sys
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("annexcov_m", PROBE)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    import cce_claim_frame as CF
    pairs = _d()["contract_pairs"]
    _rows, base = m.run(pairs, CF)
    live = m.mutate(pairs, base)
    assert set(live) == set(mut), "★★★ 档案的变异清单与现跑不符: %r vs %r" % (sorted(mut), sorted(live))
    for name, v in live.items():
        assert v.startswith("被抓到"), "★★★ 变异「%s」现跑结果 → %s" % (name, v)
        assert mut[name] == v, "★★★ 「%s」档案写 %r, 现跑 %r —— 结论是手写的" % (name, mut[name], v)
    key = [x for x in mut if "降回解释档" in x]
    assert key, "★★★ 缺最要紧那条变异(把附件 A 降回解释档 = 模拟裁定被撤销)"
    assert "只用合同明文_错误放行" in mut[key[0]], (
        "★★★ 撤销裁定必须让**只用合同明文**那一档回到漏 —— 否则这套对照测的不是附件 A")
    assert [x for x in mut if "恒拦" in x], (
        "★★★ 缺「恒拦」变异 —— 只报漏数不报对照, 任何一刀切都能拿满分")


# ───────────────────────── 边界不许被读错 ─────────────────────────

def test_产物写明这不是模型能做到_r4枚举里根本没这个取值():
    r = _res()
    if not r:
        return
    body = json.dumps(r, ensure_ascii=False)
    assert "RESTATES_IDENTIFIER" in body and "无从填出" in body, (
        "★★★ 必须写明 r4 的提示词枚举里**没有** RESTATES_IDENTIFIER ⇒ 模型在 r4 里无从填出它。"
        "否则半年后有人会把这份 0/2 读成「模型能分辨复述与增量」")
    assert "上界" in body and "端到端" in body
    assert "未接进生产" in body


def test_那10对上仍然零覆盖这件事不许被抹掉():
    """★★★ 补在别处**不等于**补上了。原登记的事实仍然成立, 不许因为「已补」就撤销它。"""
    d = _d()
    k = [x for x in d if "附件 A" in x and "零覆盖" in x]
    assert k, "★ 零覆盖登记被删了"
    v = d[k[0]]
    assert "contract_pairs" in v and "补在别处" in v, "★ 登记没说补在哪"
    assert "依然零覆盖" in v and "4/10" in v, (
        "★★★ 必须写明: `pairs` 那 10 对上附件 A **依然零覆盖**, 上界仍是 4/10 → 0/10。"
        "把「补在别处」写成「已解决」就是虚报覆盖面")


def test_probe零调用():
    src = PROBE.read_text(encoding="utf-8")
    for bad in ("call_model", "MINIMAX", "requests.post", "_load_key"):
        assert bad not in src, "★★★ 合同条款对照里出现模型调用入口 %r" % bad


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("附件 A 可观察性闸 %d 项全过" % n)
