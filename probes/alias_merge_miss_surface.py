#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""量「不做别名归并」的漏判面 —— **它有多大, 以及这个量本身能说多少**。

## 背景
`scripts/cce_label_qualification.py` 的 P2 要求两个必要条件的证据片段**指向同一个对象**,
并且**不做别名归并**:「the Oticon」与「Oticon」在那里是**两个**对象。
理由是 fail-closed —— 归并要读文本, 不归并会漏判、乱归并会误判, 宁可漏判。
但那条选择当时**没有量过代价**。本探针量它。

## ★★★ 这个量的两层, 必须分开读
**第一层(字面量, 本探针能算)**: 同一个裸名出现多少种词面(the X / X)。
**第二层(指代, 本探针算不了)**: 代词(it / them / the ones)指回前文的对象 ——
  **字符串判据结构上看不见它**。而在本语料里, **指代才是别名的主力**。
⇒ 只报第一层会把漏判面报小。两层都报, 并明写第二层是**下界之外的未知**。

★ 本探针**不解析指代**(那要读文本)。它只做一件事: 把「有多少文本含指代词」数出来,
  作为**第二层的规模指示**, 并如实说明它不等于漏判数。
"""
import collections
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "tests" / "data" / "local_contract_assertions_v2.json"

# ★ 排除句首动词/助词等大写词 —— 它们不是专名。名单写死是故意的: 这是**语料相关**的,
#   换语料必须重列, 不许假装它通用。
_NOT_A_NAME = {"Settled", "Made", "Waiting", "Just", "Decision", "Sitting", "Locked",
               "Going", "Not", "Given", "Spent", "Finally", "Was", "Could", "Bought",
               "Kept", "Then", "I", "Won", "Tuesday"}
_PRONOUN = r"\b(it|them|they|these|those|the ones|one)\b"


def build() -> dict:
    A = json.loads(SRC.read_text(encoding="utf-8"))["断言"]
    texts = {a["用例"]: a["文本"] for a in A}

    forms = collections.Counter()
    for t in texts.values():
        for m in re.finditer(r"\b(?:the\s+)?([A-Z][A-Za-z]+)\b", t):
            if m.group(1) in _NOT_A_NAME:
                continue
            forms[m.group(0)] += 1
    bare = collections.defaultdict(set)
    for w in forms:
        bare[re.sub(r"^the\s+", "", w)].add(w)
    multi = {k: sorted(v) for k, v in bare.items() if len(v) > 1}

    pron = {c: [m.group(0) for m in re.finditer(_PRONOUN, t, re.I)]
            for c, t in texts.items()}
    pron = {c: v for c, v in pron.items() if v}

    return {
        "block": "ALIAS_MERGE_MISS_SURFACE",
        "语料": {"来源": str(SRC.relative_to(ROOT)), "文本数": len(texts)},
        "★第一层·字面别名(本探针能算)": {
            "专名词面": dict(forms),
            "同一裸名多种写法": multi,
            "受影响裸名数": len(multi),
            "读法": "P2 不归并 ⇒ 这些词面被当成不同对象 ⇒ 若两个合取项分别用了 %s, 会被判成不同对象而不升格。"
                  % (list(multi.values())[0] if multi else "(本语料无)"),
        },
        "★★★第二层·指代(本探针**算不了**)": {
            "含指代词的文本": {c: v for c, v in sorted(pron.items())},
            "文本数": "%d/%d" % (len(pron), len(texts)),
            "★为什么算不了": "代词(it/them/the ones)指回前文的对象, **字符串判据结构上看不见**。"
                       "解析它要读文本 —— 那正是 P2 刻意不做的那件事。",
            "★★这个数不是漏判数": "它只说明**有多少文本里存在指代**, 不说明其中多少会真的造成漏判 —— "
                          "后者要逐条判断代词指的是不是那个对象。**不许把它当漏判率引用。**",
        },
        "★★★结论怎么写才不越界": [
            "字面别名面在本语料上**很小**(%d 个裸名受影响)。" % len(multi),
            "但**指代**出现在 %d/%d 个文本里, 而 P2 对它**结构上无能为力** ⇒ "
            "「字面面小」**推不出**「漏判少」。" % (len(pron), len(texts)),
            "★ 真实漏判率**仍未测**, 且本探针给不出 —— 它需要逐条判断指代对象, "
            "要么靠人, 要么靠模型(后者回到 gen9 测出有偏的那一面)。",
            "★ 本语料是 12 条**孤立构造题**, 不是自然语料 ⇒ 上面两个数都**不得外推**。",
        ],
    }


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=1))
