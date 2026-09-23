# -*- coding: utf-8 -*-
"""预注册: 填槽打分策略 v2(possession 按合同等价类) —— r7 起生效。零调用, 只写 JSON。"""
import hashlib, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]; OUT = ROOT / "tests/data/slot_filling_score_policy_v2_prereg.json"
PREREG = {
 "block": "SLOT_FILLING_SCORE_POLICY_V2_PREREG", "date": "2026-09-23", "★★★status": "**REGISTERED** —— r7 及以后的填槽轮次按此打分; r5/r6/r6-jev 的数**不回改**",
 "★问题": "possession 槽位三轮净增益为负(−6/−11/−24), results/possession_gain_artifact.json 现证是打分伪影: 判据层对 OWNED 与 EXPERIENCED 结局相同(合同 Q 是析取), v1 打分却把两者当两个答案。",
 "★★★规则": {
  "①等价类由判据层现算": "对 cce_claim_frame.POSSESSION 每个取值, 在标准框架(SELF/ASSERTED/PAST_OR_PRESENT/DIRECT, P 支 OF_DECLARED_KIND+数据)上跑 allow_label 两档; 结局相同者同类。**禁止手写类表**。★ 现算出来的事实(不是选择): {OWNED, EXPERIENCED} · {ONE_NEGATED, UNSPECIFIED}(两者都让 Q 不成立, 判据层结局逐字相同) · {BOTH_NEGATED} —— 三类。若有人觉得 UNSPECIFIED 不该与 ONE_NEGATED 同类, 该改的是判据层, 不是打分表。",
  "②打分": "possession 格 对 ⟺ class(模型) == class(金标)。其余五槽 v1 不变。",
  "③零基线": "仍是全填 OWNED, 但也按类算 ⇒ 可得增益 = n − 零基线(按类)。",
  "④测不出的类": "金标里样本数 < 6 的类(现状: ONE_NEGATED 0 / BOTH_NEGATED 2 / UNSPECIFIED 2)标「测不出」, 该类的对错**不得**引用为能力证据; 要测它们须先补金标(另立预注册)。",
  "⑤可比不可合": "v2 读数与 v1 读数不得合并; 三轮的 v2 附带读数只在 results/slot_filling_score_policy_v2.json 里, 冻结产物 sha 由闸核未改。",
  "⑥作废条件": "cce_claim_frame.py 改动导致等价类变化 ⇒ 本预注册与 v2 产物作废重算(产物记判据源 sha)。"},
 "★预期(先写)": {"三轮 v2 净增益": "由负转为 ≥0(艺术品文件已给 +2/+2/+4, 本轮由策略模块独立重算核对)", "★不得据此说": ["不得说三个模型 possession 都对 —— 测不出的类没测。", "不得回头改 r5/r6/r6-jev 的槽位级数。", "不得把 v2 与 v1 数合并。"]},
 "★实现": {"模块": "probes/slot_filling_score_policy_v2.py", "闸": "tests/test_cce_slot_filling_score_policy_v2.py", "接入 r7 执行器的方式": "r7 执行器 import 本模块的 same_class/derive_classes 给 score() 的 possession 格; 不改 r5 模块(r6 仍 import 它一行不改)。"}}


def main():
    OUT.write_text(json.dumps(PREREG, ensure_ascii=False, indent=1), encoding="utf-8"); print("→", OUT, hashlib.sha256(OUT.read_bytes()).hexdigest()[:16]); return 0


if __name__ == "__main__": raise SystemExit(main())
