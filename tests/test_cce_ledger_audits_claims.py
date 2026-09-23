#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闸的闸: cce_ledger_audits_claims 自己有没有检定力。

★ 这个测试存在的理由: 第一版闸**抓不到它被设计去抓的那句话** ——
  我写的是「违反**既有必要条件**」, 闸只认字段名 hard_discriminant。
  **没验过的闸等于没建。**
"""
import json, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import cce_ledger_audits_claims as G  # noqa: E402


def test_it_catches_the_input_it_was_built_for():
    r = G.build()
    hits = r["self_check"]
    assert hits, "★ 闸抓不到它被设计去抓的那条历史输入 —— 等于没建"
    h = hits[0]
    assert h["字段"] == "hard_discriminant" and h["被施加到"] == "PROD"
    assert h["命中的说法"] == "必要条件", "★ 别名机制失效, 又退回只认字段名"
    return h


def test_paraphrase_is_why_aliases_exist_and_it_is_stated_as_partial():
    """★ 别名把「要我登记」从『下每条结论时』搬到『建账本时』, **没有消灭依赖**。
    留档必须明写这一点, 不许说成已解决。"""
    r = G.build()
    lim = " ".join(r["★★局限_必须写下来"])
    assert "不保证零漏检" in lim
    assert "没被消灭" in lim and "不许说成「已解决」" in lim, \
        "★ 把部分缓解写成彻底解决 —— 这正是本项目反复栽的形态"


def test_false_positives_go_to_an_adjudication_book_not_into_the_gate():
    """★★ 误报必须由**裁决簿**吸收, 不许靠调窗口/加豁免词让它消失 ——
    那是照着结果调闸。"""
    adj = json.loads((ROOT / "tests/data/ledger_claim_audit_adjudications.json").read_text(encoding="utf-8"))
    assert "不许靠调窗口/调词表让命中消失" in adj["★★规则"]
    perf = adj["★★★这个闸的真实性能_不许粉饰"]
    assert "误报" in perf["精度"]
    # ★ 「不为了好看调参」的措辞随记录演进过, 这里钉住**语义**: 必须明写没缩别名/没调窗口
    assert ("没有为了好看缩别名表或调窗口" in perf["精度"]) or ("没有为了好看去调参" in perf["精度"]), \
        "★ 必须明写误报是由裁决簿吸收的, 不是靠调闸消掉的"
    assert "不保证零漏检" in perf["★仍会漏"]
    # 每条裁决都要有理由, 不许只贴标签
    for a in adj["adjudicated"]:
        assert a.get("理由") and len(a["理由"]) > 30, f"★ 裁决无实质理由: {a['文件']}"
    return adj


def test_no_unadjudicated_hits_and_no_stale_adjudications():
    r = G.build()
    assert not r["★★★未裁决命中(判红的就是这些)"], \
        "★ 有未裁决命中 —— 要么它是真错要修, 要么写进裁决簿并说明理由"
    stale = r["★★裁决簿里已失效的条目(对应命中不在了, 要么已修要么闸被改窄了)"]
    assert not stale, f"★ 裁决簿有失效条目 {stale} —— 命中消失了要说清是修好了还是闸被改窄了"
    # ★ 已修复的必须归到 resolved 并**说明为何消失**; 「修好了」与「闸被改窄」不许混
    for x in r["★已修复并归档(命中消失且说明了为何消失)"]:
        assert "违规" not in x["★命中为何消失"], f"★ {x['文件']} 命中消失但没说明原因"
        assert ("修好了" in x["★命中为何消失"]) or ("改窄" in x["★命中为何消失"])


def test_self_referential_exclusion_list_stays_tiny():
    """★ 排除文件是藏东西最方便的手法 ⇒ 名单必须短、显式, 且被钉住。"""
    r = G.build()
    ex = r["★自指排除的文件(名单必须短且显式)"]
    assert len(ex) == 2, f"★ 自指排除名单变长了({ex}) —— 每加一个都要说明为什么不是在藏命中"
    assert set(ex) == {"taxonomy_field_reach_ledger.json", "ledger_claim_audit_adjudications.json"}


def test_reverse_a_clean_sentence_must_not_fire():
    """反向: 不含规范框架的同现**不该**判红, 否则闸会因漫天误报被弃用。"""
    facts = G.ledger_negative_facts()
    clean = "生产 stage2 的 prompt 里没有 hard_discriminant, 这是一条字段送达的事实记录。"
    assert not G.scan(clean, facts), "★ 无「违反/必须」框架却判红 —— 精度已崩"


if __name__ == "__main__":
    h = test_it_catches_the_input_it_was_built_for()
    test_paraphrase_is_why_aliases_exist_and_it_is_stated_as_partial()
    adj = test_false_positives_go_to_an_adjudication_book_not_into_the_gate()
    test_no_unadjudicated_hits_and_no_stale_adjudications()
    test_self_referential_exclusion_list_stays_tiny()
    test_reverse_a_clean_sentence_must_not_fire()
    print("test_cce_ledger_audits_claims: OK ("
          "★★★方向反过来: **不要求结论登记依赖**(那一步正是我失守处), 让账本的否定性事实自带检测器去扫全部留档 | "
          f"★第一版**抓不到**它该抓的那句话(我写「必要条件」不是字段名), 加别名后抓到: 「{h['命中的说法']}」→{h['被施加到']} | "
          "★★但别名仍要我登记 —— 只是**登记时机**从「下每条结论时」搬到「建账本时」, **依赖没被消灭** | "
          f"★裁决簿 {len(adj['adjudicated'])} 条在册 + {len(adj.get('resolved', []))} 条已修复归档 | "
          "★★★它**当场抓住了我同一天写的一条缺送达前提的归因**(候选代 display 违例) —— 处置是**补前提**, "
          "不是裁决掉; 且闸的代码/词表/窗口**一字未改** | "
          "3 条反向验证判红)")
