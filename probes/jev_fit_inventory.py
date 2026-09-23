# -*- coding: utf-8 -*-
"""全链判断点盘点: 哪几段真的调 LLM(AST 现算, 不口述), 哪几段是 Choice 形状(可由 System One 模型判), 哪几段是生成式(不能)。零调用。"""
import ast, json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]; OUT = ROOT / "results/jev_fit_inventory.json"
FILES = ["scripts/cce_full_run.py", "scripts/cce_knot_classify.py", "scripts/cce_outbound_guard.py", "scripts/cce_label_qualification.py", "scripts/cce_claim_frame.py"]
LLM = {"call_model", "call_parse", "_stage2_draw", "run_knot_classify"}


def llm_sites(rel):
    src = (ROOT / rel).read_text(encoding="utf-8"); tree = ast.parse(src); out = {}
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        calls = [c.func.attr if isinstance(c.func, ast.Attribute) else getattr(c.func, "id", None) for c in ast.walk(fn) if isinstance(c, ast.Call)]
        hit = sorted(set(c for c in calls if c in LLM))
        if hit: out[fn.name] = hit
    return out


def build():
    sites = {rel: llm_sites(rel) for rel in FILES}
    stages = {
        "reader_baseline": {"调 LLM": "是(run_knot_classify ⇒ s1 k 次 + s2 n 次)", "形状": "生成式(四层分布 + 九结 + 证据句)", "Jev 能接": False,
                            "备注": "★ 它是**第二次**完整 knot_classify —— 全链里 LLM 调用的一半在这里, 不在 s0。"},
        "s0_context": {"调 LLM": "是(1 次, 仅未声明且可读的面)", "形状": "**Choice**: 9 面里 6 面可读, 每面从固定取值集选一(含「未知」)", "Jev 能接": True,
                       "备注": "无金标; 只能做 Jev vs MiniMax 一致性 + 置信度描述。body[:2000] 截断是现状。"},
        "s1_readout": {"调 LLM": "是(k=3 温度档 × ≤3 次尝试)", "形状": "生成式(四层分布向量 + appraisal + chain_trace 逐字引句)", "Jev 能接": False, "备注": "引句必须逐字出自原文, Jev 不生成文本。"},
        "s2_knots": {"调 LLM": "是(n=5 次抽样 × ≤3 次尝试)", "形状": "生成式(九结 intensity + 证据句 + 弃权)", "Jev 能接": False,
                     "备注": "Score 原语能给九结各自的等级分布, 但 K/N 重复抽样与 within_js 是仪器定义的一部分, 换掉等于换仪器(库内 2026-08-18 已否决过「用一次分布冒充 N 次观察」同型方案)。"},
        "s3_emotion_policy": {"调 LLM": "否(只报 s1 的分布)", "形状": "无判断", "Jev 能接": None, "备注": ""},
        "s4_guard": {"调 LLM": "否(正则白/黑名单)", "形状": "确定性规则", "Jev 能接": None, "备注": "已经不是 LLM; 换成概率模型反而引入不确定。"},
        "qualified(资格层)": {"调 LLM": "否(cce_label_qualification.qualify 机械判据)", "形状": "确定性规则", "Jev 能接": None, "备注": ""},
        "判据层六槽位(度量层, 非生产链)": {"调 LLM": "是(r5/r6 用 MiniMax 填)", "形状": "**Choice** ×6", "Jev 能接": True,
                                        "备注": "r6-jev 已实测: speaker/polarity/time/citation 全对; possession 是打分伪影(见 possession_gain_artifact); predicate 与 MiniMax 同一结局。"},
        "P2 两支同对象 / P2 三族(度量层)": {"调 LLM": "否(规范化字符串比对)", "形状": "确定性规则; 三族分类可做成 Choice", "Jev 能接": "可试(无金标)", "备注": "SET_MISMATCH/SUBSTRING/DISJOINT 目前由文本关系机械判, 不需要模型。"},
    }
    return {"block": "JEV_FIT_INVENTORY", "date": "2026-09-23", "★零调用": "AST 现算调用点; 形状分类是判断, 逐条给理由。",
            "★★★LLM 调用点(AST 现算)": sites,
            "★★★逐段": stages,
            "★★★结论": {"生产链里唯一的 Choice 形状 LLM 点": "s0_context(1 次调用)。",
                        "生产链的 LLM 时间在哪": "reader_baseline + s1 + s2 —— 两次完整 knot_classify, 都是生成式, Jev 接不了。",
                        "度量层里已证 Jev 能接的": "判据层里的分类槽位(speaker/polarity/time/citation), 便宜且全对。",
                        "★替换 s0 的前提": "无金标 ⇒ 先做 Jev vs MiniMax 一致性(shadow), 不一致的面人工看; 生产接线是核心文件改动, 要 owner 点头。"},
            "★不得据此说": ["不得说「换 Jev 全链提速」—— 提速点在两次 knot_classify, 那是生成式。", "不得用 Score 原语替换九结 intensity 冒充 N 次观察(已否决同型方案)。"]}


def main():
    out = build(); OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for rel, s in out["★★★LLM 调用点(AST 现算)"].items(): print("  %-40s %s" % (rel, s))
    print("  Choice 形状且调 LLM 的生产段:", [k for k, v in out["★★★逐段"].items() if v["Jev 能接"] is True]); print("→", OUT); return 0


if __name__ == "__main__": sys.exit(main())
