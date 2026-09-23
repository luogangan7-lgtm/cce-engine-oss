"""★ 闸 prompt 的版本标签**陈旧且不许被顺手改掉**。零 API。

## 事实
· 闸的 DIST_TMPL 第一行硬编「九结分类学(**v1.1.1**)」
· config/knot_taxonomy.json 的 version 是 **1.3.1**
· 而决策树与负例**是从 config 现组装的**(2026-08-09 起) ⇒ 1.3.1 的内容**已经进了** prompt
⇒ **标签在否认已经发生的同步**。生产 s2 相反, 它注入 `taxo['version']`, 标签是活的。

## ★★ 本闸的立场: 登记, 不修
闸的 prompt 就是那台仪器。改一个字就换刺激, 历史读数不可比 ——
taxonomy 的 `_order_note` 已立同一条规矩(「非经重新验收不得变更」)。
⇒ 本闸**双向**钉住: 标签被改 ⇒ 红(必须走验收流程); config 版本变了 ⇒ 也红(提醒重新评估这条陈旧)。
"""
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
os.environ.setdefault("MINIMAX_API_KEY", "ZERO_API_TEST_SENTINEL_NOT_A_KEY")
sys.path.insert(0, str(ROOT / "accuracy"))
sys.path.insert(0, str(ROOT / "scripts"))
DOC = ROOT / "tests" / "data" / "gate_prompt_version_label.json"
LABEL = "九结分类学(v1.1.1)"


def _gate_tmpl():
    import run_gates as RG
    return RG.DIST_TMPL


def _taxo_version():
    return json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))["version"]


def test_the_label_is_frozen_and_still_stale():
    """★★ 双向: 标签不许被顺手改; config 版本变了也要红。"""
    assert LABEL in _gate_tmpl(), (
        f"★★★ 闸 prompt 的版本标签变了(原为「{LABEL}」)。"
        "**改 prompt = 换仪器** —— 若是有意改动, 必须先冻结预注册再重跑完整验收闸, "
        "并声明与旧读数可比不可合。若只是顺手改整齐, 请撤回。")
    v = _taxo_version()
    assert v == "1.3.1", (
        f"★ config 版本变成 {v} 了 —— 请重新评估「标签停在 1.1.1」这条登记是否还这么说。")


def test_the_content_really_is_synced_so_the_label_really_does_lie():
    """★ 「标签在否认已发生的同步」这句必须**现算成立**, 不能只是我写得好听。"""
    import run_gates as RG
    taxo = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
    dt = taxo["annotation_protocol"]["decision_tree_prompt"][0]
    ne = [k.get("negative_examples_prompt") for k in taxo["knots"] if k.get("negative_examples_prompt")][0]
    assert dt[:20] in RG.DECISION_TREE, "★ 决策树不再是从 config 组装的 ⇒ 本登记的前提没了"
    assert ne[:20] in RG.NEGATIVE_EXAMPLES, "★ 负例不再是从 config 组装的 ⇒ 本登记的前提没了"
    assert taxo["annotation_protocol"]["version"] == taxo["version"], \
        "★ protocol 版本与分类学版本脱钩了 —— 那是另一个问题, 要单独查"


def test_production_by_contrast_injects_the_live_version():
    """★ 对照组: 生产 s2 注入 `taxo['version']` ⇒ 它的标签是活的。差异是真的, 不是我编的。"""
    import cce_knot_classify as CK
    taxo = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
    prod = CK._build_stage2_prompt(taxo, "<T>", {"tops": "<S>", "appraisal": "<A>"})
    assert f"v{taxo['version']}" in prod, "★ 生产 prompt 不再注入活版本号 ⇒ 两侧不再有这个差异"
    assert "v1.1.1" not in prod, "★ 生产 prompt 里出现了 v1.1.1 —— 与本登记矛盾, 先查哪个错了"


def test_the_doc_says_do_not_fix_it():
    """★★ 「不修」这个决定必须留在文档里 —— 否则下一个人会顺手改整齐, 悄悄换掉仪器。"""
    d = json.dumps(json.loads(DOC.read_text(encoding="utf-8")), ensure_ascii=False)
    assert "不改" in d and "非经重新验收不得变更" in d, "★ 「不修」的理由不见了"
    assert "标签在否认已经发生的同步" in d, "★ 这条判断的核心句不许删"


def _reverse_checks():
    n, g = 0, globals()
    saved = g["_gate_tmpl"]
    g["_gate_tmpl"] = lambda: saved().replace(LABEL, "九结分类学(v1.3.1)")
    try:
        test_the_label_is_frozen_and_still_stale()
        raise SystemExit("★ 反向验证失败: 标签被改成 1.3.1 后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_gate_tmpl"] = saved

    saved_v = g["_taxo_version"]
    g["_taxo_version"] = lambda: "1.4.0"
    try:
        test_the_label_is_frozen_and_still_stale()
        raise SystemExit("★ 反向验证失败: config 升版后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_taxo_version"] = saved_v
    return n


if __name__ == "__main__":
    test_the_label_is_frozen_and_still_stale()
    test_the_content_really_is_synced_so_the_label_really_does_lie()
    test_production_by_contrast_injects_the_live_version()
    test_the_doc_says_do_not_fix_it()
    n = _reverse_checks()
    print(f"test_cce_gate_prompt_version_label: OK ("
          f"闸 prompt 自称「{LABEL}」而 config 是 v{_taxo_version()} | "
          f"★ 而决策树/负例**确实**是从 config 现组装的 ⇒ **标签在否认已发生的同步** | "
          f"生产 s2 对照: 注入活版本号 | ★★ 判定为**登记不修**(改 prompt=换仪器), 理由已钉 | "
          f"{n} 条反向验证判红(改标签 / config 升版 双向))")
