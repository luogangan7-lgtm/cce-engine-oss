"""★★★ 花钱之前必须先检查「这条判据裁得动吗」。零 API。

## 为什么
2026-09-09 花 **220 次**跑完一个候选实验, 才发现否决判据 R3 是多组零容差规则,
在一次实际的纯噪声对照里**确实会 FAIL** ⇒ 钱花了, 结论是「未建立」。

★★★ 而用 scripts/cce_criterion_preflight.py 拿**本轮实际用过的四条判据**跑一遍,
**四条全部被拦下**, 且这是**零调用、发起前就能做的**:
· R3 的两个小组: 阈值「不得变坏」在 n=10 上**离散后是零容差**(必须恰好 0/10)
· R1(n=2) / R2(n=4) 的题级符号检验: 最好单侧 p = 0.25 / 0.0625 > α=0.05 ⇒ **不可达**

⇒ **那 220 次本可以省下, 或至少换一个设计。**

## 网页版 GPT-6 Pro 的裁定(本仓采纳)
「真正需要打破的…是**『先写一个看似严格的二值规则, 花钱后才发现它裁不了, 再靠下一轮修规则』的循环**。
 **预注册必须约束分析自由度, 但它不能替代对判据本身的验证。**」

## 本闸钉两件
① 工具本身有效: 用本轮那四条判据现算, 必须仍然全部判红(否则工具失效了)
② **凡声明了调用预算的预注册, 必须带判据准入结果** —— 没带就红
"""
import glob
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from cce_criterion_preflight import (check, best_one_sided_p, integer_band,  # noqa: E402
                                    zero_baseline_downgrade)

# ★ 本轮**实际用过**的四条判据 —— 它们必须仍被拦下
THIS_ROUND = {"alpha": 0.05, "criteria": [
    {"name": "R3·仅收藏(10单元) 不得变坏", "n": 10, "thr": 0.0, "direction": "<=", "kind": "rate"},
    {"name": "R3·纯向往(10单元) 不得变坏", "n": 10, "thr": 0.0, "direction": "<=", "kind": "rate"},
    {"name": "R2·真悬置(4题) 符号检验", "n": 4, "kind": "significance"},
    {"name": "R1·仅收藏(2题) 符号检验", "n": 2, "kind": "significance"},
]}
# ★ 声明了调用预算却必须带准入结果的预注册(按文件名登记, 新增预注册须自行加入或带结果)
BUDGETED = ["gate_decision_tree_candidate_prereg", "production_retest_reliability_prereg",
            "gate_protocol_v2_acceptance_prereg", "production_suspend_defect_prereg",
            "gate_vs_production_fieldset_prereg", "suspend_fix_confirmation_prereg"]


def test_the_tool_still_catches_this_rounds_criteria():
    """★★★ 灵敏度自证: 拿**本轮实际用过**的四条判据现算, 必须**全部**被拦下。"""
    ok, errs, info = check(THIS_ROUND)
    assert not ok, "★★★ 工具不再拦下本轮那四条判据 —— **它失效了**"
    assert len(errs) == 4, f"★★ 应拦下 4 条, 实际 {len(errs)}: {errs}"
    assert any("零容差" in e for e in errs), "★ 零容差检查失灵"
    assert any("不可达" in e for e in errs), "★ 可达性检查失灵"


def test_the_discrete_translation_is_right():
    """★ 「文字看起来有余量、离散后却零容差」必须被算出来。"""
    assert integer_band(10, 0.0, "<=")["★零容差"] is True
    assert integer_band(10, 0.2, "<=")["允许的整数计数"] == [0, 1, 2]
    assert integer_band(8, 0.95, ">=")["★实际等价于"] == "必须恰好 8/8", \
        "★★ n=8 · >=0.95 必须被翻译成「8/8 全同」—— 那正是 playbook 那轮栽的形状"


def test_the_best_p_bound_is_right():
    """★ m 个独立同向观测的最好单侧 p = 2^-m。两题 0.25, 四题 0.0625。"""
    assert best_one_sided_p(2) == 0.25
    assert best_one_sided_p(4) == 0.0625
    assert best_one_sided_p(5) == 0.03125          # 五题才够 α=0.05
    assert best_one_sided_p(4) > 0.05 >= best_one_sided_p(5)


def test_every_budgeted_prereg_carries_a_preflight():
    """★★★ 凡声明调用预算的预注册, 必须带判据准入结果 —— 没带就红。

    ★ 这是把「已确认且反复适用的规则」从**检索**挪进**执行**:
      GPT 明说不必每次把全部记忆库塞进上下文, 应有**固定规则注册表**负责执行已知规则。
    """
    missing = []
    for name in BUDGETED:
        p = ROOT / "tests" / "data" / f"{name}.json"
        if not p.exists():
            missing.append(f"{name}(文件不存在)")
            continue
        d = json.dumps(json.loads(p.read_text(encoding="utf-8")), ensure_ascii=False)
        if "criterion_preflight" not in d and "判据准入" not in d:
            missing.append(name)
    assert not missing, (
        f"★★★ 这些预注册声明了调用预算却**没有判据准入结果**: {missing}\n"
        "⇒ 在花钱之前跑 `python3 scripts/cce_criterion_preflight.py <spec.json>`, "
        "把结果写进预注册。**没有它就不许发起。**\n"
        "★ 2026-09-09 的教训: 220 次跑完才发现否决判据是零容差且符号检验不可达。")


def _reverse_checks():
    n = 0
    # ① 一条真正可达的判据不该被拦
    ok, errs, _ = check({"alpha": 0.05, "criteria": [
        {"name": "宽松率", "n": 20, "thr": 0.2, "direction": "<=", "kind": "rate"},
        {"name": "n=6 符号检验", "n": 6, "kind": "significance"}]})
    assert ok, f"★★ 工具把可达的判据也拦了(假阳性): {errs}"
    n += 1
    # ② 零容差必被拦
    ok2, e2, _ = check({"alpha": 0.05, "criteria": [
        {"name": "零容差", "n": 30, "thr": 0.0, "direction": "<=", "kind": "rate"}]})
    assert not ok2 and "零容差" in e2[0]
    n += 1
    # ③ 不可达必被拦
    ok3, e3, _ = check({"alpha": 0.05, "criteria": [{"name": "n=3", "n": 3, "kind": "significance"}]})
    assert not ok3 and "不可达" in e3[0]
    n += 1
    return n


# ───────── 第三道: 零基线降级必备(2026-09-15 加, r4 实测逼出来的) ─────────

_ARMS = ["金标(上界)", "零基线(完全不读文本的常数填充)", "模型"]
_D5 = "D5: 模型阴性放行与零基线相同 ⇒ 没有证据说明模型在读文本"
_D6 = "D6: 某敏感槽位准确率 ≤ 零基线 ⇒ 该槽位**零增益**, 它的数**不得读成能力**"


def test_声明零基线臂却没有逐槽位零增益降级_必须拦():
    """★★★ r4 实测: 端到端降级(D5)响应了, 而 predicate 18/20 == 零基线 18/20(零增益)、
    possession 14/20 < 零基线 16/20(负增益) —— **四条降级一条没响**, 那两格照样被当成能力读出去。"""
    spec = {"alpha": 0.05, "criteria": [], "arms": _ARMS, "downgrades": [_D5]}
    ok, errs, _ = check(spec)
    assert not ok, "★★★ 只有端到端降级就放行 ⇒ 逐槽位零增益又会溜过去"
    assert any("零增益" in e for e in errs)


def test_补上那条降级就放行():
    spec = {"alpha": 0.05, "criteria": [], "arms": _ARMS, "downgrades": [_D5, _D6]}
    assert check(spec)[0]


def test_没有零基线臂的预注册不被这条误伤():
    """★ 新规则不许把历史上不含零基线臂的预注册一起判红 —— 那是事后追加要求。"""
    assert check({"alpha": 0.05, "criteria": []})[0]
    assert zero_baseline_downgrade({"criteria": []}) == []


def test_这条规则不回溯已付费的那一轮():
    """★★★ 制度从下一轮起生效。**测量后改判据 = 调结果** —— r4 的读数不因此重算。"""
    src = (ROOT / "scripts/cce_criterion_preflight.py").read_text(encoding="utf-8")
    assert "不回溯 r4 的读数" in src and "调结果" in src, (
        "★★★ 必须在源码里写明这条不回溯 r4 —— 否则下一个人会拿它去重算已付费的读数")

# ── 2026-09-15 补: 第三道立起来的当天是**空转**的(280-agent 评审抓到) ──────────
# 原实现只认 arms/downgrades 两个**英文键**, 而本仓真实预注册全用中文键 ⇒ 机器检查一次都没生效过。

_CN_NEW = {"date": "2026-09-16", "★★★四臂必须一起报": ["金标", "零基线(常数填充)", "模型"],
           "★★★降级条件": ["D5: 阴性放行与零基线相同 ⇒ 没有证据说明它在读文本"]}


def test_中文键的新预注册也必须被第三道拦住_原实现在这里是空转的():
    assert zero_baseline_downgrade(_CN_NEW), (
        "★★★ 中文键 + 2026-09-15 之后 + 提到零基线 + 只有端到端降级 ⇒ 必须拦。"
        "不拦意味着这条制度**只在英文键的合成 spec 上生效**, 对真实预注册是空转。")
    ok = dict(_CN_NEW)
    ok["★★★降级条件"] = _CN_NEW["★★★降级条件"] + ["D6: 某敏感槽位准确率 ≤ 零基线 ⇒ 该槽位零增益, 不得读成能力"]
    assert not zero_baseline_downgrade(ok), "★ 补上零增益条款后应放行"


def test_日期门必须真的挡住历史件_不回溯是写死的规则():
    old = dict(_CN_NEW, date="2026-09-14")
    assert not zero_baseline_downgrade(old), "★★★ 2026-09-15 之前的预注册被拦 ⇒ 回溯了已付费的那些轮"
    nodate = {k: v for k, v in _CN_NEW.items() if k != "date"}
    assert not zero_baseline_downgrade(nodate), "★ 无 date 的历史件不该被拦"
    for f in ("slot_filling_prereg_r4.json", "extractor_counterexample_prereg_r2.json",
              "repeat_measure_prereg_r3.json"):
        d = json.loads((ROOT / "tests/data" / f).read_text(encoding="utf-8"))
        assert not zero_baseline_downgrade(d), "★★★ 历史预注册 %s 被新规则误伤" % f


def test_新预注册必须带date_否则日期门可以靠不写date绕过():
    """★★★ 日期门的 fail-open 是**故意的**(不回溯), 但它开了一条绕过路径: 不写 date。
    ⇒ 这里把它堵上: 2026-09-15 之后新增的预注册必须带 date。"""
    src = (ROOT / "scripts/cce_criterion_preflight.py").read_text(encoding="utf-8")
    assert "这个 fail-open 是故意的" in src, (
        "★★★ 源码必须写明那个 fail-open 是故意的, 否则下一个人会把它当 bug「修」成 fail-closed, "
        "从而回溯掉所有历史预注册")
    import glob
    bad = []
    for f in sorted(glob.glob(str(ROOT / "tests/data/*prereg*.json"))):
        d = json.loads(pathlib.Path(f).read_text(encoding="utf-8"))
        body = json.dumps(d, ensure_ascii=False)
        # 只查**本轮之后新建**的: 以带 date 或明确标注 2026-09-15 之后为准
        if "2026-09-15" in body or "2026-09-16" in body:
            if not d.get("date"):
                bad.append(pathlib.Path(f).name)
    assert not bad, "★★★ 这些新预注册没带 date, 等于绕过日期门: %r" % bad


if __name__ == "__main__":
    test_the_tool_still_catches_this_rounds_criteria()
    test_the_discrete_translation_is_right()
    test_the_best_p_bound_is_right()
    test_every_budgeted_prereg_carries_a_preflight()
    n = _reverse_checks()
    print(f"test_cce_criterion_preflight: OK ("
          f"★★★工具拿**本轮实际用过的四条判据**现算, **四条全被拦下**(2 条零容差 + 2 条 α=0.05 下不可达) "
          f"—— 而这是**零调用、发起前就能做的**, 那 220 次本可省下 | "
          f"离散翻译正确(n=8·>=0.95 ⇒ **必须 8/8**, 正是 playbook 那轮的形状) | "
          f"最好单侧 p = 2^-m(两题 0.25 · 四题 0.0625 · **五题才够 0.05**) | "
          f"★★声明调用预算的预注册**必须带准入结果**(把已知规则从检索挪进执行) | "
          f"{n} 条反向验证(含**假阳性**检查: 可达的判据不许被拦))")
