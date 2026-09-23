#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""账本反向审结论 —— 对「事实已在自己的账本上, 却没被用来复查依赖它的结论」的闸。

★ 为什么不是「每条结论登记它依赖哪些账本条目」:
  那要求我**在下结论时就想到该登记** —— 而我恰恰是在那一步失守的
  (2026-09-09: 我建了字段送达账本, 记着 hard_discriminant=NEITHER,
   却仍然写下「生产违反了这条必要条件」)。
  自证式的闸抓不到「我没想到要登记」。

★ 所以方向反过来: **账本主动去扫结论**。
  账本里每条**否定性事实**(某字段到不了某台仪器)自带一个「与它矛盾的断言长什么样」的检测器,
  闸把所有检测器跑遍 tests/data/ 下的全部留档。**不需要结论那边配合。**

  这是「守卫的生效判定必须构造它应该抓住的输入」的同一条原理:
  账本条目不只是记录, 它必须能**指认自己的反例**。
"""
import json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
LEDGER = ROOT / "tests/data/taxonomy_field_reach_ledger.json"
ADJUDICATIONS = ROOT / "tests/data/ledger_claim_audit_adjudications.json"
SELF_REFERENTIAL = {LEDGER.name, ADJUDICATIONS.name}
CLAIMS_DIR = ROOT / "tests/data"

# 「这条断言把某字段的效力施加到了哪台仪器上」—— 仪器的指称词
INSTRUMENT_WORDS = {
    "PROD": ("生产", "production", "分类器 P", "cce_knot_classify", "s2_prompt"),
    "GATE": ("验收闸", "标注面板", "run_gates", "闸协议"),
}
# 「违反/遵守」框架词 —— 只有落在这种框架里, 才是在**把规则施加给仪器**
NORMATIVE = ("违反", "违背", "不符合", "没遵守", "应当遵守", "必须满足", "符合合同")

# ★★★ 第一版**没抓到它被设计去抓的那句话** —— 我写的是「违反**既有必要条件**」,
#   而闸只认字段名 `hard_discriminant`。**换个说法就绕过去了。**
#   修法: 每条账本事实登记它在自然语言里**被怎么称呼**。
#   ★ 这仍然是「要我登记」, 但登记的位置换了 ——
#     **建账本时登记一次(那时我正在想字段)**, 而不是**下每条结论时登记一次(那时我在想别的)**。
#     依赖没被消灭, 只被搬到我更可能做对的那一刻。这条差别必须写明, 不许说成「已经解决」。
ALIASES = {
    "hard_discriminant": ("必要条件", "硬判别", "附带犹豫理由", "明确悬置"),
    "negative_examples_prompt": ("负例", "负例判据", "不用于"),
    "definition_of_knot": ("本体论定义", "结的定义"),
    "identity_criterion": ("同一性判据",),
    "playbook": ("话术", "干预设计"),
    "annotation_protocol": ("标注协议",),
    "cost_tier": ("成本档",),
    "evidence_level": ("证据等级",),
}
# 太短或太常见的键名单独扫会漫天误报(source/version/status/key/name/family)
TOO_GENERIC = {"source", "version", "status", "key", "name", "family", "frozen_at"}


def ledger_negative_facts():
    """账本里的否定性事实: 字段 -> 它到不了的仪器集合。"""
    d = json.loads(LEDGER.read_text(encoding="utf-8"))
    per = d["per_field"]
    out = {}
    for field, bucket in per.items():
        short = field.split("].")[-1].split("[")[0]
        unreachable = set()
        if bucket in ("NEITHER", "GATE_ONLY"):
            unreachable.add("PROD")
        if bucket in ("NEITHER", "PROD_ONLY"):
            unreachable.add("GATE")
        if unreachable:
            out.setdefault(short, set()).update(unreachable)
    return out


def scan(text, facts):
    """返回这段文字里「把某字段的规范效力施加到它到不了的仪器」的命中。"""
    hits = []
    for field, unreachable in facts.items():
        if field in TOO_GENERIC:
            continue
        needles = (field,) + ALIASES.get(field, ())
        pat = "|".join(re.escape(n) for n in needles)
        for m in re.finditer(pat, text):
            win = text[max(0, m.start() - 220): m.end() + 220]
            if not any(w in win for w in NORMATIVE):
                continue
            for inst in unreachable:
                if any(w in win for w in INSTRUMENT_WORDS[inst]):
                    # 已经明写「送不到/够不着/未送达」的, 是**正在更正**, 不判红
                    if any(x in win for x in ("未送达", "够不着", "收不到", "不进生产",
                                              "从未收到", "归错了对象", "只进闸")):
                        continue
                    hits.append({"字段": field, "命中的说法": m.group(0),
                                 "被施加到": inst, "窗口": win.strip()[:260]})
    return hits


WITNESS = "「仅收藏被判 suspend **违反**既有必要条件」—— 生产分类器 P 在这两道题上判了 suspend。"


def build():
    facts = ledger_negative_facts()
    findings = []
    for p in sorted(CLAIMS_DIR.rglob("*.json")):
        # ★ 自指排除: 账本本身与裁决簿必然含有字段名+规范词(它们就是在谈这件事)。
        #   **排除名单只有这两项且写死在这里** —— 排除文件是藏东西最方便的手法,
        #   所以名单必须短、必须显式、必须有测试钉住长度。
        if p.name in SELF_REFERENTIAL:
            continue
        try:
            t = p.read_text(encoding="utf-8")
        except Exception:
            continue
        for h in scan(t, facts):
            findings.append({"文件": str(p.relative_to(ROOT)), **h})
    adj = json.loads(ADJUDICATIONS.read_text(encoding="utf-8"))
    known = {(a["文件"], a["字段"], a["说法"]) for a in adj["adjudicated"]}
    unadj = [h for h in findings if (h["文件"], h["字段"], h["命中的说法"]) not in known]
    stale = [a for a in adj["adjudicated"]
             if (a["文件"], a["字段"], a["说法"]) not in
             {(h["文件"], h["字段"], h["命中的说法"]) for h in findings}]
    return {
        "block": "LEDGER_AUDITS_CLAIMS",
        "★zero_api": "纯文本扫描, 零调用。",
        "★原理": (
            "**不要求结论登记依赖**(那一步正是我失守的地方), 而是让**账本里的否定性事实**"
            "各自携带一个「与它矛盾的断言长什么样」的检测器, 由闸把检测器跑遍全部留档。"
        ),
        "账本否定性事实数": {k: sorted(v) for k, v in sorted(facts.items())},
        "★★★命中(把某字段的规范效力施加到它到不了的仪器上)": findings,
        "★★★未裁决命中(判红的就是这些)": unadj,
        "★已裁决": len(known),
        "★自指排除的文件(名单必须短且显式)": sorted(SELF_REFERENTIAL),
        "★★裁决簿里已失效的条目(对应命中不在了, 要么已修要么闸被改窄了)": stale,
        "★已修复并归档(命中消失且说明了为何消失)": [
            {"文件": r["文件"], "字段": r["字段"], "★命中为何消失": r.get("★命中为何消失", "**未说明 —— 违规**")}
            for r in adj.get("resolved", [])],
        "★★★这个闸自己的反向验证": {
            "被设计去抓的输入": "「仅收藏被判 suspend **违反**既有必要条件」—— 生产分类器 P 在这两道题上判了 suspend。",
            "第一版": "**抓不到** —— 只认字段名, 我用的是「必要条件」这个说法",
            "加别名后": "抓到(见 self_check)",
            "★教训": "闸建完必须**拿它该抓的那条历史输入**去验; 没验过的闸等于没建。",
        },
        "self_check": scan(WITNESS, facts),
        "★★局限_必须写下来": [
            "① 只查**字面**同现 —— 别名表以外的新说法仍会绕过。它降低漏检率, **不保证零漏检**。",
            "★ 别名表仍要我登记, 只是**登记时机**从「下每条结论时」搬到「建账本时」—— "
            "依赖**没被消灭**, 只搬到我更可能做对的那一刻。不许说成「已解决」。",
            "② 只覆盖 taxonomy 字段送达这一本账。**其它账本要各自写自己的检测器**, 这是模板不是全集。",
            "③ 「正在更正」的豁免词表是我列的 ⇒ 有被滥用成消音的风险。**豁免必须在留档里真的展开说明**, 不能只放一个词。",
        ],
    }


if __name__ == "__main__":
    r = build()
    print(json.dumps(r, ensure_ascii=False, indent=1))
    sys.exit(1 if r["★★★未裁决命中(判红的就是这些)"] else 0)
