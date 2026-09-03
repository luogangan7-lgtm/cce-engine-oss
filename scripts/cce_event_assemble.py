#!/usr/bin/env python3
"""Assemble conservative CCE events from Foundation observations.

This is deliberately an event *assembler*, not a psychological inference
engine.  It emits atomic events and time-synchronised composites only; words
such as reinforces, attention, trust or intent never arise from overlap alone.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from cce_contract import validate_case

ASSEMBLER_VERSION = "1.0.0"


ATOMIC_TYPES = {
    "visual_frame_description": "visual_frame_observed",
    "on_screen_text": "on_screen_text_observed",
    "speech_transcript": "speech_observed",
    "audio_tags": "audio_tags_observed",
}


def overlaps(a: dict[str, Any], b: dict[str, Any]) -> bool:
    ta, tb = a.get("time"), b.get("time")
    if not isinstance(ta, dict) or not isinstance(tb, dict):
        return False
    return max(ta["start"], tb["start"]) < min(ta["end"], tb["end"])


def intersection(a: dict[str, Any], b: dict[str, Any]) -> dict[str, float]:
    return {"start": max(a["time"]["start"], b["time"]["start"]),
            "end": min(a["time"]["end"], b["time"]["end"])}


# 状态层字段: 与 cce_ledger.STATE_KEYS 同源(铁律 4 用的是同一张表)
_STATE_KEYS = {"knots", "intensity", "weight", "mass", "quadrant", "families",
               "desire_vec", "emotion_vec", "action_vec", "appraisal", "composition",
               "state"}


def assemble(case: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(case)
    observations = out.get("observations") or []
    # 铁律 3: Event != State。★ 2026-09-03 实测: 调用方自带的 events 被**原样透传** ——
    #   于是一条贴着 assertion="observed" 的状态断言可以直接冒充事件活下来。
    #   事件在这里是**派生**出来的(assertion="derived"), 不是断言进来的。
    # ★ 事件的**形状**(event_type/layer/assertion/member_refs/confidence)由
    #   cce_contract.validate_case 校验, 这里不重造 —— 我第一版重造了两次都造窄了:
    #   ① 拿 assertion=="derived" 当判别器, 拦红了真实的 evt:shot-cut(observed 合法);
    #   ② 补 event_type 后又拦红了 evt:reinforcement(inferred 也是合同里的合法值)。
    #   **闸开太宽和开太窄一样是缺陷。**
    #   合同没管的只有一件: 事件对象不得携带状态层字段。铁律 3 只补这一条。
    for e in out.get("events") or []:
        if _STATE_KEYS & set(e):
            raise ValueError(
                f"事件 {e.get('id')!r} 带状态层字段 {sorted(_STATE_KEYS & set(e))} —— "
                "铁律 3: Event != State。状态是**测**出来的推断, 事件是**发生**的事; "
                "把状态挂在事件上, 下游就会把推断当成观察。")
    existing = {event.get("id") for event in out.get("events") or []}
    events = out.setdefault("events", [])
    atomic: list[dict[str, Any]] = []
    for obs in observations:
        event_type = ATOMIC_TYPES.get(obs.get("kind"))
        if not event_type or not isinstance(obs.get("time"), dict):
            continue
        eid = "evt:assembled:" + obs["id"].replace("obs:", "")
        if eid in existing:
            continue
        event = {
            "id": eid, "event_type": event_type, "layer": "atomic", "assertion": "derived",
            "time": obs["time"], "member_refs": [obs["id"]], "evidence_refs": [obs["id"]],
            # 该事件是**既有观测的 1:1 复述** ⇒ 给定成员即必然为真, 不是测量结果。
            "confidence": 1.0, "confidence_basis": "definitional",
            "provenance": {"producer": "cce_event_assemble", "version": ASSEMBLER_VERSION},
        }
        events.append(event); atomic.append(event); existing.add(eid)

    # Cross-modal composite only asserts synchronisation.  It intentionally
    # avoids "reinforcement", which needs a separately validated mechanism.
    visuals = [e for e in atomic if e["event_type"] == "visual_frame_observed"]
    texts = [e for e in atomic if e["event_type"] == "on_screen_text_observed"]
    for visual in visuals:
        for text in texts:
            if not overlaps(visual, text):
                continue
            eid = f"evt:assembled:sync:{visual['id'].split(':')[-2]}:{text['id'].split(':')[-1]}"
            if eid in existing:
                continue
            events.append({
                "id": eid, "event_type": "cross_modal_synchronization", "layer": "composite",
                "assertion": "derived", "time": intersection(visual, text),
                "member_refs": [visual["id"], text["id"]],
                "evidence_refs": visual["evidence_refs"] + text["evidence_refs"],
                # 「两区间重叠」由时间戳算出 ⇒ 构造上必然为真, 不是同步强度的度量。
                "confidence": 1.0, "confidence_basis": "definitional",
                "relations": ["synchronizes"],
                "provenance": {"producer": "cce_event_assemble", "version": ASSEMBLER_VERSION},
            })
            existing.add(eid)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    case = json.loads(args.case.read_text(encoding="utf-8"))
    out = assemble(case)
    verdict = validate_case(out)
    if not verdict["ok"]:
        raise SystemExit("assembler emitted invalid contract:\n" + "\n".join(verdict["errors"]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out), "events": verdict["counts"]["events"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
