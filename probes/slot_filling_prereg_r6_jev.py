# -*- coding: utf-8 -*-
"""r6-jev 预注册: 主判据/items/金标/零假设/门/功效**全部继承 r6**(逐键复制并钉 r6 预注册 sha), 只加 Jev 特有的冻结项。零调用。"""
import hashlib, importlib.util, json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
R6 = ROOT / "tests/data/slot_filling_prereg_r6.json"; OUT = ROOT / "tests/data/slot_filling_prereg_r6_jev.json"

def main():
    r6 = json.loads(R6.read_text(encoding="utf-8"))
    s = importlib.util.spec_from_file_location("jx", ROOT / "probes/slot_filling_run_r6_jev.py"); x = importlib.util.module_from_spec(s); s.loader.exec_module(x)
    pre = {"block": "SLOT_FILLING_PREREG_R6_JEV", "date": "2026-09-23", "★★★status": "**READY**",
           "★★★这一轮问什么": "把填槽的模型从 MiniMax(生成式)换成 TypeSafe Jev(System One, 不生成文本、每题一个校准过的分布), "
                             "在**同一批 r6 items、同一套金标、同一套打分/judge**下, 它能不能填出 predicate 的鉴别格(RESTATES_IDENTIFIER)? 其他五个槽位一起报。",
           "★继承 r6 的一切": "items / 金标哈希 / 零假设(v4 上现搜) / 门 ≥8/24 / base_net 3 / 功效 / 降级 D1–D6 / 判据准入 —— 逐键复制自 r6 预注册, 由闸断言相等。",
           "r6 预注册 sha256": hashlib.sha256(R6.read_bytes()).hexdigest(),
           "★★★items(测量前冻结)": r6["★★★items(测量前冻结)"], "★★★金标哈希(测量前冻结)": r6["★★★金标哈希(测量前冻结)"],
           "★★★主判据(测量前冻结_confirmatory)": r6["★★★主判据(测量前冻结_confirmatory)"], "★★★降级条件(测量前冻结)": r6["★★★降级条件(测量前冻结)"],
           "★★★判据准入结果(零调用预检_库内硬规则)": r6["★★★判据准入结果(零调用预检_库内硬规则)"],
           "★★★Jev 特有(冻结)": {
               "模型": x.MODEL + "(探活解析为 jev-1.13.0)", "端点": x.API,
               "题目集": "每条证据 5 道 Choice(speaker/polarity/time/citation/possession) + 片段一 1 道 predicate = 11 题/请求; 选项 = 判据层合法枚举(LEGAL 现算派生), 片段二 predicate 填 None 与 MiniMax 提示词一致。",
               "predicate 题里给的判据": "附件 A 条款英译(与 r5/r6 B 臂同一条, 不给例句)。",
               "语言": "题目英文, items 文本本就是英文。官方: 英语是主要训练语言, CJK 不同等 —— 本轮不涉及中文材料。",
               "state": "完整文本 + 两条片段(不截断)。",
               "★不给 Jev 任何 MiniMax 的读数": "两臂独立。"},
           "★题目集哈希(测量前冻结)": x.question_set_sha(),
           "★★★怎么读": {"达成": "Jev 在 v4 的 24 个鉴别格上超过浅层规则 ⇒ 这一格**可以由 System One 模型填**, 那是两轮 136 次 MiniMax 都没做到的。",
                        "未达成": "与 MiniMax 同一个结局 ⇒ 问题在**判据/材料**不在模型家族。",
                        "★不得据此说": ["不得说 Jev 比 MiniMax 好/差 —— 同批 items 但**提示语言与形态不同**, 只能比结论与方向。",
                                        "不得把 confidence 当准确率 —— 校准是群体性质。", "不得外推到中文材料。"]},
           "★★★预算(计量付费, 先报上限)": {"请求硬上限": x.CAP_REQ, "input_tokens 硬上限": x.CAP_TOK, "估算": "68 请求 × ~700 token ≈ 5 万 token ≈ $0.002(输入 $0.042/M, 输出免费)",
                                         "重试": "仅 429/529 退避 ≤3 次, 每次尝试计入请求数", "★撞上限即停": True},
           "★调用预算(MiniMax)": "0 —— 本轮不调 MiniMax。累计仍 310。"}
    OUT.write_text(json.dumps(pre, ensure_ascii=False, indent=1), encoding="utf-8")
    print("题目集 sha", x.question_set_sha(), "· 继承 r6 门", pre["★★★主判据(测量前冻结_confirmatory)"]["★冻结的门"], "· 上限 %d 请求" % x.CAP_REQ); return 0

if __name__ == "__main__": sys.exit(main())
