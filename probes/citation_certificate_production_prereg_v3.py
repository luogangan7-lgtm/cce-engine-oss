# -*- coding: utf-8 -*-
"""预注册 v3: 引用证书采集协议 v3(原因码 + kind 菜单 + 逐字明示 + 一次修复重问)的试点。零调用, 只写 JSON。取代 v1 预注册(45aee33c, 已执行判 STOP)的**协议部分**; 材料、判决线、影子段形状原样继承。"""
import hashlib, importlib.util, inspect, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
OUT = ROOT / "tests/data/citation_certificate_production_prereg_v3.json"; V1 = ROOT / "tests/data/citation_certificate_production_prereg.json"


def _load(rel, name):
    s = importlib.util.spec_from_file_location(name, ROOT / rel); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def build():
    g1 = _load("probes/citation_certificate_production_prereg.py", "_g1")
    P3 = _load("probes/citation_certificate_protocol_v3.py", "_p3"); r2 = P3.r2; import cce_label_qualification as LQ
    v1 = json.loads(V1.read_text(encoding="utf-8")); v1sha = hashlib.sha256(V1.read_text(encoding="utf-8").encode()).hexdigest()[:16]
    A, B = g1.stratum_a(), g1.stratum_b(); n = len(A) + len(B); cap = 2 * 2 * n
    pilot = json.loads((ROOT / "results/citation_certificate_pilot.json").read_text(encoding="utf-8"))["★★★指标"]
    return {
     "block": "CITATION_CERTIFICATE_PRODUCTION_PREREG_V3", "date": "2026-09-24", "supersedes": {"prereg": "tests/data/citation_certificate_production_prereg.json", "sha": v1sha, "★继承": "材料 A/B · 影子段形状 · 判决线阈值 · 不得据此说; **只换采集协议**"},
     "★★★status": "**REGISTERED · 未执行 · 生产未接线** —— 执行要 owner 一句「跑」(硬上限 %d 次 MiniMax 订阅)。" % cap,
     "★为什么有 v3": "v2 试点(88 次)判 STOP: M4 MALFORMED 率 %.1f%% > 10%%。r2 真实语料两轮能拆出的 MALFORMED 族: kind 多重命中 5 · span 非逐字 4 · object 缺/非逐字 2(/34 张交卷) ⇒ 最大一族是**采集面**问题(没给菜单、没明示逐字), 不是验证器问题。★ v2 试点产物没存原因码(保护原文), 这一族分布来自 r2 而非 v2 —— 如实标注。" % (100 * pilot["M4 MALFORMED 率"]["p"]),
     "★★★协议 v3(由闸现算比对)": {
      "prompt": "probes/citation_certificate_protocol_v3.prompt_v3(text) = r2.PROMPT 三处改动", "prompt_sha(模板, text 置空)": hashlib.sha256(P3.prompt_v3("").encode()).hexdigest()[:16],
      "①kind 菜单(由判别式括号机械导出)": P3.kind_menu(), "②逐字明示": "连续子串·复制粘贴; 找不到 ⇒ supported=false", "③修复重问": "仅当首答有格式码; 只回传错误码(不含判据/对错); 每张证书最多 2 次调用; 修复后仍按同一 _judge 判",
      "错误码集": list(P3.CODES), "机械验证器": "probes/extractor_counterexample_run_r2._judge **一字不动**", "_judge 源码 sha": hashlib.sha256(inspect.getsource(r2._judge).encode()).hexdigest()[:16], "P2 绑定": LQ.P2_BINDING,
      "★不放松什么": "逐字判据、kind 枚举、P2 见证交集、附件 A 复述闸全部原样; 修复重问不给模型任何判据文字, 只说「哪个字段格式不对」。"},
     "★★★影子段 s2b 的形状": v1["★★★影子段 s2b 的形状(接线时照此, 现在不接)"],
     "★★★试点材料(指针+sha, 冻结, 与 v1 相同)": v1["★★★试点材料(指针+sha, 冻结)"],
     "★预算硬上限": {"证书调用": cap, "构成": "(%d + %d) × 2 张 × 最多 2 次(首答 + 修复)" % (len(A), len(B)), "撞上即停": True, "★预计": "≈ 88 + 首答有格式码的张数(v2 里约 1/4 文本至少一张) ≈ 100–110"},
     "★★★判据(测量前冻结)": {**v1["★★★判据(测量前冻结)"], "M5 修复(新增, 描述性)": "首答有格式码的证书数 · 修复后仍 MALFORMED 数 · 首答/终态原因码族分布 —— 不进判决, 用来定位下一步改哪一族。", "★M4 的口径": "按**终态**(修复后)算 —— 修复是协议的一部分。首答 MALFORMED 率另报, 供与 v2 对照。"},
     "★★★决策规则(测量前冻结)": {**{k: v for k, v in v1["★★★决策规则(测量前冻结)"].items() if not k.startswith("★预测")},
      "★预测(先写)": "M4(终态)由 24% 降到 **5–12%**(菜单+只填一个 消掉 kind 族; 修复重问只能救回一部分 span/object 族); M1 可判率**不会**因协议 v3 明显改善(它来自模型在 supported 上的不一致, 与格式无关), 仍 ≈ 55–65% ⇒ 即使 M4 过门, 大概率落 **NEEDS_N3**。若 M4 仍 >10% ⇒ 剩下的族是 span/object 非逐字, 那是模型改写倾向, 下一步该换「先让模型指定 span 起止词再机械截取」的协议, 不是再改措辞。"},
     "★★★与 v2 试点的对照(可比不可合)": {"v2 M1": pilot["M1 可判率"], "v2 M2": pilot["M2 升格率"], "v2 M3": pilot["M3 代价 median(max 两张 s)"], "v2 M4": pilot["M4 MALFORMED 率"], "★读法": "同材料、不同协议、不同时间 ⇒ 方向可比, 数不可合; r3 已证同协议重测就有 40% 翻转。"},
     "★★★不得据此说": v1["★★★不得据此说"] + ["不得把修复重问的成功读成「模型会了」—— 它只是把格式错的答案改成格式对的, 语义同前。"],
     "★接线闸(接线时必须齐)": v1["★接线闸(接线时必须齐)"]}


def main():
    OUT.write_text(json.dumps(build(), ensure_ascii=False, indent=1), encoding="utf-8")
    r = json.loads(OUT.read_text(encoding="utf-8")); print("cap", r["★预算硬上限"]["证书调用"], "menu", r["★★★协议 v3(由闸现算比对)"]["①kind 菜单(由判别式括号机械导出)"]); print("→", OUT, hashlib.sha256(OUT.read_bytes()).hexdigest()[:16]); return 0


if __name__ == "__main__": sys.exit(main())
