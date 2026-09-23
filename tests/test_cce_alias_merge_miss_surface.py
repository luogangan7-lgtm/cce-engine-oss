#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闸: 「不做别名归并」的代价必须被量过, 且**量出来的数不许被越界引用**。

★★★ 本闸真正要挡的不是「有没有量」, 而是**量完之后的那句结论**:
字面别名面在本语料上只有 1 个裸名受影响 —— 这个数**很好看**,
而它紧邻的事实是: **指代**(it / them / the ones)出现在 5/12 个文本里,
而 P2 的字符串判据对指代**结构上无能为力**。
⇒ 「字面面小」**推不出**「漏判少」。把第一层的数单独拿出去引用, 就是拿一个好看的下界
   冒充没测过的那个量 —— 这正是本仓反复记过的形状。
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "probes"))
import alias_merge_miss_surface as S  # noqa: E402

R = S.build()
L1 = R["★第一层·字面别名(本探针能算)"]
L2 = R["★★★第二层·指代(本探针**算不了**)"]


def test_both_layers_are_reported():
    """★★★ 两层都得在。只报能算的那层, 是把下界当结论。"""
    assert L1["受影响裸名数"] >= 0 and isinstance(L1["同一裸名多种写法"], dict)
    assert L2["含指代词的文本"], "★★★ 第二层空了 —— 那层不是「没有」, 是**算不了**, 不许因为算不了就不报"
    assert "/" in L2["文本数"]


def test_the_second_layer_says_it_is_not_a_miss_rate():
    """★★★ 第二层那个数**不是漏判率** —— 这句限定不许被删。"""
    assert "不是漏判数" in json.dumps(L2, ensure_ascii=False)
    assert "不许把它当漏判率引用" in json.dumps(L2, ensure_ascii=False)


def test_the_conclusion_refuses_the_tempting_inference():
    """★★★ 结论里必须明写「字面面小 ⇏ 漏判少」—— 那是本闸存在的理由。"""
    blob = json.dumps(R["★★★结论怎么写才不越界"], ensure_ascii=False)
    assert "推不出" in blob, "★★★ 那句「字面面小推不出漏判少」被删了"
    assert "真实漏判率**仍未测**" in blob, "★ 必须承认真实漏判率仍未测"
    assert "不得外推" in blob, "★ 12 条孤立构造题的数不许外推到自然语料"


def test_the_measurement_is_recomputed_not_stored():
    """★ 现算: 语料一变数就得跟着变, 不许是写死的。"""
    n_texts = R["语料"]["文本数"]
    A = json.loads((ROOT / "tests/data/local_contract_assertions_v2.json").read_text(encoding="utf-8"))
    live = len({a["用例"] for a in A["断言"]})
    assert n_texts == live, "★ 探针报 %d 个文本, 断言表现算 %d 个" % (n_texts, live)
    # ★ 第一层的每一组词面都必须真的出现在语料里(不是我编的)
    texts = " ".join(a["文本"] for a in A["断言"])
    for bare, forms in L1["同一裸名多种写法"].items():
        for f in forms:
            assert f in texts, "★★★ 报了一个语料里没有的词面 %r —— 探针在编" % f
    return n_texts, L1["受影响裸名数"], L2["文本数"]


def test_the_pronoun_list_is_not_silently_narrowed():
    """★★ 指代词表缩窄 = 第二层的数变小 = 结论变好看。钉住它不许悄悄缩。"""
    import re
    src = (ROOT / "probes/alias_merge_miss_surface.py").read_text(encoding="utf-8")
    m = re.search(r'_PRONOUN = r"([^"]+)"', src)
    assert m, "★ 找不到指代词表"
    for w in ("it", "them", "they", "the ones"):
        assert w in m.group(1), (
            "★★★ 指代词表里少了 %r —— 缩窄词表会让第二层的数变小, 结论跟着变好看" % w)


if __name__ == "__main__":
    test_both_layers_are_reported()
    test_the_second_layer_says_it_is_not_a_miss_rate()
    test_the_conclusion_refuses_the_tempting_inference()
    n, n1, n2 = test_the_measurement_is_recomputed_not_stored()
    test_the_pronoun_list_is_not_silently_narrowed()
    print("test_cce_alias_merge_miss_surface: OK ("
          f"★★量了 P2「**不做别名归并**」这条 fail-closed 选择的代价 —— 先前只写了选择, **没量过代价** | "
          f"★第一层(字面别名, 能算): {n} 个文本里只有 **{n1} 个裸名**有多种写法(Phonak / the Phonak) —— "
          "这个数**很好看** | "
          f"★★★第二层(指代, **算不了**): it / them / the ones 出现在 **{n2}** 个文本里, "
          "而 P2 的字符串判据对指代**结构上无能为力** ⇒ **「字面面小」推不出「漏判少」** —— "
          "把第一层单独拿出去引用, 就是拿一个好看的下界冒充没测过的那个量 | "
          "★★真实漏判率**仍未测**且本探针给不出(要逐条判断指代对象: 靠人, 或靠模型——后者回到 gen9 测出有偏的那一面) | "
          "★ 12 条**孤立构造题**不是自然语料 ⇒ 两个数都**不得外推**; 指代词表被钉住不许悄悄缩窄(缩了结论就变好看))")
