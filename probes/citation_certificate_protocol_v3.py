# -*- coding: utf-8 -*-
"""引用证书采集协议 v3 —— 只改**采集面**, 验证器(_judge / qualify / P2 v2)一字不动。零调用模块。

试点 v2(2026-09-24, 88 次)判 STOP: MALFORMED 24% > 10%。r2 真实语料两轮里能拆出的 MALFORMED 族: kind 多重命中 5 · span 非逐字 4 · object 缺/非逐字 2(/34 张交卷)。
v3 三处改动(每处对应一族, 都不放松判据):
  ① increment_kind 给**闭合菜单** —— 五个名字由合同文本(DISC 括号内)**机械导出**, 不手写; 并明示「只填一个」。
     (r2 撤菜单是因为附件 A 当时是私人解释; 2026-09-14 升合同后, 菜单就是合同原文, 不是泄露。)
  ② 「逐字」明示为**连续子串·复制粘贴**; 找不到就 supported=false, 不许改写。
  ③ **一次结构化修复重问**: 只回传**错误码**(不含判据、不含正确答案), 要求只修格式不改判断; 每张证书最多 2 次调用。
★ 原因码是本模块的另一半: reason_codes() 纯函数, 只输出码, 不输出文本 —— 产物可存。
"""
import importlib.util, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
_s = importlib.util.spec_from_file_location("_r2_proto", ROOT / "probes/extractor_counterexample_run_r2.py"); r2 = importlib.util.module_from_spec(_s); _s.loader.exec_module(r2)

E_JSON, E_SHAPE, E_SUPPORTS, E_SPAN, E_OBJECT, E_KIND_MENU, E_KIND_MULTI, E_KIND_ON_B = ("E_JSON", "E_EVIDENCE_SHAPE", "E_SUPPORTS_INVALID", "E_SPAN_NOT_VERBATIM", "E_OBJECT_NOT_VERBATIM", "E_KIND_NOT_IN_MENU", "E_KIND_MULTI", "E_KIND_ON_B")
CODES = (E_JSON, E_SHAPE, E_SUPPORTS, E_SPAN, E_OBJECT, E_KIND_MENU, E_KIND_MULTI, E_KIND_ON_B)


def kind_menu(disc=None):
    """五类名字从判别式括号里机械导出: 「(具体型号/数据/使用细节/纠错/结构化经验)」→ 列表。"""
    m = re.search(r"[（(]([^）)]*)[）)]", disc or r2.DISC); return [x.strip() for x in m.group(1).split("/") if x.strip()]


def prompt_v3(text):
    menu = kind_menu(); menu_txt = " / ".join("「%s」" % k for k in menu)
    p = r2.PROMPT % (r2.DISC, text)
    old_kind = '"increment_kind": "仅当 supports 为 A 时填:这段增量属于上面判别式所列的哪一种,照判别式里的措辞原样写,**只写其中一种**,不要连写多种;supports 为 B 时填 null"'
    assert old_kind in p, "★ r2 提示词的 kind 行变了 —— v3 的替换点失效"
    new_kind = '"increment_kind": "仅当 supports 为 A 时填, **只能是下面五个之一, 原样抄一个, 只填一个, 不要用斜杠连写**: %s ;supports 为 B 时填 null"' % menu_txt
    p = p.replace(old_kind, new_kind, 1)
    tail = "所有 span 与 object 都必须**逐字**出自上面的文本。不要改写、不要合并不相邻的词。"
    assert tail in p
    p = p.replace(tail, tail + "\n「逐字」的意思是: **从上面的文本里复制粘贴出的一段连续文字**(大小写、标点、空格都一样)。如果你找不到能原样复制的片段, 就把 supported 填 false, 不要改写成近似的话。", 1)
    return p


def repair_prompt(prev_json_text, codes):
    """修复重问: 只给错误码与格式规则, **不给判据、不给对错**; 要求只修格式不改判断。"""
    rules = {E_JSON: "输出不是合法 JSON 对象", E_SHAPE: "evidence 不是对象数组或为空", E_SUPPORTS: "某条 evidence 的 supports 不是 \"A\" 或 \"B\"",
             E_SPAN: "某条 evidence 的 span 不是文本里可复制粘贴的连续原文", E_OBJECT: "某条 evidence 的 object 不是文本里可复制粘贴的连续原文",
             E_KIND_MENU: "某条 evidence 的 increment_kind 不是给定五个之一", E_KIND_MULTI: "某条 evidence 的 increment_kind 连写了多个, 只能填一个", E_KIND_ON_B: "supports 为 B 的 evidence 填了 increment_kind, 应为 null"}
    lst = "\n".join("- %s: %s" % (c, rules[c]) for c in codes if c in rules)
    return ("你上一份回答有**格式**问题(只是格式, 不涉及判断对错):\n%s\n\n请**只修正格式**, 不要改变你对 supported 的判断, 也不要新增或删除证据条目(除非某条无法逐字给出, 那就删掉它)。"
            "重新输出**完整**的 JSON, 与之前相同的结构。\n\n你上一份回答:\n%s" % (lst, prev_json_text))


def reason_codes(obj, text, menu=None):
    """把一张证书(已解析 JSON 或 None)分类成错误码集合 —— 与 _judge 的 MALFORMED 分支同源, 但**只回码不回文本**。空集合 ⇒ 格式合规(语义另说)。"""
    menu = set(menu or kind_menu()); codes = []
    if not isinstance(obj, dict): return [E_JSON]
    if not obj.get("supported"): return []            # 拒答不是格式问题
    ev = obj.get("evidence")
    if not isinstance(ev, list) or not ev or not all(isinstance(e, dict) for e in ev): return [E_SHAPE]
    for e in ev:
        sup = str(e.get("supports", "")).strip().upper()
        if sup not in ("A", "B"): codes.append(E_SUPPORTS)
        span = e.get("span"); obj_ = e.get("object")
        if not isinstance(span, str) or not span.strip() or span not in text: codes.append(E_SPAN)
        if not isinstance(obj_, str) or not obj_.strip() or obj_.strip() not in text: codes.append(E_OBJECT)
        k = e.get("increment_kind")
        if sup == "A":
            kc = r2._clean_kind(k)
            if kc is None: codes.append(E_KIND_MENU)
            elif "/" in kc or "、" in kc: codes.append(E_KIND_MULTI)
            elif kc not in menu: codes.append(E_KIND_MENU)
        elif sup == "B" and k not in (None, "", "null"): codes.append(E_KIND_ON_B)
    return sorted(set(codes))
