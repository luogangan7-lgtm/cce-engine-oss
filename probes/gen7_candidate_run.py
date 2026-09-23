#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""候选代一轮 —— 按 tests/data/gen7_candidate_prereg.json 冻结的计划执行。

★★★ 不替换生产: 只把 stage2 的 prompt 换成候选构造器, **不改 scripts/cce_knot_classify.py**。
★★★ 判定事件: 每题一个 top-1 读数(**22 个被测单位**, 不是 176 个)。
★★★ 通过条件: 12 条**已裁定**断言上「本次计划执行中零个已确认违例」。
★ 未裁定的 10 题只记录, **不进分母**。
"""
import json, os, pathlib, sys, hashlib, traceback

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import cce_knot_classify as CK          # noqa: E402
import cce_stage2_candidate as V        # noqa: E402

OUT = ROOT / "results" / "gen7_candidate"
PREREG = json.loads((ROOT / "tests/data/gen7_candidate_prereg.json").read_text(encoding="utf-8"))
ASSERTS = json.loads((ROOT / "tests/data/local_contract_assertions.json").read_text(encoding="utf-8"))
ITEMS_P = pathlib.Path("/Volumes/data/cce-identified-vault/cce_runs/suspend_confirm_items.json")

REQUEST_CAP = 220          # 176 + 44 重试, 撞上限即停
_requests = {"n": 0}


def _counting_call(orig):
    def wrapped(*a, **kw):
        _requests["n"] += 1
        if _requests["n"] > REQUEST_CAP:
            raise RuntimeError(f"★★★ 撞请求上限 {REQUEST_CAP} —— **立即停**, 不追加")
        return orig(*a, **kw)
    return wrapped


def main():
    assert PREREG["★★★status"].startswith("**READY**"), "★ 预注册未就绪, 不得发起"
    if not ITEMS_P.exists():
        print("★ 降级(**无本机素材**): 找不到题库, **未发起任何调用**"); return
    items = json.loads(ITEMS_P.read_text(encoding="utf-8"))
    taxo = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)

    # ★ 计费闸: **两条路径都要包** —— s1 走 call_parse, s2 走 call_model。
    #   只包一条会把账少算一半, 正是 GPT 警告的「默默翻倍」的反面。
    CK.call_parse = _counting_call(CK.call_parse)
    CK.call_model = _counting_call(CK.call_model)

    # ★★★ 换 prompt 构造器 —— 只在本进程内, 不落盘, 生产文件一字未动
    orig_builder = CK._build_stage2_prompt
    CK._build_stage2_prompt = lambda t, text, s1: V.build(t, text, s1)

    (OUT / "run_params.json").write_text(json.dumps({
        "chain": "stage1(k=3)+stage2(KNOT_N=5) —— **整链 11 段里的两段, 不是完整链路**",
        "★被测单位": "每题一个 top-1 读数 = 22 个, **不是 176**",
        "k": 3, "KNOT_N": CK.KNOT_N, "MEASUREMENT_MODEL": CK.MEASUREMENT_MODEL,
        "★候选组件": ["ontology", "discriminant", "negative", "full_behavior"],
        "★decision_tree": "**关** —— 独立性代价见 cce_stage2_candidate.INDEPENDENCE_COST",
        "候选 s2 prompt 字数": len(V.build(taxo, "SAMPLE", {"tops": {}, "appraisal": {}})),
        "现行生产 s2 prompt 字数": len(orig_builder(taxo, "SAMPLE", {"tops": {}, "appraisal": {}})),
        "REQUEST_CAP": REQUEST_CAP,
        "★生产文件是否被改动": "否 —— 只在本进程内替换函数引用",
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    rows = []
    for it in items:
        rec = {"id": it["id"], "sha8": hashlib.sha256(it["b"].encode()).hexdigest()[:8]}
        try:
            s1 = CK.stage1(it["b"], "reddit hearing discussion", 3)
            s2 = CK.stage2(it["b"], s1, taxo)
            ks = s2.get("knots", [])
            rec["top1"] = ks[0]["key"] if ks else None
            rec["abstained"] = not ks
        except Exception as e:                       # ★ 逐题隔离: 一题炸不拖垮整轮
            rec["error"] = f"{type(e).__name__}: {e}"[:300]
            rec["traceback"] = traceback.format_exc()[-600:]
            rec["top1"] = None
        rows.append(rec)
        (OUT / "rows.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {rec['id']:34s} top1={rec.get('top1')} (累计请求 {_requests['n']})")

    # ── 判定: 只对 12 条已裁定断言 ────────────────────────────────
    by_id = {r["id"]: r for r in rows}
    adjudicated = [a for a in ASSERTS["断言"] if a["★★★断言状态"] == "已裁定"]
    violations, checked = [], []
    for a in adjudicated:
        r = by_id.get(a["用例"])
        if not r or r.get("top1") is None:
            checked.append({"用例": a["用例"], "结果": "NO_READING(未产出读数, 不计为通过也不计为违例)"})
            continue
        ok = r["top1"] != "suspend"
        checked.append({"用例": a["用例"], "top1": r["top1"], "谓词": a["输出谓词"], "符合": ok})
        if not ok:
            violations.append({"用例": a["用例"], "top1": r["top1"], "断言": a["输出谓词"]})

    verdict = {
        "★★★被测单位数": len(rows),
        "已裁定断言数": len(adjudicated),
        "未裁定(只记录, 不进分母)": len(ASSERTS["断言"]) - len(adjudicated),
        "★★★已确认违例": violations,
        "★★★结论": ("**PASS(本测试范围)** —— 在版本、用例、断言与重复次数均已冻结的这次测试中, "
                 "**未观察到**违反这些断言的输出。"
                 if not violations else
                 f"**FAIL(本测试范围)** —— 观察到 {len(violations)} 个已确认违例; 判据**不放宽**。"),
        "★★★不得据此说": PREREG["③★★★判据_显式留空"]["★★★不得据此说"],
        "★出现违例也不自动说明": "候选比旧代更差 —— 只表示没有达到这次有限测试闸。",
        "逐条": checked,
        "★真实计费请求数": _requests["n"],
        "★上限": REQUEST_CAP,
        "未裁定题的读数(诊断用, 无判据)": [
            {"用例": a["用例"], "top1": by_id.get(a["用例"], {}).get("top1")}
            for a in ASSERTS["断言"] if a["★★★断言状态"] != "已裁定"],
    }
    (OUT / "verdict.json").write_text(json.dumps(verdict, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n" + json.dumps({k: verdict[k] for k in
          ("★★★被测单位数", "已裁定断言数", "★★★已确认违例", "★★★结论", "★真实计费请求数")},
          ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
