#!/usr/bin/env python3
"""冻结 s1 的 2×2 因子实验：把 prompt 效应与采样数效应分开。

为什么必须这么做（对抗评审 wgd3n1wrv 的结论）:
  之前那个 A/B 同时改了 prompt 与采样数, 且两个判据跨臂不可比 ——
  单结极差的归一分母不同(OLD 每 rep 4-6 结 vs NEW 恒 3 结),
  top-1 一致率在 R=8 下无分辨力(同一真实 q 下该结果概率 7-12%),
  而 top1_unanimous 在 n=1 时恒真、P≈p^n 随 n 单调下降 —— 提 n 即收紧闸, 是算术不是证据。

设计:
  1) 冻结 s1: 跑 2 次 stage1, 各存成固定 payload。s1 从噪声源变成**区组因子**。
  2) 两份 prompt: NEW(HEAD, 独立强度) vs OLD(6c650ea, 权重和=1)。
     两者吃的 s1 字段完全相同, 且 _stage2_draw 已把 weight 归到 intensity, 旧 prompt 直接可跑。
  3) 只调 _stage2_draw, **绝不调 _stage2_aggregate** —— 每格 20 次原始 draw 原样落盘。
     这同时根治「探针丢掉 occur」: 不是补字段, 是干脆不聚合。
  4) 分析全部离线, 0 次额外调用。

★ 判决线在跑之前写死（见 VERDICT_LINES），不许事后挑。

成本: 6(s1) + 2 prompt × 2 s1 × 20 = 86 次调用。
"""
import json, os, sys, time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_knot_classify as K  # noqa: E402

TEXT = Path(sys.argv[1]).read_text(encoding="utf-8").strip()
CTX = "reddit r/HearingAids hearing_aid: 冻结 s1 因子实验"
PER_CELL = int(os.environ.get("CELL_N", "20"))
OUT = Path("/tmp/frozen_s1.json")
TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))

VERDICT_LINES = [
    "新 prompt 的 draw 内 top1−top2 均差 < 旧 prompt 的一半 → 近平局是 prompt 造的",
    "两者相当 → 三结确实近平局, 扣发 playbook 是对的动作(但不由旧那组 A/B 证明)",
    "两个 s1 区组之间的差 > 两个 prompt 之间的差 → 锅在 s1 单抽 appraisal 进 s2 prompt",
]

KNOTS_BRIEF = "\n".join(
    f"- {k['key']}({k['name']}, {k['family']}): {k['signature']}; "
    f"典型codes={json.dumps(k['typical_codes'], ensure_ascii=False)}; 行为={k['behavior'][:60]}"
    for k in TAXO["knots"])
LEVERS = "、".join(TAXO["levers_not_knots"].keys())

HEAD_MULTI = """【多结】一个人可同时持多结(如 归属+惯性)。
【★强度独立打分, 不要归一】对每个结独立给 intensity ∈ [0,1]:
  0 = 该结在这段内容里完全没有迹象; 1 = 强烈且明确。
  **不同结的 intensity 互相独立, 不要求加起来等于 1** ——
  「想要很强」与「审查也很强」可以同时成立(如 reward=0.85 且 audit=0.80),
  强行让总和为 1 会逼着你在两个都真实存在的结之间人为压低一个。
  只列 intensity > 0 的结; 没有迹象的结不要列。"""
OLD_MULTI = "【多结】一个人可同时持多结(如 归属+惯性)。输出组合带权重(和=1),不要强行单选。"
HEAD_FIELD = '"intensity":0.0'
OLD_FIELD = '"weight":0.0'


def build_prompt(s1, multi_line, field):
    return f"""你是 CCE 结分类器。「结」= 人身上预装的动机配置(四层的具名绑定),满足: 人侧预装、有保质期(约75天)。
与「杠杆」严格区分(杠杆=内容侧制造、瞬时: {LEVERS})。

【九结签名(冻结 v{TAXO['version']})】
{KNOTS_BRIEF}

【补充判定槽】attribution(归责): self/other_agent/system/none。target_layer(闸门对象): consumption_goal/epistemic_trust/identity/fairness。
【阻挡结特别提示】inertia 的行为签名是缺席与替代行为——认命句("but I understand it now"式)、长期忍受、伪装,即使文本表面是致谢也要识别。
{multi_line}

【第 1 级引擎读出(参考,不是真值)】
四层首位: {json.dumps(s1['tops'], ensure_ascii=False)}
appraisal: {json.dumps(s1['appraisal'], ensure_ascii=False)}

【待分类内容】
{TEXT}

只输出 JSON:
{{"knots":[{{"key":"<九结key之一>",{field},"evidence_quote":"<原文引句>",
  "signature":{{"congruence":"","need_status":"","coping":"","time":"","attribution":"","target_layer":""}},
  "desire_code":"","need_code":"","freshness_days_hint":0}}],
 "levers_present":["内容里出现的杠杆(若有)"],"notes":"<一句话>"}}"""


def main():
    print("═══ 步骤 1: 冻结 s1（2 个区组，6 次调用）═══", flush=True)
    blocks = []
    for b in range(2):
        t0 = time.time()
        s1 = K.stage1(TEXT, CTX, 3)
        blocks.append(s1)
        print(f"  区组 B{b}  {int(time.time()-t0)}s  tops={s1['tops']}  within_js={s1['within_js']}", flush=True)

    print(f"\n═══ 步骤 2: 2 prompt × 2 区组 × {PER_CELL} draw（{4*PER_CELL} 次调用）═══", flush=True)
    cells = {}
    for pname, multi, field in (("NEW", HEAD_MULTI, HEAD_FIELD), ("OLD", OLD_MULTI, OLD_FIELD)):
        for b, s1 in enumerate(blocks):
            prompt = build_prompt(s1, multi, field)
            draws = []
            t0 = time.time()
            for i in range(PER_CELL):
                d = K._stage2_draw(prompt, TAXO, f"{pname}B{b}_{i}")
                if d:
                    draws.append([[x["key"], x["intensity"]] for x in d["knots"]])
            cells[f"{pname}_B{b}"] = draws
            print(f"  {pname} B{b}: {len(draws)}/{PER_CELL} 成功  {int(time.time()-t0)}s", flush=True)
    OUT.write_text(json.dumps({"cells": cells, "verdict_lines": VERDICT_LINES,
                               "blocks_tops": [b["tops"] for b in blocks]},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n  原始 draw 已落盘 {OUT}（未聚合、未归一）", flush=True)


if __name__ == "__main__":
    main()
