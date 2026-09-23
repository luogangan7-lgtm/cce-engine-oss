#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""r4 · **模型自己填六槽位** —— 判据见 tests/data/slot_filling_prereg_r4.json(测量前冻结)。

★★★ 前三步(全零调用)已给出**能力上界**: 槽位标注正确时, 最小对照 10/10 漏 → 0/10,
  真实证书回放阴性 3/3 拦住 · 对照 0/12 误拦。**但那是因为标注是我做的。**
  r4 问: **模型自己填, 填得对吗? 标注误差会让端到端漏掉几条?**

★★★ 刻意隔离: 只测**给定片段时的槽位标注**。span 与 supports 从已冻结的最小对照取,
  **不让模型选片段** ⇒ 「填错槽位」与「选错片段」不混在一起。

★ key 仅从 /Volumes/data/viral-skill-eval/.env 进程内加载, 不回显 · 不复制 · 不写仓 · 不写记忆。
★ 硬上限 20 · 零重试 · 失败也计数, 不进分母。
"""
import json, os, pathlib, random, re, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

PREREG = json.loads((ROOT / "tests/data/slot_filling_prereg_r4.json").read_text(encoding="utf-8"))
PAIRS = json.loads((ROOT / "tests/data/semantic_minimal_pairs.json").read_text(encoding="utf-8"))
GOLD = json.loads((ROOT / "tests/data/claim_frame_annotations.json").read_text(encoding="utf-8"))
CAP = PREREG["执行"]["★请求硬上限"]
OUT = pathlib.Path(os.environ.get("CCE_SLOT_OUT") or (ROOT / "results" / "slot_filling_r4.json"))
# ★★★ 2026-09-15 登记(**不改本文件的提示词**, 改了读数就不再对应它):
#   下面第 66 行给模型的 predicate 枚举是 OF_DECLARED_KIND / NOT_OF_DECLARED_KIND / UNSPECIFIED,
#   **没有 RESTATES_IDENTIFIER** —— 而 2026-09-14 owner 裁定升为合同的附件 A 正是那一条。
#   ⇒ **r4 那一轮, 模型在这一格上无从填出合同要求的取值**。
#   ★ 所以 r4 读到的「predicate 18/20 = 零基线 18/20(零增益)」**不能**读成
#     「模型分不出复述与增量」—— 它连那个选项都没拿到。
#   ★ 下一轮必须: ① 枚举补 RESTATES_IDENTIFIER ② 提示词给出附件 A 的判据文字
#     (合同已升, 不再是「没给模型看的解释」) ③ 对照对见 tests/data 的 contract_pairs。
#   ★★ **不在本轮补**: 预算已用尽且读数已出, 改提示词 = 让已付费的读数失去对应物。

SLOTS = ("speaker", "polarity", "time", "citation", "possession", "predicate")
# ★★★ **敏感格**由判据结构决定(不由数据决定): _p 只用 polarity/citation/predicate;
#   _q 只用 polarity/speaker/time/possession。其余是**装饰格** —— 填对填错都不进端到端。
#   ⇒ 逐槽位准确率必须**分开报**, 否则装饰格会把真实能力稀释掉。
SENSITIVE = {"A": ("polarity", "citation", "predicate"),
             "B": ("polarity", "speaker", "time", "possession")}
# ★ 枚举校验: 非法取值**单列**, 不许混进「被拦住」
import cce_claim_frame as _CF_ENUM
LEGAL = {"speaker": set(_CF_ENUM.SPEAKER), "polarity": set(_CF_ENUM.POLARITY),
         "time": set(_CF_ENUM.TIME), "citation": set(_CF_ENUM.CITATION),
         "possession": set(_CF_ENUM.POSSESSION),
         "predicate": {"OF_DECLARED_KIND", "NOT_OF_DECLARED_KIND", "OWNERSHIP",
                       _CF_ENUM.UNSPEC}}
# ★★★ **零基线臂**(零调用): 完全不读文本, 每格都填多数类。
#   金标取值极度倾斜 ⇒ 没有这条基线, 「逐槽位准确率 93%」毫无意义。
BASELINE = {"speaker": "SELF", "polarity": "ASSERTED", "time": "PAST_OR_PRESENT",
            "citation": "DIRECT", "possession": "OWNED", "predicate": "OF_DECLARED_KIND"}

PROMPT = """下面是一段英文文本, 和从它里面取出的**两条片段**。

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
                 OF_DECLARED_KIND(是那一类) / NOT_OF_DECLARED_KIND(不是那一类) / UNSPECIFIED
                 没标 kind 的那条填 null。
                 ★ 只填这六个大写标签之一, **不要加括号、不要加说明文字**。

只输出 JSON, 不要别的:
{
  "片段一": {"speaker": "...", "polarity": "...", "time": "...", "citation": "...", "possession": "...", "predicate": "..."},
  "片段二": {"speaker": "...", "polarity": "...", "time": "...", "citation": "...", "possession": "...", "predicate": "..."}
}"""


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


def _norm(v):
    """只做表面清洗(去空白引号、大写) —— 不做任何取值映射。"""
    if v is None:
        return "UNSPECIFIED"
    if not isinstance(v, str):
        return "UNSPECIFIED"
    return v.strip().strip("\"'「」`").upper() or "UNSPECIFIED"


def items():
    """20 条 = 10 对 × pos/neg。每条带两条已冻结的证据。"""
    out = []
    for p in PAIRS["pairs"]:
        for side in ("pos", "neg"):
            s = p[side]
            out.append({"id": "%s/%s" % (p["id"], side), "cls": p["cls"], "side": side,
                        "依据": p["依据"], "text": s["text"],
                        "ev": [("A", s["A"][0], s["A"][2]), ("B", s["B"][0], None)],
                        "gold": GOLD["annotations"][p["id"]]["frames"][side]})
    return out


def score(filled, it, CF):
    """给一份槽位填充打分。filled = {"片段一":{...}, "片段二":{...}}。

    返回 dict: 逐槽位对错(分敏感/装饰) · 非法取值数 · 两档端到端 allow。
    ★ **非法取值单列**, 不混进「被拦住」—— 否则 10 个枚举外取值就能伪造「复现上界」。
    """
    cells, illegal = [], 0
    frames_ok, frames = True, []
    for idx, key in ((0, "片段一"), (1, "片段二")):
        sup = it["ev"][idx][0]
        d = filled.get(key) or {}
        g = it["gold"]["A" if sup == "A" else "B"]
        kw = {}
        for s_ in SLOTS:
            mv = _norm(d.get(s_))
            if mv not in LEGAL[s_]:
                illegal += 1
                mv_use = CF.UNSPEC          # 非法 ⇒ 当未填, 但**另计**
            else:
                mv_use = mv
            kw[s_] = mv_use
            if s_ == "predicate" and sup == "B":
                continue
            cells.append({"支": sup, "槽": s_, "模型": mv, "金标": g.get(s_, CF.UNSPEC),
                          "对": mv == g.get(s_, CF.UNSPEC),
                          "敏感": s_ in SENSITIVE[sup], "合法": mv in LEGAL[s_]})
        if sup == "B":
            kw["predicate"] = it["gold"]["B"].get("predicate", "OWNERSHIP")
        try:
            frames.append(CF.ClaimFrame(
                it["ev"][idx][1], CF.CONJ_P if sup == "A" else CF.CONJ_Q,
                object="o", increment_kind=(it["ev"][idx][2] if sup == "A" else None), **kw))
        except Exception:
            frames_ok = False
    # ★★★ 含非法取值的条目, 端到端结果**不可用** —— 与「调用失败不进分母」同一个原则。
    #   非法取值被当成未填 ⇒ fail-closed ⇒ 看起来像「拦住了」,
    #   那会让「复现上界」由若干个枚举外取值**伪造**出来。
    out = {"cells": cells, "非法取值": illegal, "构造成功": frames_ok,
           "端到端可用": (illegal == 0 and frames_ok)}
    for tier, ui in (("只用合同明文", False), ("明文+解释", True)):
        out[tier] = (CF.allow_label(frames, use_interpretation=ui)["allow"]
                     if frames_ok and frames else False)
    return out


def tally(scored):
    """scored: [(it, score_dict)]。返回逐槽位(分敏感/装饰) + 两档端到端。"""
    acc = {}
    for s_ in SLOTS:
        sel = [c for _, sc in scored for c in sc["cells"] if c["槽"] == s_ and c["敏感"]]
        if sel:
            acc.setdefault(s_, {})["敏感"] = "%d/%d" % (sum(c["对"] for c in sel), len(sel))
        dec = [c for _, sc in scored for c in sc["cells"] if c["槽"] == s_ and not c["敏感"]]
        if dec:
            # ★★★ 装饰格**不计分**。判据根本不读它们, 而金标在这些格上是**填充值**
            #   (实测 A 支有 8 格与文本直接矛盾), 按文本实读反而扣分(possession 读 34/40 < 不读 36/40)
            #   ⇒ 报它的「准确率」= 报一个**负鉴别力**的数。
            acc.setdefault(s_, {})["装饰"] = "%d 格 —— **不计分**(判据不读 · 金标是填充值)" % len(dec)
    # ★ 端到端分母**只算可用的**(无非法取值且构造成功)
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
    return {"逐槽位": acc, "端到端": e2e,
            "★端到端可用": "%d/%d" % (len(usable), len(scored)),
            "非法取值": sum(sc["非法取值"] for _, sc in scored),
            "构造失败": sum(1 for _, sc in scored if not sc["构造成功"])}


def main():
    assert PREREG["★★★status"].startswith("**READY**"), "★ 预注册未就绪, 不得发起"
    _load_key()
    from exp_crossmodel_desire import call_model
    import cce_knot_classify as CK
    import cce_claim_frame as CF

    its = items()
    random.Random(20260914).shuffle(its)
    rows, scored, n = [], [], 0
    t0 = time.time()
    for it in its:
        if n >= CAP:
            print("★★★ 撞硬上限 %d —— 停" % CAP); break
        n += 1
        (sa, spa, ka), (sb, spb, _) = it["ev"]
        raw, meta = call_model(
            CK.MEASUREMENT_MODEL,
            PROMPT % (it["text"], spa, ("  · kind=%s" % ka) if ka else "", spb, ""),
            temperature=0.0, max_retries=1)
        obj = _parse(raw) if not meta.get("error") else None
        if obj is None:
            rows.append({"id": it["id"], "cls": it["cls"], "side": it["side"],
                         "调用成功": False,
                         "why": "调用或格式失败(计入预算, 不进分母): %s"
                                % (meta.get("error") or "无法解析 JSON"),
                         "raw": (raw or "")[:160]})
            print("  %-14s CALL_FAILED" % it["id"]); continue
        sc = score(obj, it, CF)
        scored.append((it, sc))
        rows.append({"id": it["id"], "cls": it["cls"], "side": it["side"], "调用成功": True,
                     "模型原样": obj, "非法取值": sc["非法取值"], "构造成功": sc["构造成功"],
                     "只用合同明文": sc["只用合同明文"], "明文+解释": sc["明文+解释"],
                     "敏感格全对": all(c["对"] for c in sc["cells"] if c["敏感"])})
        print("  %-14s %-12s 敏感格全对=%-5s 非法=%d 明文+解释allow=%s"
              % (it["id"], it["cls"], rows[-1]["敏感格全对"], sc["非法取值"], sc["明文+解释"]))

    model = tally(scored)
    # ★★★ 两条**零调用**参照臂 —— 与模型同一批 items、同一套打分
    ref = {}
    for name, fill in (("金标(上界)", None), ("零基线(常数多数类填充)", BASELINE)):
        rs = []
        for it, _ in scored:
            if fill is None:
                f = {"片段一": it["gold"]["A"], "片段二": it["gold"]["B"]}
            else:
                f = {"片段一": dict(fill), "片段二": dict(fill)}
            rs.append((it, score(f, it, CF)))
        ref[name] = tally(rs)

    dg = []
    fails = len(rows) - len(scored)
    if fails * 2 > len(rows):
        dg.append("D1 调用或格式失败 %d/%d(过半) ⇒ 失效在**格式层**" % (fails, len(rows)))
    for s_ in SLOTS:
        vals = [c["模型"] for _, sc in scored for c in sc["cells"] if c["槽"] == s_]
        if vals and all(v == "UNSPECIFIED" for v in vals):
            dg.append("D2 槽位 **%s** 全部填 UNSPECIFIED ⇒ **该槽位这一轮没被测到**" % s_)
    if scored and not any(sc["明文+解释"] for it, sc in scored if it["side"] == "pos"):
        dg.append("D3 对照**全部**不通过 ⇒ 通道退化, 阴性读数作废")
    usable_n = int(model["★端到端可用"].split("/")[0])
    if scored and usable_n * 2 <= len(scored):
        dg.append("D4 端到端**可用样本只有 %s** —— 其余含非法取值或构造失败 ⇒ "
                  "失效在**取值层**, 语义能力未被测到; 端到端那几个数**不得单独引用**"
                  % model["★端到端可用"])
    # ★★★ D5: 模型不优于零基线 ⇒ 没有证据说明它在读文本
    mb = model["端到端"]["明文+解释"]["阴性被放行"]
    bb = ref["零基线(常数多数类填充)"]["端到端"]["明文+解释"]["阴性被放行"]
    if mb == bb and usable_n:
        dg.append("D5 模型的阴性放行 %s 与**零基线**(完全不读文本的常数填充) %s **相同** "
                  "⇒ **没有证据说明模型在读文本**" % (mb, bb))

    res = {"block": "SLOT_FILLING_RESULT_R4",
           "prereg": "tests/data/slot_filling_prereg_r4.json",
           "model": CK.MEASUREMENT_MODEL,
           "★实际执行数": n, "★硬上限": CAP, "★重试": 0, "调用或格式失败": fails,
           "★★★三臂对照(同一批 items · 同一套打分)": {
               "模型": model, "金标(上界)": ref["金标(上界)"],
               "零基线(常数多数类填充)": ref["零基线(常数多数类填充)"]},
           "★★★零基线是什么": "**完全不读文本**, 每格都填多数类"
               "(SELF/ASSERTED/PAST_OR_PRESENT/DIRECT/OWNED/OF_DECLARED_KIND)。"
               "★ 金标取值极度倾斜(38:2 一类), 没有这条基线, 「逐槽位准确率 93%」**毫无意义**。"
               "**模型必须显著优于它, 才说明它在读文本。**",
           "★★★敏感格与装饰格": "**敏感格**由判据结构决定: _p 只用 polarity/citation/predicate; "
               "_q 只用 polarity/speaker/time/possession。其余是**装饰格**, 填对填错**都不进端到端**。"
               "⇒ 分开报, 否则装饰格会把真实能力稀释掉。",
           "★★★非法取值单列": "枚举外取值**另计**, 当作未填(UNSPECIFIED)进判据, "
               "**不许**混进「被拦住」—— 否则「复现上界」可以由若干个非法取值伪造出来。",
           "★★★两档都报": "只用合同明文 / 明文+解释 **分开报, 不许合并** —— "
               "r3/MIS-4 的头条结论就挂在「只用明文」那一档上。",
           "★★★判读降级(测量前冻结)": dg or "无",
           "★★★不得据此说": PREREG["★★★不得据此说"],
           "★★★已知局限(测量前写下)": PREREG["★★★已知局限(测量前写下)"],
           "★★★本轮不设达标线": PREREG["★★★主判据(测量前冻结)"]["★★★本轮不设达标线"],
           "★这些数是什么不是什么": PREREG["★★★主判据(测量前冻结)"]["★这些数是什么不是什么"],
           "elapsed_s": round(time.time() - t0, 1), "rows": rows}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n%-24s %-16s %-16s" % ("", "阴性放行(明文+解释)", "对照通过"))
    for k in ("金标(上界)", "零基线(常数多数类填充)"):
        e = ref[k]["端到端"]["明文+解释"]
        print("  %-22s %-16s %-16s" % (k, e["阴性被放行"], e["对照通过"]))
    e = model["端到端"]["明文+解释"]
    print("  %-22s %-16s %-16s" % ("**模型**", e["阴性被放行"], e["对照通过"]))
    print("\n逐槽位(敏感格 / 装饰格):")
    for s_ in SLOTS:
        m_ = model["逐槽位"].get(s_, {})
        b_ = ref["零基线(常数多数类填充)"]["逐槽位"].get(s_, {})
        print("  %-12s 模型 敏感%-8s 装饰%-8s | 零基线 敏感%-8s"
              % (s_, m_.get("敏感", "-"), m_.get("装饰", "-"), b_.get("敏感", "-")))
    print("\n端到端可用 %s · 非法取值 %d · 构造失败 %d · 执行 %d/%d · 调用失败 %d"
          % (model["★端到端可用"], model["非法取值"], model["构造失败"], n, CAP, fails))
    for d_ in dg:
        print("  ★★★ 判读降级: %s" % d_)
    print("→", OUT)


if __name__ == "__main__":
    main()
