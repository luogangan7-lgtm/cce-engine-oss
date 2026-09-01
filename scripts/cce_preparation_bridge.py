#!/usr/bin/env python3
"""制备桥接: 完整测量程序 = 制备 + 仪器 + 资格协议。

## 为什么需要它
此前的身份体系只有两个哈希: instrument_hash(这把尺子) 和
qualification_policy_hash(怎么解读 draw)。样品制备(preparation_id)虽然
已经存在, 却**不进入任何联合身份**, 于是:

  · 换了制备 → 送进仪器的不是同一段文字 → 读数其实不可比,
    但两个哈希都不变, 上层看到「同一把尺子、同一套解读」就照常对账;
  · assert_same_preparation 抛的是普通 RuntimeError, 一个 try/except 就绕过去了,
    绕过之后照样能产出一份合法的 production artifact。

ISO 的 measurement procedure 明确把 extraction / separation 这类制备步骤
算在完整测量程序内。所以这里补齐第三个身份, 并把「不可比」升到 Contract 层。

## 三层拦截(缺一层就能绕过去)
  1. 比较函数   → 抛 **typed** PreparationMismatchError, 不是裸 RuntimeError
  2. 结果 schema → comparability.status 必须存在, 缺了就是不合法结果
  3. workflow manifest → preparation 不一致且非 bridge_mode
                        ⇒ production_verified=False 且 complete=False
即使下游 catch 掉异常, 也无法生成一个合法的 production artifact。

## 标定迁移(不是「全部重跑」也不是「全部照搬」)
判据是**逐字节**的有效输入, 不是「制备代码路径变没变」:
  prepared_bytes == raw_bytes → EXACT_INPUT_IDENTITY
      送进测量仪的有效样本没有变 ⇒ 历史 raw draw 直接复用, 不必为形式完整重投料
  prepared_bytes != raw_bytes → NONTRANSFERABLE_PREPARATION_CHANGED
      旧 qualification/readout/resolution 不能代表新制备结果 ⇒ 该 item 重跑
需要重跑的规模 = 标定 frame ∩ 实际被新制备改动的 item, 不是语料全集的改动数。
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

RAW_PREPARATION_ID = "prep_raw_unfiltered"

# calibration_transfer.status 的取值域
EXACT_INPUT_IDENTITY = "EXACT_INPUT_IDENTITY"
NONTRANSFERABLE_PREPARATION_CHANGED = "NONTRANSFERABLE_PREPARATION_CHANGED"

# comparability.status 的取值域
COMPARABLE = "COMPARABLE"
NOT_COMPARABLE = "NOT_COMPARABLE"

BRIDGE_PURPOSE = "preparation_bridge"
PREPARATION_EFFECT_ESTIMATE = "PREPARATION_EFFECT_ESTIMATE"


class PreparationMismatchError(RuntimeError):
    """★ typed —— 上层可以精确捕获这一类, 但捕获它并不能换来合法产物。

    第 2/3 层拦截独立于本异常存在: 结果 schema 缺 comparability.status 就非法,
    manifest 见到 preparation 不一致且非 bridge_mode 就把 complete 打成 False。
    """

    def __init__(self, preparations: list[str], what: str):
        self.preparations = sorted(preparations)
        super().__init__(
            f"{what}被拒绝: 涉及 {len(self.preparations)} 种样品制备 {self.preparations}。"
            "同一把尺子量了不同的样品, 读数差可能全部来自制备差异。"
            f"确需比较制备本身时, 显式声明 comparison_purpose='{BRIDGE_PURPOSE}', "
            f"产出 {PREPARATION_EFFECT_ESTIMATE} 而不是普通 delta。")


def measurement_procedure_id(instrument_hash: str, preparation_id: str,
                             qualification_policy_hash: str) -> str:
    """完整测量程序的身份。三者任一变化都换一个 id。"""
    for name, value in (("instrument_hash", instrument_hash),
                        ("preparation_id", preparation_id),
                        ("qualification_policy_hash", qualification_policy_hash)):
        if not value or not isinstance(value, str):
            raise ValueError(f"measurement_procedure_id 缺 {name} —— 不得用缺省值凑出一个 id")
    payload = json.dumps({"instrument_hash": instrument_hash,
                          "preparation_id": preparation_id,
                          "qualification_policy_hash": qualification_policy_hash},
                         sort_keys=True, ensure_ascii=False)
    return "mp_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def classify_transfer(raw_text: str, prepared_text: str | None) -> dict[str, Any]:
    """单个标定 item 的迁移判定。判据是逐字节, 不是「制备版本号变没变」。"""
    raw_hash = _sha(raw_text)
    if prepared_text is None:
        # 制备后弃权 —— 没有有效样本可送, 旧读数当然不代表它
        return {"status": NONTRANSFERABLE_PREPARATION_CHANGED,
                "reason": "制备后无可推断主体(弃权), 不存在可比的有效输入",
                "raw_sha256": raw_hash, "prepared_sha256": None}
    prepared_hash = _sha(prepared_text)
    if prepared_hash == raw_hash:
        return {"status": EXACT_INPUT_IDENTITY,
                "reason": "过闸后与原文逐字节一致, 送进测量仪的有效样本未变",
                "raw_sha256": raw_hash, "prepared_sha256": prepared_hash}
    return {"status": NONTRANSFERABLE_PREPARATION_CHANGED,
            "reason": "制备改变了有效输入, 旧 qualification/readout 不代表新制备结果",
            "raw_sha256": raw_hash, "prepared_sha256": prepared_hash}


def bridge_calibration_frame(items: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """把一个标定 frame 分成「可精确复用」和「必须重跑」。

    items: [{"item_id": str, "raw_text": str, "prepared_text": str|None}, ...]
    """
    reuse: list[dict[str, Any]] = []
    rerun: list[dict[str, Any]] = []
    for item in items:
        verdict = classify_transfer(item["raw_text"], item.get("prepared_text"))
        row = {"item_id": item["item_id"], **verdict}
        (reuse if verdict["status"] == EXACT_INPUT_IDENTITY else rerun).append(row)
    n = len(reuse) + len(rerun)
    return {
        "kind": "cce.calibration_transfer.v1",
        "frame_size": n,
        "exact_input_identity": len(reuse),
        "nontransferable": len(rerun),
        "rerun_item_ids": [row["item_id"] for row in rerun],
        "reuse_item_ids": [row["item_id"] for row in reuse],
        "rows": reuse + rerun,
        # 明确写出「重跑规模 = frame ∩ 改动」, 防止把语料全集的改动数当成重跑数
        "note": (f"需重跑 {len(rerun)}/{n} —— 这是标定 frame 与实际改动的**交集**, "
                 "不是语料全集里被改动的条数。"),
        # 改动比例不同的两组不得假装总体率可搬
        "report_separately": len(rerun) > 0 and len(reuse) > 0,
    }


def comparability(readouts: list[dict[str, Any]], *,
                  comparison_purpose: str | None = None,
                  what: str = "跨读数比较") -> dict[str, Any]:
    """第 1 层拦截。返回 comparability 块; 不可比且非 bridge 时抛 typed 异常。"""
    preps = {r.get("preparation_id", RAW_PREPARATION_ID) for r in readouts}
    instruments = {r.get("instrument", {}).get("instrument_hash") for r in readouts}
    policies = {r.get("instrument", {}).get("qualification_policy_hash") for r in readouts}
    block = {
        "instrument": "SAME" if len(instruments) <= 1 else "DIFFERENT",
        "preparation": "SAME" if len(preps) <= 1 else "DIFFERENT",
        "qualification_policy": "SAME" if len(policies) <= 1 else "DIFFERENT",
        "preparations_seen": sorted(preps),
    }
    if len(preps) <= 1:
        block["status"] = COMPARABLE if block["instrument"] == "SAME" else NOT_COMPARABLE
        block["allowed_operation"] = (["delta", "rank", "drift", "same_population_change"]
                                      if block["status"] == COMPARABLE else [])
        return block
    block["status"] = NOT_COMPARABLE
    block["allowed_operation"] = ["preparation_bridge_only"]
    if comparison_purpose == BRIDGE_PURPOSE:
        block["output_kind"] = PREPARATION_EFFECT_ESTIMATE
        block["bridge_mode"] = True
        return block
    raise PreparationMismatchError(list(preps), what)


def require_comparability_declared(result: dict[str, Any]) -> None:
    """第 2 层拦截: 结果 schema 里 comparability.status 必须存在且合法。"""
    status = (result.get("comparability") or {}).get("status")
    if status not in (COMPARABLE, NOT_COMPARABLE):
        raise PreparationMismatchError(
            [RAW_PREPARATION_ID],
            "结果缺 comparability.status(或取值非法) —— 无从判断这份结果是否可比, ")


def manifest_preparation_verdict(job_preparations: list[str], *,
                                 bridge_mode: bool = False) -> dict[str, Any]:
    """第 3 层拦截: manifest 级。

    即使下游 catch 掉 PreparationMismatchError, 只要 preparation 不一致且非
    bridge_mode, 这里就把 production_verified 和 complete 打成 False ——
    拿不到一个合法的 production artifact。
    """
    preps = sorted({p or RAW_PREPARATION_ID for p in job_preparations})
    mixed = len(preps) > 1
    if not mixed:
        return {"preparations_seen": preps, "mixed_preparation": False,
                "production_verified": True, "complete": True, "errors": []}
    if bridge_mode:
        return {"preparations_seen": preps, "mixed_preparation": True, "bridge_mode": True,
                "production_verified": False, "complete": True,
                "output_kind": PREPARATION_EFFECT_ESTIMATE,
                "errors": [],
                "note": "bridge run: 合法产出制备效应估计, 但不是 production-verified 读数"}
    return {"preparations_seen": preps, "mixed_preparation": True, "bridge_mode": False,
            "production_verified": False, "complete": False,
            "errors": [f"mixed preparation without bridge_mode: {preps}"]}
