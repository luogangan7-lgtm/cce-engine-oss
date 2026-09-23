# -*- coding: utf-8 -*-
"""真实语料小批试的**预注册生成器**。零调用。v2

★★★ v1 被 8 维 × 22 agent 的零调用对抗评审打回, **九条实缺陷逐条自核属实**:
  A 拒绝域按 n=42 定却套在 n_ok 上(全失败 ⇒ 自信判 TRANSFERS_NOT)  [BLOCKING]
  B 判别式声称来自冻结生产件, 实际取自模板文件                      [MAJOR]
  C 交卷判定两边不同(等价性证明用真值, 执行器用 is True)            [MAJOR]
  D _kind_tally 对非字符串 kd 抛 TypeError —— 在**全部调用之后、写盘之前**(r5-v3 原样重演) [BLOCKING]
  E 模型自由文本(increment_kind)被逐字写进产物 —— 破隐私不变量       [MAJOR]
  F 硬上限 50 > 条数 42 ⇒ 永不触发, 从未被测过                      [MINOR]
  G 提示词 sha 只在预注册时算, 执行时不再验                          [MAJOR]
  H 两样本长度差 3.2 倍, 26/42 比最长模板还长 —— 混淆未披露          [BLOCKING]
  I 底数 10/31 是**同 16 个模板测两轮**(伪重复), 有效 n 被高估       [MAJOR]

★★★ 投料**之前**冻结。之后一个字不许改 —— 看过结果再改判据就是调参。
★ 隐私: 只登记 (文件, 行号, 行 sha256, 字符数), **不写一个字的语料原文**。
"""
import hashlib, importlib.util, json, pathlib, re, statistics, sys
from math import comb

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "tests/data/real_corpus_pilot_prereg.json"
CORPUS = ["corpus/reddit_hearingaids_audience_v2.txt",
          "corpus/reddit_hearingaids_utterances.txt"]
HAND = ["results/extractor_counterexample_r2.json", "results/repeat_measure_r3.json"]
BUDGET_CAP = 50               # owner 说的 ~50 次; 实际条数由语料决定, 取两者较小
ALPHA = 0.05
TAXONOMY = "config/knot_taxonomy.json"


# ── ★★★ C 的修法: 交卷判定**只有这一个定义**, 两边都用它 ──────────────
def submitted(obj):
    """交卷 ⟺ supported 严格为布尔 True。

    ★ v1 的毛病: 等价性证明用 `bool(...)`(真值), 执行器用 `is True`(严格)。
      模型回 "true"(字符串) 或 1 时两者不同, 而**漂移只会单向压低 k** ⇒ 偏向低臂拒绝。
    ⇒ 现在只留一个定义, 证明与执行**共用这个函数**。
    """
    return obj.get("supported") is True if isinstance(obj, dict) else False


def _models_entry_by_ast(key):
    """从 scripts/exp_crossmodel_desire.py 的源码里读出 MODELS[key] 的常量字段。

    ★ 不 import 那个模块 —— 它顶层 import requests, 而本文件必须保持**无发调用能力**。
    ★ MODELS 整体不是纯字面量(有 os.environ.get), 所以逐字段取, 非常量的字段返回 None。
    """
    import ast
    tree = ast.parse((ROOT / "scripts/exp_crossmodel_desire.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if not (isinstance(node, ast.Assign)
                and any(getattr(t, "id", "") == "MODELS" for t in node.targets)):
            continue
        for k, v in zip(node.value.keys, node.value.values):
            if getattr(k, "value", None) != key:
                continue
            out = {}
            for kk, vv in zip(v.keys, v.values):
                try:
                    out[kk.value] = ast.literal_eval(vv)
                except Exception:
                    out[kk.value] = None      # 非常量(如 os.environ.get) ⇒ 不冻它
            return out
    raise AssertionError("★★★ 源码里找不到 MODELS[%r]" % key)


def _r2():
    s = importlib.util.spec_from_file_location("_r2", ROOT / "probes/extractor_counterexample_run_r2.py")
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def fisher_p(a, b, c, d):
    """两侧 Fisher 精确检验, 2x2 表 [[a,b],[c,d]] —— b 与 d 是**失败数**不是总数。

    ★ 2026-09-17 我在一份临时脚本里把 d 传成了总数, 算出的功效差了近一倍。
      这里把参数含义写死在 docstring 里。
    """
    n, r1, c1 = a + b + c + d, a + b, a + c
    def pr(x): return comb(r1, x) * comb(n - r1, c1 - x) / comb(n, c1)
    lo, hi = max(0, c1 - (n - r1)), min(r1, c1)
    p0 = pr(a)
    return sum(pr(x) for x in range(lo, hi + 1) if pr(x) <= p0 + 1e-12)


def clopper_pearson(k, n, alpha=ALPHA):
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


def frozen_inputs(brands):
    items = []
    for rel in CORPUS:
        for i, line in enumerate((ROOT / rel).read_text(encoding="utf-8").split("\n")):
            if line.strip() and brands.search(line):
                items.append({"file": rel, "line_index": i,
                              "sha256": hashlib.sha256(line.encode()).hexdigest(),
                              "n_chars": len(line)})
    return items


def template_level_baseline(m):
    """★★★ I 的修法: 独立单元是**模板**, 不是调用。

    r2 与 r3 是**同 16 个模板各测一轮**。把它们当 31 个独立样本会高估有效 n,
    让检验**反保守**。这里按模板算每个模板的交卷比例, 再取模板级平均。
    """
    per = {}
    for rel in HAND:
        for r in json.loads((ROOT / rel).read_text(encoding="utf-8"))["rows"]:
            if not r.get("调用成功"):
                continue
            per.setdefault(r["id"], []).append(bool(submitted(r.get("模型原样"))))
    n_unit = len(per)
    mean_p = sum(sum(v) / len(v) for v in per.values()) / n_unit
    k_unit = round(mean_p * n_unit)
    stable = sum(1 for v in per.values() if len(v) > 1 and len(set(v)) == 1)
    flipped = sum(1 for v in per.values() if len(v) > 1 and len(set(v)) > 1)
    return {
        "★独立单元": "**模板**, 不是调用 —— r2 与 r3 是同 %d 个模板各测一轮。" % n_unit,
        "单元数": n_unit,
        "模板级平均交卷率": round(mean_p, 4),
        "k_unit(= 平均率 × 单元数)": k_unit,
        "两轮都有效且一致的模板数": stable,
        "两轮都有效但翻转的模板数": flipped,
        "★★★伪重复的证据": "两轮**都有效**的模板里, **%d 个两轮一致、只有 %d 个翻转** "
                            "⇒ 第二轮几乎不带新信息 ⇒ 把 31 次当独立样本会高估有效 n。"
                            "★ 这两个数是上面两个**结构化字段**, 闸断言的是字段不是这句话。"
                            % (stable, flipped),
        "逐模板(交卷数/有效数)": {k: "%d/%d" % (sum(v), len(v)) for k, v in sorted(per.items())},
        "★合并率作对照(**不用于判决**)": "%d/%d = %.4f"
            % (sum(sum(v) for v in per.values()), sum(len(v) for v in per.values()),
               sum(sum(v) for v in per.values()) / sum(len(v) for v in per.values())),
    }, k_unit, n_unit


def main():
    m = _r2()
    bs = importlib.util.spec_from_file_location("_cb", ROOT / "probes/corpus_balance_audit.py")
    cb = importlib.util.module_from_spec(bs); bs.loader.exec_module(cb)

    items = frozen_inputs(cb.BRANDS)
    N1 = len(items)
    cap = min(BUDGET_CAP, N1)                       # ★ F 的修法: 上限就是实际要跑的条数
    assert N1 <= BUDGET_CAP, "★ 条数 %d 超出 owner 给的 ~%d 次" % (N1, BUDGET_CAP)

    base, K2, N2 = template_level_baseline(m)

    # ★★★ A 的修法: 每一个可能的 n_ok 都事前算出自己的拒绝域, 执行时按实际 n_ok 查表。
    # ★★★★★ 评审二轮抓到的 BLOCKING: v2 的「最低可判 n_ok」取的是**第一个拒绝域非空**的 n,
    #     而那个 n 的拒绝域**只有上尾**。本轮预期的方向是**下尾**(真实语料更难交卷)。
    #     ⇒ 在 n_ok ≤ 12 时, 下尾门槛是 k ≤ -1, **先验不可达** —— 那正是 r5-v1 的死因,
    #       只是搬到了小 n_ok 分支里。判决仍会印 CANNOT_DISTINGUISH 并谎报功效。
    #     ⇒ 最低可判改成「**下尾可达**的最低 n_ok」。
    QGRID = (0.0, 0.02, 0.05, 0.08, 0.10, 0.15, 0.20, 0.25, round(K2 / N2, 4), 0.55, 0.65)
    table, min_any, min_lower = {}, None, None
    power_by_n = {}
    for n in range(0, N1 + 1):
        R = [k for k in range(n + 1) if fisher_p(k, n - k, K2, N2 - K2) < ALPHA]
        if not R:
            table[str(n)] = None
            power_by_n[str(n)] = None
            continue
        p0 = K2 / N2
        lo = max([k for k in R if k / n < p0], default=-1)
        hi = min([k for k in R if k / n > p0], default=n + 1)
        table[str(n)] = {"k ≤": lo, "k ≥": hi if hi <= n else None}
        power_by_n[str(n)] = {("q=%.4f" % q):
                              round(sum(comb(n, k) * q ** k * (1 - q) ** (n - k) for k in R), 4)
                              for q in QGRID}
        if min_any is None:
            min_any = n
        if lo >= 0 and min_lower is None:
            min_lower = n
    min_n = min_lower                      # ★ 门槛用**下尾可达**的那个
    power = power_by_n[str(N1)]

    # ★★★ C: 等价性证明现在用**执行器将要用的同一个函数**
    mism = 0
    for rel in HAND:
        for r in json.loads((ROOT / rel).read_text(encoding="utf-8"))["rows"]:
            if not r.get("调用成功"):
                continue
            if submitted(r.get("模型原样")) != (r.get("outcome") in m.ISSUED):
                mism += 1

    # ★★★ B: 判别式从**冻结生产件**取, 并与 r2 实际用的那份逐字节比对
    tax = json.loads((ROOT / TAXONOMY).read_text(encoding="utf-8"))
    knots = tax["knots"] if isinstance(tax, dict) else tax
    disc_prod = [k["hard_discriminant"] for k in knots
                 if isinstance(k, dict) and k.get("hard_discriminant") == m.DISC]
    assert len(disc_prod) == 1, "★★★ r2 用的判别式在冻结生产件里找不到唯一对应 —— 停手"
    disc_sha = hashlib.sha256(m.DISC.encode()).hexdigest()

    # ★★★ 评审二轮抓到: v2 hash 的是**源码字面量**(带 \\" 转义), 不是真正发出去的串。
    #     两者 sha 不同, 而真串的 sha16 = 7a8f9417 **正是本仓 r3 记录里一直引用的那个**。
    #     ⇒ 冻 m.PROMPT, 不冻源码。
    prompt_sha = hashlib.sha256(m.PROMPT.encode()).hexdigest()

    # ★★★ E: 从冻结生产件的判别式里**机械抠出**五项, 不手打
    mk = re.search(r"新信息增量\*\*\(([^)]*)\)", m.DISC)
    assert mk, "★★★ 判别式里抠不出 increment_kind 枚举 —— 停手"
    KIND_ENUM = [x.strip() for x in mk.group(1).split("/") if x.strip()]
    assert len(KIND_ENUM) == 5, "★ 枚举应为 5 项, 实为 %d: %r" % (len(KIND_ENUM), KIND_ENUM)

    # ★★★ H: 长度差必须量出来写进去
    tpl = json.loads((ROOT / "tests/data/extractor_counterexample_templates_r2.json")
                     .read_text(encoding="utf-8"))["templates"]
    tl = [len(t["text"]) for t in tpl]
    cl = [i["n_chars"] for i in items]
    longer = sum(1 for x in cl if x > max(tl))
    _nb = [len(l) for rel in CORPUS
           for l in (ROOT / rel).read_text(encoding="utf-8").split("\n")
           if l.strip() and not cb.BRANDS.search(l)]
    _n_nobrand, _med_nobrand = len(_nb), statistics.median(_nb)

    # ★★★ (c) 的修法: v1 的事前枚举是按**鉴别格数**列的, 但执行器**没有金标, 根本算不出鉴别格**
    #     —— 那是在预注册一个本轮测不了的量。改成按**交卷数**列(那才是真会测的), 并把
    #     「鉴别格不可测」这件事单独说清, 不再假装会枚举它。
    # ★★★ (b) 的修法: 标签必须写明是**哪个量**的上界 —— v1 两处用同一个标签指两个不同的量。
    secondary = {}
    for k in (0, 2, 4, 7, 13):
        lo, hi = clopper_pearson(k, N1)
        secondary["若 %d/%d **交卷**" % (k, N1)] = {
            "交卷率": round(k / N1, 4), "交卷率 CP95": [round(lo, 4), round(hi, 4)],
            "★区间跨度(倍)": "下界为 0, 上不封顶" if lo == 0 else round(hi / lo, 1),
            "买 24 格的代价下界(只用**交卷率上界**, 不借别的数)":
                "≥ %.0f 次" % (24 / hi) if hi else "∞"}

    # ★★★ P2: 冻结**模型臂** —— 整个对照就是关于它的, 却是唯一没被冻的东西。
    # ★★★ 但**不许 import exp_crossmodel_desire** —— 那个模块顶层带 requests,
    #     本文件的零调用闸(AST 查联网模块导入)会因此见红, 而那道闸是对的:
    #     预注册生成器不该有能力发调用。⇒ 用 AST 从源码里把 MODELS 那一项抠出来。
    sys.path.insert(0, str(ROOT / "scripts"))
    import cce_knot_classify as CK
    mcfg = _models_entry_by_ast(CK.MEASUREMENT_MODEL)
    model_frozen = {
        "MEASUREMENT_MODEL": CK.MEASUREMENT_MODEL,
        "model 字符串": mcfg["model"],
        "max_tokens": mcfg["max_tokens"],
        "key_env": mcfg["key_env"],
        "★force_temp": mcfg.get("force_temp"),
        "★为什么要冻": "两样本对照的**另一半**是 r2/r3, 它们跑在同一个模型臂上。"
                       "模型臂换了, 对照就不成立 —— 而它原本是唯一没被冻的冻结项。",
        "★★★ max_tokens 这个数不可信, 别拿它做判断": (
            "上面那个 %s 是**源码声明值**。运行时 scripts/exp_v4_full_validation.py:62 与 "
            "scripts/exp_v4_causal_chain.py:60 会在**导入时**把它改成 8000 ⇒ "
            "**有效值取决于谁被导入过**。实测: 只导 exp_crossmodel_desire 是 12000, "
            "再导 cce_knot_classify 就变 8000; r2 的链与本轮的链**都是 8000** ⇒ 可比性成立。"
            "★ 预注册**不冻这个数**(冻源码值会让预检误报); 由闸现场跑两条链核它们相等, "
            "由执行器把**有效值**记进产物。" % mcfg["max_tokens"]),
        "★段落长度远在限额内": "最长 %d 字符; 若仍出现截断, finish_reason 会是 length "
                               "⇒ 逐行记 finish_reason 以便事后分辨。" % max(cl),
    }
    # ★★★ P3: 把零假设**钉在两份具名产物**上 —— 否则底数可以被事后换掉(r5-v2 的死因)
    baseline_pin = {rel: hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() for rel in HAND}

    pre = {
        "block": "REAL_CORPUS_PILOT_PREREG",
        "version": 2,
        "date": "2026-09-17",
        "★★★status": "**READY**",
        "★零调用": "本文件由零调用探针生成; 投料由 probes/real_corpus_pilot_run.py 单独执行。",

        "★★★★★ v1 被零调用对抗评审打回, 这是 v2": {
            "评审规模": "8 个维度 × 22 个 agent, 51 条发现, 14 条经对抗验证, 4 条存活。",
            "★我没有只修存活的那 4 条": "被丢掉未验的 37 条里, 我**逐条自核**了 9 条, **全部属实**。",
            "逐条": {
                "A [BLOCKING] 拒绝域按 n=42 定却套在 n_ok 上":
                    "全部调用失败 ⇒ n_ok=0, k=0 ≤ 5 ⇒ **自信地判 TRANSFERS_NOT**。"
                    "修法: 每个可能的 n_ok 事前各算一套拒绝域, 执行时查表; 并设最低 n_ok。",
                "B [MAJOR] 判别式来源声称错":
                    "声称取自 %s, 实际取自模板文件。修法: 从冻结生产件取, 并与模板那份**逐字节比对**(已比对通过)。" % TAXONOMY,
                "C [MAJOR] 交卷判定两边不同":
                    "等价性证明用真值、执行器用 `is True`; 模型回 \"true\"/1 时不同, 且**漂移单向压低 k**。"
                    "修法: 只留 submitted() 一个定义, 证明与执行共用。",
                "D [BLOCKING] 计数对非字符串抛 TypeError":
                    "位置在**全部调用之后、写盘之前** ⇒ 42 次全丢。**r5-v3 原样重演**。"
                    "修法: ①每次调用后**立即落盘** ②计数前强制 str()。",
                "E [MAJOR] 模型自由文本进产物":
                    "increment_kind 是模型照措辞自填的自由文本, 逐字写进 results/ 破了隐私不变量。"
                    "修法: 只存「是否命中冻结枚举」与 sha, 不存文本。",
                "F [MINOR] 硬上限永不触发":
                    "上限 50 > 条数 42 ⇒ 那条保护从未被测过。修法: 上限 = min(预算, 条数) = %d。" % cap,
                "G [MAJOR] 提示词 sha 执行时不再验":
                    "预注册时算一次就不管了。修法: 执行器在**第一次调用之前**重验 PROMPT 与判别式的 sha, 不符即停。",
                "H [BLOCKING] 两样本长度差 3.2 倍未披露":
                    "见下面「★★★ 已知混淆」。",
                "I [MAJOR] 底数是伪重复":
                    "10/31 是同 16 个模板测两轮。修法: 改用**模板级**底数(见下)。",
            }},

        "★★★问的是什么": "把「从真实语料拿鉴别格」的**代价**拆成两个因子, 实测其中可测的那一个(因子一: 交卷率)。",

        "★★★★★ 这一轮不是「把 ~570 次的外推换成实测」": {
            "★为什么要更正": "我在上一份汇报里把下一步写成「~50 次把外推换成实测产出率」。"
                "**事前可达性检验证明那做不到** —— 在**预期的低 k**(0–2)上, 鉴别格产出率的区间跨 28 倍以上且上不封顶 "
                "⇒ 定不了「花不花」。(k 大时会收窄, 但大 k 本身就要求交卷率高, 而那正是主判据在测的东西。)",
            "★它真正能买到的": "**因子一**(交卷率)在 n=%d 上有可用精度, 而且它是**能把整条路关掉的那个** —— "
                "没交卷的调用不可能产出鉴别格, 所以交卷率是鉴别格率的**上界**。" % N1},

        "★★★ 冻结输入集": {
            "★取法": "**全取**含品牌/型号的段落, **不抽样** —— 没有抽样规则就没有抽样偏差。",
            "★★★这是个上界不是总体率": "含品牌段落是**最有利**的子总体(有可指认的对象)。"
                "⇒ 本轮读数是**语料整体交卷率的上界**, 不得当成整体率引用。",
            "★★★但「最有利」与「更长」混在一起(d)": "含品牌的 %d 条中位 %d 字符, 不含的 %d 条中位 %d 字符 "
                "—— **前者是后者的 %.1f 倍**。⇒ 这个选择器同时选中了「有可指认对象」和「更长」, "
                "两者**分不开**。上界的性质不受影响(仍是上界), 但**不得说是因为「有对象」**。"
                % (N1, statistics.median(cl), _n_nobrand, _med_nobrand,
                   statistics.median(cl) / max(1, _med_nobrand)),
            "★上界有多松, 本轮答不了": "语料里 %d 个非空段落中 %d 个含品牌; "
                "整体率与子总体率的差**没有测**, 所以只知道方向不知道幅度。"
                % (sum(1 for rel in CORPUS for l in (ROOT / rel).read_text(encoding="utf-8").split("\n") if l.strip()), N1),
            "品牌词表": "复用 probes/corpus_balance_audit.py 的 BRANDS(未重写)",
            "条数": N1, "硬上限": cap,
            "★只登记指针不登记原文": "每条只记 (file, line_index, sha256, n_chars) —— 语料是去标识后的真人内容, "
                                     "**产物里一个字的原文都不写**。",
            "items": items,
            "语料文件 sha256": {rel: hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() for rel in CORPUS}},

        "★★★ 已知混淆(H): 两样本的长度差了 3 倍": {
            "手构模板": "中位 %d 字符 · 最长 %d" % (statistics.median(tl), max(tl)),
            "真实语料": "中位 %d 字符 · 最长 %d" % (statistics.median(cl), max(cl)),
            "中位数之比": round(statistics.median(cl) / statistics.median(tl), 2),
            "比最长模板还长的语料条数": "%d/%d" % (longer, N1),
            "★★★对结论的限制": "若判出 TRANSFERS_NOT, **不得读成「因为是真实语料」** —— "
                "长度、结构、话题都同时变了。能说的只有「**手构模板上的外推不迁移**」, "
                "**机制未识别**。",
            "★为什么不去掉这个混淆": "把真实段落截短就不再是真实语料; 把模板加长就不再是那个已付费的底数。"
                "⇒ 这是**这个问题自带的**, 只能披露不能消除。",
            "★描述性辅助(不参与判决)": "结果里按长度三分位报交卷率 —— 若长度是主因, 三分位间应有梯度。"},

        "★★★ 冻结模型臂(P2)": model_frozen,
        "★★★ 零假设钉在这两份产物上(P3)": {
            "sha256": baseline_pin,
            "★为什么": "底数若不钉死, 事后换一份产物就能换掉零假设 —— **r5-v2 正是死在底数来源上**。"
                       "执行器在调用前重算这两个 sha。"},

        "★★★ 冻结提示词与判别式": {
            "★逐字复用": "probes/extractor_counterexample_run_r2.py 的 PROMPT, **一个字未改**。",
            "PROMPT sha256": prompt_sha,
            "★这是真发出去那个串的 sha, 不是源码字面量": "sha16=%s —— 与本仓 r3 记录里引用的一致。" % prompt_sha[:16],
            "判别式 sha256": disc_sha,
            "★判别式来源(B 已改正)": "取自冻结生产件 %s, 并与 r2 模板文件里那份**逐字节比对通过**。" % TAXONOMY,
            "temperature": 0.0, "max_retries": 1,
            "★max_retries 不得是 0": "call_model 是 `for attempt in range(max_retries)` —— "
                                     "写 0 等于**一次 HTTP 都不发**。2026-09-15 栽过这个。",
            "★执行时必须重验(G)": "执行器在**第一次调用之前**重算这两个 sha 并与此处比对, 不符即停。"},

        "★★★ 冻结 increment_kind 枚举(E)": {
            "★为什么要冻结": "模型是**照判别式措辞原样写**的自由文本。逐字写进产物就把模型自由文本"
                             "(可能夹带语料原文)带进了 results/。",
            "★取法": "从**冻结生产件的判别式**里机械抠出那个括号里的五项, 不是我手打的。",
            "枚举": KIND_ENUM,
            "★产物只存什么": "命中枚举的**第几项**(或 OTHER) + 模型原文的 sha256[:16]。**不存文本**。"},

        "★★★ 冻结交卷定义": {
            "定义": "交卷 ⟺ `supported is True`(**严格布尔**, 不是真值)。",
            "★只有一个定义(C)": "probes/real_corpus_pilot_prereg.py 的 submitted(); 执行器 import 它, 不另写。",
            "★为什么不能用 _judge()": "_judge() 吃模板的**金标字段**(span_P/span_Q/about), 真实语料**没有金标**。",
            "★★★ 同口径的机械证明": "手构有效行上, `submitted()` 与 `outcome ∈ ISSUED` "
                                    "**不一致的行数 = %d**。" % mism,
            "ISSUED(冻结)": list(m.ISSUED)},

        "★★★ 主判据(投料前定死)": {
            "★★★底数用模板级, 不用合并(I)": base,
            "零假设": "真实语料的交卷率 = 手构模板的**模板级**交卷率 %d/%d = %.4f"
                      % (K2, N2, K2 / N2),
            "检验": "两侧 Fisher 精确检验, 名义 α=%.2f" % ALPHA,
            "★★★ 但实际 size 远小于名义 α": (
                "Fisher 精确检验在小样本上是**保守**的: 在零假设点 q=%.4f 上, "
                "本设计的实际拒绝概率只有 **%.4f**, 比名义 0.05 小两个数量级。"
                "⇒ 第一类错误被压得很低, **代价是功效**(q=0.05 时 %s)。"
                "★ 这不是可以调的旋钮 —— 唯一能提功效的改法(单侧 / 名义 α 放大)都是**反保守**的, "
                "而本轮预期方向是事前声明过的, 事后改单侧就是调参。"
                % (K2 / N2, power["q=%.4f" % round(K2 / N2, 4)], power["q=0.0500"])),
            "★温度": "0.0(与 r2/r3 一致; 已实测该端点 temp=0 并不确定, 见 results/seed_probe.json)",
            "★★★拒绝域按实际 n_ok 查表(A)": table,
            "★★★功效也按实际 n_ok 查表": power_by_n,
            "★★★最低可判 n_ok(= **下尾可达**的最低 n_ok)": min_n,
            "★对照: 任意一侧非空的最低 n_ok": min_any,
            "★★★为什么门槛不能用「任意一侧非空」的那个": (
                "n_ok 在 %d–%d 时拒绝域**只有上尾**, 下尾是 k ≤ -1 —— "
                "而本轮**预期的方向就是下尾**(真实语料更难交卷)。"
                "在那段区间里, 对一切 q < %.4f 的功效**约等于 0** ⇒ **先验不可达**, "
                "那正是 r5-v1 的死因搬到小 n_ok 分支。⇒ 低于 %d 一律 INSUFFICIENT_DATA。"
                % (min_any, min_n - 1, K2 / N2, min_n)),
            "★n_ok 低于它时的判决": "INSUFFICIENT_DATA —— **不是** TRANSFERS_NOT, 也**不是** CANNOT_DISTINGUISH。"
                "v1 会把「全部调用失败」判成「显著不同」; v2 会在 n_ok≤%d 时判「分不出」并谎报 n=42 的功效。"
                % (min_n - 1),
            "判 TRANSFERS_NOT": "k 落在**该 n_ok 对应的**拒绝域 ⇒ 手构模板上的外推**不迁移**"
                                "(★ 机制未识别, 见已知混淆)。",
            "判 CANNOT_DISTINGUISH": "k 不在拒绝域 ⇒ **这批数据分不出**, **不等于两者相同**。",
            "★功效(n_ok = %d 时, 即上表 [%d] 那一行)" % (N1, N1): power,
            "★★★功效的老实话": "只有 q ≤ 0.05 才到 0.8; q=0.10 时只有 %s。"
                "⇒ **CANNOT_DISTINGUISH 是很可能的结局**, 且它基本不携带信息。"
                % power.get("q=0.1000"),
            "★比 v1 弱了多少": "v1 忽略伪重复用 10/31 作底数, 同样 q 下功效是 0.983/0.884/0.760。"
                "v2 改用模板级 5/16 后降到 %s/%s/%s —— **这不是退步, 是 v1 把有效 n 算多了**。"
                % (power.get("q=0.0500"), power.get("q=0.0800"), power.get("q=0.1000"))},

        "★★★ 鉴别格产出率: 本轮**根本测不了**, 不是「测不准」": {
            "★★★为什么是测不了": "鉴别格 = 金标 ≠ 零基线常数的格子。真实语料**没有金标**, "
                "而 RESTATES_IDENTIFIER 的定义含「声称这是增量」—— 那是 A 支的属性, "
                "**人从语料里标不出来**(results/real_corpus_feasibility.json 已证)。"
                "⇒ 执行器**不计算鉴别格**, 产物里也不会有这个数。",
            "★v1 在这里做错了什么": "v1 的事前枚举是按**鉴别格数**列的, 读起来像是会去数它。"
                "实际执行器根本算不出。**已删掉那个假枚举**, 改成按**交卷数**列。",
            "★那还剩什么": "交卷率是鉴别格率的**上界**(没交卷不可能出鉴别格) ⇒ "
                "只能给**代价下界**, 给不了产出率。",
            "★★★不得当点估计引用": (
                "★ **更正我自己的一句过度断言**: 我先写过「任何结果的区间都跨一个数量级」—— 那是假的, "
                "由闸当场抓到: 交卷 4/%d 只跨 8.5 倍、7/%d 只跨 4.5 倍。"
                "**准确的说法**: 在预期的低 k(0–2)区间跨 28 倍以上且上不封顶; k 变大会收窄。" % (N1, N1)),
            "事前枚举(按**交卷数**, 那是真会测的量)": secondary,
            "★纯下界只用交卷率": "鉴别格 ≤ 交卷 ⇒ 24 格代价 ≥ 24/CI上界(**交卷率**)。这条**不依赖**因子二。",
            "★另一条要用手构因子二": "24/(CI上界 × 0.1333) —— **借了手构的数**, 引用必须标明; "
                "而且因子二自己的 CI 从未传播进来, 所以那个数**不是下界, 只是一个点算**。"},

        "★★★ 首次把真实语料送到外部模型": {
            "★事实": "r1/r2/r3 跑的都是我手写的模板。**本轮是第一次把真人语料(去标识的公开 Reddit 内容)发给 MiniMax**。",
            "★范围": "只发被抽中的 %d 个段落(合计约 %d 字符), 不发整份语料。" % (N1, sum(cl)),
            "★产物侧": "结果文件里只存指针与结构化事实, **不回写任何原文、任何模型 span、任何模型自由文本**。"},

        "★★★ 不得做的事": [
            "不得看过结果再改任何判据 —— 已因此否决过 r5 两版。",
            "不得与 r4 的历史读数直接比 —— r3 实测同一仪器重测一致率仅 60%。",
            "不得把本轮的「含品牌子总体」读数当成语料整体率。",
            "不得把 TRANSFERS_NOT 读成「因为是真实语料」—— 长度混淆未消除, 机制未识别。",
            "不得用测量模型给自己的输出做盲验(循环)。",
            "撞硬上限 %d 立即停。" % cap],

        "预算": {"本轮上限": cap, "之前已用": 158, "上限达成时合计": 158 + cap,
                 "★计费": "订阅制(非按量), 但仍逐次登记。"},
    }
    OUT.write_text(json.dumps(pre, ensure_ascii=False, indent=1), encoding="utf-8")
    print("输入集 %d 条(全取) · 模板级底数 %d/%d = %.4f" % (N1, K2, N2, K2 / N2))
    print("拒绝域(n_ok=%d): %r" % (N1, table[str(N1)]))
    print("最低可判 n_ok =", min_n)
    print("功效:", json.dumps(power, ensure_ascii=False))
    print("交卷口径不一致行数 =", mism, "· 判别式与冻结生产件比对: 通过")
    print("→", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
