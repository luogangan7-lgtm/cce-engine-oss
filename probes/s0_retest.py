# -*- coding: utf-8 -*-
"""s0 两臂**无金标**对比: 同一批 42 条再读一轮, 与 results/s0_jev_shadow.json 的第一轮配对。

★ owner 裁定(2026-09-23): s0 六面(进程位置/触发事件/…/情绪余温)**没有人类金标可言** —— 人读纯文本也判不出内在状态。
  所以这里**不问谁对**, 只问三件不需要真值的事:
  ① 同臂重测稳定性: 每面每臂 Cohen κ(多类, 独立基线 pe=Σ p_i q_i)。
  ② 准确率上界: 两轮读出不同的条目至多一轮对 ⇒ 该臂在这面的**两轮平均准确率 ≤ 1 − d/(2n)**, 对任何真值成立。
  ③ 结构约束: 情绪余温 按 taxonomy 是「上一轮互动留下的感觉(闭环接口)」; 这里是**首次冷读**, 没有上一轮 ⇒
     唯一站得住的取值是 首轮无余温 / 未知; 其他取值 = 凭常识补 = 违反「读不出就填未知, 严禁猜」。这一条与文本是首帖还是回帖无关。
★ 会发起调用: MiniMax 42(订阅) + Jev 42(计量 ≈$0.002)。硬上限各 42, 撞上即停。产物只放指针与统计量, 不落原文。
"""
import argparse, collections, hashlib, importlib.util, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUN1 = ROOT / "results/s0_jev_shadow.json"
OUT = ROOT / "results/s0_retest.json"; PARTIAL = ROOT / "results/s0_retest_partial.jsonl"
STRUCT_OK = {"首轮无余温", "未知"}          # ③ 冷读时 情绪余温 唯一站得住的取值
_s = importlib.util.spec_from_file_location("_shadow", ROOT / "probes/s0_jev_shadow.py"); shadow = importlib.util.module_from_spec(_s); _s.loader.exec_module(shadow)
KEYS = [f["key"] for f in shadow.READABLE]


def norm(v, facet):
    """未知/未提及/非法值 合并成 '未知' —— 稳定性看的是「读出了什么」, 非法值和未知同属「没读出」。"""
    if v in shadow.UNKNOWN or v not in facet["values"] + ["未知"]: return "未知"
    return v


def kappa_multi(xs, ys):
    """多类 Cohen κ, pe 用独立基线 Σ p_i q_i(与 r2 的二类 kappa_ci 同一约定)。"""
    n = len(xs); assert n == len(ys) and n > 0
    po = sum(1 for x, y in zip(xs, ys) if x == y) / n
    px, py = collections.Counter(xs), collections.Counter(ys)
    pe = sum(px[c] / n * py[c] / n for c in set(xs) | set(ys))
    if pe >= 1: return {"po": round(po, 4), "pe": 1.0, "kappa": None, "★为什么算不出": "两轮各自全是同一取值 ⇒ pe=1, κ 无定义(读出的是常数, 不是文本)。"}
    return {"po": round(po, 4), "pe": round(pe, 4), "kappa": round((po - pe) / (1 - pe), 4)}


def arm_stats(run1, run2, arm):
    """run1/run2: {ptr: {面: 值}}。返回 {面: {...}}。"""
    ptrs = sorted(set(run1) & set(run2)); per = {}
    for f in shadow.READABLE:
        k = f["key"]; xs = [norm(run1[p].get(k), f) for p in ptrs]; ys = [norm(run2[p].get(k), f) for p in ptrs]
        d = sum(1 for x, y in zip(xs, ys) if x != y); n = len(ptrs)
        flips = collections.Counter("%s→%s" % (x, y) for x, y in zip(xs, ys) if x != y)
        per[k] = {"n": n, "两轮不同": d, **kappa_multi(xs, ys), "★准确率上界(两轮均值)": round(1 - d / (2 * n), 4),
                  "未知率 轮1/轮2": [sum(1 for x in xs if x == "未知"), sum(1 for y in ys if y == "未知")],
                  "翻转形态 top3": dict(flips.most_common(3))}
    return per


def struct_check(run, arm):
    vals = [norm(r.get("情绪余温"), next(f for f in shadow.READABLE if f["key"] == "情绪余温")) for r in run.values()]
    bad = sum(1 for v in vals if v not in STRUCT_OK)
    return {"n": len(vals), "违反结构约束(填了 正向/负向/中性)": bad, "取值分布": dict(collections.Counter(vals))}


def build_result(rows1, rows2, ledger):
    r1 = {"mm": {r["ptr"]: r["mm"] for r in rows1 if r["mm_ok"]}, "jev": {r["ptr"]: r["jev"] for r in rows1 if r["jev_ok"]}}
    r2 = {"mm": {r["ptr"]: r["mm"] for r in rows2 if r["mm_ok"]}, "jev": {r["ptr"]: r["jev"] for r in rows2 if r["jev_ok"]}}
    per = {arm: arm_stats(r1[arm], r2[arm], arm) for arm in ("mm", "jev")}
    struct = {arm: {"轮1": struct_check(r1[arm], arm), "轮2": struct_check(r2[arm], arm)} for arm in ("mm", "jev")}
    # 逐面裁决: 只比「稳定性」与「结构纪律」, 不比准确率(没有真值)
    verdict = {}
    for k in KEYS:
        km, kj = per["mm"][k]["kappa"], per["jev"][k]["kappa"]
        um, uj = per["mm"][k]["★准确率上界(两轮均值)"], per["jev"][k]["★准确率上界(两轮均值)"]
        verdict[k] = {"κ MiniMax/Jev": [km, kj], "上界 MiniMax/Jev": [um, uj],
                      "更稳的臂": None if km is None or kj is None else ("Jev" if kj > km else "MiniMax" if km > kj else "持平")}
    return {"block": "S0_RETEST_NO_GOLD", "date": "2026-09-23", "★依据": "owner 2026-09-23 裁定: s0 内在状态面无人类金标, 只用无金标判据。",
            "★与第一轮配对": {"文件": str(RUN1.relative_to(ROOT)), "轮1 提示词 sha": shadow.s0_prompt("") and hashlib.sha256(shadow.s0_prompt("").encode()).hexdigest()[:16],
                           "轮1 Jev 题目集 sha": shadow.question_sha(), "★设计": "两轮同提示词/同题目集/同 body[:2000]/同 temperature=0 —— 只有时间在变"},
            "★判据": {"①稳定性": "同臂两轮 Cohen κ(多类, 独立基线)。κ 低 = 这一面读的是噪声, 不管换谁都不能接。",
                     "②准确率上界": "acc ≤ 1 − d/(2n): 两轮不同的条目至多一轮对。**对任何真值成立, 不需要金标**。",
                     "③结构约束": "情绪余温 是闭环接口(上一轮互动); 首次冷读没有上一轮 ⇒ 只能 首轮无余温/未知。填 正向/负向/中性 = 凭常识补。"},
            "★实际执行": {"轮2 行数": len(rows2), "双臂都成功": sum(1 for r in rows2 if r["mm_ok"] and r["jev_ok"])}, "★账本": ledger,
            "★★★逐面逐臂": per, "★★★情绪余温结构约束": struct, "★★★逐面裁决(只比稳定性)": verdict,
            "★不得据此说": ["不得说哪臂更准 —— 上界是上界, 不是估计。", "不得据此接生产 —— 接线是核心文件改动, 要 owner 点头。",
                          "κ 高只说明读得稳, 稳的可能是同一个偏见(两轮同 prompt 同模型)。"],
            "rows": rows2}


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); a = ap.parse_args(argv)
    rows1 = json.loads(RUN1.read_text(encoding="utf-8"))["rows"]
    ps = shadow.load_passages(); assert len(ps) == shadow.CAP == len(rows1)
    sys.path.insert(0, str(ROOT / "scripts")); from exp_v4_full_validation import extract_json_robust
    ledger = {"req": 0, "tok_in": 0, "minimax": 0}
    if a.dry_run:
        def mm_call(p): return json.dumps({f["key"]: f["values"][0] for f in shadow.READABLE}, ensure_ascii=False), {}
        def jv_call(body): return {"answers": {k: {"choice": "未知", "probabilities": {"未知": 1.0}} for k in body["questions"]}}, None
    else:
        s = importlib.util.spec_from_file_location("_r2", ROOT / "probes/extractor_counterexample_run_r2.py"); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); m._load_key()
        from exp_crossmodel_desire import call_model
        key = shadow._key()
        def mm_call(p):
            ledger["minimax"] += 1
            if ledger["minimax"] > shadow.CAP: raise RuntimeError("BUDGET_EXCEEDED minimax")
            return call_model("M3", p, temperature=0.0, max_retries=1)
        def jv_call(body): return shadow.jev_call(body, key, ledger)
        if PARTIAL.exists(): PARTIAL.unlink()
    rows2 = []
    for ptr, body in ps:
        c, meta = mm_call(shadow.s0_prompt(body)); rd = extract_json_robust(c, log_note="s0_retest") if c else None
        mm_ok = isinstance(rd, dict) and not (meta or {}).get("error")
        jr, jp, err = shadow.s0_jev_fill(body, jv_call)
        row = {"ptr": ptr, "mm_ok": bool(mm_ok), "mm": ({k: rd.get(k) for k in KEYS} if mm_ok else None), "jev_ok": jr is not None, "jev": jr,
               "jev_conf": ({k: round(max(v.values()), 4) for k, v in jp.items()} if jp else None), "jev_err": err}
        rows2.append(row)
        if not a.dry_run:
            with PARTIAL.open("a", encoding="utf-8") as fh: fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print("  %-48s mm=%s jev=%s" % (ptr, "ok" if mm_ok else "ERR", "ok" if jr else err))
    res = build_result(rows1, rows2, ledger)
    if a.dry_run: print("[dry-run] %d 条" % len(rows2)); return 0
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    for k, v in res["★★★逐面裁决(只比稳定性)"].items(): print("  %-6s κ mm/jev %s · 上界 %s · 更稳 %s" % (k, v["κ MiniMax/Jev"], v["上界 MiniMax/Jev"], v["更稳的臂"]))
    print("情绪余温结构违反 mm 轮1/轮2:", [res["★★★情绪余温结构约束"]["mm"][r]["违反结构约束(填了 正向/负向/中性)"] for r in ("轮1", "轮2")],
          "jev:", [res["★★★情绪余温结构约束"]["jev"][r]["违反结构约束(填了 正向/负向/中性)"] for r in ("轮1", "轮2")])
    print("账本:", ledger, "→", OUT); return 0


if __name__ == "__main__": sys.exit(main())
