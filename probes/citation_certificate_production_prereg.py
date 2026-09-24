# -*- coding: utf-8 -*-
"""预注册: 引用证书协议(r2 式 span/supports/object/increment_kind + 机械资格层)接进生产链的**影子段 s2b**。零调用, 只写 JSON。

★ 为什么要预注册: 这是生产产出面的变更 + 要花真调用; r3 实测同协议重测一致率只有 60% ⇒ 单张证书不是测量, 生产接线必须 n=2 一致才升格。
★ 现状: s2 已有 label_qualification 诊断字段(恒候选); 本预注册定义它**怎样才能升到 ③′ CITED_UNVERIFIED**(出处可核·语义未验), ④ 仍不可达。
★ 材料只登记指针 + sha, 不落原文。
"""
import glob, hashlib, importlib.util, inspect, json, os, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
OUT = ROOT / "tests/data/citation_certificate_production_prereg.json"
R2 = ROOT / "probes/extractor_counterexample_run_r2.py"; PRE1 = ROOT / "tests/data/real_corpus_pilot_prereg.json"


def _r2():
    s = importlib.util.spec_from_file_location("_r2p", R2); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def stratum_a():
    """归档里 s2 top-1 == display 且原文可由 input_sha 在同 run 的 items.json 里找回的读数; 按**文本**去重(同一文本的多次 run 只记指针列表)。"""
    by_text = {}
    for f in sorted(glob.glob(str(ROOT / "archive/*/*s1_readout.json"))):
        d = json.loads(pathlib.Path(f).read_text(encoding="utf-8"))
        if (d["stage2"]["knots"] or [{}])[0].get("key") != "display": continue
        run = os.path.dirname(f); p = os.path.join(run, "cce-submission-source__items.json")
        if not os.path.exists(p): continue
        items = json.loads(pathlib.Path(p).read_text(encoding="utf-8")); items = items if isinstance(items, list) else items.get("items") or []
        h = d.get("input_sha"); hit = None
        for i, it in enumerate(items):
            t = it.get("text") if isinstance(it, dict) else None
            if isinstance(t, str) and hashlib.sha256(t.encode()).hexdigest()[:16] == h: hit = (i, len(t)); break
        if hit is None: continue
        e = by_text.setdefault(h, {"input_sha": h, "text_source": os.path.relpath(p, ROOT), "item_index": hit[0], "n_chars": hit[1], "readouts": []})
        e["readouts"].append(os.path.relpath(f, ROOT))
    return sorted(by_text.values(), key=lambda e: e["input_sha"])


def stratum_b():
    pre = json.loads(PRE1.read_text(encoding="utf-8")); items = [pre[k] for k in pre if "冻结输入集" in k][0]["items"]
    return [{"file": it["file"], "line_index": it["line_index"], "sha256": it["sha256"], "n_chars": it.get("n_chars")} for it in items]


def build():
    m = _r2(); import cce_label_qualification as LQ
    A, B = stratum_a(), stratum_b(); n = len(A) + len(B); cap = 2 * n
    return {
     "block": "CITATION_CERTIFICATE_PRODUCTION_PREREG", "date": "2026-09-24",
     "★★★status": "**REGISTERED · 未执行 · 生产未接线** —— 执行要真调用(MiniMax 订阅, 硬上限 %d), 跑之前 owner 一句「跑」; 接线要 ADOPT_SHADOW 判决 + owner 点头。" % cap,
     "★问题": "s2 的 label_qualification 现在恒为 ③ 候选(协议缺口: 没有 supports/about)。把 r2 式引用证书协议作为**影子段 s2b** 接进生产, 状态能否可靠升到 ③′(出处可核·语义未验)? 代价(墙钟/调用)多少? 单张证书不稳(r3 一致率 60%), n=2 一致的可判率是多少?",
     "★★★协议(逐字沿用 r2, 由闸现算比对)": {
      "prompt": "probes/extractor_counterexample_run_r2.PROMPT % (DISC, text)", "prompt_sha(模板, text 置空)": hashlib.sha256((m.PROMPT % (m.DISC, "")).encode()).hexdigest()[:16],
      "机械验证器": "probes/extractor_counterexample_run_r2._judge(逐字沿用)", "_judge 源码 sha": hashlib.sha256(inspect.getsource(m._judge).encode()).hexdigest()[:16],
      "P2 绑定": LQ.P2_BINDING, "★与 r2 的唯一差别": "P2 由 v1 改 v2 见证交集(2026-09-23 代定), 多余证据不拦; 其余一字不改。",
      "结局分类法": list(m.ISSUED) + [m.REFUSED_RIGHT, m.REFUSED_OTHER]},
     "★★★影子段 s2b 的形状(接线时照此, 现在不接)": {
      "触发": "仅当 s2 top-1 == display 且 top1_stable is True(与 playbook_primary 同门槛); 其他结 NOT_APPLICABLE(它们没有合同合取项)。",
      "调用": "同一文本发 **2 张证书**(temperature=0, 同 prompt, 并发); 每张各自过 _judge。",
      "升格规则": "两张都 UPGRADED **且** 两张的 P2 见证集合交集非空 ⇒ label_qualification.state = CITED_UNVERIFIED(③′); 否则维持 UNCONFIRMED_CANDIDATE 并写明 DISAGREE / BOTH_NOT_UPGRADED / CALL_FAIL。",
      "★不变量": "citable_as_confirmed **恒 False**(④ 需确定性识别器, 未实现); 除 label_qualification 外 manifest 其他字段逐字节不变(由闸守); 开关 CCE_CITATION_CERT 默认关, 关时行为与今日完全相同。",
      "记账": "每张证书的 outcome / 见证 / 逐字核 / 耗时 落 s2b_citation.json; 原文不落产物(生产产物本来含 input, 但证书 span 只记 sha16)。"},
     "★★★试点材料(指针+sha, 冻结)": {
      "A · 归档里 s2 top-1=display 且原文可找回": {"n_texts": len(A), "★读法": "同一文本被多次 run 命中, 按文本去重; n 太小只作描述, 不进判决", "items": A},
      "B · real_corpus_pilot 冻结 42 条(top-1 未知)": {"n": len(B), "★读法": "协议稳定性的主材料; 与 r1/r2 同指针 ⇒ 可与 r2 的单张结局对照(可比不可合)", "items": B},
      "★为什么不是「先跑 s1/s2 找 display 文本」": "那要 42×2 次 knot_classify(≈672 次调用)只为选材; 本预注册问的是证书协议的稳定性与代价, 与文本是不是 display 无关(触发门槛由零调用闸守)。"},
     "★预算硬上限": {"证书调用": cap, "构成": "(%d + %d) × 2, 每张尝试 1 次, 失败记 CALL_FAIL 不重试" % (len(A), len(B)), "撞上即停": True},
     "★★★判据(测量前冻结)": {
      "M1 可判率": "B 层里两张结局同类(同为 UPGRADED / 同为非 UPGRADED)的比例; 报 Clopper-Pearson 95%。",
      "M2 升格率": "B 层里两张都 UPGRADED 且见证交集非空的比例(= 生产会升到 ③′ 的比例)。",
      "M3 代价": "每条 max(两张耗时) 的中位数(并发发 ⇒ 增加的墙钟 ≈ 这个数)。",
      "M4 MALFORMED 率": "两张里任一 MALFORMED 的条数 / n。",
      "★与 r2 对照": "B 层单张结局分布 vs results/real_corpus_pilot_r2.json 的 v2 口径(20/42 PASS) —— 只看方向, 不合并。"},
     "★★★决策规则(测量前冻结)": {
      "ADOPT_SHADOW": "M1 ≥ 60% 且 M4 ≤ 10% 且 M3 ≤ 45 s ⇒ 接影子段(默认关, owner 开)。",
      "NEEDS_N3": "M1 < 60% 且 M4 ≤ 10% ⇒ 单靠两张判不动, 另立 n=3 多数票预注册(不在本轮加)。",
      "STOP": "M4 > 10% ⇒ 协议在生产文本上不够格式稳定, 不接; 先修采集协议。",
      "COST_BLOCK": "M3 > 45 s ⇒ 即使 ADOPT 也只能异步(不阻塞发布), 另立设计。",
      "★n=42 的分辨率": "M1 判 60% 门: 25/42 通过(CP 下界 0.43), 22/42 不过 —— 区间宽, 结论句必须带区间; 不许拿点估计说「稳定」。",
      "★预测(先写)": "按 r3 的 60% 一致率, M1 预期 ≈ 55–65%, 大概率落在 NEEDS_N3 与 ADOPT 之间 —— 写在这里防事后包装。"},
     "★★★不得据此说": ["不得说升到 ③′ 的读数「语义正确」—— MIS-4 类(形式合规·语义错误)照样过, ④ 仍不可达。", "不得说「验证器守得住」。", "不得把 A 层 n=%d 的数当结论。" % len(A), "不得把本轮当 r2/r3 的重复测量(P2 口径已变)。"],
     "★接线闸(接线时必须齐)": ["tests: 开关关 ⇒ manifest 逐字节同今日", "开关开 + 两张桩证书一致 ⇒ ③′; 不一致 ⇒ 候选并写 DISAGREE", "citable_as_confirmed 恒 False", "非 display 或 top1_stable 非 True ⇒ 不发证书(零调用)", "产物无原文 span(只 sha16)"]}


def main():
    OUT.write_text(json.dumps(build(), ensure_ascii=False, indent=1), encoding="utf-8")
    r = json.loads(OUT.read_text(encoding="utf-8")); print("A", r["★★★试点材料(指针+sha, 冻结)"]["A · 归档里 s2 top-1=display 且原文可找回"]["n_texts"], "B", r["★★★试点材料(指针+sha, 冻结)"]["B · real_corpus_pilot 冻结 42 条(top-1 未知)"]["n"], "cap", r["★预算硬上限"]["证书调用"]); print("→", OUT, hashlib.sha256(OUT.read_bytes()).hexdigest()[:16]); return 0


if __name__ == "__main__": sys.exit(main())
