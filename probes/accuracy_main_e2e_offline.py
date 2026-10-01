#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""accuracy/run_gates.py 的 main() 端到端编排 + G-K2 链路 —— 离线软件验证(零 API)。

★ 补的是 tests/data/accuracy_directed_tests.json「★仍未验证的」里的两条:
  「G-K2 成本档链路」与「main() 的端到端编排」。另两条(真实 provider 的语义准确率 / 重复稳定性)
  零 API 测不了, 预注册见 tests/data/accuracy_real_provider_prereg.json。
★ 替换边界: 只替换**传输结果**(urllib.request.urlopen, 经 probes/accuracy_offline_harness.load);
  资格考 / 准入 / 标注 / 落盘 / G-K1 / G-K2 / 汇总 / 扣发 全走**原代码**。
  假回复是确定性合成的(按 prompt 种类与正文哈希), 只用来驱动编排 —— **它不是金标, 也不测准确率**。
★ 每个臂都对一组**写在跑之前**的性质求真值; 变异臂必须让至少一条性质翻假(检出), 且确认源码真被改了。
"""
import collections, contextlib, hashlib, io, json, os, pathlib, sys, tempfile, threading

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "probes"))
sys.path.insert(0, str(ROOT / "scripts"))
import accuracy_offline_harness as AH  # noqa: E402

OUT = ROOT / "tests/data/accuracy_main_e2e_offline.json"
KN = ["pain_seek", "injustice", "belong", "reward", "display", "itch", "suspend", "inertia", "audit"]


def _h(*parts):
    return int(hashlib.sha256("|".join(parts).encode()).hexdigest(), 16)


class Fake:
    """按 prompt 种类给确定性回复, 并按种类计数(线程安全)。"""
    def __init__(self, wrong_qual=(), fact_outage=False, dist_mode="hash", fact_mode="hash"):
        self.wrong_qual, self.fact_outage = set(wrong_qual), fact_outage
        self.dist_mode, self.fact_mode = dist_mode, fact_mode
        self.n = collections.Counter()
        self.by_model = collections.Counter()
        self.lock = threading.Lock()
        self.m = None

    def __call__(self, model, prompt):
        m = self.m
        if "★示范锚例(留一法" in prompt:
            kind = "qualify"
            held = next(i for i in m.ANCHOR_TRUTH
                        if next(x for x in m.ANCHOR_CORPUS if x["id"] == i)["b"][:m.BODY_CHARS] in prompt)
            truth = m.ANCHOR_TRUTH[held]
            k = KN[(KN.index(truth) + 1) % 9] if model in self.wrong_qual else truth
            out = json.dumps({"knots": [{"key": k, "weight": 0.7}, {"key": KN[(KN.index(k) + 2) % 9], "weight": 0.3}]})
        elif "你是事实抽取器" in prompt:
            kind = "fact"
            hv = _h("fact", prompt)
            if self.fact_mode == "correlated" and not self.fact_outage:
                # 事实由该条「隐藏主结」的成本档决定 ⇒ 成本分与实测档相关, G-K2 应可过
                it = self._item(prompt)
                tier = m.tier_of(self._primary(it["id"]), it)
                nc = {"high": 3, "mid": 1}.get(tier, 0)
                keys = ("named_specific_model", "described_own_situation_in_detail", "asked_question")
                out = json.dumps({**{k: i < nc for i, k in enumerate(keys)}, "challenged_or_confronted": False,
                                  "offered_help_or_correction": False, "thanks_only": tier == "low"})
            else:
                out = "" if self.fact_outage else json.dumps({k: bool((hv >> i) & 1) for i, k in enumerate(
                ("named_specific_model", "described_own_situation_in_detail", "asked_question",
                 "challenged_or_confronted", "thanks_only", "offered_help_or_correction"))})
        elif "多个标注者在下列真实评论上判定不一致" in prompt:
            kind = "diag"
            out = json.dumps({"pairs": [], "taxonomy_fix": "offline"})
        elif self.dist_mode in ("agree", "split"):
            kind = "dist"
            iid = self._item(prompt)["id"]
            p = self._primary(iid)
            # agree: 次结也由条目定 ⇒ 面板一致; split: 次结按标注者乱给且各占 0.5 ⇒ top2 仍命中、JS 被抬高
            o = KN[_h("second", iid if self.dist_mode == "agree" else iid + model) % 9]
            o = o if o != p else KN[(KN.index(p) + 1) % 9]
            w = 0.7 if self.dist_mode == "agree" else 0.5
            out = json.dumps({"knots": [{"key": p, "weight": w}, {"key": o, "weight": round(1 - w, 2)}]})
        else:
            kind = "dist"
            hv = _h("dist", prompt.split("【")[-1])          # 主结只看正文 ⇒ 标注者之间大体一致
            a = KN[hv % 9]
            b = KN[(hv // 9 + (1 if _h(model, prompt) % 4 == 0 else 0)) % 9]   # 1/4 概率次结随标注者变
            out = json.dumps({"knots": [{"key": a, "weight": 0.6}, {"key": b if b != a else KN[(hv + 1) % 9], "weight": 0.4}]})
        with self.lock:
            self.n[kind] += 1
            self.by_model[(kind, model)] += 1
        return out


    def _item(self, prompt):
        m = self.m
        return next(x for x in m.SAMPLE if x["b"][:m.BODY_CHARS] in prompt)

    def _primary(self, iid):
        return KN[_h("primary", iid) % 9]


def run_arm(skip_gk2, wrong_qual=(), fact_outage=False, mutator=None, dist_mode="hash", fact_mode="hash"):
    fake = Fake(wrong_qual, fact_outage, dist_mode, fact_mode)
    with tempfile.TemporaryDirectory() as td:
        import calibration_framework as CF
        saved_log = CF.JSON_FAIL_LOG
        CF.JSON_FAIL_LOG = os.path.join(td, "json_extract_failures.log")      # 解析失败日志不进仓
        try:
            m = AH.load(source_mutator=mutator, responses=fake,
                        env={"CCE_SKIP_GK2": "1" if skip_gk2 else "0", "CCE_OUT_DIR": td})
            fake.m = m
            models, n_sample, n_anchor = list(m.MODELS), len(m.SAMPLE), len(m.ANCHOR_TRUTH)
            err, rc = None, None
            with AH._Tripwire() as tw, contextlib.redirect_stdout(io.StringIO()):
                try:
                    rc = m.main()
                except Exception as e:                       # 记下来, 由性质判
                    err = type(e).__name__
            gr = os.path.join(td, "gates_result.json")
            raw = os.path.join(td, "raw_annotations.json")
            g = json.load(open(gr, encoding="utf-8")) if os.path.exists(gr) else None
            r = json.load(open(raw, encoding="utf-8")) if os.path.exists(raw) else None
        finally:
            CF.JSON_FAIL_LOG = saved_log
    q = (g or {}).get("annotator_qualification") or {}
    admitted = (r or {}).get("annotators")
    return {"rc": rc, "exception": err, "tripwire_tripped": list(tw.tripped), "source_mutated": m._OFFLINE_MUTATED,
            "calls": dict(sorted(fake.n.items())),
            "dist_calls_by_model": {mm: fake.by_model[("dist", mm)] for mm in models},
            "gates_result_written": g is not None, "raw_written": r is not None,
            "admitted": admitted, "qual_status": q.get("status"),
            "overall_pass": (g or {}).get("overall_pass"),
            "withheld": bool((g or {}).get("★withheld")),
            "G_K1_pass": ((g or {}).get("G_K1v2_分布一致性") or {}).get("pass"),
            "G_K2_n": ((g or {}).get("G_K2v2_成本档预测") or {}).get("n"),
            "G_K2_pass": ((g or {}).get("G_K2v2_成本档预测") or {}).get("pass"),
            "G_K2_withheld": bool(((g or {}).get("G_K2v2_成本档预测") or {}).get("★withheld")),
            "pass_components": (g or {}).get("★pass_components"),
            "structural_max": m.structural_max_requests(), "budget_limit": m.BUDGET_LIMIT,
            "_n": {"sample": n_sample, "anchor": n_anchor, "models": models}}


def properties(name, a):
    """写在跑之前的性质。每臂只求与它相关的那几条。"""
    n, M = a["_n"], a["_n"]["models"]
    P = {"零网络": a["tripwire_tripped"] == [],
         "资格考每人考满锚例": a["calls"].get("qualify", 0) == len(M) * n["anchor"],
         "结构上限 <= 预算": a["structural_max"] <= a["budget_limit"],
         "总调用 <= 结构上限": sum(a["calls"].values()) <= a["structural_max"]}
    if name in ("A_全员准入_跑G-K2", "B_全员准入_跳G-K2", "C_两名被剔除_跑G-K2", "F_面板一致_事实相关", "G_次结分歧_事实相关"):
        adm = a["admitted"] or []
        P["原始标注已落盘且面板=准入者"] = a["raw_written"] and set(adm) == {mm for mm in M if a["dist_calls_by_model"][mm]}
        P["被剔除者零标注调用"] = all(a["dist_calls_by_model"][mm] == 0 for mm in M if mm not in adm)
        P["准入者每人标满样本"] = all(a["dist_calls_by_model"][mm] == n["sample"] for mm in adm)
        P["gates_result 已落盘"] = a["gates_result_written"] and a["rc"] is None and a["exception"] is None
    if name in ("A_全员准入_跑G-K2", "C_两名被剔除_跑G-K2", "F_面板一致_事实相关", "G_次结分歧_事实相关"):
        P["G-K2 真跑了: 事实抽取每样本一次"] = a["calls"].get("fact", 0) == n["sample"]
        P["G-K2 有行"] = (a["G_K2_n"] or 0) > 0 and not a["G_K2_withheld"]
        P["overall = G_K1 ∧ G_K2 ∧ 准入OK"] = a["overall_pass"] == bool(a["G_K1_pass"] and a["G_K2_pass"] and a["qual_status"] == "OK")
    if name == "B_全员准入_跳G-K2":
        P["跳 G-K2 ⇒ 零事实抽取"] = a["calls"].get("fact", 0) == 0
        P["跳 G-K2 ⇒ G-K2 扣发"] = a["G_K2_withheld"] and a["G_K2_pass"] is None
        P["跳 G-K2 ⇒ overall 扣发(None)"] = a["overall_pass"] is None
    if name == "C_两名被剔除_跑G-K2":
        P["恰好剔除两名"] = len(a["admitted"] or []) == len(M) - 2
    if name == "F_面板一致_事实相关":
        P["通过路径真被走到: G_K1 过 ∧ G_K2 过 ⇒ overall=True"] = a["G_K1_pass"] is True and a["G_K2_pass"] is True and a["overall_pass"] is True
    if name == "G_次结分歧_事实相关":
        P["G_K1 不过而 G_K2 过 ⇒ overall=False"] = a["G_K1_pass"] is False and a["G_K2_pass"] is True and a["overall_pass"] is False
    if name == "D_全员被剔除":
        P["扣发返回 2"] = a["rc"] == 2 and a["exception"] is None
        P["扣发写 gates_result 且 overall=None"] = a["gates_result_written"] and a["withheld"] and a["overall_pass"] is None
        P["扣发 ⇒ 零标注零抽取"] = a["calls"].get("dist", 0) == 0 and a["calls"].get("fact", 0) == 0
    if name == "E_事实抽取全断_跑G-K2":
        P["原始标注先落盘(崩前不丢数据)"] = a["raw_written"]
        P["不产出通过"] = a["overall_pass"] is not True
        # 2026-10-01 修复后补的性质(fail-closed 扣发, 不是崩, 也不是「不通过」):
        P["不崩且 gates_result 照常落盘"] = a["gates_result_written"] and a["exception"] is None
        P["G-K2 扣发: n=0 ∧ pass=None ∧ 写明原因"] = a["G_K2_n"] == 0 and a["G_K2_pass"] is None and a["G_K2_withheld"]
        P["overall 扣发(None), 不折成 False"] = a["overall_pass"] is None
    return P


ARMS = {
    "A_全员准入_跑G-K2": dict(skip_gk2=False),
    "B_全员准入_跳G-K2": dict(skip_gk2=True),
    "C_两名被剔除_跑G-K2": dict(skip_gk2=False, wrong_qual=("MiniMax-M2", "MiniMax-Text-01")),
    "D_全员被剔除": dict(skip_gk2=True, wrong_qual=("MiniMax-M3", "MiniMax-M2.5", "MiniMax-M2.7", "MiniMax-M2", "MiniMax-Text-01")),
    "E_事实抽取全断_跑G-K2": dict(skip_gk2=False, fact_outage=True),
    "F_面板一致_事实相关": dict(skip_gk2=False, dist_mode="agree", fact_mode="correlated"),
    "G_次结分歧_事实相关": dict(skip_gk2=False, dist_mode="split", fact_mode="correlated"),
}

# 变异: (针对的臂, 源码锚点, 替换) —— 每条必须让该臂至少一条性质翻假
MUTATIONS = {
    "M1_跳G-K2仍发overall": ("B_全员准入_跳G-K2", '"overall_pass": (None if SKIP_GK2 else', '"overall_pass": (bool(gk1["pass"]) if SKIP_GK2 else'),
    "M2_剔除后仍用全员标注": ("C_两名被剔除_跑G-K2", 'globals()["MODELS"] = adm["admit"]', 'globals()["MODELS"] = list(MODELS)'),
    "M3_扣发返回0": ("D_全员被剔除", "return 2      # ★ 扣发", "return 0      # ★ 扣发"),
    "M4_原始标注不落盘": ("A_全员准入_跑G-K2", '_raw = os.path.join(_OUT_DIR, "raw_annotations.json")', '_raw = os.path.join(_OUT_DIR, "_lost", "raw.json")'),
    "M5_overall不看G-K1": ("G_次结分歧_事实相关", '"overall_pass": (None if SKIP_GK2 else\n                            bool(gk1["pass"] and gk2["pass"]',
                           '"overall_pass": (None if SKIP_GK2 else\n                            bool(gk2["pass"]'),
    # 2026-10-01 修复的两道守卫: 拿掉任一道, E 臂必须红
    "M6_空抽取不扣发G-K2": ("E_事实抽取全断_跑G-K2", "        if not rows:\n            # ★ fail-closed", "        if False:\n            # ★ fail-closed"),
    "M7_G-K2扣发时overall折成bool": ("E_事实抽取全断_跑G-K2", 'if gk2["pass"] is not None else None),', 'if True else None),'),
}


def _strip(a):
    return {k: v for k, v in a.items() if k != "_n"}


def main():
    arms, props = {}, {}
    for name, kw in ARMS.items():
        a = run_arm(**kw)
        arms[name], props[name] = _strip(a), properties(name, a)
    muts = {}
    for mid, (arm, old, new) in MUTATIONS.items():
        a = run_arm(**ARMS[arm], mutator=AH_replace_once(old, new))
        p = properties(arm, a)
        muts[mid] = {"arm": arm, "source_mutated": a["source_mutated"],
                     "properties_turned_false": sorted(k for k, v in p.items() if not v),
                     "detected": a["source_mutated"] and any(not v for v in p.values())}
    e = arms["E_事实抽取全断_跑G-K2"]
    return {
        "block": "ACCURACY_MAIN_E2E_OFFLINE", "written_at": "2026-10-01",
        "★zero_api": "全程零真实调用; 每臂 socket 绊线 tripped=[] 由性质「零网络」逐臂断言。",
        "★替换边界": "只替换 urlopen 的传输结果; 资格考/准入/标注/落盘/G-K1/G-K2/汇总/扣发 全走原代码。",
        "★★★据此能支持的结论": ("**main() 编排与 G-K2 链路的离线软件验证**: 谁进面板、调用了几次、什么时候落盘、"
                           "什么时候扣发、overall 由哪几项合成。**不能**证明真实 provider 的语义准确率或重复稳定性 —— "
                           "假回复是合成的, 不是金标。"),
        "arms": arms, "properties": props,
        "★all_properties_hold": {k: all(v.values()) for k, v in props.items()},
        "mutations": muts, "★all_mutations_detected": all(v["detected"] for v in muts.values()),
        "★finding_fact_outage": {
            "observed": {"exception": e["exception"], "gates_result_written": e["gates_result_written"],
                         "raw_written": e["raw_written"], "calls": e["calls"],
                         "G_K2_n": e["G_K2_n"], "G_K2_pass": e["G_K2_pass"], "G_K2_withheld": e["G_K2_withheld"],
                         "overall_pass": e["overall_pass"]},
            "registered_2026_10_01": ("CCE_SKIP_GK2=0 且事实抽取全部返回空(如 Text-01 故障)时, G-K2 的 rows 为空, "
                        "`collections.Counter(...).most_common(1)[0]` 抛 IndexError ⇒ main() 在全部标注调用**之后**崩, "
                        "gates_result.json 不写。方向是 fail-closed(不产出通过), 原始标注已先落盘 ⇒ 数据不丢; "
                        "但付费调用已花完、且没有扣发记录说明原因。2026-09-07 修过 SKIP_GK2=1 的同一崩法, 这条路径没修。"),
            "status": "FIXED_2026-10-01" if not e["exception"] else "★ 仍复现",
            "fix": ("run_gates.main(): rows 为空时不再索引 most_common(1)[0]; G-K2 置 pass=None 并写 ★withheld(带事实抽取覆盖数), "
                    "overall_pass 在 G-K2 扣发时为 None(此前 bool(... and None) 会折成 False), ★overall_withheld_because 写同一原因; "
                    "gates_result.json 照常落盘。路由: config/cce_core_manifest.json refactor_log 事件 "
                    "GK2_EMPTY_FACTS_WITHHELD_NOT_CRASH(非 core_files、闸协议材料未动 ⇒ gate_protocol_hash 不变)。"
                    "回归: 本臂 3 条新性质 + 变异 M6/M7。"),
        },
        "★仍未验证(零 API 测不了)": ["真实 provider 的语义判断准确率", "真实 provider 的重复稳定性"],
    }


def AH_replace_once(old, new):
    def _m(src):
        n = src.count(old)
        assert n == 1, "变异锚点命中 %d 次: %r" % (n, old[:50])
        return src.replace(old, new)
    return _m


if __name__ == "__main__":
    doc = main()
    txt = json.dumps(doc, ensure_ascii=False, indent=1) + "\n"
    if "--check" in sys.argv:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == txt
        print("RECOMPUTED == STORED" if same else "★ 现算与存盘不一致")
        sys.exit(0 if same else 1)
    OUT.write_text(txt, encoding="utf-8")
    print(json.dumps({"all_properties_hold": doc["★all_properties_hold"], "all_mutations_detected": doc["★all_mutations_detected"],
                      "mutations": {k: v["properties_turned_false"] for k, v in doc["mutations"].items()},
                      "fact_outage": doc["★finding_fact_outage"]["observed"]}, ensure_ascii=False, indent=1))
    print("写入", OUT.relative_to(ROOT))
