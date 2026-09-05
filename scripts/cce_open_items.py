#!/usr/bin/env python3
"""「还差什么」—— 从各真相源**现算**, 不由我口述。

2026-08-07 立的汇报纪律: 禁用裸的「完整/全链路」字样, 必须给逐项清单。
2026-09-03 owner 两次点破我越界声报(「可以投产了」/ 收尾语气)。
⇒ 与 cce_production_status.py 配套: 那张表说「哪些读数能用」, 这张说「哪些事没做完」。

★ 分三类, 因为它们的**修法完全不同**:
   BLOCKED_EXTERNAL —— 卡在我拿不到的外部资源上(人/触达量/owner 裁定)
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
            out.append({"类": _cls, "项": f"{c['id']}: {m[:64]}",
                        "证据": (f"status={c['status']}" if _cls == OPEN
                                 else f"status={c['status']} — {m}")})

    # ④ 读数层判红的(修法只有换仪器或接受)
    ps = _j("tests/data/phase2/k1_v2_multitext_verdict.json")
    out.append({"类": DECIDED,
                "项": "结层 intensity/weight 永久不可用",
                "证据": f"K1-v2 {ps['decision']}; 已裁定不换仪器(托管 API 无法批不变)"})
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
                               "③判据改为能容忍偶发偏离, 或直接走三态。")})

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

    seen_topic = {}
    for r in out:                      # 先扫一遍: 每个主题保留**证据最长**的那条
        t = topic_of(r["项"] + r["证据"])
        if t and (t not in seen_topic or len(r["证据"]) > len(seen_topic[t]["证据"])):
            seen_topic[t] = r

    deduped, seen_open = [], set()
    for r in out:
        t = topic_of(r["项"] + r["证据"])
        if t and seen_topic[t] is not r:
            continue                      # 同主题已有证据更细的一条
        if r["类"] == OPEN and any(k[:8] in r["项"] or r["项"][:12] in k for k in blocked_keys):
            continue                      # 已被更准确的 BLOCKED 覆盖
        key = (r["类"], r["项"][:40])
        if key in seen_open:
            continue
        seen_open.add(key)
        deduped.append(r)
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
