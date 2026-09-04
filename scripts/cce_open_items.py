#!/usr/bin/env python3
"""「还差什么」—— 从各真相源**现算**, 不由我口述。

2026-08-07 立的汇报纪律: 禁用裸的「完整/全链路」字样, 必须给逐项清单。
2026-09-03 owner 两次点破我越界声报(「可以投产了」/ 收尾语气)。
⇒ 与 cce_production_status.py 配套: 那张表说「哪些读数能用」, 这张说「哪些事没做完」。

★ 分三类, 因为它们的**修法完全不同**:
   BLOCKED_EXTERNAL —— 卡在我拿不到的外部资源上(人/触达量/owner 裁定)
   OPEN_WORK        —— 我能做, 只是没做
   DECIDED_NOT_DOING—— 已裁定不做, 留着防有人重开
"""
from __future__ import annotations

import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLOCKED, OPEN, DECIDED = "BLOCKED_EXTERNAL", "OPEN_WORK", "DECIDED_NOT_DOING"


def _j(rel):
    return json.load(open(os.path.join(ROOT, rel), encoding="utf-8"))


def items() -> list[dict]:
    out = []

    # ① 链路阶段未完成的
    conf = _j("config/cce_chain_conformance.json")
    for ph in conf["phases"]:
        if not ph["status"].startswith("DONE") and "DECIDED" not in ph["status"]:
            out.append({"类": OPEN, "项": f"{ph['phase']} 未完成", "证据": ph["status"]})
        elif "SCOPED_WITHHOLDING" in ph["status"] or "DECIDED" in ph["status"]:
            # ★ 只写状态词等于没写 —— 读的人看不出「条件是什么、谁能解开」。
            #   带条件完成的项必须自带: 扣发了什么 + 什么能解开它。
            out.append({"类": DECIDED if "DECIDED" in ph["status"] else OPEN,
                        "项": f"{ph['phase']} 带条件完成",
                        "证据": f"{ph['status']} — {ph.get('★condition') or '条件未写明(需补)'}"})

    # ② profile 未经 CI 验证的
    seen = set()
    for f in glob.glob(os.path.join(ROOT, "archive", "*", "*normalized.json")):
        try:
            seen.add(json.load(open(f, encoding="utf-8")).get("profile"))
        except Exception:
            pass
    for p in _j("config/cce_submission_contract_v1.json")["profiles"]:
        if p not in seen:
            out.append({"类": OPEN, "项": f"profile `{p}` 从未在 CI 上验证过",
                        "证据": "archive/ 里没有它的成功 run"})

    # ③ 能力注册表里仍缺的
    # ★ 2026-09-04: 原来一律记 OPEN, 于是「卡在拿不到的外部资源上」和「已裁定不做」
    #   都被显示成「我能做只是没做」—— 三类混成一类, 清单就失去了它唯一的用处。
    #   ⇒ 让 missing 条目**自己声明所属类**(靠它本来就写着的字样), 默认仍是 OPEN。
    def _class_of(m: str) -> str:
        if any(w in m for w in ("仍 BLOCKED", "拿不到", "受限模型", "需英文域", "无一张标注素材",
                                "解锁动作")):
            return BLOCKED
        if any(w in m for w in ("刻意不", "已裁定", "已否决")):
            return DECIDED
        return OPEN

    for c in _j("config/cce_capability_registry_v1.json")["capabilities"]:
        for m in (c.get("missing") or []):
            _cls = _class_of(m)
            # ★ BLOCKED/DECIDED 的理由写在 missing 原文里, 而「项」只截 64 字会把它切掉。
            #   ⇒ 非 OPEN 的项, 证据必须带上原文, 否则「卡在什么资源上」无处可读。
            out.append({"类": _cls, "项": f"{c['id']}: {m[:64]}",
                        "证据": (f"status={c['status']}" if _cls == OPEN
                                 else f"status={c['status']} — {m}")})

    # ④ 读数层判红的(修法只有换仪器或接受)
    ps = _j("tests/data/phase2/k1_v2_multitext_verdict.json")
    out.append({"类": DECIDED,
                "项": "结层 intensity/weight 永久不可用",
                "证据": f"K1-v2 {ps['decision']}; 已裁定不换仪器(托管 API 无法批不变)"})
    ph_v = _j("tests/data/phase2/playbook_hit_verdict.json")
    at_v = _j("tests/data/phase2/playbook_atoms_verdict.json") if os.path.exists(
        os.path.join(ROOT, "tests/data/phase2/playbook_atoms_verdict.json")) else None
    _ev = f"{ph_v['decision']} {ph_v['meeting_criterion']}/{ph_v['texts']} 文本达标"
    if at_v:
        _ev += (f"; 替代方案已试并实测: 原子分解 {at_v['decision']} "
                f"{at_v['meeting_criterion']}/{at_v['texts']}(改善真实且非退化, 但未到 7/8 采纳线 ⇒ 不采纳)")
    out.append({"类": OPEN, "项": "对齐出口 playbook_hit 不可靠, 替代已测但未达采纳线",
                "证据": _ev + ("。★ 下一步不是再换读数形态 —— 实测显示残余不稳定不在标尺上"
                               "(belong 的正向原子只剩 1 条, 连二值都在 0/1 间摆)。"
                               "要动的是 **playbook 原子本身**(措辞太抽象, 无法逐字指认), "
                               "那是改**干预设计**不是改测量 ⇒ **需 owner 拍板**, 且要另立预注册。")})

    # ⑤ 文档与代码的分歧
    # 「已就地标注」= 分歧仍在但读那一节的人不会被误导, 且有闸钉住 ⇒ 与「符合」同属已解决
    for s in _j("config/cce_doc_reconciliation.json")["section_divergences"]:
        if s["verdict"] not in ("符合", "已就地标注"):
            out.append({"类": OPEN, "项": f"{s['section']}: {s['verdict']}",
                        "证据": s.get("note", "")[:70]})

    # ⑥ 归档里追不回的
    idx = _j("config/cce_archive_index.json")
    n = sum(1 for v in idx["runs"].values() if v["status"] == "IRRECOVERABLE")
    out.append({"类": DECIDED, "项": f"{n} 个历史 run 两仓皆无, 不可重建",
                "证据": "已实测复核, 如实登记为损失"})

    # ⑦ 卡在外部资源上的
    out.append({"类": BLOCKED, "项": "语义 SESOI 无锚点",
                "证据": "需 >=3 名人类评分者(5x60 设计已定); SESOI 现为 None 且有三处测试钉住"})
    out.append({"类": BLOCKED, "项": "内容 A/B 不可判",
                "证据": "所需样本超单帖历史最高浏览; §44.10 的 24500 不可复算(全文未定义 R)"})
    # ★ 2026-09-04 更正: 这一项**曾被我误判为 BLOCKED**。
    #   我把「需要英文标注素材」读成「需要**本域**的标注素材」, 而本项目自己的分解是
    #   能力=域无关 / **抽取质量=语言相关** / 标定=域相关 ⇒ 公开英文基准就是正确的素材。
    #   实测可得: LibriSpeech(CC BY 4.0, openslr 直链 200) · TextOCR v0.1(CC BY 4.0, 逐图 CDN 200)。
    #   ⇒ 已完成, 不再列入未完成清单。留这段注释防止下一个人再把它归回 BLOCKED。
    _ocr_en = os.path.join(ROOT, "tests/data/phase2/ocr_quality_en.json")
    _asr_en = os.path.join(ROOT, "tests/data/phase2/asr_quality_en.json")
    if not (os.path.exists(_ocr_en) and os.path.exists(_asr_en)):
        _have = [n for n, p_ in (("OCR", _ocr_en), ("ASR", _asr_en)) if os.path.exists(p_)]
        out.append({"类": OPEN, "项": "媒体抽取质量(英文)仅完成一半",
                    "证据": f"已完成 {_have or '无'}; 另一半的评测尚未落盘。"
                            "语料已核实可匿名直下, **不是外部阻塞**"})
    # ★ 2026-09-04 实际去做才确认: 这不是「没装」, 是拿不到凭据 ⇒ 从 OPEN 改归 BLOCKED。
    out.append({"类": BLOCKED, "项": "**说话人分离**(diarization) 拿不到受限模型凭据",
                "证据": ("pyannote/speaker-diarization-3.1 是 HF **受限模型**, 需账号接受条款并给 token。"
                         "解锁动作明确: owner 提供 HF token。★ 不拿源分离的能量占比冒充说话人数。")})
    # ★ 2026-09-03 查完改判: 这不是「待修的分叉」, 它**就是那次退役本身**。
    #   origin 独有的文件全是 mt_*(Hy-MT2 MT 实验), 本地提交 b33befd
    #   "retire Hy-MT2 MT experiment" 删掉了它们, 归档在
    #   /Volumes/data/archive/hymt2-retired-20260817/。
    #   **合并 = 复活退役代码** —— 正是本项目栽过三次的「拿退役组件当现行标准」。
    out.append({"类": DECIDED,
                "项": "与私仓 origin 的分叉**不合并** —— 合并会复活已退役的 Hy-MT2",
                "证据": ("origin 独有文件全是 mt_*; 本地 b33befd 已退役并归档于 "
                         "archive/hymt2-retired-20260817。私仓另带 PII 且非生产入口, 亦不推。")})

    # ★ 去重: 同一件事可能既被注册表列为 missing, 又被显式标为 BLOCKED。
    #   显式的分类优先 —— 否则「卡在外部资源」会被误报成「我能做只是没做」。
    blocked_keys = [r["项"] for r in out if r["类"] == BLOCKED]
    deduped, seen_open = [], set()
    for r in out:
        if r["类"] == OPEN and any(k[:8] in r["项"] or r["项"][:12] in k for k in blocked_keys):
            continue                      # 已被更准确的 BLOCKED 覆盖
        key = (r["类"], r["项"][:40])
        if key in seen_open:
            continue
        seen_open.add(key)
        deduped.append(r)
    return deduped


def main() -> int:
    rs = items()
    print("=" * 74)
    print("CCE 未完成清单 —— 由各真相源现算")
    print("=" * 74)
    for cls, label in ((OPEN, "还能做, 只是没做"), (BLOCKED, "卡在外部资源上"),
                       (DECIDED, "已裁定不做(留着防重开)")):
        got = [r for r in rs if r["类"] == cls]
        print(f"\n【{cls}】{label} —— {len(got)} 项")
        for r in got:
            print(f"  · {r['项']}")
            print(f"      {r['证据']}")
    print("\n" + "-" * 74)
    print(f"合计 {len(rs)} 项未完成。★ 「引擎跑得动」与「这些事做完了」是两件事。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
