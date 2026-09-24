#!/usr/bin/env python3
"""「还差什么」—— 从各真相源**现算**, 不由我口述。

2026-08-07 立的汇报纪律: 禁用裸的「完整/全链路」字样, 必须给逐项清单。
2026-09-03 owner 两次点破我越界声报(「可以投产了」/ 收尾语气)。
⇒ 与 cce_production_status.py 配套: 那张表说「哪些读数能用」, 这张说「哪些事没做完」。

★ 分三类, 因为它们的**修法完全不同**:
   BLOCKED_EXTERNAL —— 卡在我拿不到的外部资源上(人/触达量/owner 裁定/owner 撰文/权限外移)
   OPEN_WORK        —— 我能做, 只是没做
   DECIDED_NOT_DOING—— 已裁定不做, 留着防有人重开
"""
from __future__ import annotations

import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLOCKED, OPEN, DECIDED = "BLOCKED_EXTERNAL", "OPEN_WORK", "DECIDED_NOT_DOING"


def _ablation_coverage_now():
    """★★★ 2026-09-11: 这里原本把「只覆盖 17.3%」**硬编在字符串里**, 且仍指向 v2。
    v3 落地后真实数已是文件级 12.89% / 行级 27.95%, 而这张清单**永远不会自己更新** ——
    「过期判决表继续被引用」正是本仓登记过的错误族, 这次是它出现在**报告「还差什么」的那张表自己**身上。
    ⇒ 改成从判决表现算。找不到就如实说找不到, **不回落到任何硬编数字**。"""
    import json as _j, os as _o
    for name in ("ablation_verdicts_v3.json", "ablation_verdicts_v2.json"):
        fp = _o.path.join(ROOT, "tests/data", name)
        if not _o.path.exists(fp):
            continue
        try:
            cov = _j.load(open(fp, encoding="utf-8")).get("★coverage") or {}
        except Exception as e:
            return name, "读判决表失败(%s: %s) —— **不拿旧数字顶替**" % (type(e).__name__, e)
        f_pct, l_pct = cov.get("file_level_pct"), cov.get("line_level_pct_GENEROUS_UPPER_BOUND")
        if f_pct is None and l_pct is None:
            continue
        n_f, n_all = cov.get("n_touched_files"), cov.get("scope_files")
        return name, (
            "**文件级 %s%%**(%s/%s 文件) · 行级**慷慨上界 %s%%**(%s/%s 行)"
            % (f_pct, n_f, n_all, l_pct, cov.get("lines_in_touched_files"), cov.get("scope_lines")))
    return None, "★ 判决表里读不到 ★coverage —— **覆盖率现在是未知, 不是某个旧数字**"

def _j(rel):
    return json.load(open(os.path.join(ROOT, rel), encoding="utf-8"))


def items() -> list[dict]:
    out = []

    # ① 链路阶段未完成的
    conf = _j("config/cce_chain_conformance.json")
    for ph in conf["phases"]:
        if not ph["status"].startswith("DONE") and "DECIDED" not in ph["status"]:
            out.append({"类": OPEN, "项": f"{ph['phase']} 未完成", "证据": ph["status"]})
        elif "SCOPED_WITHHOLDING" in ph["status"] or "DECIDED" in ph["status"]:
            # ★ 只写状态词等于没写 —— 读的人看不出「条件是什么、谁能解开」。
            #   带条件完成的项必须自带: 扣发了什么 + 什么能解开它。
            out.append({"类": DECIDED if "DECIDED" in ph["status"] else OPEN,
                        "项": f"{ph['phase']} 带条件完成",
                        "证据": f"{ph['status']} — {ph.get('★condition') or '条件未写明(需补)'}"})

    # ② profile 未经 CI 验证的
    seen = set()
    for f in glob.glob(os.path.join(ROOT, "archive", "*", "*normalized.json")):
        try:
            seen.add(json.load(open(f, encoding="utf-8")).get("profile"))
        except Exception:
            pass
    for p in _j("config/cce_submission_contract_v1.json")["profiles"]:
        if p not in seen:
            out.append({"类": OPEN, "项": f"profile `{p}` 从未在 CI 上验证过",
                        "证据": "archive/ 里没有它的成功 run"})

    # ③ 能力注册表里仍缺的
    # ★ 2026-09-04: 原来一律记 OPEN, 于是「卡在拿不到的外部资源上」和「已裁定不做」
    #   都被显示成「我能做只是没做」—— 三类混成一类, 清单就失去了它唯一的用处。
    #   ⇒ 让 missing 条目**自己声明所属类**(靠它本来就写着的字样), 默认仍是 OPEN。
    def _class_of(m: str) -> str:
        # ★ 2026-09-04: 已实测的条目即使正文里还带「未测」字样(讲的是**另一半**),
        #   也不该被判成 BLOCKED。判据看**是否已有实测结论**优先。
        # 一条 missing 里若**同时**含「真外部阻塞」与「我能做只是没做」, 说明它没拆干净 ——
        # 判为 OPEN(能做的那半优先), 并靠正文把两半写清楚。
        if "真外部阻塞" in m and "我能做" in m:
            return OPEN
        if any(w in m for w in ("仍 BLOCKED", "拿不到", "受限模型", "需英文域", "无一张标注素材",
                                "解锁动作")):
            return BLOCKED
        if any(w in m for w in ("刻意不", "已裁定", "已否决")):
            return DECIDED
        return OPEN

    for c in _j("config/cce_capability_registry_v1.json")["capabilities"]:
        for m in (c.get("missing") or []):
            _cls = _class_of(m)
            # ★ BLOCKED/DECIDED 的理由写在 missing 原文里, 而「项」只截 64 字会把它切掉。
            #   ⇒ 非 OPEN 的项, 证据必须带上原文, 否则「卡在什么资源上」无处可读。
            # ★ 2026-09-11 加 `原文`: OPEN 的证据只写 status=..., 而「项」只截 64 字
            #   ⇒ 这条一旦被下面的去重并掉, 它的内容**在输出里一个字都不剩**。
            #   去重要能「并进去」, 就得有东西可并。**原文只供合并用, 不改任何条目的显示与分类。**
            out.append({"类": _cls, "项": f"{c['id']}: {m[:64]}",
                        "原文": m,
                        "证据": (f"status={c['status']}" if _cls == OPEN
                                 else f"status={c['status']} — {m}")})

    # ④ 读数层判红的(修法只有换仪器或接受)
    ps = _j("tests/data/phase2/k1_v2_multitext_verdict.json")
    out.append({"类": DECIDED,
                "项": "结层 intensity/weight 永久不可用",
                "证据": f"K1-v2 {ps['decision']}; 已裁定不换仪器(托管 API 无法批不变)。"
                "★★★ **2026-09-14 更正这条的范围**(网页 GPT Pro 带出处核过): "
                "批不变内核**不是逻辑上只允许自托管**, 而是**必须由服务端掌控者启用** —— "
                "托管商也能部署(vLLM 官方已有 server 模式)。真障碍是: 客户端不能通过 prompt 或批量设置"
                "**强迫** MiniMax 后端采用它。"
                "⇒ **这一条从「结构性做不了」变成「向供应商要一条可验证的确定性服务保证」** —— "
                "那是**可以去问**的动作, 不是死路。★ 在拿到保证之前, 客户端只能**管理测量不确定性**, "
                "不能宣称根因已修复; **重复采样不是修复**, **缓存首次答案是回放**不是新一次推理变确定。"
                "★★ 不变的部分: 即便实现位级确定, 也是**构造上零方差**, 不等于测量可靠性"
                "(本项目已两次判此为退化: C2 常数估计器 / quadrant 一致率 1.000 零方差) —— "
                "所以即使拿到保证, 也要先想清楚要的是「可重现」还是「可靠」。"
                "见 tests/data/user_llm_assessment_2026-09-14.json。"
                "★★★★★ **2026-09-17 已去测, 不再是待问的动作**(results/seed_probe.json, 22 次): "
                "文档侧 —— MiniMax 请求参数里**无 seed**, 响应里**无 system_fingerprint**, 未给任何可复现性保证。"
                "实测侧 —— temp=0.0 同一 prompt **6 次 → 5 种不同输出**, 零失败; "
                "seed=42 与 seed=999 组内同样不确定 ⇒ **seed 被静默忽略**。"
                "★★★ 它还**换掉了 r3 的一个保留**: r3 明写「k=6 不能单独归因于模型随机性(也可能是服务端变更)」, "
                "而本探针多次调用是**同一时刻并发**发出的 ⇒ **服务端变更这个解释被排除**, "
                "剩下的是模型自身的非确定性 ⇒ CCE 的重测一致率有一个**来自模型、不可消除的下界**。"
                "★★★ 但**它不在当前那堵墙上**: 确定性是**可复现**属性, 而三条路卡的都是**效度**"
                "(没有鉴别格) ⇒ **即便 seed 明天就生效, 一个鉴别格也不会多出来**"
                "(results/three_decisions_rollup.json: 三项同尺后逐项新增鉴别格 0/0/0)。"
                "★ 不得外推: 单一 prompt、单一模型、n 小, **不是**对 CCE 全链路一致率的测量。"})
    ph_v = _j("tests/data/phase2/playbook_hit_verdict.json")
    at_v = _j("tests/data/phase2/playbook_atoms_verdict.json") if os.path.exists(
        os.path.join(ROOT, "tests/data/phase2/playbook_atoms_verdict.json")) else None
    _ev = f"{ph_v['decision']} {ph_v['meeting_criterion']}/{ph_v['texts']} 文本达标"
    if at_v:
        _ev += (f"; 替代方案已试并实测: 原子分解 {at_v['decision']} "
                f"{at_v['meeting_criterion']}/{at_v['texts']}(改善真实且非退化, 但未到 7/8 采纳线 ⇒ 不采纳)")
    out.append({"类": OPEN, "项": "对齐出口 playbook_hit 不可靠, 替代已测但未达采纳线",
                "证据": _ev + ("。★ 下一步不是再换读数形态 —— 实测显示残余不稳定不在标尺上"
                               "(belong 的正向原子只剩 1 条, 连二值都在 0/1 间摆)。"
                               "要动的是 **playbook 原子本身**(措辞太抽象, 无法逐字指认), "
                               "那是改**干预设计**不是改测量 ⇒ **需 owner 拍板**, 且要另立预注册。"
                               "★★ 2026-09-05 已出影响分析 `tests/data/phase2/playbook_p1_decision_memo.json`: "
                               "**不是「改/不改」二选一** —— 那 2 个 FAIL 恰好就是两个**测量侧**缺陷"
                               "(A1: audit 的「第二次提及=放大事件」是**跨轮规则**, 单文本判官结构上看不见; "
                               "A2: belong 的一条原子塞了**两个动作+一个顺序约束=三件事**), "
                               "修完**有可能直接到 8/8, 根本不用动 A3 的六条抽象原子**。"
                               "⇒ 建议顺序: ①修 A1/A2(测量侧, 不需 owner 拍板) ②改三态 measurement contract "
                               "③A3 **现在不该动** —— A1/A2 未修时**测不准** A3 还剩多少问题, "
                               "现在改是在没有干净基线的情况下改产品主张, 且要烧一轮预注册 + 192 次 API 才知道白改没白改。"
                               "★ 已核实的**改不掉**的部分: 两种读数形态的 PASS **全部**落在地板/天花板"
                               "(原子分解 6/6 · 原始 4/4) ⇒ 拆原子改变了数字**没改变结构**; "
                               "机制是**可核验性**不是数字位置(ACL 2026: 可核验 0.71 vs 主观 0.19)。"
                               "★★ 2026-09-05 owner 批「①修 A1/A2」, 已执行并出 GEN2 判决书 "
                               "`tests/data/phase2/playbook_atoms_gen2_verdict.json`。三条预注册预测全部结清: "
                               "**P1 成立且决定性** —— belong 一致率 0.571 → **1.000**(拆开塞了三件事的原子确实有效, "
                               "且它是唯一被设计去改变的臂, 变化幅度远超单次翻转); "
                               "**P2 触发「低于」支** —— audit 0.750 → **0.429**, 证明 GEN1 的 0.750 是**复合掩盖出来的假稳**"
                               "(两原子每次恰好命中一个, 把抛硬币级判断包装成「一般般」); "
                               "★ 但「跨轮原子被判成执行过」与「清单变短改变了对剩下那条的判断」**两种机制分不开** —— "
                               "探针只存聚合值不存逐原子, **已修**; "
                               "**P3 被违反** —— display(playbook **一字未改**)从 1.000 PASS 翻成 0.750 FAIL。"
                               "★★★ **真正的产出不是计数, 是判据本身的问题**: 0.95 线在 n=8 下**等价于要求 8 次全同**, "
                               "零容差; 由 display 两轮 16 次重复中 1 次偏离估得单次偏离率 ≈ 1/16 ⇒ "
                               "**纯噪声就有约 40% 概率翻掉一个臂**, 纯噪声期望达标数 ≈ 4.8/8。"
                               "⇒ 「4/8 → 6/8 → 6/8」这些计数之差**落在噪声量级内**, 本轮直接观测到零改动的臂移动了 1。"
                               "★ 判决仍是 **6/8 < 7 ⇒ 不采纳**, 线**不下调** —— 噪声大只说明判据测不准, "
                               "不说明结果该往有利方向读。"
                               "★ 下一步**不是**再改 playbook 措辞(已有直接证据表明那只会得到另一个噪声样本), "
                               "尤其**不要**为了「差一个就到 7」去动 A3 —— 那是拿产品主张补一个测不准的判据。"
                               "应做: ①先跑**纯噪声基线**(零改动臂 n=30, 量轮间方差) ②逐原子落盘(已修) "
                               "③判据改为能容忍偶发偏离, 或直接走三态。"
                               "★★★ 2026-09-05 底噪 A/A 已跑(n=30 × 8 臂 = 240 次, 零丢失), "
                               "见 tests/data/phase2/judge_noise_floor.json —— 结论**推翻了我上面两条建议里的一条**: "
                               "**① 加重复数是错的** —— 零容差判据下 P(全同)=(1-p)^n **随 n 单调下降**, "
                               "加重复只会更难过。要的是**容差**不是重复数(重复数只用来把众数占比估准)。"
                               "★ 实测底噪: **20 个原子里 17 个在 30 次下完全确定(不稳度 0.000)** —— "
                               "判官不是普遍地吵, 全部不稳集中在 3 个原子且**三个原因各不相同**: "
                               "display 那条 1/30 = 纯噪声(证实它在 GEN2 的 FAIL 是噪声) · "
                               "audit「给可验证事实+接受检验的姿态」不稳度 **0.533** 但**无子串率 0.000**"
                               "(每次都能引证)⇒ 是**原子有歧义**不是判官坏, 属 A3 类需 owner 拍板 · "
                               "belong 禁令「不派任务」**无子串率 0.733** ⇒ **真 bug**: "
                               "**缺席在构造上不可引证**, 而 PROMPT 要求 executed=1 必附子串 "
                               "⇒ violations 被系统性虚增, 量的是提示词的自相矛盾不是文本。"
                               "★★ **P_A 前提被推翻**: 没有任何臂的众数落在中段, 而 **audit 众数就在地板(0.0) "
                               "占比却只有 0.733** ⇒ **位置不预测稳定性**, "
                               "「值在地板 ⇒ 可靠地没执行」有直接反例 —— 三态方案**不能**按值的位置划弃权。"
                               "★ 底噪 p̂ = **0.0048**(去掉 audit 后 210 次里 1 次), 与校准先验 0.0104 同量级; "
                               "两者都远低于我最初报的 0.0625(那是把最吵的臂当全体, 差一个数量级)。"
                               "⇒ **playbook_hit 的 4/8 在纯噪声下概率 < 1e-5 —— 那个不可靠是真的。** "
                               "⇒ 下一步: ①修禁令引证矛盾(改 manipulation, 需另立预注册约 240 次, **等 owner 定**) "
                               "②audit 那条原子的歧义属产品主张, **我不动** "
                               "③判据改众数占比 + 容差(n=30 下 0.733 与 0.967 之间可干净分开), "
                               "★ 但**众数占比测 reliability 不测 validity** —— 17 个「完全确定」的原子同样可能"
                               "**一致地判错** ⇒ 仍需独立人类金标, **与 SESOI/盲评那条线在此合流**。"
                               "★★★ 2026-09-05 禁令修复已做两轮(各 240 次)+ 网页 GPT 调研(思考 4m53s), "
                               "见 playbook_atoms_gen4_noise.json 与 judge_measurement_research_2026-09-05.json。"
                               "**GEN3(v2) 被对照组判红, 抓到的是我自己**: 我声称「正向语义不变」, 实际丢了 v1 一整句"
                               "「只是谈论相关话题不算执行」⇒ 正向判定变松。GEN3b(v3) 逐字保留那句后重做, "
                               "【做】条目行为**全部复原**(唯一例外是已知有歧义的 audit 那条), 证明最小化生效。"
                               "★★★ **主结果: 同一段文本、同一条原子、三种提问措辞 ⇒ executed 27% / 100% / 3%** "
                               "⇒ **该判定由提问框架支配, 不由文本支配。** "
                               "★★ 且反转举证责任**反转了默认值**(预注册中事先声明的风险实现了): "
                               "reward「不再投喂信息」与 audit「不辩解不表演」满足率**双双 0.000 → 1.000**; "
                               "pain_seek「不空承诺,承认边界」v1 四臂全 1.000/零方差 → v3 散成 0.633/0/0/0.833。"
                               "⇒ ★★★ **v1 下 5 条禁令的「完美确定」是被提问形状造出来的**, "
                               "故 v1 的 p̂=0.0048 有一部分量的是**提问的刚性**不是判官对文本的一致性。"
                               "★ P3 判红 ⇒ 按预注册**局部归因不成立**, P1 的数值达成(违反率 0.867→0.000)"
                               "**不能**被认证为禁令修复的效果。"
                               "★★ GPT 调研(线索层)给三条关键更正, 其中两条我**已自核算术相符**: "
                               "① 众数占比 = **variation ratio 的补数**, 是名义离散度统计量**不是** reliability coefficient; "
                               "② **众数是看完数据才挑的 ⇒ 天然向上偏**: 纯 50/50 在 n=8 时 E[众数占比]=**0.6367**"
                               "(自算相符) ⇒ **我在 n=8 下报的稳定性数全部结构性偏高**, 且 GEN2 的 audit 0.500 "
                               "其实**低于**纯随机期望; ③ A=q²+(1−q)² ⇒ **A>=0.95 等价于要求 q>=0.974**(自算相符), "
                               "我先前实测的「0.95@n=8 等价于全同」由此有闭式解释。"
                               "⇒ 阈值应由 **exact-binomial(q_bad/q_good/α/β)** 铸成, **不是**取两群实测中点; "
                               "区分 q<=.70 与 q>=.90 在 power .80 下需 **n=28, PASS 需 modal>=24/28**。"
                               "★★ GPT 的工程裁定与我的数据一致: **不要再增加一轮同模型重复实验**。"
                               "⇒ 剩三件: ①**禁令改三值** SATISFIED/VIOLATED/**INDETERMINATE** + complete_scan "
                               "(现行反转只是把假违反换成假满足) —— 有 Alpern-Schneider safety property 与 "
                               "Reiter closed-world 的理论对应, **但 GPT 明说无 LLM-judge 文献命名过它**, 不得称标准做法; "
                               "②**audit 那条弃用 latent stance**, 拆成 A 可核验事实主张 / B 显式核验开放信号, "
                               "且**实际开放但没明说的必须判 0**(这是测量定义不是漏判) —— **改产品主张, 需 owner 拍板**; "
                               "③**人类 teachability pilot 先于金标**: 3 名标注者 · 每条目 30–50 单元 · 三值标签 · "
                               "**先算 pre-adjudication 一致率再讨论** · Krippendorff α + bootstrap CI"
                               "(.800 是 convention **不是**统计定律) · 样本量**按条目**算不可混池"
                               "(per-item validity 至少 50/条目, 要分报敏感度/特异度则约 100)。"
                               "★ 文献(BARS Smith&Kendall 1963 · Eguchi&Kyle 2023 人类 stance span F1 仅 **0.663** · "
                               "Klie et al. 591 项目综述)**均待核**, 未核前不作证据。")})

    # ⑤ 文档与代码的分歧
    # 「已就地标注」= 分歧仍在但读那一节的人不会被误导, 且有闸钉住 ⇒ 与「符合」同属已解决
    for s in _j("config/cce_doc_reconciliation.json")["section_divergences"]:
        if s["verdict"] not in ("符合", "已就地标注"):
            out.append({"类": OPEN, "项": f"{s['section']}: {s['verdict']}",
                        "证据": s.get("note", "")[:70]})

    # ⑥ 归档里追不回的
    idx = _j("config/cce_archive_index.json")
    n = sum(1 for v in idx["runs"].values() if v["status"] == "IRRECOVERABLE")
    out.append({"类": DECIDED, "项": f"{n} 个历史 run 两仓皆无, 不可重建",
                "证据": "已实测复核, 如实登记为损失"})

    # ★★★ 2026-09-08: 验收闸与生产分类器用的不是同一份分类学字段集, 且闸是**乐观代理**
    _fs = os.path.join(ROOT, "tests/data/gate_vs_production_fieldset_result.json")
    if os.path.exists(_fs):
        fs = _j("tests/data/gate_vs_production_fieldset_result.json")
        t = fs["★★★relative_to_the_G_K1_threshold"]
        out.append({"类": BLOCKED,
                    "项": "验收闸与生产分类器**字段集不同**, 且闸是乐观代理 ⇒ 对齐方向需 owner 定",
                    "证据": (f"实测(405 次, 唯一变量是分类学字段集合): "
                             f"闸字段集 mean_JS={t['armA_闸字段集']['mean_JS']}(越 0.25 线的自助概率 "
                             f"{t['armA_闸字段集']['自助越线率']:.1%}) vs 生产字段集 "
                             f"{t['armB_生产字段集']['mean_JS']}(越线概率 "
                             f"{t['armB_生产字段集']['自助越线率']:.1%}); 配对自助差 "
                             f"{fs['★diff_JS_B_minus_A']['点估计']} CI {fs['★diff_JS_B_minus_A']['配对自助95%CI']} 不含 0。"
                             f"⇒ **「G-K1 通过」对闸的字段集成立, 对生产实际看到的字段集不成立。** "
                             f"★★ 注: arm B 的 JS 是「**使用生产材料的标注者面板**」的一致性, "
                             f"**不是真实生产分类器的信度** —— 后者(完整流程 top-1 重测)**仍是空的**, "
                             f"且不能由前者填上(变异来源不可互换)。见 tests/data/four_claims_separate.json。 "
                             f"★ 两条对齐路线**都要重跑验收**, 且都改仪器: "
                             f"①把闸向生产对齐(改闸=换测量仪器, 历史读数可比不可合) "
                             f"②把生产向闸对齐(改生产 prompt=换代, instrument_hash 会变)。"
                             f"★★★ 2026-09-09 **更正**: 我先前报「生产更准(3/16 vs 闸 6/16)」——"
                             f"那比的是**已退役的旧闸 V0**。同口径三方: C1 八题 生产 1/8 · V0 3/8 · "
                             f"**当前 v2 0/8**; 16 道负例 生产 3/16 · V0 6/16 · **v2 1/16**。"
                                 f"★★ 2026-09-09 完整流程重测补标: 生产的**逐题**读数**不稳定**"
                                 f"(q=19/22, 逐题翻转率 3/22, 上限 0.3159; C_纯向往_0 与 C_明确放弃_0 "
                                 f"在两次运行间**互换了对错**) ⇒ **逐组表每一格都是单次运行读数**; "
                                 f"两次汇总虽相同, 但 **n=2 不足以确立汇总稳健性**。"
                             f"⇒ **当前 v2 已经比生产好**, 「更一致的那台反而更错」**只对 v1 成立**。"
                             f"★★ 这步**零调用**补表改变了下一步该不该买: 原以为该测 (a)「闸向生产对齐」, "
                             f"现有证据指向换成生产材料**更可能变差** ⇒ **未发起那 220 次**。"
                             f"★ 但 (a) **只是优先级下降, 没有被证伪**(证据只覆盖这一条边界的 16 道"
                             f"**我自己出的**构造题; 若要测应在**自然语料**上测)。"
                             f"★ 另: 「删掉闸独有材料」**不等于**「让闸用生产材料」"
                             f"(生产还有 family/typical_codes/levers 三个闸没有的字段) ⇒ 两个设计要分开。"
                             f"★★ 选哪条是**产品主张与标定预算**的取舍, **owner 裁定**, 我不替他选。"
                             f"★ 限度: arm B **不是生产**(没吃 s1 四层/没出完整 schema/k=1), "
                             f"只隔离了字段集合这一个变量 ⇒ **不得**说「生产分类器 G-K1 不达标」。"
                             # ★★★★ 2026-09-13: 新增实测**直接冲击其中一条路线**
                             "★★★★ **2026-09-13 实测, 直接冲击路线②**: "
                             "「生产向闸对齐」= 把判别式/负例/决策树塞进生产 s2 prompt —— "
                             "而这正是候选构造器(5808 字 vs 生产 3369 字)在做的事。"
                             "gen9 双臂重测(同 10 题 · 同 n=8 · 判据测量前冻结 · 1291 次真实 M3 调用)实测: "
                             "**display 出现率由生产臂 1/80 涨到候选臂 40/80**; "
                             "A 臂(合同说**不该** display) **27/48 = 56%**, "
                             "B 臂(display **合理可能**) 13/32 = 41% ⇒ **倒挂** —— "
                             "在不该给的地方比在可以给的地方**给得更多**。"
                             "⇒ 路线② **已有实测负面证据**: owner 的选择不再是「两条路都要花钱、看取舍」, "
                             "而是「其中一条已被测出会让读数更偏」。"
                             "★ 限度(不许外推): 只测了这 10 题 · 只看 display 这一个标签 · n=8; "
                             "**不**说明路线①(闸向生产对齐)更好 —— 那条**仍未测**。"
                             "见 results/gen9_verdict.json 与 tests/test_cce_gen9_verdict.py。")})

    # ★★ 2026-09-08: suspend 修法已确证, 但落地要动 Core 钉住的 knot_taxonomy.json ⇒ owner 裁定
    _r6 = os.path.join(ROOT, "tests/data/proposed_route_6_prereg.json")
    _fx = os.path.join(ROOT, "tests/data/suspend_fix_confirmation_result.json")
    if os.path.exists(_r6) and os.path.exists(_fx):
        r6, fx = _j("tests/data/proposed_route_6_prereg.json"), _j("tests/data/suspend_fix_confirmation_result.json")
        # ★ 只在「已确证 + 提案未写进 manifest」时才报, 两个条件都从产物现读
        _v2 = os.path.join(ROOT, "tests/data/gate_protocol_v2_acceptance_result.json")
        if os.path.exists(_v2):
            v2r = _j("tests/data/gate_protocol_v2_acceptance_result.json")
            cost = v2r["★★★但代价必须单独说"]["★★越 0.25 线的自助概率"]
            out.append({"类": DECIDED,
                        "项": "suspend 修法**已落地** —— 闸协议 v1→v2 已启用(route 6 · GATE_PROTOCOL_CHANGE)",
                        "证据": (f"G-K1 判据一字未改且两项达标: top2 0.9040→0.8812 ≥0.80 · "
                                 f"mean_JS 0.2190→0.2422 ≤0.25。"
                                 f"★★ **代价**: 越 0.25 线的自助概率 {cost['v1']} → {cost['v2']}, "
                                 f"余量从 0.031 缩到 0.0078(0.16 个跨对 SD) ⇒ **PASS 不是二值事实**。"
                                 f"★ 资格考五员全 5/5 但按三态判据**全部 UNRESOLVED**, "
                                 f"status=OK 是「面板可用」**不是**「全部合格」。"
                                 f"★ 第⑦条全负例组回归: **7 组方向正确、1 个负例组「仅收藏」30%→50% 方向反转**(未掩盖)。"
                                 f"★★ instrument_hash d4cce4c745f3f991 **一字未变** ⇒ 生产没换代, 既有标定仍有效; "
                                 f"且实测生产在该缺陷上 1/8(NO_DEFECT)。"
                                 f"★★★ 2026-09-09 **更正这条的措辞** —— 我原写「**不改变生产分类器**」, "
                                 f"读起来像一条良性性质(修了闸、没惊动生产)。**正确表述是**: "
                                 f"这次改的 negative_examples_prompt 是 **GATE_ONLY 材料**, "
                                 f"⇒ 这个修复**在结构上不可能触及生产** —— 不是「没改动生产」, 是「**够不着**」。"
                                 f"哈希没变不是证明它安全, 是证明它**没到那一层**。"
                                 f"见 scripts/cce_necessary_condition_reach.py。"
                                 f"★★★ web GPT 第六轮定名: 这**不叫伪修复**, 叫「**修复错层**/**生产目标未触达**」 —— "
                                 f"只有当它被登记成「已修复生产分类器的这一缺陷」时才是**错误关闭缺陷**。"
                                 f"状态要拆三行: 验收协议修订**已完成** · 生产缺陷修复**未完成** · 该修订触达生产分类规则**否**。"
                                 f"★ 且 hash 不变**不能单独**证明「够不着生产」—— 那由真实依赖路径与出站请求证据证明(已做)。"
                                 f"⇒ 必带两句: **与 v1 可比不可合** · **该修复不进生产 prompt, 生产侧缺陷未被处理**。"
                                 f"回滚点 cce-identified-vault/backups/20260909-113923-gate-protocol-v2/")})
        elif "ALL_PASS" in fx.get("★★★overall", "") and "未写进 manifest" in r6.get("★status", ""):
            out.append({"类": BLOCKED, "项": "suspend 修法已确证, **卡在 owner 裁定**(要动 Core 钉住的 knot_taxonomy.json)",
                        "证据": (f"证据等级(2026-09-09 重命名): **预先冻结、作者构造的定向行为测试**。"
                                 f"★ 题级(伪重复更正后)配对: "
                                 f"{fx['MiniMax五员']['★★★事后_题级统计单位更正']['C1_失败方向']['题级配对']}, "
                                 f"符号检验 p="
                                 f"{fx['MiniMax五员']['★★★事后_题级统计单位更正']['C1_失败方向']['单侧精确符号检验p']}"
                                 f"(原报 0.00129 是把 8题×5模型当 40 个独立样本, **夸大约 12 倍**)。"
                                 f"★★ **8 组里 7 组方向正确、1 个负例组(仅收藏)从 30% 升到 50% 方向反转** —— "
                                 f"而 C1 只覆盖 6 个负例组里的 2 个, **四条判据没有任何一条会看到它**。"
                                 f"⇒ 不得再只说「C1~C4 全过」。"
                                 f"★ 换代路由: **走不了第一条路** —— 改 negative_examples 实测不动 instrument_hash; "
                                 f"**不硬套第五条路**(它限定 manipulation, 本例改的是验收闸本身)。"
                                 f"⇒ {r6['★status']}。★ 2026-09-09 网页版 GPT-6 Pro 裁决(留档 webgpt_ruling_2026-09-09.json): "
                                 f"**新立第 6 条路**, 定义为「验收闸协议的行为性修订(GATE_PROTOCOL_CHANGE)」并给闸独立版本; "
                                 f"第⑤条**保留但重新定位** —— 它是「**启用**新版闸」的条件而非提交门槛"
                                 f"(未经⑤可登记候选修订, 不可当作已验收版本启用); "
                                 f"**新增第⑦条全负例组回归**(「仅收藏」反转正是它要买的东西)。"
                                 f"★★ 且必须随结论同行: **本修法修不到生产分类器**(生产 s2 看不到 negative_examples)。"
                                 f"⇒ 需 owner 定: 立不立 route 6 · 落不落这个修法。**现网一字未动。**"
                                 f" ★★★ **同时未做的一件(我能做, 不卡外部资源)**: "
                                 f"**从没测过真实生产分类器上有没有同一个 suspend 缺陷。** "
                                 f"V0/V1 那轮只测了**验收闸的标注者**; 生产 s2 看不到 negative_examples, "
                                 f"所以那轮**什么都没告诉我们生产是怎么判的**。"
                                 f"做法: 同一批构造题走**真实生产链路**(s1→s2→解析→抽样聚合), "
                                 f"看它在「已决定_延后执行」上判不判 suspend。"
                                 f"要花钱且需**发起前冻结预注册与硬上限** ⇒ 建议与上面两个决定一起定。"
                                 f"原话: 「**不能用修好的 G 替没有改变的 P 宣告修复成功。**」")})

    # ★ 2026-09-04 新发现: 历史解析产物的语音层有已量化的系统性低估
    _sf = os.path.join(ROOT, "tests/data/phase2/asr_silent_failure.json")
    if os.path.exists(_sf):
        _v = _j("tests/data/phase2/asr_silent_failure.json")
        out.append({"类": OPEN, "项": "静默 ASR 失败: 判定已修, 但**规模无法定论**(高人声样本仅 2 份)",
                    "证据": ("**判定已修**为 speech_status 五态。"
                             "★ 规模我先前报错了: 用**绝对字数**外推「约 31 份」是**错的** —— "
                             "138 份里 108 份是短视频里的**正常**转写(时长中位 14.6 秒)。"
                             "按**字/秒**正确界定: 全集 31 份短转写, 高人声仅 **2 份** ⇒ "
                             "静默失败**存在但罕见**, 我放大了约 15 倍。"
                             "★ 回填已跑(对照组 10/12 重跑正常, 环境无问题), 但高人声样本 n=2 < 8 "
                             "⇒ **INSUFFICIENT**, 无法回答「是那轮坏了还是模型对这类素材不行」。"
                             "要定论需**更多高人声空转写样本** —— 现有素材里就这么多, "
                             "属于**素材限制**而非我没做。")})

    _src, _cov = _ablation_coverage_now()
    out.append({"类": OPEN, "项": "消融判决表已补工况并拆词, **覆盖率现算: %s**" % _cov,
                "证据": ("★★★ 2026-09-11 覆盖率**由本脚本从 %s 现算**, 不再硬编 —— "
                         "此处原写死「只覆盖 17.3%%」且指向 v2, v3 落地后**它永远不会自己更新**。"
                         % (_src or "(判决表缺失)")) + ("★ 2026-09-06 两轮消融(88 agent)后重判, 见 tests/data/ablation_verdicts_v2.json。"
                         "**`DECORATIVE` 这个词已废除** —— 它合并了两种处置相反的东西。拆成: "
                         "**NO_CONSUMER**(真死, 换工况也不活) **6 条** / "
                         "**UNREACHABLE**(本工况不可达, 必须写明什么条件下会活) **7 条**。"
                         "★★ 重判后 13 条原「装饰」里**真能删的只有 3 条** —— "
                         "audio.capabilities 与 prosody 真没消费者但**该接线不该删**(那个数已经算出来了, "
                         "就在两行之外写进零读者字段); sesoi 的产出**就是一次拒绝**, 删了读者会以为问题已被回答。"
                         "⇒ 故 `deletable` 是**独立字段, 不由 verdict 推导**(有闸钉住这一点)。"
                         "★ 工况已实测并**在测试时重新实测**: market=intl(cce_full_run.py 硬编) · "
                         "compliance_profiles 只有 agent_memory 一个 key · k∈{3:61, 5:2} · 三份语料 sha。"
                         "一旦漂移(如有人拿掉硬编 --intl), 依赖它的判决**当场失效**, 闸会红(已实测双向触发)。"
                         "★ 仍未完成: ① 覆盖面(现算见上)仍有大片空白 —— "
                         "生产主链 s0/s2/s3 全空(含 playbook_primary) · knot_taxonomy.json 从未消融 · "
                         "**accuracy/ 整目录(九结验收闸本身)因零 API 纪律被结构性排除, 两轮从未测过自己的验收标准** "
                         + ("★★★ 2026-09-11 **这一块已部分解开**: 离线隔离装置建成"
                            "(probes/accuracy_offline_harness.py, **先设环境再 import**, "
                            "替换点是被测代码实际查找的 `urllib.request.urlopen`), "
                            "五种失效定向测试**全过**, 4/4 变异**全被检出且都确认走到目标路径**。"
                            "★ 状态 BLOCKED_TESTABILITY → **PARTIALLY_VERIFIED_OFFLINE**。"
                            "★★ 但**只解了「离线软件验证」这一层** —— 真实 provider 的语义判断准确率与"
                            "重复稳定性、G-K2 链路、main() 端到端编排**仍未验证**。"
                            "见 tests/data/accuracy_directed_tests.json。"
                            if __import__("os").path.exists(
                                __import__("os").path.join(ROOT, "probes/accuracy_offline_harness.py"))
                            else "★ 尚未解开。") + 
                         "② 3 条 ksep 判决因审计期间语料被并行 agent 污染(+948/−316 行)**需重跑** "
                         "③ 7 条 UNREACHABLE 要判死活, 得**补对应工况的语料**(中文出站 / agent_memory 投料 / R=3 / "
                         "放行 weight), 在存量语料上永远判不了。")})

    # ⑦ 卡在外部资源上的
    out.append({"类": OPEN, "项": "语义 SESOI 无锚点 —— **渠道已解, 卡在发不发**",
                "证据": ("需 >=3 名人类评分者(5x60 设计已定); SESOI 现为 None 且有三处测试钉住。"
                         "★ 2026-09-04 owner 质疑后更正**从 BLOCKED 降为 OPEN**: 我先前把「招盲评人」"
                         "与「A/B 发帖」压成一件事, 再拿**推广**的门槛去卡**征集研究参与者**, "
                         "参照系从一开始就错了。实际渠道 **r/SampleSize**(2012 年建, 约 2.6 万成员)"
                         "社区信息面板明写「任何人均可在此社区中浏览内容、发帖和评论」⇒ **无 karma/号龄门槛**; "
                         "且其规则第 1 条**要求**正文带调查链接 ⇒ 外链在该板块是**格式要求**而非推广信号, "
                         "与我先前记的「对外链敏感」方向相反。"
                         "标题须为 `[Academic] 主题 (人群)` 形式; 允许 24h 后带 [Repost] 合规重发 "
                         "⇒ 攒够 n>=3 靠**拉长周期**而非加密频率, 恰好避开旧死因。"
                         "★★ 但同轮 GPT 调研指出一条我**完全漏掉**的约束, 属**测量效力**不是渠道便利: "
                         "SESOI 要的是「≥3 名**互相独立**的盲评人」, 而 Reddit **无从核验独立性** "
                         "(没有任何可去重的参与者标识) ⇒ 照 Reddit 路线做, 我能报的只是"
                         "「3 份来源不明的提交」, 却会写成「3 名独立盲评人」—— **又是把「查不了」写成「查过了」**, "
                         "而这条基线是要当**仪器标定证据**用的。"
                         "⇒ owner 的取舍: **付费池换可核验独立性**(Prolific / CloudResearch Connect / "
                         "Testable Minds, 均有唯一参与者 ID, **待核**) vs **免费但独立性只能声称**; "
                         "后者若采用, 读数里必须写明「参与者独立性未核验」且**不得**用它钉 SESOI。"
                         "★★ 2026-09-05 owner 拍板, **不走付费池**: 「拉人参与使用这个项目, "
                         "然后说明哪个问题没有被证明, 需要人帮助」⇒ 招募改为**开源参与**而非问卷。"
                         "已落地 `OPEN_QUESTIONS.md`(对外, 英文): 只列**陌生人真能帮上而我真做不了**的两项 —— "
                         "①语义距离人类基线(36 对, 约 10 分钟) ②社媒音轨逐字标注。"
                         "★ 独立性按**如实降级**处理: 文档明写将报为「n 份来自可公开识别账号的提交, "
                         "**distinctness not verified**」, **绝不**报「n 名独立评分者」—— "
                         "并由 test_cce_open_questions_numbers 反向钉住(拿掉这句限定即判红)。"
                         "⇒ 阻塞项只剩**发布是人工按钮**, 那是 owner 的动作。")})
    out.append({"类": BLOCKED, "项": "内容 A/B: **设计已改好, 卡在发帖序列**",
                "证据": ("★ 2026-09-04 调研后更正: 原判断「所需样本超单帖历史最高浏览」的**隐含前提**是"
                         "「实验单位 = 一篇 post」。改成**一系列 post** + 跨 post 随机化 + matched block + "
                         "分层模型估 μ_β 后, 每篇只需几十/几百曝光。"
                         "★ 顺带纠正我原以为能省样本的两条: **等价检验反而更费**(margin 窄则 n 急增); "
                         "sequential 只省 expected n 不省 max n。"
                         "⇒ 设计问题已解决, 但**实施需要真实发一系列帖并随机化** —— 那是产品侧的事, 我做不了。"
                         "★ 2026-09-04 owner 截图更正: 当前在用的账号(注册 2026-08-03)**至今存活**, "
                         "封禁史属于**另一个**已停用的号 —— 我先前把两者混了。"
                         "★★ 2026-09-04 owner 再次更正 —— 我上一版的两条渠道论断**都不成立**: "
                         "① 拿 **r/ClaudeAI 的 karma 门槛 50** 当约束是**参照系错误** —— CCE 是**开源测量仓**, "
                         "不是 Claude 的产品, 那个板块从来不是它的自然去处, 它的门槛也就不约束本项目; "
                         "② 「帖子数 0 ⇒ 休眠→突发」把「0 主题帖」读成了「0 存在感」—— 旧死因的指纹是"
                         "「**近乎休眠**的号**突然**规律化日更」, 而该号有 1 个月连续在场 + 31 条评论, "
                         "并在其已持续参与的板块有**被 OP 采纳**的实证记录; 在自己已在评论的板块发第一个主题帖"
                         "是**正常轨迹**, 是 dormant→burst 的反面。"
                         "⇒ 真正仍成立的约束只有**序列形状**(规律化+单板块+推广链接+profile 指向自家域名 四者同现), "
                         "manipulation 选不涉推广的维度即拆掉最重的一件。"
                         "★★ 2026-09-05 owner 委派我定板块, 我的裁定: **现在不跑 Reddit A/B**。"
                         "理由不是风险是**测量效力** —— 每个候选板块都带一个我**观察不到**的闸"
                         "(r/opensource 的 Automod 数值未公开 · r/programming 的系列频率上限 UNKNOWN · "
                         "r/LocalLLaMA 的 10% 比例属版主酌情), 而**能静默移除帖子的板块测的是审核过滤器**, "
                         "不是 manipulation: 帖子被移除会把曝光与互动同时打到 0, 我**无法区分**"
                         "「manipulation 不管用」与「这帖被删了」—— 这是**混淆**不是归零, "
                         "比归零更难发现(归零至少触发非退化闸, 混淆不会)。"
                         "★ 且 A/B 不是现在最缺的证据: 所有阈值都建在 SESOI 上而 SESOI 现为 None, 顺序反了就是白跑。"
                         "⇒ 建议路径: 一次**单帖可行性探针**(非序列)投 **r/programming**, "
                         "内容是讲负结果的真实技术 write-up, **链仓库不链评分工具**(该板禁 survey), "
                         "发后用**登出视角**复核可见性; 可见才谈序列, 被静默移除则该板不能当实验容器 —— "
                         "这条信息本身就值这一帖。★ 探针通过后账号即有真实发帖史, 那条约束自解。"
                         "见 tests/data/phase2/ab_design_feasibility.json")})
    # ★ 2026-09-04 更正: 这一项**曾被我误判为 BLOCKED**。
    #   我把「需要英文标注素材」读成「需要**本域**的标注素材」, 而本项目自己的分解是
    #   能力=域无关 / **抽取质量=语言相关** / 标定=域相关 ⇒ 公开英文基准就是正确的素材。
    #   实测可得: LibriSpeech(CC BY 4.0, openslr 直链 200) · TextOCR v0.1(CC BY 4.0, 逐图 CDN 200)。
    #   ⇒ 已完成, 不再列入未完成清单。留这段注释防止下一个人再把它归回 BLOCKED。
    _need = {"OCR": "tests/data/phase2/ocr_quality_en.json",
             "ASR(GEN1)": "tests/data/phase2/asr_quality_en.json",
             "ASR(GEN2 分层)": "tests/data/phase2/asr_quality_en_gen2.json"}
    _missing = [k for k, v in _need.items() if not os.path.exists(os.path.join(ROOT, v))]
    if _missing:
        out.append({"类": OPEN, "项": "媒体抽取质量(英文)未完成",
                    "证据": f"缺 {', '.join(_missing)}。语料已核实可匿名直下, **不是外部阻塞**"})
    # 已完成的部分仍有未测的一角, 单列出来防止被「英文测过了」一句话盖住
    # test-other 已于 2026-09-04 补测(均值 11.61%, 4.96x 于 clean)。
    # 仍未测的是**自发语音**与社媒音轨那一档 —— 前者语料受限(TED-LIUM3 是 CC BY-NC-ND),
    # 后者根本没有带逐字标注的公开集。这两条形状不同, 分开记。
    if not _missing and not os.path.exists(
            os.path.join(ROOT, "tests/data/phase2/asr_quality_en_other.json")):
        out.append({"类": OPEN, "项": "英文 ASR 仅测了 test-clean", "证据": "test-other 未测"})
    out.append({"类": BLOCKED, "项": "ASR 在**社媒音轨**上的真准确率未测(已有可证上界 + 曲线定位)",
                "证据": ("★ 2026-09-04 补: 用**第二个独立引擎**(faster-whisper small, Apache-2.0)在 18 份"
                         "真实社媒音轨上做跨引擎一致性, 中位 **0.475** ⇒ 由 a+b<=1+p 得"
                         "**至少一个引擎的匹配率 <= 0.738**; 对照 LibriSpeech 的 ~0.977 ⇒ "
                         "**朗读语音的数确实高估了本项目素材**(此前只能靠推测说这句话)。"
                         "★ 2026-09-04 再补: **受控退化曲线**(TTS 合成已知文本 + 噪声/压缩, "
                         "84 条 × 7 音色, 无退化 CER **0.0**)给出真 ground truth 的上界曲线, "
                         "并把真实素材**定位到了曲线上**: 非人声占比中位 0.491 ⇒ 等效 SNR ≈ **0.2 dB**, "
                         "而曲线恰在 SNR=0 dB 处 CER 跳到 **0.13**(10dB/5dB 仍 0.00)。"
                         "⇒ 本项目素材落在曲线开始塌的那一点。★ 0.13 是**下界**(高斯噪声≠音乐, TTS≠真人)。"
                         "★ 顺带的工程结论: **MP3 降到 16kbps 仍 CER 0.00**(见证证明压缩施加了) ⇒ "
                         "压缩不是问题, **该花力气的是降噪/源分离而非保码率**。"
                         "★ 但一致 != 准确 —— 真准确率仍未测。"
                         "朗读语音(test-clean 2.34% / test-other 11.61%)已测, 但社媒音轨有 BGM/压缩/重叠, "
                         "比两者都难 ⇒ 现有数**对本用例仍是乐观值**。"
                         "缺的是**带逐字标注的社媒音轨素材** —— 公开集没有; "
                         "TED-LIUM3 虽可补自发语音但许可是 CC BY-NC-ND(非商用)。")})
    # ★ 2026-09-04 实际去做才确认: 这不是「没装」, 是拿不到凭据 ⇒ 从 OPEN 改归 BLOCKED。
    # ★ 2026-09-04 更正并**完成**: 这一项曾被我记为 BLOCKED(「拿不到 HF 凭据」), 两处错 ——
    #   pyannote.audio 是 MIT 开源**包**(受限的是权重), 且 3D-Speaker 的默认路径根本不碰那些权重。
    #   已接入并实测(VoxConverse DER STRICT 0.1004 / LEGACY 0.0338, CPU RTF 0.133)。
    #   剩下的是**重叠语音检测**, 那一条才真的要 pyannote 受限权重 —— 形状不同, 单列。
    out.append({"类": BLOCKED, "项": "**重叠语音**检测(说话人分离的其余部分)",
                "证据": ("说话人分段本身已做(3D-Speaker, 无 token, DER STRICT 0.1004)。"
                         "但 include_overlap=True 需要 pyannote/segmentation-3.0 —— "
                         "HF **受限模型**, 需账号接受条款并给 token。"
                         "★ 2026-09-04 逐个查过非受限替代: pyannote/overlapped-speech-detection 与 "
                         "Revai/reverb-diarization-v2 同样受限; tezuesh 与 Den4ikAI 两个转存虽非受限, "
                         "但**许可未声明**且下载仅 17/28 次(未经审的镜像)。"
                         "**许可未声明 ≠ 无限制** —— 没有声明就是没有授权, 商用产品线不可用。"
                         "⇒ 解锁动作: owner 提供 HF token 走**官方渠道**, 而不是找镜像绕过。"
                         "★ 不拿源分离的能量占比冒充说话人数, 也不拿 DER 给说话人数背书。")})
    # ★ 2026-09-03 查完改判: 这不是「待修的分叉」, 它**就是那次退役本身**。
    #   origin 独有的文件全是 mt_*(Hy-MT2 MT 实验), 本地提交 b33befd
    #   "retire Hy-MT2 MT experiment" 删掉了它们, 归档在
    #   /Volumes/data/archive/hymt2-retired-20260817/。
    #   **合并 = 复活退役代码** —— 正是本项目栽过三次的「拿退役组件当现行标准」。
    out.append({"类": DECIDED,
                "项": "与私仓 origin 的分叉**不合并** —— 合并会复活已退役的 Hy-MT2",
                "证据": ("origin 独有文件全是 mt_*; 本地 b33befd 已退役并归档于 "
                         "archive/hymt2-retired-20260817。私仓另带 PII 且非生产入口, 亦不推。")})

    # ⑨ 2026-09-10 候选代那两轮留下的三件 —— **从留档现读, 不硬编码状态**
    #    ★ 这三件本来一件都没进清单, 是我口述报给 owner 的。「还差什么不由我口述」这条铁律
    #      **只在旧条目上生效了, 新条目又走回口述**。⇒ 接进来。
    try:
        dev = _j("tests/data/DEV-001-budget-overrun.json")
        bg = _j("results/.request_budget.json") if os.path.exists(
            os.path.join(ROOT, "results/.request_budget.json")) else None
        fixed = os.path.exists(os.path.join(ROOT, "scripts/cce_request_budget.py"))
        out.append({"类": DECIDED if fixed else OPEN,
                    "项": "跨轮请求预算闸 —— DEV-001 的机制缺口" + ("**已补**" if fixed else "**未补**"),
                    "证据": (dev["★每份引用本结果的报告要带的一句"] +
                            (" ★ 已落 scripts/cce_request_budget.py, 六条离线自检全过(假请求, 零真实调用): "
                             "上限后拦住且不产生调用 · 重启不清零 · 四进程并发抢 10 个只放行 10 个 · "
                             "失败请求仍计数 · 改大旧上限被拒; 反向验过**包错层**会少算。"
                             "★★★ 但**补闸不产生任何放行资格** —— 恢复真实请求需 **owner 新开一张授权单**。"
                             if fixed else " ★ 尚未代码化, 下次仍会静默超支。"))})
    except Exception:
        pass
    try:
        rv = _j("tests/data/assertion_review_v2_offline.json")
        # ★★★ 2026-09-13 **由 BLOCKED 转 OPEN**: owner 明确「P1–P4 仍归你, 也做了吧」⇒ 授权代定。
        #   把已经解开的东西继续挂在 BLOCKED 上, 与「把 BLOCKED 混进 OPEN」是同一种误导的两个方向。
        out.append({"类": OPEN,
                    "项": "★ display 对象域**已定**(2026-09-13 owner 授权代定 P1=只含物) —— 剩下的是**实现**",
                    "证据": ("原问题: " + rv["⑥★★★新增的 owner 待决项"]["问题"] +
                            " ★★★ **已裁定**: P1 = **只含物**(产品/使用体验, 不含选购/决策过程), "
                            "留档 P1_P4_DECIDED_2026-09-13.md, 并钉住「这是**授权代定**、owner 随时可推翻、整体作废重来」"
                            "(tests/test_cce_p1_p4_decided.py)。"
                            " ★★ 随之做完的: 2026-09-10 **按类**撤销的 8 条 display 断言**逐条重判** ⇒ "
                            "**恢复 6**(落乙·文本内正面反证, 每条能指名原文片段且代码逐字核过) / "
                            "**维持撤销 2**(落丁·指不出片段), 断言表 74→80 "
                            "(probes/withdrawn_display_assertions_reclassify.py 现算)。"
                            " ★★★ 2026-09-14 **P2 与 P3 已落成可核谓词**: "
                            "scripts/cce_label_qualification.py —— P3 的第 ③ 档(未确认候选)与 "
                            "P2 的同一对象绑定都做成了 **fail-closed 的机器可核判据**, "
                            "并由 citable_as_confirmed() 把**仪器层与合同层两道**合成唯一入口"
                            "(两道理由分别给出, 不合并)。反向 7/7 判红 + 空操作对照无伪阳性。"
                            " ★ 关键取舍: 它**一个字都不进 prompt** —— gen9 实测把合同文本塞进生产 s2 prompt "
                            "会让 display 由 1/80 涨到 40/80 且倒挂 ⇒ 用 prompt 教模型守合同是**已被测出会让读数更偏**的路。"
                            " ★★★ **仍未做, 所以留在 OPEN 不是关闭**: "
                            "① 谓词**有了生产调用方**(★ 2026-09-23 授权代定): cce_full_run.s2 对 top-1 结调 qualify()/is_citable_as_confirmed(), 产出 `label_qualification` 诊断字段(状态恒候选, citable 恒 False, 附 evidence_quote 逐字核), **不改判决**(tests/test_cce_s2_label_qualification_wired.py)。 "
                            "② **证据片段的产出方已定**(同日代定): = s2 模型的 evidence_quote(本来就在产出里, 此前从未核过是否逐字在原文); 但 s2 协议不给「支撑哪一支 + 关于哪个对象」⇒ 资格层**结构上只能给候选**, 升格要走 r2 式引用证书协议(另立预注册)。★ 引用证书协议进生产: **2026-09-24 已预注册**(tests/data/citation_certificate_production_prereg.json: 影子段 s2b, n=2 一致才升 ③′, 上限 88 次, 判决线冻结), 未执行未接线。 "
                            "③ 不做**别名归并**是 fail-closed 的选择(漏判而非误判)。★★★ **2026-09-14 已实测, 代价比预想的大一个量级**: 16 次真实调用里模型交出的 **5 张证书全部**因两支 about 不同被拦, 而真实差异不是别名(「the Oticon」vs「Oticon」)而是**粒度** —— 模型填的是「X **的某个方面**」(「Oticon More 1 助听器**的电池续航表现**」vs「Oticon More 1 助听器」)。⇒ 这是别名问题的**超集**, **正证据对照 0/4** 全军覆没(results/extractor_counterexample.json, 判决 DEGENERATE_ON_CONTROLS)。★ **不许**由此放松 P2 —— 放松会把对象错配那一格重新放进来, 而那正是 P2 存在的理由。★ 该修的是**采集协议**: 要求 about 也是**原文逐字片段**, 让比较落在文本内而不是措辞上。 ★★★ **2026-09-14 r2 已跑完**(新预注册 · 16/16 · 三轮零调用对抗评审 27 agent 后定稿): **对照臂 4/4 交卷 · 2/4 通过** ⇒ r1 的 DEGENERATE **确证是仪器伪影**, 「让模型签发引用证书」这条路**走得通**, 那条「第二次退化即路线终局」的冻结条款**不触发**。 ★★★ 但阴性 **12/12 全部由抽取器自己拒答** ⇒ **资格层一次都没被 exercise** ⇒ 「**验证器会拦住形式合规、语义错误的证书**」这句话**仍然零证据**。本轮买到的是「抽取器不太上钩」, **不是**「验证器守得住」—— 两者不可互换。 ★ 承重臂(缺P)p_challenge **无分母**(0/3 被裁决) ⇒ 0 不代表安全, 代表没测到。 ★ **新发现的通道特性**: 模型给**多于必要**的证据时, P2 对**全部**被采用证据求对象集合 ⇒ **多给反而被拦** (POS-2 额外给 'TV Connector' · POS-3 额外给 'aids', 都是原文里真实的其他物件, 不是方面名词)。协议从没说「每支给一条就够」。**不改判据重算**(已有读数, 改就是调参), 留作下一轮输入。 见 results/extractor_counterexample_r2.json 与 tests/test_cce_extractor_r2_result.py。 ★★★★ **2026-09-14 r3 重复测量把 r2 的结论推翻了一半**(同一份执行器代码 · 同一提示词 sha 7a8f9417 · 同一模板 · 同一种子, 只隔几小时): **15 个比对点翻了 6 条, 一致率 60%**(UNSTABLE_6)。 ★★★ **MIS-4 从正确拒答翻成 UPGRADED** —— 真实模型交出了一张**形式合规、语义错误**的证书并**穿过整套机械验证器**(A 支 span='What I actually wear is an old pair from before all this' · object='an old pair' · kind='使用细节'; span 逐字 ✓ object 逐字 ✓ 两支同对象 ✓ kind 在枚举内 ✓ 残余超阈值 ✓)。语义上它**没给出关于那副旧机的任何陈述**, 只是指认了对象 —— 正是库内那条「不能把对象相关的事实当作关于对象的信息增量」。⇒ 零调用反例证明该通道**存在**; r2 证明抽取器**大多数时候拒答**; **r3 证明它会走**。n=1, 只证存在性不证频率。 ★★★ 且 r2 那条「模型多给证据导致被拦」的机制解释**是运气不是机制** —— POS-2/POS-3 这次都翻成 UPGRADED。 ★ 稳的是: 否定Q 4/4 · 缺P 3/3; 不稳的全在**对象错配臂(3/4)与对照臂(3/4)**。 ★ temperature=0 不保证确定性, k=6 **不能单独归因于模型随机性**(也可能是服务端变更), 本轮区分不了; 但两种原因下结论相同: **r2 的逐条读数不可作为单次定论引用**。 ★ r2 结果文件已**加注未改数**(预注册明禁改)。见 results/repeat_measure_r3.json。 ★★★★ **2026-09-14 验证器盲区已量化**(零调用, 未动预算): 按五类语义关系建最小对照(每对两版**只在目标关系上不同**, 各配一张**形式完全合规**的证书), 现有验证器 **10/10 全部错误放行**, **对照 10/10 有效**(pos 版全过 ⇒ 没有退化格)。逐类: 否定辖域 2/2 · 归属 2/2 · 时态 2/2 · 引用层级 2/2 · 类型成员资格 2/2。★★★ **其中 6/10 是合同明文支持的判定**(「谈论对象是**自己**已拥有或已经历的」「若谈的是**期望中未得之物**→itch」) ⇒ 那三类的漏**没有任何解释空间**。 ⇒ 这把 2026-09-13 的零调用反例从「**存在**一个漏洞」量化成了「**五类全漏, 三类无争议**」。 ★★★ 度量的**灵敏度已用镜像变异实测证明**: 加一条「只拦否定辖域」的规则后, 合计 10/10→**8/10**、否定辖域 2/2→**0/2**、**其余四类一个没动** —— 合计看起来像进步, 逐类表立刻拆穿。这正是库内「补一类会留着其余四类却**制造『已关住』的错觉**」的实测演示, 也是「**分别看五类而非总正确率**」为什么是对的。★ **真加否定词正则仍然被禁**。 ★ 边界: 它测的是**验证器的盲区**, **不是模型的错误率**(证书是手构探针不经模型); 分母是构造对照**不是自然语料**, 不得当误报率。 ★ **下一步(未做)**: 把结构显式化到六槽位(说话者/对象/谓词/否定辖域/时间/引用层级), 状态含**证据不足** —— 这份 10/10 就是它的**基线对照**。 见 results/semantic_blindspot_scan.json 与 tests/test_cce_semantic_minimal_pairs.py。 ★★★★ **2026-09-14 命题框架层已建**(零调用, 未动预算): scripts/cce_claim_frame.py —— 六槽位(说话者/对象/谓词/否定辖域/时间/引用层级) + 三态(支持/反驳/**证据不足**), 出口走库内**乘性因子链**纪律(任一必要条件不被支持 ⇒ 整体不许输出)。 **同一批 10 对上: 现有资格层 10/10 漏 → 只用合同明文 4/10 → 明文+解释 0/10, 对照始终 10/10 有效。** ★ **合同明文本身买到 6/10**(否定辖域/归属/时态全拦), **剩下 4/10 必须靠解释**(引用层级/类型成员资格) —— 这个分界从**判据侧**独立得出, 与最小对照的依据分层**完全吻合**。 ★ 两档**分开报不许合并** —— 合并会让「靠解释拦住的」**冒充**「合同支持的」。 ★★★ possession 单列一个槽位: 合同的 Q 是**析取**, BOTH_NEGATED→反驳 / **ONE_NEGATED→证据不足**(库内 2026-09-10 最值钱的教训: **沉默不是否定**); 缺槽位一律落证据不足, **不许靠常识补成反驳**。 ★★★ **变异实测逼出两个真发现**: ① polarity/possession/time 三条规则在端到端对照上**互相冗余**(删任一条结果一点不变, 而冗余是**语义上真实共现**不是标注错误); ② **ONE_NEGATED 分支完全零覆盖** —— 把「沉默」改判成「否定」, 10 对最小对照**一个都没红**。 ⇒ 修法是**分工**: 最小对照测**端到端上界**, **规则级单元测试**测每条规则单独是否在起作用。第二轮变异复核 **7/7 全部被抓到**。 ★ 通则: **冗余保护会让闸看起来绿, 而其中某条规则其实从未被测过。** ★★★ **边界**: 这是**能力上界** —— 数是「**槽位标注正确时**判据能拦住多少」; **槽位由谁填、填错多少是另一个未测的问题**; 本层**不承诺**结构化抽取会正确, 只把错误**挪到可逐项检验的地方**。**新增一道不替换**现有资格层, 且**未接进生产**(接线要先解决「槽位由谁填」)。 见 results/claim_frame_upper_bound.json 与 tests/test_cce_claim_frame.py(15 项, 7 项规则级)。 ★★★★ **2026-09-14 已把 r1/r2/r3 已付费的 48 次调用回放到新层**(零调用, 边际成本为零 —— 库内纪律: 冻结环境+录制回放优先于全量重跑, 定向复验优先于无目的复跑)。15 张真实证书(阴性 3 · 对照 12): **只用合同明文 阴性拦住 1/3; 明文+解释 3/3; 对照误拦 0/12**(★ 误拦比漏更糟, 它会让整层不可用)。 ★★★★★ **头条 —— 这是一个要交给 owner 的具体问题**: **r3/MIS-4 是唯一一次真实模型产出、穿过整套验证器的语义错误证书**(旧层给的是 UPGRADED)。回放显示: **只用合同明文 → 仍放行; 明文+解释 → 拦住**。拦住它的那条规则依据是**附件 A**(「增量必须是不能由公开标识本身推出的陈述」), 而附件 A 出自 OWNER_DECISION_SHEET.md, 原文明写「**这条是我的提案, 可以被你推翻**」。⇒ **要不要把它升成合同? 不升, 合同明文就拦不住真实发生过的那次错误。** ★★★ 回放还抓到**我自己一个 fail-open 的默认值**: 标注档案原默认 possession='OWNED' —— r3/MIS-2 的文本是「诊所展示机…**Mine** are a much older pair」, 说话人对「有没有用过那台展示机」**沉默**, 而默认把它补成了 OWNED, **等于替模型补了一个文本不支持的槽位**。⇒ 默认改**全 UNSPECIFIED**(漏标落证据不足, 不落支持), 修正后阴性 2/3→3/3。★ 通则: **默认值是 fail-open 还是 fail-closed, 比判据本身更容易被忽略** —— 判据写得再严, 一个肯定型默认值就能绕过去。 ★ 边界: 证书是**真实的**, 但**六槽位标注仍是我做的** ⇒ 仍是**标注正确时的能力上界**; **「模型自己填槽位会填成什么样」仍未测**, 那要花预算。 见 results/claim_frame_replay.json 与 tests/test_cce_claim_frame_replay.py(7 项, 变异 4/4 被抓到)。 ★★★★★ **2026-09-14 r4 已跑(第四张预算 20/20, 合计 68 次)**: 让**模型自己填六槽位**, 与已冻结金标比对。零失败、零非法取值、可用 20/20、无降级。 **三臂: 金标(上界) 阴性放行 0/10 · 零基线(完全不读文本的常数填充) 10/10 · 模型 2/10** ⇒ 模型**确实在读文本**, 但标注误差有实际代价。 ★★★ **逐槽位把真东西暴露了**: speaker 20/20 · polarity 40/40 · time 20/20 · citation 20/20 (**四个「表层语义」槽位全满分且优于零基线**); 而 **predicate 18/20 = 零基线 18/20(零增益)** · **possession 14/20 < 零基线 16/20(负增益)**。**端到端漏掉的那 2 条正好是 TYP-1/neg 与 TYP-2/neg —— 类型成员资格, 也就是 predicate 那一格。** ★★★★ **三条独立线索在这里闭环**: r3 那次唯一的真实语义错误证书(MIS-4)问题出在 predicate; 回放显示它**只有依赖解释的规则**拦得住、合同明文拦不住; r4 显示模型填 predicate **与不读文本持平**。⇒ **判「这段增量是不是所声明的那一类」这件事, 模型做不了, 而合同又没定义它。** ★★★ **但不得读成模型能力差** —— 提示词给了 kind 名字却**从不定义**五类成立条件; 金标那两条依赖的是**项目自己的解释**且自带推翻条件 ⇒ 它测的是「**与一份没给模型看的解释的一致度**」。**不是模型判不出, 是没人告诉它判据是什么**, 而那份判据(附件 A)至今仍是 owner 可推翻的提案。 ★ 投料前 8 agent 零调用评审救回来的: 最要命一条**三个 agent 独立报到** —— 金标取值极度倾斜(38:2), **完全不读文本的常数填充能拿 206/220=93.6% 而阴性 10/10 全漏, 四条降级一条不响**。已修六条(加零基线臂+D5 · 非法取值剔出分母+D4 · predicate 补枚举校验 · 敏感格由判据源码现算 · 两档都跑 · 提示词去 supports 泄露), 变异实测 **9/9 全抓到**。 ★ **本轮暴露但不得事后补的缺口**: D5 只看端到端, 逐槽位的零增益/负增益**现有降级一条没响** —— 登记为下一轮预注册要加的降级, **不在本轮补**(测量后改判据=调结果)。 ★ n=1 每条零重试; r3 实测同一仪器重测一致率仅 **60%** ⇒ **本轮每个数都是单次运行读数**。 见 results/slot_filling_r4.json 与 tests/test_cce_slot_filling_r4.py(16 项)。 ★★★★★ **2026-09-14 owner 裁定: 附件 A 升为合同**(零调用, 生产**不换代**)。★★★ **升之前先拆**: predicate 那个槽位**混了两条依据不同的规则** —— **RESTATES_IDENTIFIER**(只复述/指认标识 ← **附件 A** ← **现为合同**) 与 **NOT_OF_DECLARED_KIND**(不属于所声明的那一类 ← **五类各自的成立条件** ← **仍是解释**)。拆之前两条混在同一个取值里, **一升就会把没升的那条一起当成合同**。★ 我先前笼统说「拦住 MIS-4 的依据是附件 A」**不够精确, 已更正**。 ★★ **行为证据(都现算)**: 上界(最小对照)**逐字不变** 4/10 → 0/10; 回放「只用合同明文」阴性拦住 **1/3 → 3/3**; 对照误拦 **0/12 不变**; **r3/MIS-4(唯一一次真实的错误升格)现在合同明文就拦得住了**。 ★ **裁定依据是 owner 的决定, 不是读数** —— 三条实测线索只是促成提问。 ★ **生产一个字没动**: 改动件一件都不在 core_files/parser_plane, instrument_hash 未变, instrument_generation 仍 6; 本次只作用于**判据层**, 而该层**一个字都不进 prompt**。 ★ **代价照旧且现在是合同的代价**: 更严, 「说了个型号但没给任何该型号的具体信息」落进未决, **覆盖率下降**。 ★★ **缺口**: **最小对照对附件 A 零覆盖** —— 升了合同但那套测不到它(五类里没有一类依据它), 该补一对「只复述/指认标识」的对照; **本轮不补**(金标已冻结且已用于 r4)。 ★ 回滚点 scratchpad/backup-annexA-20260914-233803/; 闸 tests/test_cce_annex_a_is_contract.py(7 项, **重点守「没升的那条不许一起升」**, 变异 9/9 全抓到)。 ★★ 顺带: 「拒答难度梯度」那版设计**已否决且从未投料**(断点判据按模型填哪个 object 分叉 · 轴实算不成立 · 「L1–L3 只依赖合同」是假声称 · main() 跑完 16 次后必 KeyError 而 12 道闸没一道碰过它 · 第四次「假保证」: 分叉执行器后旧闸只守旧文件), 留档于 tests/data/refusal_gradient_prereg_r3.json。 ★★★★ **2026-09-15 附件 A 已可被观察到**(零调用, 未动预算, 合同一个字没改)。升合同那天登记的缺口是「五类最小对照里没有一类依据附件 A ⇒ 上界 4/10 → 0/10 逐字不变」—— **一条看不见的合同条款, 与没有这条条款, 在读数上无法区分**。本轮新增 **contract_pairs**(ANX-1/ANX-2, 标识复述), **与那 10 对并列不合并**: 合并要往 r4 按 sha8 **5a018edd** 钉死的冻结金标里加条目, **等于事后改已付费那一轮的基准**; 所以槽位标注**自带在对里**, 冻结金标与 pairs 那 10 对**逐字节未动**(由闸机械把住)。**读数**: 现有资格层(形式验证)在这两对上 **2/2 全漏**, 新判据层**两档都 0/2**、对照 2/2 —— **两档相同**说明它确实被当成合同明文而非解释。**镜像变异 12/12 全抓到**, 最要紧的一条是「把附件 A 降回解释档」(模拟裁定被撤销) ⇒ 明文档 **0/2 → 2/2 漏**; ★ 另补两条**精准变异**验弱断言本身会响(差异撑大但 span 仍逐字 / 保持 3 条但换掉「恒拦」) —— 上一轮吃过亏: **文件见红不等于那一条断言见红**。★★★ **代价**: ① 标注仍是我做的 ⇒ 仍是**能力上界**; ② ★★ **r4 的提示词枚举里根本没有 RESTATES_IDENTIFIER** ⇒ **模型至今没被测过能不能填出这一格**, 这份 0/2 **不得**读成「模型能分辨复述与增量」(已登记进 probes/slot_filling_run_r4.py 源码, **不改提示词** —— 改了已付费的读数就失去对应物); ③ **`pairs` 那 10 对上附件 A 依然零覆盖**, 原登记不撤销。★ 同轮把 r4 暴露的「逐槽位零增益没人管」**制度化**进判据准入第三道: 声明零基线臂的预注册必须带「某敏感槽位准确率 ≤ 零基线 ⇒ 零增益, 不得读成能力」; **不回溯 r4 的读数**(测量后改判据 = 调结果), 且实测**不误伤**现有四份预注册, 变异 4/4 全抓到。见 results/annex_a_coverage.json 与 tests/test_cce_annex_a_coverage.py(14 项)。 ★★★★★ **2026-09-15 r5 草案已否决, 48 次预算未动**(零调用)。为「把已升为合同的附件 A 判据文字给模型看, predicate 还会不会与零基线持平」写了预注册草案, 交 **280 个零调用 agent** 对抗评审(10 维度找缺陷 → 每条 3 视角尝试推翻): **90 条发现, 存活 72, BLOCKING 30**。 ★★★ **决定性理由是信号量**: 金标 A 支 predicate 分布 **20 : 2 : 2**, 零基线填多数类就拿 **20/24**; 附件 A 只定义 RESTATES_IDENTIFIER ⇒ 处理能直接触及的只有 **2 格**, preflight 现算**最优单侧 p = 0.25, α=0.05 下事前即不可达**。★★ 更要命: **D6 判不动** —— 在 4 个鉴别格上全对、20 个多数类格上错 4 格的模型, 与完全不读文本的常数填充**拿同一个 20/24** ⇒ **假说为真时也会印出「零增益」**。⇒ **不是问题不该问, 是这个问法买不到答案**; 且它**修不了** —— 要先扩充对照对。 ★★★★ **评审实跑出的第二条, 是我造数据的失误**: 一个零语义纯正则 + 一行 `'aid' in span.lower()` 就能让 D1–D7 **七条降级全部沉默**并产出那一轮要买的结论 —— 因为 24 条 A 支片段里**只有 ANX 两条 neg 含 aid**。 ⇒ 已建 **probes/shallow_cue_arm.py 浅层线索臂**(第三条零调用基线): 零基线答「不读文本能拿多少」, 本臂答「**只读表层字符串**能拿多少」—— **任何臂只有超过它才谈得上读懂语义**。★ 改 ANX 文本消共线的机制**不是删掉线索**(「只复述标识」天然带品类词, 删不掉), 而是**让同一条线索也打中 pos**, 使净增益归零(现跑: A 支合计 **22/24 → 20/24** = 零基线)。★★ **鉴别格仍 2/4, 共线没消干净, 已如实登记**。 ★★★ **我自己的两条假声称被抓到, 已更正不是抹掉**: ① 草案写「ANX 标注已冻结且**已被闸把住**」—— 假的, contract_pairs 的 frames 全仓没有任何哈希断言碰过(**第五次假保证**, 与「改金标一格 14 道闸一道没响」同型), 已钉死; ② 2026-09-15 刚立的判据准入第三道**只认英文键**, 而真实预注册全用中文键 ⇒ **立起来当天机器检查就是空转的**, 已加兜底 + 日期门(不回溯)并堵住「不写 date 绕过」。 ★★ 另修一条真 bug: 执行器打分侧 LEGAL 唯独 predicate 手写、缺 RESTATES_IDENTIFIER ⇒ **模型填对反而被判非法、静默剔出分母, 越答对分母越小**(评审实跑: 连金标臂自己都被剔掉 ANX 两条, D4 不响)。已建 tests/test_cce_executor_legal_enum.py, r4 **显式豁免**但豁免挂在**可现算的事实**上。 ★★★★ **变异实测暴露「断言太弱」第二次复发**: 闸查结果文件 ⇒ 改源码不重跑看不见; 改查源码子串 ⇒ 同一句话 docstring 里还有一份, 子串仍在。**根本修法**: 探针把「计算+构造产物」抽成 build_result(), 闸**现算整份逐键比对** ⇒ 复验 4/4 全抓到。★ 且其中一条变异**当场抓到我自己的失误**(重排键时丢了顶层 date, 基线已红)。 ★ **仍未回答的**: r4 那条 predicate 零增益的诊断(「不是模型判不出, 是没人告诉它判据」)**至今是未经检验的假说**。 ★ **下一版 r5 的前提(本轮未做)**: ① 扩充 ANX 类对照对把鉴别格从 2 提到 ≥5; ② 主判据按鉴别格/多数类格拆开; ③ 两臂提示词逐字冻结钉 sha; ④ 端到端两档分开报(**ANX 信号只能从「只用合同明文」档读** —— 明文+解释档对它是结构性盲的); ⑤ D7 要么给有量纲的度量要么降为附带数; ⑥ 浅层线索臂进对照表。 见 tests/data/slot_filling_prereg_r5_REJECTED.json · results/shallow_cue_arm.json · tests/test_cce_r5_prereg_rejected.py(7 项)。 ★★★★★ **2026-09-15 r5 第二版也被否决, 64 次预算仍未动**(零调用)。修复版把鉴别格由 2 扩到 6、主判据换成「vs 最佳浅层规则」、门 ≥5/6(p=0.0178, confirmatory 可达)、加三个前置条件、提示词逐字冻结钉 sha、LEGAL 从判据层派生、桩自检八态(一刀切/枚举外值/纯正则全被挡) —— 交 **92 个零调用 agent** 投料前评审: 43 条发现, 存活 14, **BLOCKING 10**。★ 41 个验证 agent 撞会话限额, killed 里大量 **0/0 票是未验证不是已推翻**。 ★★★ **决定性的一条**: 主判据的零假设 p0 取自**只搜单 token** 的搜索器 ⇒ 2/6。扩到**标准闭类词表 ≤3 项合取**(族规模 378)后, `含系动词 AND 不含介词 AND 不含程度词` 拿 **5/6 · 误伤 0/24 · 净 +5** 且**通过全部三个前置条件** ⇒ p0 变 5/6, **门在任何 n 下都不可达** —— 第一版被否决的病换了个门回来。**根因是我第三次调整对照集只针对了当时可见的单 token 族**, 句法线索原封不动。 ★★★★★ **由此逼出一个更要紧的发现**: 把那条规则放到 **r1/r2/r3 已付费的真实证书**上 —— **0/2 · 净 0**; 在真实证书上重搜整个冻结族, **最佳净增益也是 0**。⇒ **它是我造的对照集的伪影, 不是自然语言的现象。** 逐条看真实形态才明白根因: 真实的 RESTATES_IDENTIFIER 是「**泛泛提及 / 只指认, 不给关于它的任何陈述**」(r1/NEGP-1 `wearing hearing aids for a good while now` 无系动词含介词; r3/MIS-4 `What I actually wear is an old pair from before all this` 有系动词**也含介词**), 而我造的 6 对 ANX **全部**是「X is Y」教科书式定义句(6/6 系动词 · 5/6 不含介词) ⇒ **那套对照集测的是「定义句 vs 描述句」这个句法区分, 不是合同条款。** ★★ 这**同时否决了两条路**: ① 现在投料(对照集有伪影); ② 用规则代替模型(真实证书上净增益是 0)。 ★★★ **买到的方法论进展 —— 外部锚点**: 「我造对照集 → 搜索器找线索 → 我再改」这个循环**没有停止规则**(在 30 个格上对越来越大的规则族做极大化, 最终能打散任何对照集)。现在有了: **新对照集上冻结族的最佳净增益, 应当接近真实证书上的水平(净 0)** —— 锚点来自 **48 次已付费调用**, 不是我拍的数。配套纪律: 族**先冻结**(标准公开闭类词表 · ≤3 合取 · 禁止自造 · 族规模随产物报), 再改对照集。 ★★ **同轮修掉四条会让 64 次全部白花的工程 bug**: ★★★ `RETRIES=0` 传给 call_model(max_retries=) —— 那是 `for attempt in range(max_retries)` ⇒ **0 表示一次 HTTP 都不发**, 64 条全记成失败而预算照记(已改 1); judge 抛错会连原始 rows 一起丢(r3 同型); B 支 **照提示词填 null 反而被罚**; p0 文件缺失退化成 0 ⇒ 任何 ≥1/6 都印「超过」。 ★ **变异 17/17**, 其中 5 条首轮漏网, 原因是「**断言太弱 / 子串仍在**」**第三次复发** —— 改法照旧: 结果文件与探针**现算整份逐键比对**, 源码断言改用完整片段。 ★ **下一版的八条前提(本轮未做)**: ① **照真实形态重造对照集**(neg 要含介词、句式多样、要有「泛泛提及」), 验收标准是**冻结族最佳净增益接近 0**, 且要留**留出集**防拟合搜索器; ② **n 必须 ≥12**(现算: n=6 时即使 p0 压到 3/6 门也是满分 6/6 零余量; n=12·p0=0.5 ⇒ 门 ≥10/12 余量 2) ⇒ ANX 加到 12–16 对; ③ 前置条件② 是 24 格零容差, 假说为真时一次误报就印「未达成」; ④ 门与 p0 必须冻结, 不许运行时现算; ⑤ 桩自检八态全是退化填充, 缺「**假说为真 + 现实噪声**」那一态; ⑥ 没算过 power; ⑦ ANX-6 依赖 Oticon R 后缀这一厂商知识, 天花板被压到 5/6 余量归零; ⑧ 评审推荐**砍掉 A 臂**(它买的次判据已声明不能下结论), 重造后若要跑**只跑 B 臂**。 见 results/shallow_rule_on_real_certs.json · results/best_shallow_rule_search.json · tests/test_cce_shallow_rule_reality_check.py(13 项)。 ★★★★★ **2026-09-15 r5 已投料 68/68, 零失败。主判据未达成。** **B 臂 predicate 鉴别格 4/24**(门 ≥11/24, 单侧 p=0.885) —— 同批 **最佳浅层规则 6/24 · 手写浅层臂 1/24 · 零基线 0/24 · 金标 24/24**。D6 触发(相对表层线索零增益)。 ★★★★★ **它推翻了 r4 那条诊断**: 「不是模型判不出, 是没人告诉它判据是什么」—— 那条自 2026-09-14 起就是**未经检验的假说**, 本轮检验了, **不成立**: **告诉了它判据, 它还是判不出。** ★★ **这不是「模型摆烂」**: 同一批 68 次里它在其他槽位几乎满分(speaker 68/68 · polarity 136/136 · time 67/68 · citation 68/68) ⇒ **它认真读了**。 ★★ **这不是 power 不够**: 测量前算好的**联合** power 是 q=0.75→0.95 · q=0.65→0.45, 而模型实际每格命中率 **4/24=0.167**, 远低于任何拐点。 ★★★ **更准确的结论**: **不是「模型不如规则」** —— 最佳浅层规则也只有 6/24。而**金标 24/24** ⇒ 这个区分**是可判的**(人标得对), 只是**自动化方法都接近随机**。⇒ **附件 A 这条合同条款目前没有可靠的自动判定方法**; 要用 predicate 这一格就得**人工标注或放弃它**。 ★★★ **投料前走了三轮零调用对抗评审**: 280 agent/30 BLOCKING → 92/10 → 39/8。第三轮抓到两条致命的: ① **RETRIES 改名漏一行** ⇒ 68 次全打完后必 NameError、结果文件一个字节不落盘, 而当时 **19 道闸全绿**(没有一道闸执行 main()); ② **power 只算了①**, 联合 power 在 q=0.65 是 **0.069** 不是 0.817。 ★★★ **三条根本修法(不是逐条打补丁)**: (a) **干跑闸** —— 桩替换模型入口**真的跑一遍 main()** 并断言产物落盘, 外加静态查未定义自由名; (b) **对照集体检器** probes/corpus_balance_audit.py —— 逐轴机械对比手构集与**真实语料**的 pos/neg 分布差, 把「事后搜出共线」变成「造对照时的机械约束」(现报全部已知轴都在真实语料水平内, 那条曾拿 19/24 的族外量词规则净增益降到 **−2**); (c) **前置条件②改用净增益** —— 分开判两个阈值会漏(那条规则两项都过而净增益 −2)。 ★ 对照集重造为 **24 对**(v1 的 6 对已撤回留档), 分**调整集 16 + 留出集 8**, p0 取**留出集**那个(未被迭代的)。 ★ **代价**: n=1 零重试(r3 重测一致率 60%) · 分母是手构最小对照不得外推自然语料 · 只测了 RESTATES_IDENTIFIER 一个取值 · **第四轮评审未跑, 不声称已无缺陷** · 判据层仍未接进生产。 ★ 预算合计 **68+68=136 次**。见 results/slot_filling_r5.json · tests/test_cce_slot_filling_r5_result.py(7 项, 变异 10/10) · results/corpus_balance_audit.json。 ★★★★★ **2026-09-15 槽位可填性档案(零调用, 重算 r5 已付费的 68 次)** —— 并**更正我自己前一条表述**。 ★★★ **被更正的**: r5 产物里我写过「其他槽位几乎满分(speaker 68/68 · polarity 136/136) ⇒ **它认真读了**」。**那个推论证据不足**: 同一批上**零基线(完全不读文本)拿 66/68 与 134/136** ⇒ 那几格的**全部增益空间只有 2 格**。「满分」等于「**这批 items 在这个槽位上几乎没有区分度**」, 不等于能力。★★ 这正是 **r4 那条教训(金标倾斜 38:2 ⇒ 不读文本能拿 93.6%)的重演** —— 区别是这次算了。已**带原文引述地更正**(不是抹掉), 由闸把住。 ★★★ **逐槽位(净增益=模型−零基线 / 可得增益=金标−零基线)**: speaker +2/+2 · polarity +2/+2 · citation +2/+2 · time +1/+2 ⇒ **这四格这批数据测不出**, 满分不得引用为能力; **possession −6/+4 ⇒ 比不读文本还差**; **predicate +3/+26 ⇒ 只取到 12%**。 ★★★ **结论**: 这批数据**只测得出两个槽位**, 而模型在有区分度的那一格上只取到 12%、在另一格上是负增益。⇒ **自动填槽位这条路, 在已测范围内没有可用的证据支持**。 ★ **通则(第三次登记, 前两次是 r4 与 r5)**: **准确率不是能力, 相对零基线的净增益才是**; 而且必须同时报**可得增益**(金标 − 零基线), 否则一个可得增益只有 2 格的槽位会以「满分」的样子被引用。 ★ **边界**: 只重算了这 68 条**手构** item 与**这一个**模型, 不得外推; 四个槽位「测不出」是**这批数据**的性质, **不是**「模型填不出」的证据 —— 要测它们需要**区分度更高的 items**。 见 results/slot_fillability_audit.json 与 tests/test_cce_slot_fillability.py(7 项, 变异 8/8)。 ★★★★★ **2026-09-15 接入决策: 判据层(命题框架层)**不接入生产**。** 三条路都走不通, 每条都有实测: **(a) 把合同文本塞进生产 prompt** —— gen9 双臂重测(1291 次真实调用)已排除: display 出现率由**生产臂 1/80**(0/48 + 1/32)涨到**候选臂 40/80**(27/48 + 13/32), 且**倒挂** —— 合同说**不该**给的 A 臂 **56%** > 合理可能的 B 臂 **41%**。 **(b) 让模型自动填六槽位** —— r5(68 次已付费)+ 槽位可填性档案: predicate 只取到可得增益的 **12%**, possession **净 −6**(比不读文本还差), 其余四格这批数据**测不出**。 **(c) 填不出的槽位一律留空** —— 本轮实测: 把 predicate+possession 留空后, 手构最小对照上**阴性拦住 34/34(满分)**, 但**对照也全被拦(0/34)**。★ 逻辑上显然(留空 ⇒ 证据不足 ⇒ fail-closed), **但算出来才是证据** —— 一个把所有东西都拦住的过滤器**没有鉴别力**, 接进生产等于关掉输出。 ★★★ **必须守住的区分**: **判据层本身是有效的**(全槽位时手构最小对照阴性拦住 **34/34** · 对照通过 **34/34**) ⇒ 问题**不在判据, 在没有可靠的方法把槽位填对**。把这两件事混为一谈, 下一个人会去改判据(改不动)而不是去解决填槽位(真问题)。 ★★ **我在这一轮犯的两个错(都已处理并留档)**: ① **重写了已有的实现** —— 我先写了一份自己的回放, 读出「对照 0/12」, 而仓里**已验证的**那份读出 **12/12** ⇒ 我那份错。处理是**撤掉**不是「修好」(两份并存下一个人不知道信哪个); **代价**是真实证书上的降级效果**没算**, 已登记; ② **同一个数写在两个地方** —— 关键读数同时在 docstring 与产物里, 变异实测显示改了 docstring 那处**没有任何闸会红**(它不进产物)。⇒ **通则: 一个数只写在一个地方 —— 现算的那个; 其余地方指过去。** 已加闸。 ★ **边界**: 「不接入」是**当前证据下的判断**, 不是永久结论 —— 若将来有可靠的填槽位方法, 要重新评估。 见 results/claim_frame_degraded_capacity.json 与 tests/test_cce_claim_frame_degraded.py(8 项, 变异 9/9)。 ★★★★ **2026-09-16 补上那条欠账: 真实证书上的降级效果**(零调用)。 ★ **做法是给已验证的 probes/claim_frame_replay.py 抽出 build_rows(drop=())** —— **默认空元组 ⇒ 它自己的历史读数逐字节不变**(sha bc72a3c09816c3a9 前后相同, 7 道闸全过)。★★ 这正是上一轮那个错的反面: 当时我**重写了一份**, 读出「对照 0/12」而已验证的是 **12/12**。 ★★★ **读数**: 真实证书 **全槽位 阴性 3/3 · 对照 12/12**; **降级后 阴性 3/3 · 对照 0/12**。手构最小对照对应的是 34/34 与 34/34 → 34/34 与 **0/34**。 ⇒ **「留空 ⇒ 对照全误拦」不是手构对照的特性**, 在**真实模型产出的证书**上同样成立。**「不接入」那条结论的第三支 (c), 现在有两批数据支撑而不是一批。** ★ 顺带确认: 全槽位时真实证书对照 12/12 与已验证探针的历史读数一致 ⇒ **再次确认我上一轮那份自己写的实现(给 0/12)是错的**。 ★ **代价**: 真实证书**对照只有 12 张 · 阴性只有 3 张**, 分母极小, **只判方向**; 那批证书的六槽位标注**仍是我做的** ⇒ 仍是「标注正确时」的上界; 「不接入」仍是**当前证据下的判断**, 不是永久结论。 见 results/claim_frame_degraded_capacity.json 与 tests/test_cce_claim_frame_degraded.py(**9 项**, 变异 7/7)。 ★★★★ **2026-09-17 对照集体检器加第二个参照: 仓内真实 Reddit 语料**(零调用)。从 corpus/reddit_hearingaids_audience_v2.txt 等抽出 **493 句**, 其中含具体品牌/型号 **41 句**。 ★★★ **两个参照回答的是不同问题**: 真实证书(9 条, **有标注**)比**类别间的差**; 真实语料(493 句, **无标注**)比**我造的句子本身像不像真人写的**。**互补不是替代** —— 类别差合格但句子根本不像真人写的, 仍然是个问题。 ★★★ **读数**: 类别差**超出的轴 无**(内部效度合格); 整体分布在阈值 40 点下**两侧都远离的轴 无**, **但偏离量本身**: 末词首字母大写 **30 点** · 含系动词 **26** · 首词是限定词 **25** · 含时段单位 **19**。 ★★ **同向偏离**(pos 与 neg 一起偏)**不影响类别区分** ⇒ 本轮**内部效度不受影响**; 但它**影响外推** ⇒ **本轮读数不得外推到自然语料** —— 这条以前只是口头边界, **现在有数了**。 ★ **为什么不把阈值从 0.4 调到 0.2**: 那是**看过这批偏离量之后**拍的, 会变成拟合当前对照集。保留 0.4 只抓极端偏离, 同时**把偏离量本身报出来**。 ★★★ **变异实测暴露的一条(同型第 N 次)**: 原闸只断言「**有没有写「不许调阈值」这句话**」, 变异把阈值真改成 0.2 并**重跑探针** —— **那句话还在, 闸不响**。⇒ 改法: 阈值提成模块常量 FAR_THRESHOLD, 闸**直接断言它的值**。**通则: 守「写没写」不等于守「是不是」。** ★ **边界**: 含品牌的可比子集只有 41 句 · 语料**无类别标注**只能比整体分布 · 来自 r/HearingAids **单一板块** · 偏离 19–30 点这件事**没有修**(修它要重造对照集), 本轮只把它**变成有数的边界**。 见 results/corpus_balance_audit.json 与 tests/test_cce_corpus_balance.py(**11 项**, 变异 8/8 + 重跑后 6/6)。 "
                            "④ ★ **我先前在这一行写过一句假话, 已更正**: 原写「维持撤销的那 2 个用例仍**零覆盖**」—— ""实测 C_明确放弃_0/1 各有 **5 条已裁定断言**(audit/injustice/pain_seek/belong/suspend), ""只有 display 那条被撤 ⇒ 是**部分覆盖 5/6**, 不是零覆盖。""真正零覆盖的是 `未裁定用例` 那 10 条。""★ 这句假话是我自己写的, 而我刚给这一节建的结构闸(要求列够项数、不许空占位)**没抓到它** —— ""结构闸查形状不查真假, 这是它的诚实边界; 已另建现算闸钉住这类计数。""★★★ **2026-09-14 已做**: 给 C_明确放弃_0/1 补上 display 断言 —— 攻的是**P 支(增量)**而非被撤的 Q 支。推导: 判别式是合取 P∧Q; 两条文本逐类核过五类皆✗ ⇒ P 不成立 ⇒ 合取式不成立 ⇒ top1 != display。**(甲) 文本内属性** —— 问的是「文本有没有给出五类之一」, 不涉任何文本外事实; 被撤那条问的是「说话人有没有经历过」(文本外, 丁)。⇒ 这两个用例各自的 7 条断言行里 **6/7 已裁定**(原 5/7), 断言表 80→82 已裁定。★ 第 7 行**不是待补** —— 它是那条被撤销的 Q 支断言, **永久保留作记录**, 所以分母永远到不了 7/7, 而那是对的: 撤销要留痕。★ **不得**读成「被撤那条恢复了」—— 合取式攻哪一支都够, 但不是同一件事, 那条**仍然撤着**。★★★ **本条依赖一个读法前提**: 判别式括号内五项是**闭列**不是示例。文本内证据是分类学的括号有两种用法(引语式 knots[3]/[8] 显然是示例 · 类名式 knots[0]/[1]/[4] 读作定义性分解), 两类在文本上可分; **但合同没有一句话说「仅限这五类」** ⇒ 这是**读法不是字面**。owner 或后续合同版本若声明该括号为示例, **本断言自动作废**, 不需再实测。★ 我上一轮跟 owner 说「五类是闭列」时说得太平, 这里补上前提。")})
        A = _j("tests/data/local_contract_assertions_v2.json")
        nw = sum(1 for a in A["断言"] if a["★★★断言状态"].startswith("**已撤销"))
        _wd = A.get("★★★2026-09-23 撤销项处置")
        out.append({"类": DECIDED if _wd else OPEN,
                    "项": (f"★ 断言表 v2 有 **{nw}** 条已撤销 —— ★ 2026-09-23 逐格核对: 对应 (用例×display) **已由增量支(甲)断言覆盖且已裁定** ⇒ 无需新断言; 撤销的是冗余的 Q 支推导") if _wd else
                          f"★ 断言表 v2 有 **{nw}** 条已撤销 —— 撤销项对应的用例回到**未裁定**, 需要新断言",
                    "证据": (("撤销依据: 它们靠**文本外事实的证据缺席**(丁), 不可由冻结合同推出。"
                             "★ 2026-09-23 更正我先前那句「零覆盖」: display 是合取 P∧Q; " + " · ".join("%s 的 display 格由「%s」(甲)已裁定覆盖" % (u, v["覆盖该格的已裁定断言 条款定位"]) for u, v in _wd["用例×结 覆盖情况"].items())
                             + " ⇒ 下一轮验收对这两格**有覆盖**, 不是零覆盖。Q 支那条维持撤销(丁), 不影响格的裁定。★ 不许为救 Q 支靠常识补; 文本 sha 冻结。") if _wd else
                            ("撤销依据: 它们靠**文本外事实的证据缺席**(丁), 不可由冻结合同推出。"
                             "⇒ 那 8 个用例目前**没有任何可裁定的断言**, 下一轮验收对它们**零覆盖**。"
                             "★ 补法取决于第三格怎么定 —— 选『对象域限定为物』则断言恢复, 选『允许事』则需另立。"))})
    except Exception:
        pass

    # ⑩ 2026-09-11 工作区写入边界 —— DEV-002 的根因, 按 web GPT 第十轮列为**第一项工程投入**
    try:
        built = os.path.exists(os.path.join(ROOT, "scripts/cce_worktree_guard.py"))
        # ★ 分类更正: 建好的那半是**防误写**, 剩下那半(权限闭合)**卡在权限外移上** ⇒ BLOCKED, 不是 DECIDED。
        #   「裁定不做」与「做不了」处置完全不同 —— 混了会让人以为这件事已经了结。
        out.append({"类": OPEN if not built else BLOCKED,
                    "项": "原始工作区写入边界 —— **防误写级已建, 权限闭合卡在权限外移**"
                          if built else "原始工作区写入边界**未建**",
                    "证据": (("已落 scripts/cce_worktree_guard.py: 副本带走**工作树当前字节**"
                             "(未提交+未跟踪, 反向对照证明 HEAD 路线两样都会丢); "
                             "回写前**检测原件是否在快照后被改过**, 是则拒绝(实测拦住了 DEV-002 的形态); "
                             "留可回滚副本。"
                             "★★★★ **但它不是权限闭合** —— 我仍握 shell+仓写权+**改它自己的权限**, "
                             "只能登记为**可绕过的防误写措施**。"
                             "「前后哈希相同」只证明这次原件没变; 「执行者没有写权限」才约束下一次, "
                             "**本模块不提供后者**。★ 真边界需 **owner 或运行环境**持有 —— "
                             "要移走的是「本次执行 agent **自行解除限制的能力**」—— "
                             "**这需要 owner 或运行环境做权限外移, 我结构上做不到**。"
                             "★ 范围: 只做本次候选修改需要的隔离, 非整章治理。")
                            if built else
                            "★ DEV-002 的根因边界尚未建 —— 下一次触及原件的修改前必须完成。")})
    except Exception:
        pass

    # ── 2026-09-17 三项决策落地后剩下的两条 ────────────────────────────
    #   ★ 不是「又想到两件事」, 是三项换到同一把尺(净增益)之后**剩下的唯一两件事**。
    _rbp = os.path.join(ROOT, "results/three_decisions_rollup.json")
    if os.path.exists(_rbp):
        _g = _j("results/three_decisions_rollup.json")["★★★★★ 三项同尺后的读数"]["逐项新增鉴别格"]
        _annexd = os.path.exists(os.path.join(ROOT, "FIVE_KINDS_ANNEX_D_CANDIDATE_2026-09-23.md"))
        out.append({"类": DECIDED if _annexd else BLOCKED,
                    "项": ("五类成立条件: ★ 2026-09-23 **授权代定**写成候选附件 D(FIVE_KINDS_ANNEX_D_CANDIDATE_2026-09-23.md), **不升合同**; 启用门槛冻结(每类 ≥6 鉴别格 · 总 ≥30 · B 臂超浅层臂 · CONTRACT_CHANGE 路)" if _annexd else
                          "五类成立条件**升不升合同**: 卡在「附件 A 里根本没有这五条定义文本」"),
                    "证据": "★★★ 这不是「批不批准」—— **附件 A 只有 A/B/C 三条定义, 没有五类成立条件的定义文本** "
                            "⇒ 升格之前得先**写五条新定义** —— 卡的是 **owner 撰文**, **不是 owner 裁定**: "
                            "裁定是有东西摆在那儿等点头, 这里**那个东西不存在**。"
                            "★ 后果已测(results/interpretation_upgrade_impact.json, 四选项**镜像**对比, "
                            "仓内 scripts/cce_claim_frame.py 一字节未动): 手构对照上明文档阴性 **+2/+2/+4** 零误封; "
                            "但**真实证书上 REPORTED 出现 0 次、NOT_OF_DECLARED_KIND 出现 0 次** ⇒ "
                            "**两条规则一次都没被 exercise** ⇒ 真实证书上新增鉴别格 **%d**。"
                            "★ 代价: 升了会让 **4 道闸见红**, 其中一道正是为拦这件事而建。"
                            "★★ 所以现在**买不到可验证的东西** —— 不是规则不对, 是**没有能检验它的格子**。"
                            % _g["①升合同"]})
        _pilot = os.path.join(ROOT, "results/real_corpus_pilot.json")
        if os.path.exists(_pilot):
            _p = _j("results/real_corpus_pilot.json")
            _R = _p["★★★ 主读数: 真实语料交卷率"]
            _fq = _j("results/real_corpus_pilot_formal_quality.json")
            out.append({"类": OPEN,
                "项": "真实语料小批试**已跑完**(42 次) —— 因子一测到了, **因子二仍未测**",
                "证据": "★★★ 读数: 交卷 %s = %s, CP95 %r, 对手构模板级底数 %s 的 Fisher 两侧 p=%s "
                        "⇒ 判决 **%s**。"
                        "★★★★★ **这推翻了我自己的事前预期** —— 我预期真实语料更难交卷(功效分析全盯下尾), "
                        "实测是反过来的: 手构模板上的外推在**因子一**上**低估**了产出。"
                        "★★★ 但**不得读成「83%% 的段落真的满足判别式」**: 交卷只是 supported==true; "
                        "手构那边 10 张交卷证书里 6 张是 UPGRADED(形式合规、语义错误), "
                        "本轮 34 张里只有 %s 整张 span 全逐字。交卷率高既可能是真实语料确实常谈自己的设备, "
                        "也可能是抽取器在真实文本上更松 —— **本轮分不开**(没有金标)。"
                        "★ 也**不得读成「因为是真实语料」**: 两样本长度中位数差 3.2 倍, **机制未识别**。"
                        "★★★ **仍然未做**: 因子二(每张交卷证书里有几个鉴别格)。它需要金标, "
                        "而 RESTATES_IDENTIFIER 的定义含「声称这是增量」(A 支属性) ⇒ 人标不出来。"
                        "⇒ 「花不花 ~570 次」**本轮没有回答**, 只把它的一个因子从外推换成了实测。"
                        % (_R["交卷/有效"], _R["率"], _R["CP95"], _R["手构模板级底数"],
                           _R["Fisher 两侧 p"], _R["★★★判决"],
                           _fq["★ 形式质量(无金标, 只看结构)"]["★★★整张证书 span 全逐字"])})
        _ru = os.path.join(ROOT, "results/real_corpus_pilot_rollup.json")
        if os.path.exists(_ru):
            _R = _j("results/real_corpus_pilot_rollup.json")
            _one = [_R[x] for x in _R if "一、第一轮的判决复现了" in x][0]
            _two = [_R[x] for x in _R if "真正的新发现" in x][0]
            out.append({"类": DECIDED,
                "项": "第一轮那个**单次读数已重测** —— 判决复现, 逐条也显著好于随机",
                "证据": "★★★ 第一轮 %s, 第二轮 %s ⇒ **%s**(拒绝域**继承第一轮的冻结表**, 未重算)。"
                        "逐条: %s "
                        "★ 但 kappa 不是 1 —— 「哪一条会交卷」仍有真实的不确定性, 只是没大到淹没信号。"
                        "★★★ 这一步**本来就该在下判决之前做** —— 我却先把单次读数登记进了 refactor_log, "
                        "是本仓「单次运行读数不可信」那条教训自己逮住了我。"
                        % (_one["第一轮"], _one["第二轮"], _one["判决"], _one["★逐条也稳"])})
            out.append({"类": OPEN,
                "项": "★★★ **交卷 ≠ 合格**: 83%% 是交卷率, 过机械资格层的只有 %s"
                      % _two["过机械资格层"].split(" = ")[0],
                "证据": "★★★ 交卷 %s, 过机械资格层 **%s**。机械出口 %r。"
                        "★★★ 主要卡点是 **P2_FAIL** —— 模型在「新信息增量」那一支说的东西, "
                        "与在「自己已拥有」那一支说的**不是同一个物**。"
                        "这与 r1/r2 的对象粒度/错配是**同一族故障**, 但那时只在 16 条手构模板上见过。"
                        "★ 它不改第一轮的读数(83%% 测的就是交卷率, 没错), 但它**改变了那个数的用法**: "
                        "83%% **不是可用产出率**。"
                        "★★★ **仍未回答**: 这些被拦下的是不是「该被拦」—— 那需要金标, 真实语料没有。"
                        % (_two["交卷"], _two["过机械资格层"], _two["机械出口分布"])})
        _r6 = os.path.join(ROOT, "results/slot_filling_r6.json")
        if os.path.exists(_r6):
            _R6 = _j("results/slot_filling_r6.json"); _M6 = _R6["★★★主判据: B 臂鉴别格 vs 最佳浅层规则"]
            out.append({"类": DECIDED,
                "项": "r6(2026-09-23, 68 次): r5 的负结果在表层配平后的 v4 上**复现** —— B 臂鉴别格 %s, D6 触发" % _M6["B 臂鉴别格"],
                "证据": "★★★ 协议与 r5 逐字相同(执行器 import r5 模块只 patch 四个名字), 只把 contract_pairs 换成 v4(偏离 14.0→1.8 点)。"
                        "B 臂鉴别格 %s vs 冻结族最佳浅层规则 %s, 净增益 B %s / 阈值 %s, 门 ≥8/24, 单侧 p=%s ⇒ **未达成**。"
                        "鉴别格上模型填 OF_DECLARED_KIND 21 / NOT 2 / RESTATES 1 —— 拿到合同条款后几乎从不启用 RESTATES; 多数类 42/42。"
                        "★ 「附件 A 这条合同条款目前没有可靠的自动判定方法」现在有两轮、两套对照集、136 次支撑。"
                        "★ 不得说「比 r5 更差」(1/24 与 4/24 CP95 重叠, item 集不同); 不得说 v3 伪影没影响(归因需同轮配对 v3)。"
                        "★ possession 再次负增益(53/68 < 零基线 64/68, r5 −6 本轮 −11)。"
                        % (_M6["B 臂鉴别格"], _M6["最佳浅层规则鉴别格"], _M6["★★★净增益(鉴别格对数 − 多数类格错数)"]["B 臂"],
                           _M6["★★★净增益(鉴别格对数 − 多数类格错数)"]["冻结的阈值"], _M6["单侧 p(二项, 事前可算)"])})
        _rj = os.path.join(ROOT, "results/slot_filling_r6_jev.json")
        if os.path.exists(_rj):
            _J = _j("results/slot_filling_r6_jev.json"); _MJ = _J["★★★主判据: B 臂鉴别格 vs 最佳浅层规则"]; _PJ = _J["★★★Jev 在鉴别格上给 RESTATES 的概率"]
            out.append({"类": DECIDED,
                "项": "r6-jev(2026-09-23, Jev 68 请求): 换成 System One 模型, predicate 鉴别格 %s, **同样未达成** ⇒ 问题在判据/材料不在模型家族" % _MJ["B 臂鉴别格"],
                "证据": "★★★ 同一批 r6 items/金标/打分/judge, 填槽模型换成 TypeSafe Jev(jev-1.13.0, 不生成文本, 每槽位一道 Choice)。"
                        "鉴别格 %s vs 浅层规则 %s, 门 ≥8/24, 净增益 %s ≤ 3 ⇒ 未达成, D6。鉴别格上填 OF_DECLARED 21 / RESTATES 2 / NOT 1, 与 MiniMax r6 几乎同一张脸。"
                        "★ possession 第三次负增益(Jev 40/68 < 零基线 64/68; MiniMax −6/−11) ⇒ 这一格的题面/金标有问题, 与模型家族无关, **待查**。"
                        "★ Jev 独有: 鉴别格上 P(RESTATES) 均值 %s vs 多数类 %s(差 44 倍), 2 格 ≥0.8 —— 分得出方向但 argmax 过不了; 降阈值是看过数据再定, 不许, 要用得另立预注册。"
                        "★ 不得说 Jev 比 MiniMax 好/差; 不得外推到中文(官方 CJK 不同等)。成本 ≈$0.006。"
                        % (_MJ["B 臂鉴别格"], _MJ["最佳浅层规则鉴别格"], _MJ["★★★净增益(鉴别格对数 − 多数类格错数)"]["B 臂"], _PJ["均值"], _PJ["多数类上均值"])})
        _pa = os.path.join(ROOT, "results/possession_gain_artifact.json")
        if os.path.exists(_pa):
            _PA = _j("results/possession_gain_artifact.json")
            out.append({"类": DECIDED, "项": "possession 三轮「负增益」是**打分伪影**: 合同 Q 是析取, 判据层对 OWNED/EXPERIENCED 结局相同(现证), 金标却一律记 OWNED",
                "证据": "等价类口径重算: " + " · ".join("%s %s→%s" % (k, v["槽位级原打分"], v["★合同等价类口径(OWNED≡EXPERIENCED)"]) for k, v in _PA["★★★三轮对照"].items())
                        + "。★ r5/r6/r6-jev 的数不回改。★ 2026-09-23 **已预注册为 r7 起的打分策略 v2**(tests/data/slot_filling_score_policy_v2_prereg.json; 等价类由判据层现算: {OWNED,EXPERIENCED}·{ONE_NEGATED,UNSPECIFIED}·{BOTH_NEGATED}); 三轮 v2 附带读数 " + (" · ".join("%s %s(净 %+d)" % (k, v["v2 等价类"], v["v2 净增益"]) for k, v in _j("results/slot_filling_score_policy_v2.json")["★★★三轮对照(可比不可合, 冻结产物未改)"].items()) if os.path.exists(os.path.join(ROOT, "results/slot_filling_score_policy_v2.json")) else "(未生成)") + "。★ ONE_NEGATED/BOTH_NEGATED 类金标 <6 ⇒ 测不出, 补金标要另立预注册。"})
        _sh = os.path.join(ROOT, "results/s0_jev_shadow.json")
        if os.path.exists(_sh):
            _S = _j("results/s0_jev_shadow.json")
            out.append({"类": DECIDED, "项": "s0 情境面 Jev 影子臂已跑(MiniMax 42 + Jev 42): 一致率 5–31/42, MiniMax 情绪余温**零未知**。★ 2026-09-23 owner 两次裁定: ①s0 六面**无人类金标可言**, 「人填 10 条金标」前置**撤回** ②「那就接线吧」⇒ **已接线**(scripts/cce_s0_jev.py, 有 TYPESAFE_API_KEY 走 Jev, 否则回退 MiniMax 并写 read_backend; tests/test_cce_s0_wiring.py 变异 5/5)",
                "证据": "逐面 一致/MiniMax未知/Jev未知: " + " · ".join("%s %s/%d/%d" % (k, v["一致"], v["MiniMax 未知/非法"], v["Jev 未知"]) for k, v in _S["★★★逐面"].items())
                        + "。★ 无金标 ⇒ 不判优劣; MiniMax 在「读不出就填未知, 严禁猜」下 42 条零未知这件事不需要金标。★ 剩一件 owner 侧动作: GitHub 仓库 secrets 加 **TYPESAFE_API_KEY**, 没加之前线上链走 minimax_fallback 并写进产物。★ 全链提速点不在 s0: 在 reader_baseline + s1 + s2 两次 knot_classify(生成式, Jev 接不了)。"})
        _ob = os.path.join(ROOT, "results/stage_overlap_bench.json")
        if os.path.exists(_ob):
            _B = _j("results/stage_overlap_bench.json"); _sv = _B["★节省"]; _a, _b = _B["arms"]
            out.append({"类": DECIDED, "项": "reply 链 reader_baseline ∥ s1_readout 已并发化(owner 2026-09-23): 核心分类器一字未动, 只改编排; 串行 %.0fs → 重叠 %.0fs(n=1)" % (_a["wall_sec"], _b["wall_sec"]),
                "证据": "可归因于重叠的节省 ≤ 理论上限 min(reader,s1) = %.0fs; 超出部分 %.0fs 是单次延迟波动。两臂 INFRA_FAILED 0/0, k_ok 3/3。闸 tests/test_cce_stage_overlap.py 变异 6/6。★ 生产 cce-submit 实测 2–7 min/run(items 已 matrix 并行), 「20 分钟」是 G-K 精度闸(5 模型×81 条), 不是单条链。★ outbound_post 无 reader 段, 零影响。" % (_sv["★可归因于重叠的节省(≤理论上限)"], _sv["★超出上限的部分=单次调用延迟波动, 不归功于重叠"])})
        _dl = os.path.join(ROOT, "results/draw_latency.json")
        if os.path.exists(_dl):
            _D = _j("results/draw_latency.json"); _E = _D["★★★评估(按预注册规则现算)"]
            out.append({"类": DECIDED, "项": "K/n 减少预注册(tests/data/sampling_reduction_prereg.json) 第一步已测 ⇒ **H0 STOP**: 期望节省 " + " · ".join("%s %.1fs(%.0f%%)" % (k, v["期望节省秒"], 100 * (v["节省比"] or 0)) for k, v in _E["候选"].items()) + ", 均 < 门(10 s 且 15%%); 不换仪器",
                "证据": "结构事实: s1 K 个 draw 与 s2 n 个 draw 各自一个并发波, 减 K/n 只砍尾部序统计量。s1 中位 %.0fs / s2 中位 %.0fs, E[T(3,5)]=%.0fs。★ 三候选 90%% 区间都跨 10 s 门(INCONCLUSIVE 标), 按预注册仍按点估计判 STOP。★ 再快只能换更快的生成模型; 换了模型延迟分布变, 本预注册要重跑第一步。★ 第二步(换代+K1+资格层, ≤250 次/候选)未启动。" % (_D["样本"]["s1 中位/最大"][0], _D["样本"]["s2 中位/最大"][0], _E["当前 E[T(3,5)]"])})
        _rt = os.path.join(ROOT, "results/s0_retest.json")
        if os.path.exists(_rt):
            _R = _j("results/s0_retest.json"); _P = _R["★★★逐面逐臂"]; _T = _R["★★★情绪余温结构约束"]
            out.append({"类": DECIDED, "项": "s0 两臂**无金标**重测(owner 裁定后, MiniMax 42 + Jev 42 再读一轮): Jev 四面 κ=1.0、两面 ≈0.88; MiniMax 六面 κ 0.38–0.58 ⇒ MiniMax 任一面两轮平均准确率**上界** 0.85–0.90(对任何真值成立)",
                "证据": "逐面 κ mm/jev: " + " · ".join("%s %s/%s" % (k, _P["mm"][k]["kappa"], _P["jev"][k]["kappa"]) for k in _P["mm"])
                        + "。情绪余温结构违反(冷读却填 正/负/中性) 轮1/轮2: MiniMax %d/%d · Jev %d/%d" % tuple(_T[a][r]["违反结构约束(填了 正向/负向/中性)"] for a in ("mm", "jev") for r in ("轮1", "轮2"))
                        + "。★ 只比稳定性与纪律, 不比准确率(无真值); κ 高可能是稳定的同一偏见。★ 据此 owner 已点头接线(见上条)。"})
        _v4 = os.path.join(ROOT, "results/contract_pairs_v4_check.json")
        if os.path.exists(_v4):
            _C = _j("results/contract_pairs_v4_check.json")
            _one = [_C[x] for x in _C if "表层像不像真人" in x][0]
            _two = [_C[x] for x in _C if "泄漏浅层线索" in x][0]
            out.append({"类": DECIDED,
                "项": "手构对照集 19–30 点表层偏离**已修**: contract_pairs_v4 平均偏离 %s → %s 点"
                      % (_one["v3 平均偏离(点)"], _one["v4 平均偏离(点)"]),
                "证据": "★ 并列新增 v4, 只重写 A 支; v3/pairs 一字节未动(r4/r5/annex/shallow 的读数建在 v3 上, sha 钉死)。"
                        "冻结族最佳净增益 v3 %s → v4 %s(没把浅层线索写进 neg); 判据层逐对相同(frames 一格未动); 抄语料 0。"
                        "FAR_THRESHOLD 未动。★ **新一轮起用 v4**; 不据 v4 重跑旧轮次改结论。"
                        % (_two["v3"]["最佳净增益"], _two["v4"]["最佳净增益"])})
        _an = os.path.join(ROOT, "results/p2_fail_anatomy.json")
        if os.path.exists(_an):
            _A = _j("results/p2_fail_anatomy.json")
            _rel = _A["★★★ 关系分布"]
            _v2 = os.path.join(ROOT, "results/p2_policy_v2_rescore.json"); _R2 = _j("results/p2_policy_v2_rescore.json") if os.path.exists(_v2) else None
            out.append({"类": DECIDED if _R2 else BLOCKED,
                "项": ("P2_FAIL %d 张已拆成三族 —— ★ 2026-09-23 **授权代定**(P2_FAIL_FAMILIES_DECIDED_2026-09-23.md, owner 一句话可作废): SET_MISMATCH→P2 v2 见证交集 · SUBSTRING 维持 fail-closed · DISJOINT 维持拒; r2 不改 v1 %s, v2 重算 %s(可比不可合)"
                       % (_A["P2_FAIL 条数"], _R2["★过机械资格层"]["v1"], _R2["★过机械资格层"]["v2"])) if _R2 else
                      ("P2_FAIL %d 张已拆成三族, 三族修法完全不同 —— 卡在 **owner 裁定**走哪条" % _A["P2_FAIL 条数"]),
                "证据": "★★★ 零调用 sha 反查(0 歧义 0 失败): **SET_MISMATCH %d**(两支有共同对象, A 支多给证据指到无关的东西 "
                        "—— r2 记的「多给反而被拦」, r3 判为运气, 现在真实语料上有样本量; 多出对象与共同对象 %r) / "
                        "**SUBSTRING %d**(粒度: 部件/方面 vs 整机) / **DISJOINT %d**(真·不同对象)。"
                        "★ 第一族是**采集协议**问题(每支只取一条? 取交集?), 第二族是**判据**问题(部件⊂整机认不认), "
                        "第三族才是模型问题。★ r2 提的「about 必须原文逐字」第二轮已生效, P2 照样卡 ⇒ 逐字约束不解决 P2。"
                        "★★★ **不得**据此放松 P2 加子串包含/别名归并 —— 那是 r2 明写的 fail-closed 选择。走哪条是 owner 裁定。"
                        % (_rel.get("SET_MISMATCH", 0), _A["★ SET_MISMATCH 里多出来的对象与共同对象的关系(汇总)"],
                           _rel.get("SUBSTRING", 0), _rel.get("DISJOINT", 0))})
        out.append({"类": DECIDED if os.path.exists(_ru) else OPEN,
                "项": ("资格层的**机械**部分已测(见上一条) —— 但「验证器守得住」**仍然零证据**"
                       if os.path.exists(_ru) else
                       "**资格层仍然零证据** —— 而且这一轮被我自己的隐私选择挡住了"),
                "证据": "★★★ r2 起就登记着「验证器会拦住形式合规、语义错误的证书」**零证据**。"
                        "本轮拿到 34 张真实语料上的证书, 本可以拿它们 exercise 资格层 —— "
                        "但为守「产物里不写一个字语料原文」, 我**没存 object 字段**, "
                        "而资格层的核心判据(两支同对象)需要它 ⇒ **事后无法重算**。"
                        "★ 下一轮的可行办法: 只存对象名的 **sha** 与「两支的 sha 是否相等」, "
                        "既能核同对象又不落原文。见 results/real_corpus_pilot_formal_quality.json。"
                        "★★★ **2026-09-17 第二轮已按这个办法把它做了** —— 资格层的**机械**部分测到了。"
                        "但**语义那一半仍然零证据**: 机械出口只回答形式, "
                        "「形式合规、语义错误的证书会不会被拦」需要金标, 真实语料没有 ⇒ "
                        "**跑了两轮、花了 84 次之后, 那句话自 r2 起仍然零证据**。"})
        out.append({"类": DECIDED if os.path.exists(_pilot) else OPEN,
                    "项": ("真实语料 ~50 次小批试 —— **已完成**(见上一条)"
                           if os.path.exists(_pilot) else
                           "真实语料 **~50 次小批试** —— 三条路里**唯一**能把「没有格子」变成「有几个格子」的"),
                    "证据": "★★★ 现状: RESTATES_IDENTIFIER 是**抽取错误类别**不是语言现象"
                            "(定义含「声称这是增量」, 而那是 A 支的属性) ⇒ 人从 493 句语料里**标不出一个鉴别格**"
                            "(results/real_corpus_feasibility.json), 现成可标的鉴别格 **%d**。"
                            "★ 要拿到 24 个鉴别格, 按「48 次产出 2 条」**外推**约需 ~570 次 —— "
                            "**那是外推不是预算**; 累计已用仅 158 次。"
                            "★★★ 小批试(~50 次)把外推换成**实测产出率**, 之后才谈得上要不要花大的。"
                            "★ 它同时是**手构对照集 19–30 个百分点表层偏离**的唯一解 —— "
                            "那个偏离**至今未修**, 修它要重建对照集, 而重建需要真实模板。"
                            % _g["②换真实语料"]})

    # ★ 去重: 同一件事可能既被注册表列为 missing, 又被显式标为 BLOCKED。
    #   显式的分类优先 —— 否则「卡在外部资源」会被误报成「我能做只是没做」。
    blocked_keys = [r["项"] for r in out if r["类"] == BLOCKED]
    # ★ 2026-09-04 补: 前缀去重挡不住「注册表 missing 与显式项讲同一件事但措辞不同」——
    #   静默 ASR 失败就同时出现了两条。改为**按主题词**去重, 显式项(证据更细的那条)优先。
    TOPICS = ("静默 ASR 失败", "抽取质量", "跨域标定", "重叠语音", "说话人分离")

    def topic_of(item):
        for t in TOPICS:
            if t in item:
                return t
        return None

    # ★ 主题**先一次性算完**再进合并环 —— 否则下面往幸存条目追加的原文
    #   会反过来改变后续条目的主题判定(追加的文本里就带着主题词)。
    topics = [topic_of(r["项"] + r["证据"]) for r in out]
    seen_topic = {}
    for t, r in zip(topics, out):      # 先扫一遍: 每个主题保留**证据最长**的那条
        if t and (t not in seen_topic or len(r["证据"]) > len(seen_topic[t]["证据"])):
            seen_topic[t] = r

    # ★★★ 2026-09-09: 去重原来是**静默**的 —— 实测它吞掉了一条内容完全不同的新条目
    #   (「没测过生产上有没有同一个 suspend 缺陷」被并进了「suspend 修法卡在 owner 裁定」,
    #    只因为两者都命中 topic「suspend」)。
    #   ★ 一个专门回答「什么没做完」的清单**静默丢条目**, 与本仓反复栽的
    #     「豁免名单里的东西没人再看」同族。⇒ 改为**记下被并掉的是什么**, 并在末尾报出来。
    dropped = []
    deduped, seen_open = [], set()
    for t, r in zip(topics, out):
        if t and seen_topic[t] is not r:
            dropped.append({"被并入主题": t, "项": r["项"], "类": r["类"]})
            # ★★★ 2026-09-11: 「被并入」原来只是**丢掉** —— 逐句比对三条被并掉的条目,
            #   实质信息在幸存那条里**读不到**: 根因句 `speech = audio.present` 把
            #   「本就无口播」与「ASR 失败」压成一个 true · 界是 **<0.15 字/秒** 不是 <20 字 ·
            #   语言密度 **2.84 倍** / 录音难度 **4.96 倍** 的出处 ·
            #   「现有真实素材仅 6 张分 3 类」· 「历史产物**未按新判定重跑**」·
            #   以及**这缺口同时属于 standalone_image_ingest** 这件事 —— 全没了。
            #   ⇒ 改为真的并: 把被并掉那条的**原文逐字追加**到幸存条目的证据里。
            #     不改措辞、不改分类, 只是搬过去。
            #     由 tests/test_cce_open_items_dedup_no_silent_loss.py **现算**守住。
            _add = f" ★ 并入同主题条目「{r['项']}」原文: {r.get('原文') or r['证据']}"
            if _add not in seen_topic[t]["证据"]:
                seen_topic[t]["证据"] += _add
            continue                      # 同主题已有证据更细的一条
        if r["类"] == OPEN and any(k[:8] in r["项"] or r["项"][:12] in k for k in blocked_keys):
            continue                      # 已被更准确的 BLOCKED 覆盖
        key = (r["类"], r["项"][:40])
        if key in seen_open:
            continue
        seen_open.add(key)
        deduped.append(r)
    if dropped:
        deduped.append({"类": OPEN, "项": f"★ 本清单去重时并掉了 {len(dropped)} 条同主题条目",
                        "证据": ("★ 去重按**主题**保留证据最长的一条, 并把被并掉那条的**原文逐字追加**"
                                 "到幸存条目的证据里(前缀「★ 并入同主题条目」) ⇒ **被并掉 ≠ 被丢掉**。"
                                 "**逐条列出**: "
                                 + " | ".join(f"[{d['类']}] {d['项'][:60]}" for d in dropped)
                                 + " ★★ 这条不靠自觉: tests/test_cce_open_items_dedup_no_silent_loss.py "
                                 "**现算**每条被并掉条目的原文是否真的出现在幸存条目里, 读不到就判红 "
                                 "(2026-09-11 实测: 未加合并前这三条的根因句 / <0.15 字每秒的界 / "
                                 "2.84 倍与 4.96 倍 / 「仅 6 张分 3 类」/ 「历史产物未按新判定重跑」"
                                 "在输出里一个字都读不到)。")})
    return deduped


def main() -> int:
    rs = items()
    print("=" * 74)
    print("CCE 未完成清单 —— 由各真相源现算")
    print("=" * 74)
    for cls, label in ((OPEN, "还能做, 只是没做"), (BLOCKED, "卡在外部资源上"),
                       (DECIDED, "已裁定不做(留着防重开)")):
        got = [r for r in rs if r["类"] == cls]
        print(f"\n【{cls}】{label} —— {len(got)} 项")
        for r in got:
            print(f"  · {r['项']}")
            print(f"      {r['证据']}")
    print("\n" + "-" * 74)
    print(f"合计 {len(rs)} 项未完成。★ 「引擎跑得动」与「这些事做完了」是两件事。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
