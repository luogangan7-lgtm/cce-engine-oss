# -*- coding: utf-8 -*-
"""r6-jev: **同一批 r6 items · 同一套金标 · 同一套打分/judge**, 只把填槽的模型换成 TypeSafe Jev(System One)。

★ 复用: probes/slot_filling_run_r6.py 的 patched() ⇒ r5 执行器模块(items/score/tally/judge/run_ref 一行不改)。
★ Jev 不生成文本: 每条证据的每个槽位是一道 Choice 题, 选项 = 判据层的合法枚举(LEGAL, 现算派生)。
★ 密钥只从 /Volumes/data/viral-skill-eval/.env 读 TYPESAFE_API_KEY; **不回显、不落盘**。
★ 计量付费: 请求数与 token 都记账; 撞硬上限即停。429/529 退避重试, **每次尝试都计数**。
"""
import argparse, hashlib, importlib.util, json, pathlib, sys, time, urllib.request, urllib.error

ROOT = pathlib.Path(__file__).resolve().parents[1]
PRE = ROOT / "tests/data/slot_filling_prereg_r6_jev.json"
OUT = ROOT / "results/slot_filling_r6_jev.json"
PARTIAL = ROOT / "results/slot_filling_r6_jev_partial.jsonl"
API = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"
ARM = "B_判据展开为合同条款"          # ★ 复用 judge() 的主判据入口; 本轮这条臂**是 Jev**, 产物里逐字标明
CAP_REQ, CAP_TOK = 200, 300_000

SLOT_Q = {
    "speaker":   ("Is the subject of what this snippet states the speaker themself?",
                  {"SELF": "the statement is about the speaker themself", "OTHER": "the statement is about someone else",
                   "UNSPECIFIED": "the text does not make this clear"}),
    "polarity":  ("In the original text, is this snippet asserted, or does it fall inside the scope of a negation?",
                  {"ASSERTED": "it is asserted as holding", "NEGATED": "it falls inside a negation (denied)",
                   "UNSPECIFIED": "the text does not make this clear"}),
    "time":      ("Does the thing this snippet states happen in the past or present, or has it not happened yet?",
                  {"PAST_OR_PRESENT": "past or present", "FUTURE": "not yet happened / future",
                   "UNSPECIFIED": "the text does not make this clear"}),
    "citation":  ("Is this snippet the speaker's own direct statement, or is it relaying what someone else said?",
                  {"DIRECT": "the speaker's own direct statement", "REPORTED": "relayed from someone else",
                   "UNSPECIFIED": "the text does not make this clear"}),
    "possession": ("For the thing this snippet talks about, what is the speaker's relation to it?",
                  {"OWNED": "explicitly owns it", "EXPERIENCED": "does not own it but explicitly used or experienced it",
                   "ONE_NEGATED": "explicitly denies exactly one of owning / having used it, the other not mentioned",
                   "BOTH_NEGATED": "explicitly denies both owning it and having used it",
                   "UNSPECIFIED": "the text does not make this clear"}),
}
PRED_Q = ("This snippet is labeled kind={kind}. Is the content this snippet gives of that kind? "
          "Contract clause: an increment relative to x holds iff the text contains a statement about x that cannot be "
          "inferred from x's public identifier (model name, category) alone. If what the snippet says can be inferred "
          "from the thing's name alone, it produces no increment.")
PRED_OPTS = {"OF_DECLARED_KIND": "yes, it gives content of the declared kind",
             "NOT_OF_DECLARED_KIND": "it gives content, but not of the declared kind",
             "RESTATES_IDENTIFIER": "it only restates or points to the thing's identifier (name, brand, category); nothing that cannot be inferred from the name",
             "UNSPECIFIED": "the text does not make this clear"}


def _r6():
    s = importlib.util.spec_from_file_location("r6x", ROOT / "probes/slot_filling_run_r6.py")
    x = importlib.util.module_from_spec(s); s.loader.exec_module(x)
    return x.patched()


def build_request(it):
    """★ state 用完整文本(不截断) + 两条片段; 12 题(片段二不问 predicate, 与 MiniMax 提示词「填 null」一致)。"""
    (sa, spa, ka), (sb, spb, _) = it["ev"]
    state = {"text": it["text"], "snippet_1": {"span": spa, "kind": ka}, "snippet_2": {"span": spb}}
    qs = {}
    for i, sup in ((1, "A"), (2, "B")):
        for slot, (ins, opts) in SLOT_Q.items():
            qs["s%d_%s" % (i, slot)] = {"type": "choice", "instructions": "About snippet_%d: %s" % (i, ins), "criteria": opts}
    qs["s1_predicate"] = {"type": "choice", "instructions": "About snippet_1: " + PRED_Q.format(kind=ka), "criteria": PRED_OPTS}
    return {"model": MODEL, "state": state, "questions": qs}


def question_set_sha():
    """题目措辞的哈希 —— 预注册钉它。与 items 无关(把 kind 与片段占位)。"""
    blob = json.dumps({"SLOT_Q": SLOT_Q, "PRED_Q": PRED_Q, "PRED_OPTS": PRED_OPTS, "MODEL": MODEL}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _key():
    for line in (pathlib.Path("/Volumes/data/viral-skill-eval/.env")).read_text(encoding="utf-8").splitlines():
        line = line.strip().removeprefix("export ")
        if line.startswith("TYPESAFE_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("★ .env 里没有 TYPESAFE_API_KEY —— **未发起任何调用**")


class Ledger:
    def __init__(self): self.req = 0; self.tok_in = 0; self.tok_out = 0; self.retries = 0
    def reserve(self):
        if self.req + 1 > CAP_REQ or self.tok_in > CAP_TOK:
            raise RuntimeError("BUDGET_EXCEEDED req=%d tok_in=%d" % (self.req, self.tok_in))
        self.req += 1
    def d(self): return {"请求数(含重试)": self.req, "重试次数": self.retries, "input_tokens": self.tok_in, "output_tokens": self.tok_out,
                         "硬上限": {"请求": CAP_REQ, "input_tokens": CAP_TOK}}


def call_jev(body, key, ledger):
    for att in range(3):
        ledger.reserve()
        req = urllib.request.Request(API, data=json.dumps(body, ensure_ascii=False).encode(),
                                     headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.load(r)
            u = d.get("usage") or {}
            ledger.tok_in += int(u.get("input_tokens") or 0); ledger.tok_out += int(u.get("output_tokens") or 0)
            return d, None
        except urllib.error.HTTPError as e:
            code = e.code
            if code in (429, 529) and att < 2:
                ledger.retries += 1; time.sleep(3 * (att + 1)); continue
            return None, "HTTP %d" % code          # ★ 不带响应体
        except Exception as e:
            return None, type(e).__name__
    return None, "RETRY_EXHAUSTED"


def to_fill(resp):
    """Jev 答案 → r5 的填充形状 {片段一: {6 槽}, 片段二: {6 槽, predicate None}} + 概率。"""
    a = resp["answers"]; f1, f2, probs = {}, {}, {}
    for slot in SLOT_Q:
        f1[slot] = a["s1_%s" % slot]["choice"]; f2[slot] = a["s2_%s" % slot]["choice"]
        probs["s1_%s" % slot] = a["s1_%s" % slot]["probabilities"]; probs["s2_%s" % slot] = a["s2_%s" % slot]["probabilities"]
    f1["predicate"] = a["s1_predicate"]["choice"]; f2["predicate"] = None
    probs["s1_predicate"] = a["s1_predicate"]["probabilities"]
    return {"片段一": f1, "片段二": f2}, probs


def build_result(m, pre, rows, ledger_d, env, CF):
    its = {it["id"]: it for it in m.items()}
    by = [(its[r["id"]], m.score(r["模型原样"], its[r["id"]], CF)) for r in rows if r["调用成功"]]
    arms = {ARM: m.tally(by)}
    ref = m.run_ref([it for it, _ in by], CF)
    j = m.judge(arms, ref, ledger_d["请求数(含重试)"], sum(1 for r in rows if not r["调用成功"]))
    # ★ Jev 独有的读数: 鉴别格上它给 RESTATES 的概率
    disc = [r for r in rows if r["调用成功"] and r["predicate金标"] == "RESTATES_IDENTIFIER"]
    pr = [r["jev_probs"]["s1_predicate"].get("RESTATES_IDENTIFIER", 0.0) for r in disc]
    bulk = [r for r in rows if r["调用成功"] and r["predicate金标"] == "OF_DECLARED_KIND"]
    pb = [r["jev_probs"]["s1_predicate"].get("RESTATES_IDENTIFIER", 0.0) for r in bulk]
    res = {"block": "SLOT_FILLING_RESULT_R6_JEV", "prereg": str(PRE.relative_to(ROOT)),
           "prereg_sha256": hashlib.sha256(PRE.read_bytes()).hexdigest(),
           "model": env.get("model", MODEL), "★★★本轮的「B 臂」是 Jev": "为复用 r5 的 judge(), Jev 的填充放在 ARM=%r 这个键下; 它**不是** MiniMax。" % ARM,
           "★题目集哈希(现算)": question_set_sha(),
           "★实际执行数": len(rows), "★硬上限": len(m.items()), "调用或格式失败": sum(1 for r in rows if not r["调用成功"]),
           "★预算账本": ledger_d,
           "★★★五臂对照(四条零调用 + 一条模型臂 · 同一批 items · 同一套打分)": dict(arms, **ref),
           "★★★Jev 在鉴别格上给 RESTATES 的概率": {
               "鉴别格(金标=RESTATES) n": len(pr), "均值": round(sum(pr) / len(pr), 4) if pr else None,
               "≥0.5 的格数": sum(1 for x in pr if x >= 0.5), "分布(四舍五入 0.1)": sorted(round(x, 1) for x in pr),
               "多数类格(金标=OF_DECLARED) n": len(pb), "多数类上均值": round(sum(pb) / len(pb), 4) if pb else None,
               "★读法": "argmax 之外的信息: 若鉴别格上的概率整体高于多数类, 说明它**分得出方向**但阈值/校准不对; 若两者一样, 说明它根本没读出。"},
           "rows": rows}
    res.update(j)
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); a = ap.parse_args(argv)
    m = _r6()
    pre = json.loads(PRE.read_text(encoding="utf-8")); assert pre["★★★status"].startswith("**READY**")
    assert pre["★题目集哈希(测量前冻结)"] == question_set_sha(), "★★★ 题目措辞与预注册不符 —— **未发起任何调用**"
    sys.path.insert(0, str(ROOT / "scripts")); import cce_claim_frame as CF
    its = m.items(); import random; random.Random(20260915).shuffle(its)
    ledger = Ledger(); rows = []; env = {"model": MODEL}
    if a.dry_run:
        D = m.GOLD["★默认槽位"]
        def call(body, key, ledger):
            ledger.reserve(); ledger.tok_in += 500
            it = next(x for x in its if x["text"] == body["state"]["text"])
            g1, g2 = dict(D, **it["gold"]["A"]), dict(D, **it["gold"]["B"])
            ans = {}
            for slot in SLOT_Q:
                ans["s1_%s" % slot] = {"choice": g1[slot], "probabilities": {g1[slot]: 1.0}}
                ans["s2_%s" % slot] = {"choice": g2[slot], "probabilities": {g2[slot]: 1.0}}
            ans["s1_predicate"] = {"choice": g1["predicate"], "probabilities": {g1["predicate"]: 1.0}}
            return {"answers": ans, "model": "DRY_RUN", "usage": {}}, None
        key = "dry"
    else:
        call, key = call_jev, _key()
        if PARTIAL.exists(): PARTIAL.unlink()
    for it in its:
        body = build_request(it)
        resp, err = call(body, key, ledger)
        if err or not resp:
            row = {"臂": ARM, "id": it["id"], "调用成功": False, "err_类型": err}
        else:
            try:
                fill, probs = to_fill(resp)
                sc = m.score(fill, it, CF)
                row = {"臂": ARM, "id": it["id"], "调用成功": True, "模型原样": fill, "jev_probs": probs,
                       "predicate": fill["片段一"]["predicate"], "predicate金标": dict(m.GOLD["★默认槽位"], **it["gold"]["A"])["predicate"],
                       "鉴别格": dict(m.GOLD["★默认槽位"], **it["gold"]["A"])["predicate"] != m.MAJORITY_PRED}
                env["model"] = resp.get("model", MODEL)
            except Exception as e:
                row = {"臂": ARM, "id": it["id"], "调用成功": False, "err_类型": "OUTPUT_INVALID:" + type(e).__name__}
        rows.append(row)
        if not a.dry_run:
            with PARTIAL.open("a", encoding="utf-8") as fh: fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print("  %-14s %s pred=%s 金标=%s %s" % (it["id"], "ok " if row["调用成功"] else "ERR", row.get("predicate"), row.get("predicate金标"), "★鉴别格" if row.get("鉴别格") else ""))
    res = build_result(m, pre, rows, ledger.d(), env, CF)
    if a.dry_run:
        print("[dry-run] %d 条 · %s" % (len(rows), res["★★★主判据: B 臂鉴别格 vs 最佳浅层规则"]["★结论"][:30])); return 0
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    M = res["★★★主判据: B 臂鉴别格 vs 最佳浅层规则"]
    print("\nJev 鉴别格 %s · 净增益 %s · 门 %s ⇒ %s" % (M["B 臂鉴别格"], M["★★★净增益(鉴别格对数 − 多数类格错数)"]["B 臂"], M["★冻结的门(预注册, 非现算)"], M["★结论"]))
    print("降级:", res["★★★判读降级"]); print("账本:", ledger.d()); print("→", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
