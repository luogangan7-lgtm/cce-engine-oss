#!/usr/bin/env python3
"""结构闸: 测量**之前**的样品制备 —— 把「不是作者写的话」从被测文本里摘出去。

## 为什么存在
库里已否决过一条(CCE v2·状态推断):「把评论文本的 CCE 分布直接命名为 observed
author state」—— 文本只是 observed evidence。但实现上一直只有**整篇**的弃权:
stage1 prompt 让模型自己判「这是不是个人表达」, 于是
  · 纯非人称(链接堆/条款)  → 模型多数会弃权(实测 base 3fb58419ad8f 8 次里弃权 6 次)
  · **混合**(大段引用 + 一句自己的话) → 模型照读不误, 读到的是**被引用者**的状态
后者从未被拦过。这道闸补的是后者, 顺带把前者变成 **0 次 API 调用**就能判。

## 判据(只有一条)
对每一段问: **能不能证明这段不是作者自己写的话?**
证得出(引用标记 / 代码围栏 / 整行只有链接) → NONPERSONAL, 摘出去;
证不出 → AMBIGUOUS, **保留**。
所以它只会少删不会多删 —— 误判方向是「漏摘」(退化回今天的行为), 不是「错摘」。
PERSONAL 只是 AMBIGUOUS 里带第一人称标记的那部分, **只用于报告, 不参与去留决策**;
去留完全由「证得出/证不出」决定, 因此不存在需要调的阈值。

## 与仪器身份的关系(★ 别搞混)
本闸**一个字都不碰 stage1 prompt 模板** —— 碰了 s1_prompt_sha256 就变, 仪器换代,
gen4 那 311 样本的资格标定当场作废。它改的是**送进去的文本**, 属样品制备。
但制备不同的读数同样不可直接比较, 所以另立 preparation_id + assert_same_preparation,
与 assert_same_instrument 同形。
"""
import hashlib
import re

GATE_VERSION = "1.0.0"
SPAN_KINDS = ("PERSONAL", "NONPERSONAL", "AMBIGUOUS")
DROPPED_KINDS = ("NONPERSONAL",)

VERDICT_MEASURE = "MEASURE"
VERDICT_ABSTAIN = "ABSTAIN_NO_INFERABLE_SUBJECT"

_FENCE = re.compile(r"^\s*(```|~~~)")
# 引用标记: markdown 的 > , 以及 HTML 转义后的 &gt; (实测语料里就是这个形态)
_QUOTE = re.compile(r"^\s*(?:>|&gt;)+\s?")
# ★ markdown 链接**只剥 URL, 保留锚文本**。实测反例 f062a35fb9d2:
#   `[Look, I know the camera angle is simply weird, but this arm is SHORT!](url)`
#   —— 锚文本是作者自己的话。锚文本证不出非作者所写 ⇒ 按判据必须保留。
#   代价: 引用条目式的 `- [新闻标题](url)` 会被留下(实测 3fb58419ad8f 因此不再零调用弃权)。
#   不为保住那个结果去加「列表记号=引用条目」的规则 —— 那是照着想要的结论调规则。
_MD_LINK = re.compile(r"\[([^\]]*)\]\(\s*<?https?://[^)\s]+>?[^)]*\)")
_BARE_URL = re.compile(r"<?https?://\S+>?")
# 行首的列表/编号记号 —— 它们是排版, 不是话
_LIST_MARK = re.compile(r"^\s*(?:[-*+•]|\d+[.)])\s+")
_WORD = re.compile(r"\w", re.UNICODE)
# 第一人称标记(仅用于 PERSONAL 报告, 不影响去留)
_FIRST_PERSON = re.compile(r"(?:\bI\b|\bI'|\bme\b|\bmy\b|\bmine\b|\bmyself\b|\bwe\b|\bour\b"
                           r"|我|咱|俺)", re.IGNORECASE)


def _is_link_only(line):
    """整行除了链接与排版记号再无别的字 ⇒ 这行没有作者的话。"""
    rest = _LIST_MARK.sub("", line)
    rest = _MD_LINK.sub(r" \1 ", rest)   # 保锚文本, 只吃掉 URL
    rest = _BARE_URL.sub(" ", rest)
    return not _WORD.search(rest)


def segment(text):
    """按行切段并定性。返回 [{line_no, text, kind, reason}]。"""
    spans, in_fence = [], False
    for i, line in enumerate(text.splitlines()):
        if _FENCE.match(line):
            in_fence = not in_fence
            spans.append({"line_no": i, "text": line,
                          "kind": "NONPERSONAL", "reason": "code_fence"})
            continue
        if in_fence:
            spans.append({"line_no": i, "text": line,
                          "kind": "NONPERSONAL", "reason": "inside_code_fence"})
        elif _QUOTE.match(line):
            spans.append({"line_no": i, "text": line,
                          "kind": "NONPERSONAL", "reason": "blockquote"})
        elif line.strip() and _is_link_only(line):
            spans.append({"line_no": i, "text": line,
                          "kind": "NONPERSONAL", "reason": "link_only_line"})
        else:
            kind = "PERSONAL" if _FIRST_PERSON.search(line) else "AMBIGUOUS"
            spans.append({"line_no": i, "text": line, "kind": kind,
                          "reason": "first_person_marker" if kind == "PERSONAL"
                                    else "not_provably_non_authorial"})
    return spans


def structural_gate(text):
    """样品制备 + 弃权判定。**零 API 调用**。

    subject_text = PERSONAL + AMBIGUOUS − NONPERSONAL(保序拼回, 不重排)。
    去掉 NONPERSONAL 后**一个词都不剩** ⇒ 没有可推断的主体 ⇒ 弃权。
    """
    spans = segment(text)
    kept = [s for s in spans if s["kind"] not in DROPPED_KINDS]
    subject_text = "\n".join(s["text"] for s in kept).strip()
    has_words = bool(_WORD.search(subject_text))
    counts = {k: sum(1 for s in spans if s["kind"] == k) for k in SPAN_KINDS}
    dropped_chars = sum(len(s["text"]) for s in spans if s["kind"] in DROPPED_KINDS)
    return {
        "gate_version": GATE_VERSION,
        "verdict": VERDICT_MEASURE if has_words else VERDICT_ABSTAIN,
        # ★ 弃权时 subject_text 必须为 None 而不是 "" —— 空串会被下游当成
        #   「有文本, 只是短」而照常投料。这一类静默兜底本项目栽过不止一次。
        "subject_text": subject_text if has_words else None,
        "abstain_reason": None if has_words else
            "结构闸: 全文每一段都可证为非作者原话(引用/代码/纯链接), 无可推断主体",
        "span_counts": counts,
        "chars_in": len(text),
        "chars_kept": len(subject_text),
        "chars_dropped": dropped_chars,
        "spans": spans,
        "preparation_id": preparation_id(),
    }


def preparation_id():
    """制备身份。与 instrument_hash 分开: 换制备不换仪器, 但读数同样不可直接比。"""
    payload = f"{GATE_VERSION}|drop={','.join(DROPPED_KINDS)}|rules=fence,blockquote,link_only"
    return "prep_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


RAW_PREPARATION_ID = "prep_raw_unfiltered"   # 本闸接入之前的全部读数都属这一档


def assert_same_preparation(readouts, what="跨读数比较"):
    """★ 与 assert_same_instrument 同形: 制备不同的读数不可直接比较。

    同一把尺子量了不同的样品, 读数差可能全部来自「量的不是同一段文字」。
    """
    ps = {r.get("preparation_id", RAW_PREPARATION_ID) for r in readouts}
    if len(ps) > 1:
        raise RuntimeError(
            f"{what}被拒绝: 涉及 {len(ps)} 种样品制备 {sorted(ps)}。"
            "结构闸摘掉引用/代码/链接之后送进去的文本, 与未过闸的原文**不是同一个样品**; "
            "读数差可能全部来自制备差异, 与仪器无关。")
    return ps.pop()


if __name__ == "__main__":
    import json
    import sys
    src = sys.stdin.read() if len(sys.argv) < 2 else open(sys.argv[1], encoding="utf-8").read()
    r = structural_gate(src)
    r.pop("spans")
    print(json.dumps(r, ensure_ascii=False, indent=2))
    sys.exit(0 if r["verdict"] == VERDICT_MEASURE else 3)
