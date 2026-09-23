#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闸: web GPT 第九轮的裁定是否真的落到了留档上, 而不是只被我读了一遍。

★★★ 这个闸本身受制于第九轮自己给的限制:
  「如果同一个 agent 仍然同时拥有任意 shell、真实密钥、原仓写权限, 以及**修改这些闸的权限**,
    那么一个包装脚本并不构成不可绕过的机制 —— 那仍然是**加强版约定**。」
  ⇒ 本闸能挡住「我忘了改」, **挡不住「我决定改掉它」**。这一点必须写在这里, 不许假装它是硬闸。
"""
import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
R = json.loads((ROOT / "tests/data/webgpt_ruling_round9_2026-09-10.json").read_text(encoding="utf-8"))
G8 = json.loads((ROOT / "tests/data/gen8_shipping_result.json").read_text(encoding="utf-8"))
D2 = json.loads((ROOT / "tests/data/DEV-002-destructive-checkout.json").read_text(encoding="utf-8"))
AC = json.loads((ROOT / "tests/data/accuracy_testability_blocked.json").read_text(encoding="utf-8"))
MEMO = (ROOT / "OWNER_DECISION_log_2026-09-09_to_11.md").read_text(encoding="utf-8")


def test_the_common_shape_was_replaced_not_kept():
    """★★★ 我原来的说法「都是没把知识变成闸」被判会**掩盖事实**, 必须换掉。"""
    f = R["★★★★它换掉了我的整个框架"]
    assert "没有形成足以阻断目标违规的控制链" in f["★★★GPT 改的"]
    assert "闸的设计本身不成立" in f["★为什么必须改"]
    assert len(f["★六次不是同一种失效机制"]) == 6, "★ 六次要逐条给出**各自**的失效机制, 不许一句带过"
    kinds = set(f["★六次不是同一种失效机制"].values())
    assert len(kinds) >= 3, f"★ 只归出 {len(kinds)} 种机制 —— 那还是在压成一类"


def test_the_recursion_terminator_and_its_own_limit_are_both_recorded():
    """★★★ 递归终止点**和它自己的限制**必须同时在。只记前者=夸大。"""
    t = R["★★★★递归的终止点(这是本轮最值钱的一条)"]
    assert "没有满足条件, 就没有执行能力" in t["GPT 原话"]
    assert "始终被调用" in t["★理论对应"] and "抗篡改" in t["★理论对应"]
    lim = t["★★★★重要限制(GPT 自己给的)"]
    assert "修改这些闸的权限" in lim and "加强版约定" in lim
    assert "必须由执行者之外的运行环境或授权者维持" in lim, \
        "★ 这句是全轮最要紧的 —— 它说明我一个人建不出真闸"
    assert len(t["★★★先只收紧三个边界_不建巨大治理系统"]) == 3


def test_my_own_proposal_was_rejected_and_the_reason_is_kept():
    r = R["★★我提的方案被否"]
    assert "不建议采用" in r["GPT"]
    assert "把「还没有保障的已知风险」藏掉" in r["GPT"]
    assert "已知但未落实" in r["★应该禁止的是"]
    assert "一个永远拒绝的闸, 同样可以通过全部负例" in " ".join(r["★可机械检查的约束, 最低证据不止「有一个会失败的测试」"])


def test_residual_rate_question_was_answered_as_mis_posed():
    r = R["★★★残余率_我问错了方向"]
    assert "已知、低成本可关闭" in r["★不该接受的"]
    assert "政策上零容忍 ≠ 统计上宣称概率为零" in r["★★要区分"]
    assert "不等于" in r["★★★这六次估不出残余率"] and "六次独立操作失败" in r["★★★这六次估不出残余率"]
    assert len(r["★以后该记的四个数(按动作类型与控制版本分别保留)"]) == 4


def test_the_verdict_meaning_was_narrowed():
    n = G8["★★★★第九轮对改判含义的收窄"]
    assert "这些输出是否符合合同仍未决" in n["★★★准确含义(GPT 原话)"]
    assert "已经证明正确" in " ".join(n["★不是"])
    assert "不是追求把它包装成" in n["★★对「先定原则再套用」的修正"]
    assert "仍未决" in G8["★★★结论"], "★ 结论行没跟着收窄"


def test_dev002_upgraded_to_data_loss_with_bounded_blast_radius():
    u = D2["★★★★第九轮对本事故的定性升格"]
    assert "已经发生的数据保全失败" in u["GPT 原话"]
    assert "重建不能补回原文血缘" in u["GPT 原话"]
    assert "不应扩散成「整仓都不可信」" in u["★★★后果的划界"]
    assert "降级为不可复现" in u["★依赖该丢失版本的历史主张"], "★ 必须点名**哪一条**主张被降级"
    assert "我只查了 git, 没查库" in u["★★我先前说「不可恢复」说得太快"]


def test_accuracy_registered_as_blocked_testability_not_as_a_defect():
    # ★★ 2026-09-11 状态已推进: BLOCKED_TESTABILITY → PARTIALLY_VERIFIED_OFFLINE。
    #    断言随之改, 但**两句限定不许跟着松**。
    assert AC["状态"].startswith("**PARTIALLY_VERIFIED_OFFLINE**"), AC["状态"]
    assert "原 UNVERIFIED / BLOCKED_TESTABILITY" in AC["状态"], "★ 旧状态要留在字符串里, 不许抹掉沿革"
    u = AC["★★★★2026-09-11 离线隔离已建, 状态更新"]
    assert "只解了离线软件验证这一层" in u["★新状态"]
    assert len(u["★★★已完成的离线验证"]) == 5
    assert len(u["★★★变异检定_4/4 检出且都确认走到目标路径"]) == 4
    assert "不计为检出" in u["★变异检定防的假成功"]
    for x in ("真实 provider 的语义判断准确率", "真实 provider 的重复稳定性"):
        assert any(x in y for y in u["★★★仍未验证的(结论范围必须与替换边界一致)"]), f"★ 缺: {x}"
    assert "不覆盖" in u["★★绊线作用域_如实写不夸大"] and "子进程" in u["★★绊线作用域_如实写不夸大"]
    assert "不能声称该模块已经通过这两轮离线审计" in AC["★★★结论限制"]
    two = " ".join(AC["★两句都要"])
    assert "不能变成永久豁免" in two and "不应该被登记成已证实功能错误" in two
    assert len(AC["★★「还是不是同一台闸」_分层回答(GPT)"]) == 5
    assert "空必需集合空过" in " ".join(AC["★第一批定向测试要挑战的五种失效"])
    assert "语法错误或导入失败" in AC["★★变异测试要防的假成功"]


def test_the_four_numbers_are_present_and_computed():
    f = G8["★★★★四个数(GPT 第九轮要求, 以后每份报告都要同时呈现)"]
    for k in ("原定案例数", "实际可裁定数", "未决数", "可裁定范围内的结果"):
        assert k in f, f"★ 缺 {k}"
    assert f["原定案例数"] == 22 and f["实际可裁定数"] == 12
    assert "完整覆盖未实现" in f["★★★必须同时陈述的那句"]
    return f


def test_memo_says_one_name_is_not_enough_and_lists_what_i_can_do_meanwhile():
    assert "只给一个「对象域」的名称**可能仍然不够**" in MEMO
    assert "从「对象域」移到了「证据规则」" in MEMO
    for x in ("条件究竟作用于哪个对象", "怎样关联到那个对象", "缺乏文本证据时验收应当如何处理"):
        assert x in MEMO, f"★ 交办件缺: {x}"
    assert "扩大成了「不能做任何准备工作」" in MEMO, "★ 必须写明我先前的边界画错了"
    assert "规范欠定导致不可裁定" in MEMO and "不标为模型错误，也不标为通过" in MEMO


def test_the_part_it_endorsed_is_recorded_not_only_the_rebuttals():
    """★★★ 我上一轮只报了它驳我的, 漏了它认可的那段。
    **只抓驳斥、漏掉认可, 会让汇报看起来更严谨, 实际上不如实。** ⇒ 钉住两边都在。"""
    e = R["★★★★我上一轮漏读的结尾_而它正好是对我的一处纠正"]
    assert len(e["★它认可的四件(照抄, 不替它加码也不替它减码)"]) == 4
    lim = e["★★但它给这四件加的三个限定, 一个都不许丢"]
    assert len(lim) == 3
    for x in ("不抵消损失", "不产生放行资格", "不能因为又发现一个缺口就被全部抹掉"):
        assert any(x in y for y in lim), f"★ 限定缺: {x}"
    assert "偏斜的读法" in e["★★★我怎么漏的"]
    b = e["★★★该承担什么_该建立什么"]
    assert b["该承担"] == "**事件责任和修复责任**" and "不可逆损失" in b["该建立"]


def test_this_gate_admits_it_is_not_tamper_proof():
    """★★★ 本闸自己必须承认它挡不住「我决定改掉它」—— 否则就是把约定冒充成机制。"""
    src = pathlib.Path(__file__).read_text(encoding="utf-8")
    assert "挡不住「我决定改掉它」" in src and "加强版约定" in src


if __name__ == "__main__":
    test_the_common_shape_was_replaced_not_kept()
    test_the_recursion_terminator_and_its_own_limit_are_both_recorded()
    test_my_own_proposal_was_rejected_and_the_reason_is_kept()
    test_residual_rate_question_was_answered_as_mis_posed()
    test_the_verdict_meaning_was_narrowed()
    test_dev002_upgraded_to_data_loss_with_bounded_blast_radius()
    test_accuracy_registered_as_blocked_testability_not_as_a_defect()
    f = test_the_four_numbers_are_present_and_computed()
    test_memo_says_one_name_is_not_enough_and_lists_what_i_can_do_meanwhile()
    test_the_part_it_endorsed_is_recorded_not_only_the_rebuttals()
    test_this_gate_admits_it_is_not_tamper_proof()
    print("test_cce_round9_corrections: OK ("
          "★★★★共同形状被换掉: 不是「知识没变成闸」而是「**规则到动作之间没有形成足以阻断违规的控制链**」—— "
          "前者会掩盖「**我已经做过若干闸, 只是闸的设计本身不成立**」| "
          "★六次归出 ≥3 种不同失效机制, 不再压成一类 | "
          "★★★递归终止点: **把高风险动作的权限交给一个不能被日常执行者跳过的入口**(参考监控器: 始终被调用/抗篡改/可验证) | "
          "★★★★但它自己的限制同时在册: 我仍握着 shell+密钥+仓写权+**改闸权** ⇒ "
          "任何我建的东西**都只是加强版约定**, 真闸**必须由执行者之外维持** | "
          "★我提的「无失败检查不许登记为已知」**被否**(会把没保障的已知风险藏掉) | "
          "★残余率**这六次估不出**(无完整机会数; 「发现六个历史缺口」≠「六次独立操作失败」) | "
          "★改判含义收窄为「**指控依据被撤销, 是否合规仍未决**」| "
          "★DEV-002 升格为**已发生的数据保全失败**, 但影响面**沿依赖划界不扩散** | "
          "★accuracy/ 登记为 **UNVERIFIED/BLOCKED_TESTABILITY**, 两句都在 | "
          f"★四个数已落: 原定 {f['原定案例数']} / 可裁定 {f['实际可裁定数']} / 未决 {f['未决数']} —— **完整覆盖未实现** | "
          "★本闸自陈**挡不住我决定改掉它** | "
          "★★★★补: 我上一轮**只报了它驳我的、漏了它认可的那段** —— "
          "「撤销不成立的指控 · 保留未决范围 · 没有再付费取判 · 把预算规则真正接到代码上」是**具体的纠错进展**, "
          "且它给的三个限定(不抵消损失/不产生放行资格/不能因又发现一个缺口就被全部抹掉)一个不丢; "
          "**只抓驳斥漏掉认可, 看着更严谨, 实际不如实**)")
