#!/usr/bin/env python3
"""铁律 20 的可执行形式: 新模态增加 Parser, 不应修改 CCE Core。

## 为什么需要一条闸
铁律 20 是一句话, 一句话拦不住任何东西。§44.9 给 P3 定的验收 gate 是
「新增 Parser 后 CCE Core 文件 diff = 0」, 反向测试是「故意在 Core 里改一行,
CI 必须拦」—— 那就得先能机器判定「哪些文件是 Core」。

## 判据
Core = **改了它就换仪器**的文件。这与 instrument_hash 的判据同源:
      「改它之后, 已采集的原始 draw 还能不能用」。
Parser/Ingest = 把外部素材变成 CCE 能吃的输入; 它换了, 已采集的 draw 照样有效。

## 闸怎么判
Core 文件的 sha256 钉在 config/cce_core_manifest.json 里。
  · hash 与钉住的不同, 且 instrument_generation 没有跟着变 -> **红**
    (这就是「静默换仪器」, 正是 instrument_id 当初要防的事)
  · 有意换代时, 同时更新 pin 与 instrument_generation -> 绿
  · Parser 层怎么加、加多少个 -> 完全不影响本闸
Core 清单本身也钉住: 从清单里**删掉**一个 Core 文件同样是红,
否则「把文件移出 Core」就成了绕过闸的办法。
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "config", "cce_core_manifest.json")


def sha256_of(rel: str) -> str:
    with open(os.path.join(ROOT, rel), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:16]


def current_core_hashes(core_files: list[str]) -> dict[str, str]:
    return {rel: sha256_of(rel) for rel in sorted(core_files)}


def check(manifest_path: str = MANIFEST) -> tuple[bool, list[str], dict]:
    man = json.load(open(manifest_path, encoding="utf-8"))
    errors: list[str] = []
    pinned = man["core_files"]
    missing = [rel for rel in pinned if not os.path.exists(os.path.join(ROOT, rel))]
    for rel in missing:
        errors.append(f"Core 文件不存在: {rel} —— 把文件移出 Core 不是绕过闸的办法")
    live = {rel: sha256_of(rel) for rel in pinned if rel not in missing}
    drifted = {rel: (pinned[rel], live[rel]) for rel in live if pinned[rel] != live[rel]}

    # ★ 2026-09-02: 只钉文件 sha 抓不到「换环境变量换仪器」——
    #   MEASUREMENT_MODEL 是 env, 换它就换仪器却一个文件都不动。现算比对。
    exp = man.get("instrument_expected")
    if not exp:
        errors.append("清单缺 instrument_expected —— 只比文件字节抓不到 env 改仪器")
    else:
        try:
            sys.path.insert(0, os.path.join(ROOT, "scripts"))
            import json as _j
            import cce_knot_classify as _kc
            _t = _j.load(open(os.path.join(ROOT, "config", "knot_taxonomy.json"), encoding="utf-8"))
            _i = _kc.instrument_id(_t, k=3, knot_n=5,
                                   s1_pairing="round_robin_over_3_s1_draws")
            for key in ("instrument_hash", "qualification_policy_hash"):
                if _i[key] != exp[key]:
                    errors.append(f"现算 {key} = {_i[key]} != 清单钉的 {exp[key]} —— "
                                  "仪器变了(可能是 env 换了模型/端点), 必须换代")
        except Exception as exc:
            errors.append(f"无法现算仪器哈希: {type(exc).__name__}: {exc}")
    # ★★★ 2026-09-09: 闸(G)有**自己的版本** —— 只钉 instrument_hash 抓不到「静默换闸」。
    #   实测缺陷: 改 knots[].negative_examples_prompt 会改**验收闸标注者的 prompt**,
    #   而 instrument_hash **一字不变**(它只覆盖生产 s1/s2)。⇒ 若只有一个版本号,
    #   这类改动就成了「一面说生产没换代, 一面把发证的那台仪器换了」。
    gexp = man.get("gate_protocol_expected")
    if not gexp:
        errors.append("清单缺 gate_protocol_expected —— 只钉生产仪器抓不到**静默换闸**")
    else:
        try:
            sys.path.insert(0, os.path.join(ROOT, "accuracy"))
            os.environ.setdefault("MINIMAX_API_KEY", "ZERO_API_BOUNDARY_SENTINEL")
            import run_gates as _rg
            live_gh = _rg.gate_protocol_hash()
            if live_gh != gexp["hash"]:
                if _rg.GATE_PROTOCOL_VERSION == gexp["version"]:
                    errors.append(
                        f"现算闸协议哈希 {live_gh} != 清单钉的 {gexp['hash']}, 而 "
                        f"gate_protocol_version 仍是 {gexp['version']} —— **静默换闸**。"
                        "改闸 prompt 必须走 GATE_PROTOCOL_CHANGE: 递增 gate_protocol_version、"
                        "更新本 hash、并在 refactor_log 记一条事件类型为 GATE_PROTOCOL_CHANGE 的条目。")
                else:
                    gc = [e for e in man.get("refactor_log", [])
                          if e.get("event") == "GATE_PROTOCOL_CHANGE"
                          and e.get("to_gate_hash") == live_gh]
                    if not gc:
                        errors.append(
                            f"闸协议已换代({gexp['version']} → {_rg.GATE_PROTOCOL_VERSION}) 但 "
                            "refactor_log 里没有对应的 GATE_PROTOCOL_CHANGE 条目 —— "
                            "**换代必须留痕, 且不得冒充行为不变的 refactor**")
            elif _rg.GATE_PROTOCOL_VERSION != gexp["version"]:
                # ★★★ 2026-09-09 更正(网页版 GPT 指出, 我已接受): 本条原来写成
                #   「材料没变时不许跳版本」—— **写窄了**。判据、聚合方式、资格筛选、
                #   缺失/重试规则**即使不改 prompt 材料**, 也可能构成**合法且必要的**协议修订。
                #   ⇒ 该禁的是「**无协议变化的跳号**」, 不是「无材料变化的协议换版」。
                gc = [e for e in man.get("refactor_log", [])
                      if e.get("event") == "GATE_PROTOCOL_CHANGE"
                      and e.get("to_gate_version") == _rg.GATE_PROTOCOL_VERSION]
                if not gc:
                    errors.append(
                        f"gate_protocol_version 现为 {_rg.GATE_PROTOCOL_VERSION} 而清单钉 {gexp['version']}, "
                        "且 refactor_log 里**没有对应的 GATE_PROTOCOL_CHANGE 条目** —— "
                        "**无协议变化的跳号**。★ 注: 材料没变也可以合法换版(改判据/聚合/资格筛选/"
                        "缺失重试规则都算协议修订), 但必须留痕并写明**改的是协议的哪一部分**。")
                elif not gc[0].get("★协议改的是哪一部分"):
                    errors.append(
                        f"闸协议换到 v{_rg.GATE_PROTOCOL_VERSION} 但材料哈希未变, "
                        "而 refactor_log 条目没写「★协议改的是哪一部分」—— "
                        "材料没变的换版**必须**指名道姓说清改的是判据/聚合/资格筛选/缺失规则里的哪一项")
        except Exception as exc:
            errors.append(f"无法现算闸协议哈希: {type(exc).__name__}: {exc}")

    # 纯重构(行为不变)走 refactor_log: 必须写明 from/to sha 与**行为证据**。
    # ★ 键必须是 (文件, from_sha, to_sha) 的**完整转移**, 不能只匹配 to_sha ——
    #   只匹配 to_sha 时, 把 pin 改成任意垃圾值也会被这条路豁免(既有反向测试抓到的)。
    log = {(e["file"], e.get("from_sha"), e["to_sha"]): e for e in man.get("refactor_log", [])}
    for rel, (was, now) in sorted(drifted.items()):
        e = log.get((rel, was, now))
        if e is None:
            errors.append(
                f"{rel}: pinned {was} != live {now}, 而 instrument_generation 仍是 "
                f"{man['instrument_generation']} 且无 refactor_log 记录 —— **静默换仪器**")
            continue
        if not e.get("behavior_evidence"):
            errors.append(f"{rel}: refactor_log 条目没写 behavior_evidence —— "
                          "「仪器哈希没变」不足以证明行为没变")
        for t in e.get("behavior_evidence", []):
            if not os.path.exists(os.path.join(ROOT, t)):
                errors.append(f"{rel}: refactor_log 引的行为证据 {t} 不存在")
        if not e.get("reason"):
            errors.append(f"{rel}: refactor_log 条目没写 reason")
    # Parser 层允许自由增删, 但不许把 Core 文件也塞进 Parser 清单蒙混
    overlap = sorted(set(pinned) & set(man.get("parser_plane", [])))
    if overlap:
        errors.append(f"同一文件同时被声明为 Core 与 Parser: {overlap}")
    return (not errors), errors, {"core_n": len(pinned), "drifted": sorted(drifted),
                                  "parser_n": len(man.get("parser_plane", [])),
                                  "instrument_generation": man["instrument_generation"],
                                  "gate_protocol_version": (gexp or {}).get("version")}


def main() -> int:
    ok, errors, info = check()
    print("=" * 60)
    print("铁律 20 闸: 新增 Parser 不得修改 CCE Core")
    print("=" * 60)
    print(f"Core 文件 {info['core_n']} 个 · Parser 层 {info['parser_n']} 个")
    print(f"★ instrument_generation = {info['instrument_generation']} (**只指生产 P**) · "
          f"gate_protocol_version = {info['gate_protocol_version']} (**验收闸 G, 独立版本**)")
    for e in errors:
        print("  ✗ " + e)
    print("CORE_BOUNDARY_PASS" if ok else "CORE_BOUNDARY_FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
