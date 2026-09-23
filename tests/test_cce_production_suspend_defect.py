"""★★★ 生产分类器上**没有**那个 suspend 缺陷 —— 而且它比验收闸判得**更准**。零 API。

## 结果(本闸从原始读数现算)
· 阳性对照**先行**: 真悬置 生产 **4/4** 判 suspend ⇒ 主结论可解释
  (若 <2/4 则整轮 NOT_INTERPRETABLE —— 低命中率会被误读成「没缺陷」, 真相可能是「从不说 suspend」)
· 主判据: 失败方向 **1/8** ≤ 1 ⇒ **NO_DEFECT**
· 负例组总错: **生产 3/16 · 闸 V0 6/16**

## ★★★ 比判决本身更要紧的那一条
arm B 实测**生产字段集的一致性更差**(JS 0.3008 vs 0.2163); 本轮实测**生产判得更准**。
⇒ **更一致的那台, 反而更容易在这条边界上判错。**
这是「**信度 ≠ 效度**」的实测例证, 而且方向是反的。

## ★ 我赌错了
发起前赌 HAS_DEFECT(信心中), 理由是缺陷载体都进生产 prompt。**实测反过来。**
本闸钉住这条记录 —— 赌注的用处就在赌错的时候。
"""
import json
import pathlib
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
V = pathlib.Path("/Volumes/data/cce-identified-vault/cce_runs")
RAW = V / "production_suspend_defect" / "raw.json"
GATE = V / "suspend_fix_confirm" / "raw.json"
PRE = ROOT / "tests" / "data" / "production_suspend_defect_prereg.json"
RES = ROOT / "tests" / "data" / "production_suspend_defect_result.json"
FAIL = ["已决定_延后执行", "历史悬置_现已决定"]
TRUE = ["★真悬置_必须仍判"]


def _have():
    return RAW.exists() and GATE.exists()


def _res():
    return json.loads(RES.read_text(encoding="utf-8"))


def _pre():
    return json.loads(PRE.read_text(encoding="utf-8"))


def _rows():
    return json.loads(RAW.read_text(encoding="utf-8"))


def test_positive_control_comes_first_and_passed():
    """★★★ 阳性对照**先行**: 生产必须真的会产 suspend, 否则主结论无法解释。"""
    if not _have():
        pc = _res()["★★★阳性对照(先行)"]
        assert "PASS" in pc["verdict"], "★ 产物里的阳性对照不再通过"
        print("  ★ 降级: 无本机素材, 只核对产物")
        return
    s = [r for r in _rows() if r["cell"] in TRUE]
    k = sum(1 for r in s if r["top1"] == "suspend")
    assert k >= 2, (
        f"★★★ 生产在**该判 suspend 的题上**只判了 {k}/{len(s)} —— "
        "主结论**不可解释**: 低命中率无法区分「没缺陷」与「从不说 suspend」。整轮应扣发。")
    assert k == 4, f"★ 阳性对照从 4/4 变成 {k}/4, 请复核结论"


def test_no_defect_verdict_is_recomputed():
    """★ 主判据现算: 失败方向 ≤1/8 ⇒ NO_DEFECT。"""
    if not _have():
        assert "NO_DEFECT" in _res()["★★★verdict"]
        print("  ★ 降级: 无本机素材, 只核对产物判决")
        return
    s = [r for r in _rows() if r["cell"] in FAIL]
    k = sum(1 for r in s if r["top1"] == "suspend")
    assert len(s) == 8, f"★ 失败方向应有 8 题, 现在 {len(s)}"
    assert k <= 1, (
        f"★★ 生产在失败方向上判了 {k}/8 suspend —— 不再是 NO_DEFECT。"
        "若 >=3 则 route 6 **不够**, 必须另立生产修复候选。请重跑判决并复核两个决定。")


def test_production_beats_the_gate_on_negative_groups():
    """★★★ 核心发现: **生产比闸更准** —— 而 arm B 说生产字段集**更不一致**。"""
    if not _have():
        d = json.dumps(_res(), ensure_ascii=False)
        assert "生产 3/16" in d and "闸 V0 6/16" in d
        print("  ★ 降级: 无本机素材, 只核对产物里的对照数")
        return
    prod = {r["id"]: r for r in _rows()}
    gate = defaultdict(list)
    for x in json.loads(GATE.read_text(encoding="utf-8")):
        if x["arm"] == "V0" and not x["model"].startswith("glm") and x["top1"]:
            gate[x["id"]].append(x["top1"] == "suspend")
    neg = [r for r in prod.values() if r.get("should_be_suspend") is False]
    p_err = sum(1 for r in neg if r["top1"] == "suspend")
    g_err = sum(1 for r in neg if gate.get(r["id"]) and
                sum(gate[r["id"]]) / len(gate[r["id"]]) > .5)
    assert len(neg) == 16, f"★ 负例组应有 16 题, 现在 {len(neg)}"
    assert p_err < g_err, (
        f"★★★ 生产不再比闸更准(生产 {p_err}/16 vs 闸 {g_err}/16) —— "
        "「更一致的那台反而更容易判错」这条结论需要重写")
    assert (p_err, g_err) == (3, 6), f"★ 数变了: 生产 {p_err}/16 · 闸 {g_err}/16, 请复核结论"


def test_the_reliability_vs_validity_reading_is_recorded():
    """★★ 「信度 ≠ 效度」这条读法必须留档, 且必须标明机理只是**猜测**。"""
    d = json.dumps(_res(), ensure_ascii=False)
    assert "更一致的那台, 反而更容易在这条边界上判错" in d, "★ 核心结论句不见了"
    assert "信度 ≠ 效度" in d.replace(" ", "").replace("**", "") or "信度" in d and "效度" in d
    assert "机理猜测(**未验**)" in d, (
        "★★ 机理必须标为**未验猜测** —— 本轮没做拆解实验证明是哪一块材料造成的")


def test_my_bet_was_wrong_and_it_is_recorded():
    """★ 赌注的用处就在赌错的时候。这条记录不许被抹。"""
    b = _res()["★my_bet"]
    assert b["★结果"] == "**赌错**", "★ 赌注结果被改了"
    assert b["信心"] == "中", "★ 预先声明的信心水平被改了"
    d = json.dumps(_res(), ensure_ascii=False)
    assert "我赌错了" in d and "实测反过来" in d, "★ 「我赌错了」的记录不见了"


def test_the_scope_and_caps_were_frozen_before_running():
    """★ 成本上限、重试规则、阳性对照**都在发起前冻结** —— 上一轮吃过「重试规则事后定」的亏。"""
    p = _pre()
    assert p["design"]["cap_calls"] == 176
    r = p["design"]["★★retry_rule_frozen_now"]
    assert "这次先写死" in r and "与答案内容无关" in r, "★ 重试规则的事前性声明不见了"
    assert "撞上限即停" in r
    assert "NOT_INTERPRETABLE" in json.dumps(p["★★★positive_control_gate_this_comes_first"],
                                             ensure_ascii=False)
    d = json.dumps(p, ensure_ascii=False).replace("**", "")
    assert "整链 11 段里的两段" in d and "不得说「跑了完整 CCE 链路」" in d, \
        "★★ 「只跑了两段, 不是完整链路」的口径声明不许删(2026-08-11 铁律)"


def _reverse_checks():
    n, g = 0, globals()
    saved = g["_rows"]
    rows = _rows()

    # ① 阳性对照垮掉 ⇒ 红
    bad = [dict(r) for r in rows]
    for r in bad:
        if r["cell"] in TRUE:
            r["top1"] = "itch"
    g["_rows"] = lambda: bad
    try:
        test_positive_control_comes_first_and_passed()
        raise SystemExit("★ 反向验证失败: 阳性对照垮掉后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_rows"] = saved

    # ② 生产也开始把失败方向判成 suspend ⇒ 红
    bad2 = [dict(r) for r in rows]
    for r in bad2:
        if r["cell"] in FAIL:
            r["top1"] = "suspend"
    g["_rows"] = lambda: bad2
    try:
        test_no_defect_verdict_is_recomputed()
        raise SystemExit("★ 反向验证失败: 生产全判 suspend 后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_rows"] = saved

    # ③ 降级分支实跑
    saved_h = g["_have"]
    g["_have"] = lambda: False
    try:
        test_positive_control_comes_first_and_passed()
        test_no_defect_verdict_is_recomputed()
        test_production_beats_the_gate_on_negative_groups()
    finally:
        g["_have"] = saved_h
    return n + 3


if __name__ == "__main__":
    test_positive_control_comes_first_and_passed()
    test_no_defect_verdict_is_recomputed()
    test_production_beats_the_gate_on_negative_groups()
    test_the_reliability_vs_validity_reading_is_recorded()
    test_my_bet_was_wrong_and_it_is_recorded()
    test_the_scope_and_caps_were_frozen_before_running()
    n = _reverse_checks()
    print(f"test_cce_production_suspend_defect: OK ("
          f"★★★阳性对照**先行**且过(真悬置 4/4) | 失败方向 1/8 ⇒ **NO_DEFECT** ⇒ route 6 够 | "
          f"★★★负例组总错 **生产 3/16 vs 闸 6/16 —— 生产更准**, 而 arm B 说生产字段集**更不一致** "
          f"⇒ **更一致的那台反而更容易判错**(信度≠效度的实测例证; 机理标为**未验猜测**) | "
          f"★我赌错了(赌 HAS_DEFECT, 信心中)且记录未抹 | "
          f"上限/重试规则/阳性对照**均发起前冻结** · 「只跑两段不是完整链路」口径在 | "
          f"{n} 条反向验证/降级实跑)")
