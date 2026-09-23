#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""r5 执行器 —— **两臂同轮配对** + **四条零调用参照臂**。

★★★ 与 r4 的关系: **另起一份, 不改 r4**(改了它, 20 次已付费调用的读数就失去对应物)。
  ★ 「分叉执行器后旧闸只守旧文件」是本项目栽过的第四次假保证 ⇒
    tests/test_cce_slot_filling_r5.py 会**同时**核 r4 执行器逐字节未变。

★★★ 本轮问什么: **把附件 A 的判据展开给模型看**(而不是只给一个标签名),
  它在**鉴别格**上能不能超过**最佳浅层规则**?

★★★ 本轮**不**问: 「模型在完全不知道该判据时能否填对」——
  因为 RESTATES_IDENTIFIER 这个**标签名本身就是判据的压缩**, A 臂也拿到了它。
  ⇒ A/B 的差是「**判据展开 vs 判据压缩成标签名**」, 不是「无判据 vs 有判据」。
"""
import hashlib, json, os, pathlib, random, re, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "probes"))
PREREG = json.loads((ROOT / "tests/data/slot_filling_prereg_r5.json").read_text(encoding="utf-8"))
GOLD = json.loads((ROOT / "tests/data/claim_frame_annotations.json").read_text(encoding="utf-8"))
PAIRS = json.loads((ROOT / "tests/data/semantic_minimal_pairs.json").read_text(encoding="utf-8"))
OUT = ROOT / "results" / "slot_filling_r5.json"
CAP = 68                     # ★ 硬上限: 68 条 × **只跑 B 臂**。撞上即停。
ATTEMPTS = 1                 # ★★★ 传给 call_model(max_retries=) 的值。
#   ★★★ **这个参数名有误导性**: scripts/exp_crossmodel_desire.py:132 是 `for attempt in range(max_retries)`
#     ⇒ 它是**总尝试次数**, 不是「重试次数」。写 0 **一次 HTTP 都不发**, 64 条全被记成「格式失败」,
#     而 n 照样递增 ⇒ 预算记成已用、读数全是空的。
#   ★ 我第一版写的就是 0, 由 2026-09-15 投料前评审抓到(BLOCKING)。r4 用的是 1。
#   ⇒ **1 = 一次尝试、零重试**, 这才是「零重试」的正确写法。

SLOTS = ("speaker", "polarity", "time", "citation", "possession", "predicate")
SENSITIVE = {"A": ("polarity", "citation", "predicate"),
             "B": ("polarity", "speaker", "time", "possession")}
import cce_claim_frame as _CF
# ★★★ LEGAL **从判据层现算派生**, 不许手写。
#   r4 唯独 predicate 手写且漏了 RESTATES_IDENTIFIER ⇒ 模型填对反而被判非法、静默剔出分母
#   (评审实跑: 连金标臂自己都被剔掉 ANX 条目, 而 D4 不响)。由 tests/test_cce_executor_legal_enum.py 把住。
LEGAL = {"speaker": set(_CF.SPEAKER), "polarity": set(_CF.POLARITY), "time": set(_CF.TIME),
         "citation": set(_CF.CITATION), "possession": set(_CF.POSSESSION),
         "predicate": set(_CF.PREDICATE_NEG) | {"OF_DECLARED_KIND", "OWNERSHIP", _CF.UNSPEC}}
BASELINE = {"speaker": "SELF", "polarity": "ASSERTED", "time": "PAST_OR_PRESENT",
            "citation": "DIRECT", "possession": "OWNED", "predicate": "OF_DECLARED_KIND"}
MAJORITY_PRED = BASELINE["predicate"]

# ────────────────────── 两臂提示词: **逐字冻结**, 唯一差异是 CRITERION_B ──────────────────────
_STEM = """下面是一段英文文本, 和从它里面取出的**两条片段**。

文本:
\"\"\"%s\"\"\"

片段一: \"%s\"%s
片段二: \"%s\"%s

请为**每一条**证据填下面六个槽位。**文本没有明确说明的, 填 UNSPECIFIED, 不要猜。**

  speaker    —— 这条片段所陈述的那件事, 主语是不是说话人自己?
                 SELF(是自己) / OTHER(是别人) / UNSPECIFIED
  polarity   —— 这条片段在原文里是**被肯定**的, 还是落在**否定的辖域**里?
                 ASSERTED(被肯定) / NEGATED(落在否定辖域内) / UNSPECIFIED
  time       —— 这条片段陈述的事情发生在过去或现在, 还是尚未发生?
                 PAST_OR_PRESENT / FUTURE / UNSPECIFIED
  citation   —— 这条片段是说话人**直接陈述**的, 还是**转述别人**的说法?
                 DIRECT(直接陈述) / REPORTED(转述别人) / UNSPECIFIED
  possession —— 就这条片段所谈的那个东西而言, 说话人与它是什么关系?
                 OWNED(明确拥有) / EXPERIENCED(不拥有但明确用过或经历过) /
                 ONE_NEGATED(明确否定了「拥有」与「用过」当中的**一支**, 另一支没提) /
                 BOTH_NEGATED(**两支都明确否定**了) / UNSPECIFIED
  predicate  —— **只在该片段下面标了 kind 时填**: 这条片段给出的内容, 是不是 kind 说的那一类?
                 OF_DECLARED_KIND(是那一类) / NOT_OF_DECLARED_KIND(不是那一类) /
                 RESTATES_IDENTIFIER(只复述或指认了那个东西的标识) / UNSPECIFIED
                 没标 kind 的那条填 null。
                 ★ 只填这几个大写标签之一, **不要加括号、不要加说明文字**。
%s
只输出 JSON, 不要别的:
{
  "片段一": {"speaker": "...", "polarity": "...", "time": "...", "citation": "...", "possession": "...", "predicate": "..."},
  "片段二": {"speaker": "...", "polarity": "...", "time": "...", "citation": "...", "possession": "...", "predicate": "..."}
}"""

# ★★★ A 臂: 判据只压缩成标签名 + 一句最小 gloss(上面那行括号里的字)。**不给条款**。
CRITERION_A = ""
# ★★★ B 臂: 把**已升为合同的附件 A 条款**逐字展开。
#   ★ 刻意**不给例句** —— 附件 A 原文破折号后的例(「复述型号名不产生增量」)
#     与本轮 ANX-3 **同构**, 给了就是把答案写在卷子上。只给破折号**前**的条款。
CRITERION_B = """
★ 关于 RESTATES_IDENTIFIER 这一个取值, 判据如下(这是合同明文):
  「增量相对 x 成立 ⟺ 文本含**关于 x 的陈述**, 且该陈述**不能**由 x 的公开标识
   (型号名、品类名)本身推出。」
  ⇒ 若这条片段说的内容, **从那个东西的名字本身就推得出来**, 它就没有产生增量, 填 RESTATES_IDENTIFIER。
"""
# ★★★ 2026-09-15: **A 臂已砍**。投料前评审: 它买的次判据(B−A)已登记为 descriptive、不设门槛、
#   配对差误拒率 0.349 ⇒ 半个预算买一个**不能下结论的数**。
#   ⇒ 本轮**只跑 B 臂**; CRITERION_A 保留只为闸能 diff 出「两臂唯一差异是判据文字」。
ARMS = {"B_判据展开为合同条款": CRITERION_B}


def prompt_sha():
    """两臂提示词的哈希 —— 预注册钉它, 闸现算比对。处理物不冻结, 「唯一差异是判据文字」就没有对象。"""
    return {k: hashlib.sha256((_STEM % ("", "", "", "", "", v)).encode()).hexdigest()[:16]
            for k, v in ARMS.items()}


def _norm(v):
    if v is None or not isinstance(v, str):
        return "UNSPECIFIED"
    return v.strip().strip("\"'「」`").upper() or "UNSPECIFIED"


def _parse(raw):
    if not raw or not raw.strip():
        return None
    s = raw.find("{")
    if s < 0:
        return None
    depth = 0
    for i in range(s, len(raw)):
        if raw[i] == "{":
            depth += 1
        elif raw[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(raw[s:i + 1])
                except Exception:
                    return None
    return None


def items():
    """32 条 = (pairs 10 对 + contract_pairs 6 对) × pos/neg。"""
    out = []
    for p in PAIRS["pairs"]:
        for side in ("pos", "neg"):
            s = p[side]
            out.append({"id": "%s/%s" % (p["id"], side), "cls": p["cls"], "side": side,
                        "text": s["text"], "is_ANX": False,
                        "ev": [("A", s["A"][0], s["A"][2]), ("B", s["B"][0], None)],
                        "gold": GOLD["annotations"][p["id"]]["frames"][side]})
    for p in PAIRS["contract_pairs"]:
        for side in ("pos", "neg"):
            s = p[side]
            out.append({"id": "%s/%s" % (p["id"], side), "cls": p["cls"], "side": side,
                        "text": s["text"], "is_ANX": True,
                        "ev": [("A", s["A"][0], s["A"][2]), ("B", s["B"][0], None)],
                        "gold": p["frames"][side]})
    return out


def score(filled, it, CF):
    cells, illegal = [], 0
    frames_ok, frames = True, []
    D = GOLD["★默认槽位"]
    for idx, key in ((0, "片段一"), (1, "片段二")):
        sup = it["ev"][idx][0]
        d = filled.get(key) or {}
        g = dict(D, **it["gold"]["A" if sup == "A" else "B"])
        kw = {}
        for s_ in SLOTS:
            mv = _norm(d.get(s_))
            ok_legal = mv in LEGAL[s_]
            # ★★★ B 支的 predicate **不计分也不影响任何判定**(下面直接用金标覆盖),
            #   而提示词自己写着「没标 kind 的那条填 null」⇒ 模型照做填 "NULL" 会被判非法,
            #   进而把前置条件③(端到端可用过半)打成 false。**照提示词做反而被罚**。
            if not ok_legal and not (s_ == "predicate" and sup == "B"):
                illegal += 1
            kw[s_] = mv if ok_legal else CF.UNSPEC
            if s_ == "predicate" and sup == "B":
                continue
            cell = {"支": sup, "槽": s_, "模型": mv, "金标": g.get(s_, CF.UNSPEC),
                    "对": mv == g.get(s_, CF.UNSPEC),
                    "敏感": s_ in SENSITIVE[sup], "合法": ok_legal}
            if s_ == "predicate" and sup == "A":
                # ★★★ predicate 必须拆开: 金标 == 零基线常数的格是**零基线免费答对的**,
                #   20+ 个这样的格会把少数几个鉴别格**稀释掉** —— 聚合数读不出鉴别力。
                cell["鉴别格"] = (g.get(s_) != MAJORITY_PRED)
                cell["目标取值"] = g.get(s_)
            cells.append(cell)
        if sup == "B":
            kw["predicate"] = g.get("predicate", "OWNERSHIP")
        try:
            frames.append(CF.ClaimFrame(
                it["ev"][idx][1], CF.CONJ_P if sup == "A" else CF.CONJ_Q,
                object="o", increment_kind=(it["ev"][idx][2] if sup == "A" else None), **kw))
        except Exception:
            frames_ok = False
    out = {"cells": cells, "非法取值": illegal, "构造成功": frames_ok,
           "端到端可用": (illegal == 0 and frames_ok)}
    for tier, ui in (("只用合同明文", False), ("明文+解释", True)):
        out[tier] = (CF.allow_label(frames, use_interpretation=ui)["allow"]
                     if frames_ok and frames else False)
    return out


def tally(scored):
    acc = {}
    for s_ in SLOTS:
        sel = [c for _, sc in scored for c in sc["cells"] if c["槽"] == s_ and c["敏感"]]
        if sel:
            acc.setdefault(s_, {})["敏感"] = "%d/%d" % (sum(c["对"] for c in sel), len(sel))
        dec = [c for _, sc in scored for c in sc["cells"] if c["槽"] == s_ and not c["敏感"]]
        if dec:
            acc.setdefault(s_, {})["装饰"] = "%d 格 —— **不计分**(判据不读 · 金标是填充值)" % len(dec)
    # ★★★ predicate 拆鉴别格 / 多数类格, 且鉴别格**按目标取值再拆**
    pc = [c for _, sc in scored for c in sc["cells"] if c["槽"] == "predicate" and c["支"] == "A"]
    disc = [c for c in pc if c.get("鉴别格")]
    bulk = [c for c in pc if not c.get("鉴别格")]
    by_t = {}
    for t in sorted({c["目标取值"] for c in disc}):
        sel = [c for c in disc if c["目标取值"] == t]
        by_t[t] = "%d/%d" % (sum(c["对"] for c in sel), len(sel))
    acc["predicate"] = dict(acc.get("predicate", {}), **{
        "★★★鉴别格(金标 ≠ 零基线常数)": "%d/%d" % (sum(c["对"] for c in disc), len(disc)),
        "★★★鉴别格_按目标取值": by_t,
        "多数类格(零基线免费答对的)": "%d/%d" % (sum(c["对"] for c in bulk), len(bulk)),
        "★为什么拆": "%d 个多数类格会把 %d 个鉴别格**稀释掉** —— 聚合数与零基线可以完全相同。"
                  % (len(bulk), len(disc))})
    usable = [(i, sc) for i, sc in scored if sc["端到端可用"]]
    neg = [(i, sc) for i, sc in usable if i["side"] == "neg"]
    pos = [(i, sc) for i, sc in usable if i["side"] == "pos"]
    e2e = {}
    for tier in ("只用合同明文", "明文+解释"):
        e2e[tier] = {
            "阴性被放行": ("%d/%d" % (sum(1 for _, sc in neg if sc[tier]), len(neg))
                       if neg else "0/0 —— **无可用样本**"),
            "对照通过": ("%d/%d" % (sum(1 for _, sc in pos if sc[tier]), len(pos))
                      if pos else "0/0 —— **无可用样本**")}
    return {"逐槽位": acc, "端到端(两档分开报_不许合并)": e2e,
            "★端到端可用": "%d/%d" % (len(usable), len(scored)),
            "非法取值": sum(sc["非法取值"] for _, sc in scored),
            "构造失败": sum(1 for _, sc in scored if not sc["构造成功"])}


# ────────────────────── 四条零调用参照臂 ──────────────────────

def _best_token():
    """从 results/best_shallow_rule_search.json 取**净增益最大**的那个 token。

    ★ 它是**搜出来的**不是我选的 —— 手写的浅层臂只能测我想得到的规则。
    """
    p = ROOT / "results/best_shallow_rule_search.json"
    if not p.exists():
        # ★★★ **不许静默退化**: 缺它 ⇒ p0=0 ⇒ 任何 ≥1/6 都会印「超过最佳浅层规则(p<0.05)」,
        #   而 D6 同时哑掉。⇒ 直接拒发。
        raise SystemExit("★★★ 缺 results/best_shallow_rule_search.json —— "
                         "它决定主判据的零假设 p0。**未发起任何调用**。")
    d = json.loads(p.read_text(encoding="utf-8"))
    # ★★★ 评审 MAJOR: 原版读的是**单 token** 候选表 ⇒ ④ 号参照臂与 bb 都成了单 token 的,
    #   而预注册与搜索器都写明 p0 必须用**冻结族**。这里改读冻结族最佳。
    fam = d["★★★目标取值 RESTATES_IDENTIFIER"].get("★★★冻结族最佳(这才是 p0 该用的数)")
    if fam and fam.get("规则"):
        return {"__family_rule__": fam["规则"]}
    c = d["★★★目标取值 RESTATES_IDENTIFIER"]["前 5 条候选"]
    return c[0]["token"] if c else None


def ref_fills():
    """四条零调用臂各自的 fill 函数。都**不经任何模型**。"""
    import shallow_cue_arm as SCA
    tok = _best_token()

    def gold(it, sup):
        return dict(GOLD["★默认槽位"], **it["gold"][sup])

    def base(it, sup):
        f = dict(BASELINE)
        if sup == "B":
            f["predicate"] = "OWNERSHIP"
        return f

    def shallow(it, sup):
        return SCA.fill(it["text"], it["ev"][0 if sup == "A" else 1][1], sup == "A")

    def best(it, sup):
        f = base(it, sup)
        if sup != "A" or not tok:
            return f
        if isinstance(tok, dict):                      # ★ 冻结族规则
            import importlib.util as _iu
            _s = _iu.spec_from_file_location("bs", ROOT / "probes/best_shallow_rule_search.py")
            _b = _iu.module_from_spec(_s); _s.loader.exec_module(_b)
            fn = dict(_b._rules()).get(tok["__family_rule__"])
            if fn and fn(it["ev"][0][1]):
                f["predicate"] = "RESTATES_IDENTIFIER"
        elif tok in it["ev"][0][1].lower():
            f["predicate"] = "RESTATES_IDENTIFIER"
        return f

    lbl = ("④ 最佳浅层规则(**冻结族**搜出来的: %s)" % tok["__family_rule__"]) if isinstance(tok, dict) \
        else ("④ 最佳单token浅层规则(搜出来的: %r)" % tok)
    return [("① 金标(能力上界)", gold),
            ("② 零基线(完全不读文本的常数填充)", base),
            ("③ 浅层线索臂(手写正则_规则先于文本固定)", shallow),
            (lbl, best)]


def run_ref(scored_items, CF):
    out = {}
    for name, fill in ref_fills():
        rs = [(it, score({"片段一": fill(it, "A"), "片段二": fill(it, "B")}, it, CF))
              for it in scored_items]
        out[name] = tally(rs)
    return out


TARGET = "RESTATES_IDENTIFIER"     # ★ 主判据只看这一个取值 —— 它才是附件 A 定义的那条


def _disc(t, target=TARGET):
    """predicate 鉴别格的 (对, 总)。

    ★★★ **只取 target 那一类**。桩自检抓到: 不限定 target 时分母是 8(RESTATES 6 + NOT_OF 2),
      而 NOT_OF_DECLARED_KIND 依据的「五类各自的成立条件」**仍是解释未升合同**,
      B 臂**根本没拿到它的判据文字** ⇒ 把它混进主判据, 门就算错了。
    """
    d = t["逐槽位"]["predicate"]
    if target is None:
        a, b = d["★★★鉴别格(金标 ≠ 零基线常数)"].split("/")
    else:
        v = d["★★★鉴别格_按目标取值"].get(target, "0/0")
        a, b = v.split("/")
    return int(a), int(b)


def _bulk(t):
    """多数类格的 (对, 总) —— 零基线免费答对的那些。**过度触发会打在这里。**"""
    a, b = t["逐槽位"]["predicate"]["多数类格(零基线免费答对的)"].split("/")
    return int(a), int(b)


def _binom_ge(k, n, p):
    """P(X ≥ k | n, p) —— 事前可算的单侧 p。零依赖。"""
    from math import comb
    return sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))


# ────────────────────── 主流程 ──────────────────────

def _load_key():
    p = pathlib.Path("/Volumes/data/viral-skill-eval/.env")
    if not p.exists():
        raise SystemExit("★ 找不到订阅凭据文件 —— **未发起任何调用**")
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:]
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    if not os.environ.get("MINIMAX_API_KEY"):
        raise SystemExit("★ 凭据文件里没有 MINIMAX_API_KEY —— **未发起任何调用**")


def judge(model_arms, ref, n_calls, fails):
    """测量前冻结的判据与降级。**只报数, 不判 PASS/FAIL**(主判据除外, 它事前可算)。"""
    dg, out = [], {}
    A = model_arms.get("A_判据压缩成标签名")
    B = model_arms.get("B_判据展开为合同条款")
    best = [v for k_, v in ref.items() if k_.startswith("④")][0]
    bk, bn = _disc(best)

    # ★★★ 主判据(测量前冻结, confirmatory): B 臂在鉴别格上超过**最佳浅层规则**
    if B:
        k, n = _disc(B)
        # ★★★ p0 与门**冻结在预注册里**, 运行时只**校验**不现算。
        #   评审 BLOCKING: 原版 p0 与 n 从配对交集现算 ⇒ 掉一条就换一个门, 声称 confirmatory 却没锁分析自由度。
        FZ = PREREG["★★★主判据(测量前冻结_confirmatory)"]
        p0 = FZ["★冻结的 p0"]
        n_fz, gate = FZ["★冻结的 n"], FZ["★冻结的门"]
        if n != n_fz:
            # ★★★ 评审 BLOCKING: 原版在这里 `return out` ⇒ 把 D1–D6 六条降级**一起吞掉**,
            #   一条 ANX/neg 调用失败就让 68 次只剩原始 rows。⇒ 只跳过主判据, **降级照算**。
            out["★★★鉴别格数与预注册不符_主判据不计算"] = (
                "现算 %d vs 冻结 %d ⇒ **主判据不计算**(不许掉了样本就换一个门)。"
                "★ 这**不是**「模型未达成」, 是**样本不完整**。★★ 降级条件 D1–D6 **照常计算并报出**。"
                % (n, n_fz))
            skip_main = True
        else:
            skip_main = False
        p = _binom_ge(k, n, p0)
        Bb, Bbn = _bulk(B); bb, bbn = _bulk(best)
        if skip_main:
            out["★主判据被跳过时仍报出的数"] = {"B 臂鉴别格": "%d/%d" % (k, n),
                "B 臂多数类格": "%d/%d" % (Bb, Bbn),
                "★": "**不得**拿它与冻结的门比 —— 分母不同, 那正是不许换门的理由。"}
        u, ut = (int(x) for x in B["★端到端可用"].split("/"))
        # ★★★ 三个前置条件, 缺一不可 —— 桩自检抓到的三个漏洞各对应一条
        gate_sig = (k >= gate)
        # ★★★ 2026-09-15 第三次改: ② 由「多数类格 ≥ 阈值」改成 **「净增益 > 最佳浅层规则的净增益」**。
        #   两版分开判的毛病(评审实测): 那条族外量词规则鉴别格 14≥11 ✓、多数类格 26≥阈值 ✓, **两项都过**,
        #   而它的**净增益是 −2**(比零基线还差)。⇒ 鉴别力必须**净看**, 这也是评审自己的立论。
        #   ★ 阈值 base_net 冻结在预注册里, 由 probes/best_shallow_rule_search.py 现搜得出。
        base_net = FZ["★冻结的最佳浅层规则净增益"]
        B_net = k - (Bbn - Bb)
        best_net = bk - (bbn - bb)
        gate_bulk = (B_net > base_net)
        gate_use = (ut and u * 2 > ut)  # ⑤ 枚举外取值: 端到端 0/32 可用, 主判据不该还报「超过」
        out["★★★主判据: B 臂鉴别格 vs 最佳浅层规则"] = {} if skip_main else {
            "★只看 %s" % TARGET: "NOT_OF_DECLARED_KIND 那 2 格**不进主判据** —— "
                "它依据的「五类各自的成立条件」**仍是解释未升合同**, B 臂没拿到它的判据文字。",
            "B 臂鉴别格": "%d/%d" % (k, n), "最佳浅层规则鉴别格": "%d/%d" % (bk, bn),
            "B 臂多数类格": "%d/%d" % (Bb, Bbn), "最佳浅层规则多数类格": "%d/%d" % (bb, bbn),
            "★★★净增益(鉴别格对数 − 多数类格错数)": {
                "B 臂": B_net, "最佳浅层规则(现算)": best_net, "冻结的阈值": base_net,
                "★为什么用净增益": "分开判「鉴别格≥门」与「多数类格≥阈值」会漏: "
                    "实测一条族外规则两项都过而净增益是 **−2**(比零基线还差)。"},
            "零假设 p0(= 最佳浅层规则的命中率)": round(p0, 4),
            "单侧 p(二项, 事前可算)": (round(p, 5) if p is not None else "—"),
            "★冻结的门(预注册, 非现算)": "n=%d · p0=%.3f ⇒ **≥%d/%d**" % (n_fz, p0, gate, n_fz),
            "★三个前置条件": {"① 鉴别格 ≥ 冻结的门": gate_sig,
                        "② 净增益 > 最佳浅层规则的净增益": gate_bulk,
                        "③ 端到端可用过半": bool(gate_use)},
            "★结论": ("**超过最佳浅层规则(p<0.05, 且多数类格未塌, 且样本可用)**"
                    if (gate_sig and gate_bulk and gate_use)
                    else "**未达成** —— 不得读成「模型读懂了判据」。未达成的原因见「三个前置条件」。"),
            "★★★为什么必须有②": "**只看鉴别格, 一刀切就能过门**(桩自检实测: A 支一律填 %s ⇒ 鉴别格满分)。"
                "★★ 而②**必须用净增益**, 不能拆成两个分开的阈值 —— 实测一条族外规则"
                "「不含量词/时段 ⇒ %s」鉴别格 14≥门、多数类格也过阈值, **两项都过**, 净增益却是 **−2**。"
                % (TARGET, TARGET),
            "★★★为什么必须有③": "桩自检实测: 全部填枚举外取值时端到端 **0/32 可用**, "
                "而 predicate 那一格仍按原值与金标比 ⇒ 主判据照样报「超过」。",
            "★★★这不证明什么": "即使达成, 也只说明**在这 %d 个手构鉴别格上**优于**单 token** 规则。"
                "搜索空间不含 n-gram/位置/长度 ⇒ **更强的浅层规则可能存在**。" % n}

    # 次判据: B − A(配对, 只在两臂都可用的条目上)
    if A and B:
        ak, an = _disc(A)
        out["次判据: B − A(判据展开 vs 压缩成标签名)"] = {
            "A 臂鉴别格": "%d/%d" % (ak, an), "B 臂鉴别格": "%d/%d" % (_disc(B)[0], _disc(B)[1]),
            "差": _disc(B)[0] - ak,
            "★★★这不回答什么": "**不回答「模型在完全不知道该判据时能否填对」** —— "
                "RESTATES_IDENTIFIER 这个**标签名本身就是判据的压缩**, A 臂也拿到了它。"}

    # 降级
    if fails * 2 > n_calls:
        dg.append("D1 调用或格式失败 %d/%d(过半) ⇒ 失效在**格式层**" % (fails, n_calls))
    for arm, t in model_arms.items():
        for s_ in SLOTS:
            v = t["逐槽位"].get(s_, {}).get("敏感")
            if v and v.startswith("0/") and not v.endswith("/0"):
                dg.append("D2 臂 %s 的槽位 **%s** 敏感格全错(%s)" % (arm, s_, v))
        if t["端到端(两档分开报_不许合并)"]["明文+解释"]["对照通过"].startswith("0/"):
            dg.append("D3 臂 %s 对照**全部**不通过 ⇒ 该臂退化, 阴性读数作废" % arm)
        u, tot = (int(x) for x in t["★端到端可用"].split("/"))
        if tot and u * 2 <= tot:
            dg.append("D4 臂 %s 端到端可用只有 %s ⇒ 失效在**取值层**, 那几个数不得单独引用"
                      % (arm, t["★端到端可用"]))
        zk, _ = _disc(ref["② 零基线(完全不读文本的常数填充)"])
        mk, _ = _disc(t)
        if mk <= zk:
            dg.append("D5 臂 %s 的 predicate 鉴别格 %d ≤ **零基线** %d ⇒ 没有证据说明它在读文本"
                      % (arm, mk, zk))
        if mk <= bk:
            dg.append("D6 臂 %s 的 predicate 鉴别格 %d ≤ **最佳浅层规则** %d ⇒ "
                      "**该槽位相对表层线索零增益**, 它的数**不得读成读懂了判据**" % (arm, mk, bk))
    out["★★★判读降级"] = dg or "无"

    # D7 —— **降为附带报出的数, 不给它作废主判据的权力**
    if A and B:
        oth = {}
        for s_ in ("speaker", "polarity", "time", "citation", "possession"):
            a = A["逐槽位"].get(s_, {}).get("敏感")
            b = B["逐槽位"].get(s_, {}).get("敏感")
            if a and b:
                oth[s_] = "A %s → B %s" % (a, b)
        out["★附带数: 判据文字对其他槽位的影响(不是降级条件)"] = {
            "逐槽位": oth,
            "★★★为什么只是附带数": "草案原版把它写成降级 D7(「其他槽位差异超过 predicate 差异 ⇒ B−A 不可归因」)。"
                "评审用蒙特卡洛现算: 在**判据文字零效果**的零假设下, 该条件的误触发率在三种可辩护读法下"
                "分别是 **0.54 / 0.54 / 0.96~0.98** —— 它会以掷硬币的方式作废主判据。"
                "★ 且格数 144:24 不对等、度量未定义。⇒ **降为附带数**。"}
    return out


def main():
    st = PREREG.get("★★★status", "")
    assert st.startswith("**READY**"), "★ 预注册未就绪(%s) —— 不得发起" % st[:40]
    sha_now, sha_pin = prompt_sha(), PREREG["★★★两臂提示词哈希(测量前冻结)"]
    assert sha_now == sha_pin, "★★★ 提示词与预注册钉的哈希不符: %r vs %r" % (sha_now, sha_pin)
    _load_key()
    from exp_crossmodel_desire import call_model
    import cce_knot_classify as CK
    import cce_claim_frame as CF

    its = items()
    random.Random(20260915).shuffle(its)
    # ★ 两臂**交错**发起, 而不是按臂分块 —— 否则「臂」与「执行时间」完全共线,
    #   同轮配对就只消掉了 item 方差, 没消掉时间漂移。
    plan = [(arm, it) for it in its for arm in ARMS]
    rows, by_arm, n, fails = [], {a: [] for a in ARMS}, 0, 0
    for arm, it in plan:
        if n >= CAP:
            print("★★★ 撞硬上限 %d —— 停" % CAP); break
        n += 1
        (sa, spa, ka), (sb, spb, _) = it["ev"]
        raw, meta = call_model(
            CK.MEASUREMENT_MODEL,
            _STEM % (it["text"], spa, ("  · kind=%s" % ka) if ka else "", spb, "", ARMS[arm]),
            temperature=0.0, max_retries=ATTEMPTS)
        obj = _parse(raw) if not meta.get("error") else None
        if obj is None:
            fails += 1
            rows.append({"臂": arm, "id": it["id"], "调用成功": False,
                         "why": "调用或格式失败(**计入预算, 不进分母**): %s"
                                % (meta.get("error") or "无法解析 JSON"),
                         "raw": (raw or "")[:160]})
            print("  %-6s %-14s CALL_FAILED" % (arm[0], it["id"])); continue
        sc = score(obj, it, CF)
        by_arm[arm].append((it, sc))
        pc = [c for c in sc["cells"] if c["槽"] == "predicate" and c["支"] == "A"]
        rows.append({"臂": arm, "id": it["id"], "调用成功": True, "模型原样": obj,
                     "非法取值": sc["非法取值"], "端到端可用": sc["端到端可用"],
                     "predicate": (pc[0]["模型"] if pc else None),
                     "predicate金标": (pc[0]["金标"] if pc else None),
                     "鉴别格": (pc[0].get("鉴别格") if pc else None),
                     "只用合同明文": sc["只用合同明文"], "明文+解释": sc["明文+解释"]})
        print("  %-6s %-14s pred=%-22s 金标=%-22s %s"
              % (arm[0], it["id"], rows[-1]["predicate"], rows[-1]["predicate金标"],
                 "★鉴别格" if rows[-1]["鉴别格"] else ""))

    # ★ 配对只在**两臂都有可用读数**的条目上
    ids = set.intersection(*[{i["id"] for i, _ in v} for v in by_arm.values()]) if all(by_arm.values()) else set()
    model_arms = {a: tally([(i, s) for i, s in v if i["id"] in ids]) for a, v in by_arm.items() if v}
    ref = run_ref([i for i in its if i["id"] in ids], CF) if ids else {}

    res = {"block": "SLOT_FILLING_RESULT_R5",
           "prereg": "tests/data/slot_filling_prereg_r5.json",
           "model": CK.MEASUREMENT_MODEL,
           "★实际执行数": n, "★硬上限": CAP, "★每条尝试次数(不是重试次数)": ATTEMPTS, "调用或格式失败": fails,
           "★配对交集": "%d/%d 条(两臂都有可用读数的)" % (len(ids), len(its)),
           "★★★两臂提示词哈希(现算)": sha_now,
           "★★★两臂唯一差异(逐字)": {"A": CRITERION_A or "(空)", "B": CRITERION_B},
           "★★★五臂对照(四条零调用 + 一条模型臂 · 同一批 items · 同一套打分)": dict(model_arms, **ref),
           "★★★怎么读这些数": "① **predicate 只看鉴别格** —— 多数类格是零基线免费答对的, 会把鉴别格稀释掉; "
               "② **端到端两档分开报不许合并** —— 附件 A 的信号**只能从「只用合同明文」档读**, "
               "因为「明文+解释」档下 NOT_OF_DECLARED_KIND 会产生相同的拦截结果; "
               "③ **超过零基线只证明读了文本**, 要超过**最佳浅层规则**才谈得上读懂语义; "
               "④ **n=1 每条零重试** —— r3 实测同一仪器重测一致率仅 60%, 每个数都是**单次读数**; "
               "⑤ **不得**与 r4 的历史读数直接比(item 集不同 + 重测噪声)。",
           "★★★这一轮不回答什么": "**不回答「模型在完全不知道该判据时能否填对」** —— "
               "RESTATES_IDENTIFIER 这个标签名**本身就是判据的压缩**, A 臂也拿到了它。"
               "A/B 的差是「判据展开 vs 压缩成标签名」。"
               "★ 也**不回答**「模型能不能在自然语料上做这件事」—— 分母是**手构最小对照**。",
           "rows": rows}
    # ★★★ 先把**原始 rows 落盘的内容准备好**, judge 出任何问题都不许吃掉 64 次调用的原始记录。
    #   r3 那版正是 main() 跑完 16 次后必 KeyError, 而 12 道闸没一道碰过它。
    if model_arms:
        try:
            res.update(judge(model_arms, ref, n, fails))
        except Exception as e:
            res["★★★判据计算抛错(原始 rows 已保全)"] = "%s: %s" % (type(e).__name__, e)
    else:
        res["★★★没有可用的配对交集"] = ("两臂没有共同的可用条目 ⇒ **判据未计算**。"
            "★ 这**不是**「模型未达成」, 是**没有读数**。不得按未达成读。")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n执行 %d/%d · 失败 %d · 配对交集 %s" % (n, CAP, fails, res["★配对交集"]))
    for k in ("★★★主判据: B 臂鉴别格 vs 最佳浅层规则", "次判据: B − A(判据展开 vs 压缩成标签名)"):
        if k in res:
            print("\n%s\n  %s" % (k, json.dumps(res[k], ensure_ascii=False, indent=2)[:600]))
    print("\n判读降级:", res.get("★★★判读降级"))
    print("\n→", OUT)


if __name__ == "__main__":
    main()


# ────────────────────── 零调用桩自检 ──────────────────────

def selfcheck():
    """★★★ **零调用**。用构造出来的填充跑完整判据链, 验证它**双向可达**。

    ★ r4 的教训: 全新判据若没有桩自检, 就不知道它能不能红。
    ★★ 本轮最要紧的一态是 ⑧ —— 评审用来穿过草案 D1–D7 全部七条的**纯正则填充器**,
       现在必须被 **D6(≤ 最佳浅层规则)** 抓住。
    """
    import cce_claim_frame as CF
    import shallow_cue_arm as SCA
    its = items()
    tok = _best_token()
    D = GOLD["★默认槽位"]

    def F_gold(it, sup):  return dict(D, **it["gold"][sup])
    def F_base(it, sup):
        f = dict(BASELINE)
        if sup == "B": f["predicate"] = "OWNERSHIP"
        return f
    def F_shallow(it, sup): return SCA.fill(it["text"], it["ev"][0 if sup == "A" else 1][1], sup == "A")
    _fills = dict((n, fn) for n, fn in ref_fills())
    F_best = [fn for n, fn in ref_fills() if n.startswith("④")][0]
    def F_unspec(it, sup): return {s: "UNSPECIFIED" for s in SLOTS}
    def F_illegal(it, sup):
        f = dict(F_gold(it, sup)); f["polarity"] = "TOTALLY_MADE_UP"; return f
    def _noisy(q, seed):
        """★★★ **假说为真 + 现实噪声**: 金标, 但每格以 1−q 的概率翻成别的合法值。

        ★ 这一态是投料前评审抓到的缺口: 原八态**全是退化填充**, 没有一态是「模型其实会做, 只是有噪声」
          —— 而前置条件② 的 24 格零容差正是在这种态下才暴露。
        """
        import random as _r
        def f(it, sup):
            g = dict(D, **it["gold"][sup])
            rnd = _r.Random("%s|%s|%d" % (it["id"], sup, seed))
            out = {}
            for s_ in SLOTS:
                v = g.get(s_, "UNSPECIFIED")
                if rnd.random() > q:
                    alt = sorted(LEGAL[s_] - {v})
                    v = alt[rnd.randrange(len(alt))] if alt else v
                out[s_] = v
            return out
        return f

    import re as _re
    _QTY = _re.compile(r"\b(one|two|three|four|five|six|seven|eight|nine|ten|twice|half|few|about|\d+)\b", _re.I)
    _TIME = _re.compile(r"\b(hour|hours|minute|minutes|day|days|week|weeks|month|months|"
                        r"year|years|night|morning|mornings|while|lately|now)\b", _re.I)

    def _qty_rule(it, sup):
        """★★★ 2026-09-15 投料前评审实测抓到的那条**族外**规则:
        「A 支既不含量词/数字、也不含时段单位 ⇒ 填 RESTATES_IDENTIFIER」。
        它当时鉴别格 **19/24**、通过**全部三个前置条件**、单侧 p=3.8e-5 —— 一条零语义的正则。
        ⇒ 对照集重造 + ② 改用净增益之后, 它**必须被挡住**。这一态就是那个回归测试。
        """
        f = F_base(it, sup)
        if sup == "A":
            sp_ = it["ev"][0][1]
            if not (_QTY.search(sp_) or _TIME.search(sp_)):
                f["predicate"] = "RESTATES_IDENTIFIER"
        return f

    def F_overfire(it, sup):        # 一刀切: A 支一律 RESTATES_IDENTIFIER
        f = F_base(it, sup)
        if sup == "A": f["predicate"] = "RESTATES_IDENTIFIER"
        return f

    STATES = [
        ("① 两臂=金标",                     F_gold,    F_gold),
        ("② 两臂=零基线(不读文本)",           F_base,    F_base),
        ("③ 两臂=最佳单token浅层规则",        F_best,    F_best),
        ("④ A=浅层 · B=金标",               F_shallow, F_gold),
        ("⑤ 两臂=枚举外取值",                F_illegal, F_illegal),
        ("⑥ 两臂=全 UNSPECIFIED",           F_unspec,  F_unspec),
        ("⑦ 两臂=一刀切(A支全填RESTATES)",    F_overfire, F_overfire),
        ("⑧ ★★★两臂=纯正则(评审用来穿过七条降级的那个)", F_shallow, F_shallow),
        ("⑨ ★★★假说为真+噪声 q=0.95", _noisy(0.95, 1), _noisy(0.95, 1)),
        ("⑩ ★★★假说为真+噪声 q=0.90", _noisy(0.90, 2), _noisy(0.90, 2)),
        ("⑪ ★★★假说为真+噪声 q=0.80", _noisy(0.80, 3), _noisy(0.80, 3)),
        ("⑫ ★★★族外量词规则(2026-09-15 评审抓到的那条)", _qty_rule, _qty_rule),
    ]
    out = {}
    for name, fa, fb in STATES:
        arms = {}
        for arm, f in (("A_判据压缩成标签名", fa), ("B_判据展开为合同条款", fb)):
            arms[arm] = tally([(it, score({"片段一": f(it, "A"), "片段二": f(it, "B")}, it, CF))
                               for it in its])
        ref = run_ref(its, CF)
        j = judge(arms, ref, len(its) * 2, 0)
        m = j.get("★★★主判据: B 臂鉴别格 vs 最佳浅层规则", {})
        out[name] = {"B 鉴别格": m.get("B 臂鉴别格"), "B 多数类格": m.get("B 臂多数类格"),
                     "净增益": (m.get("★★★净增益(鉴别格对数 − 多数类格错数)") or {}).get("B 臂"),
                     "单侧p": m.get("单侧 p(二项, 事前可算)"),
                     "三个前置条件": m.get("★三个前置条件"), "主判据结论": m.get("★结论"),
                     "非法取值": arms["B_判据展开为合同条款"]["非法取值"],
                     "端到端可用": arms["B_判据展开为合同条款"]["★端到端可用"],
                     "降级": j.get("★★★判读降级")}
    return out
