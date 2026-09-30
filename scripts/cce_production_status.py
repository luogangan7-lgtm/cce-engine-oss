#!/usr/bin/env python3
"""「CCE 能不能投产」不由一句话回答, 由这里逐项算出来。

## 为什么存在
2026-08-07 owner 指控「你一直欺骗我说跑了完整的 cce」, 指控成立。当时立的硬规则:
  · **禁用裸的「完整/全链路」字样** —— 必须给逐项清单(组件 + 跑/没跑 + 文件路径)
  · 任何「已验证/已通过」必须附 gate 名 + 数字 + 判据
  · **「未验」标注 + 继续越界使用 = 用免责声明掩护过度声报, 等同欺骗**

2026-09-03 我又犯了一次: 说「现在可以投产了」再挂一张 caveat 表。
⇒ 把这句话从「我说」改成「仓库算」。**三档: 可用 / 已测不达标 / 未测。**
★ 「未测」与「已测不达标」必须分开 —— not started is not green, 判过不合格也不是 not started。
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

USABLE, FAILED, UNMEASURED = "可用", "已测·不达标", "未测"
# ★ 第四档(2026-09-03 加): 能力已实证但没接进生产链。
#   它既不是「可用」(生产里调不到)也不是「未测」(已在 275 个真实产物上跑通),
#   更不是「不达标」。缺这一档我就把它误报成了「未测」。
NOT_WIRED = "已具备·未接入"


def _j(rel):
    return json.load(open(os.path.join(ROOT, rel), encoding="utf-8"))


def rows() -> list[dict]:
    from cce_k1_status import knot_readout_usable
    inst = "565470cf26c16d01"
    v2 = _j("tests/data/phase2/k1_v2_multitext_verdict.json")
    panel = _j("tests/data/phase2/intensity_across_panel.json")
    cap = {c["id"]: c for c in _j("config/cce_capability_registry_v1.json")["capabilities"]}
    out = []

    # ── 读数层 ────────────────────────────────────────────────────────
    # ★ 2026-09-03 生产实跑更正: 「结层 top-1 可用」**只对 k=3 的 profile 成立**。
    #   instrument_id 含 k ⇒ outbound_post(k=5) 是**另一台仪器** 0e9ca1d4e7a2f180,
    #   K1 的标定在它上面不成立, 闸如实扣发(「这台仪器没有 K1 判定, 不是判定通过」)。
    #   我此前给的是一句笼统的「top-1 可用」—— 那是把 K1 仪器上的结论说成了全生产的结论。
    import cce_knot_classify as _K
    _taxo = json.load(open(os.path.join(ROOT, "config/knot_taxonomy.json"), encoding="utf-8"))
    _hash_of = lambda k: _K.instrument_id(
        _taxo, k=k, knot_n=5, s1_pairing=f"round_robin_over_{k}_s1_draws")["instrument_hash"]
    for _prof, _k in (("reply / response", 3), ("outbound_post", 5)):
        _ih = _hash_of(_k)
        _ok, _why = knot_readout_usable("top1", instrument_hash=_ih)
        # ★ 三态纪律: 这台仪器上**从没跑过 K1** ⇒ 是「未测」, 不是「已测不达标」。
        #   我第一版标成 FAILED —— 那是把 not-started 说成 judged-and-failed, 方向反了。
        _state = USABLE if _ok else (
            UNMEASURED if "没有 K1 判定" in _why or "不可跨仪器搬" in _why else FAILED)
        out.append({"组件": f"结层 top-1 @ {_prof} (k={_k})",
                    "状态": _state,
                    "证据": f"仪器 {_ih} · {_why}",
                    "文件": "scripts/cce_k1_status.py"})

    a = panel["agreement"]
    out.append({"组件": "结层 intensity", "状态": FAILED,
                "证据": (f"K1-v2 预注册判定 {v2['layers']['intensity']['passed_texts']}/"
                         f"{v2['layers']['intensity']['of']} 文本; "
                         f"面板复核 {panel['texts']} 文本 A 均值 {a['mean']}, "
                         f"达 0.95 仅 {a['texts_meeting_0.95']}/{panel['texts']}"),
                "文件": "tests/data/phase2/k1_v2_multitext_verdict.json"})
    out.append({"组件": "结层 weight", "状态": FAILED,
                "证据": (f"K1-v2 预注册判定 {v2['layers']['weight']['passed_texts']}/"
                         f"{v2['layers']['weight']['of']} 文本(面板无 weight, 无法复核)"),
                "文件": "tests/data/phase2/k1_v2_multitext_verdict.json"})

    # ── 对齐 ──────────────────────────────────────────────────────────
    sens = _j("tests/data/phase2/align_theta_sensitivity.json")
    out.append({"组件": "九结加权对齐分", "状态": FAILED,
                "证据": (f"θ={sens['theta']} 判决 {sens['verdict_flip_rate']:.1%} 被 weight 抖动翻转"
                         f"(该数是**下界**, 未含 dissolve_hit 噪声); 已随 weight 扣发"),
                "文件": "probes/align_theta_sensitivity.py"})
    ph = _j("tests/data/phase2/playbook_hit_verdict.json")
    pm = _j("tests/data/phase2/playbook_mode_verdict.json")
    out.append({"组件": "top-1 playbook_hit(唯一剩下的对齐出口)", "状态": FAILED,
                "证据": (f"预注册判定 {ph['decision']}: {ph['meeting_criterion']}/{ph['texts']} 文本达标"
                         "。★ 只在答案明显「是」或「否」时稳(极差 0), 中间地带极差 0.3–0.7 —— "
                         "阈值判决正住在中间。非退化闸**过了**, 所以是「测到了但不稳」不是「没测到」"),
                "文件": "tests/data/phase2/playbook_hit_verdict.json"})
    out.append({"组件": "对齐出口 playbook **众数占比**形式(替代尝试)", "状态": FAILED,
                "证据": (f"预注册判定 {pm['decision']}: 达标 {pm['meeting_criterion']}/{pm['texts']}"
                         f"(需 {pm['required']})。★ 改读数形式**确实有改善**(旧判据 4/8 → 新 6/8, "
                         f"非退化由 6/8 同众数降到 {pm['degeneracy']['texts_sharing_top_mode']}/8), "
                         "**但差一个也是差** —— 不采纳, 不下调阈值, 不合并两轮凑数。"
                         "⇒ 对齐线整体保持关闭"),
                "文件": "tests/data/phase2/playbook_mode_verdict.json"})
    _ap = os.path.join(ROOT, "tests/data/phase2/playbook_atoms_verdict.json")
    if os.path.exists(_ap):
        pa = _j("tests/data/phase2/playbook_atoms_verdict.json")
        out.append({"组件": "对齐出口 playbook **原子分解**形式(第二次替代尝试)", "状态": FAILED,
                    "证据": (f"预注册判定 {pa['decision']}: 达标 {pa['meeting_criterion']}/{pa['texts']}(需 7)。"
                             "同一批文本/同一仪器/δ 与判决线逐字同 GEN4, 两条非退化闸都过 —— "
                             "**改善是真的**(4/8 → 6/8), 但未到采纳线 ⇒ 不采纳。"
                             "★ 更锐: 残余不稳定**不在标尺上** —— belong 的正向原子只剩 1 条, "
                             "复合值退化成单个二值判断, 而它在 0/1 间来回摆。"
                             "⇒ 再推一版要动的是 **playbook 原子本身**(效度), 不是读数形态(复现性), "
                             "那是改干预设计, **需 owner 拍板**"),
                    "文件": "tests/data/phase2/playbook_atoms_verdict.json"})
    _ho = _j("results/align_atoms_heldout_v41.json"); _dv = _j("results/align_atoms_calibration.json"); _v5 = _j("results/align_atoms_v5.json")
    _jv = _j("results/align_atoms_jev.json")
    _rw = _j("results/align_atoms_jev_reward.json")
    _fin = _j("results/align_atoms_jev_final.json")
    _cal = sorted(k for k, v in _fin["per_atom"].items() if v["verdict"] == "CALIBRATED")
    _v2 = _j("results/align_atoms_v2.json"); _v2ok = sorted(k for k, v in _v2["per_atom"].items() if v["verdict"] == "VALIDATED")
    _v3 = _j("results/align_atoms_v3.json"); _v3ok = sorted(k for k, v in _v3["per_atom"].items() if v["verdict"] == "VALIDATED")
    _v2drop = sorted(set(_cal) & set(_v2["per_atom"]) - set(_v2ok)); _v2fp = sum(v["failure_types"].get("F_P", 0) for v in _v2["per_atom"].values())
    out.append({"组件": "对齐出口 逐原子三值(读者 top-1 结; Jev 判官; 只判校对通过的条目)", "状态": USABLE,
                "证据": (f"2026-09-30 重做: 不碰结权重(K1 0/5), 只用读者稳定 top-1(K1 可用); 【做】做了/没做/不确定、【禁】违反/未违反/不确定, "
                         f"在场一侧要逐字子串; 不出总分、不出放行布尔。校对 = 构造正反例 × 两种相反问法 × 两次, 8/8 全对才算: "
                         f"开发集(v4){_dv['summary']['calibrated']}/25(准确率 {_dv['summary']['v4_accuracy']}, 旧问法 {_dv['summary']['v1_accuracy']})"
                         f" → 修两处后在**新写的留出集**(v4.1)上 {_ho['summary']['calibrated']}/25(准确率 {_ho['summary']['v4_accuracy']})"
                         f" → v5 加严(每原子再 4 份新草稿 16/16 + 20 条真实回复上两种问法一致率 >= 0.85; suspend/audit 拆成 8 条单动作条目): "
                         f"{_v5['summary']['calibrated']}/{_v5['summary']['in_play']}。上一轮的 11 个里只有 4 个留下 —— 「11 个」是样本太少的假象。"
                         f"⇒ 换判官: Jev 闭选分类器(一题一个条目, 英文操作化描述), 同口径校对 {_jv['summary']['calibrated']}/{_jv['summary']['atoms']}"
                         f"(构造草稿准确率 {_jv['summary']['constructed_accuracy']}); 按预注册发货规则(多于 v5 的 5 个)生产改用 Jev 判官。"
                         f"V1 生产名单 {len(_cal)} 个条目: {' · '.join(_cal)}; 两种问法不一致 ⇒ uncertain; 其余记 not_calibrated(不是「没做」)。"
                         "reward 结重做(短收改机械规则: <=2 句且 <=40 词; 另两条改成只看回复文本的描述), 在没用过的 20 条真实回复上复核: "
                         + " · ".join(f"{k} {v['verdict']}(一致率 {v['natural_agree_rate']})" for k, v in _rw["per_atom"].items())
                         + f"。最终名单 = 全部 29 条在 **60 条**真实回复上对称复核(results/align_atoms_jev_final.json; 20 条时 0.85 线只差 1 条就翻): "
                           f"{_fin['summary']['calibrated']}/29, pain_seek#1 被拿掉(0.817)、suspend#3 进(0.85)、reward#2 仍不进(0.733)"
                         + "。以上是 V1(两种问法一致作准入)的历史。★★ 2026-09-30 V2 取代之(网页 GPT 复审: 两种问法不是同一命题, 自洽 ≠ 正确): "
                           "只用问法 A + 同极性改写 A′ 作反查; 准入改成**真实回复上的受控变形测试**(60 条没用过的回复 × 每条目: 追加充分见证句 / 难负例句 / 中性句 / 原文重读 / A 对 A′; "
                           "一条回复上任一项失败记 1 次, 60 条里至多 1 次才过)。"
                         + f"结果 {_v2['summary']['validated']}/{_v2['summary']['items']}: {' · '.join(_v2ok)}(另加机械条目 reward#0) ⇒ 生产名单从 16 条缩到 {len(_v2ok) + 1} 条, "
                           f"只覆盖 {' / '.join(sorted({k.split('#')[0] for k in _v2ok} | {'reward'}))} 四个结; 其余五个结**整结扣发**(不是「没做」)。"
                           f"V1 入选的 15 条里 {len(_v2drop)} 条没过(主因 F_P: 同一条真实回复上 A 与 A′ 给出相反的确定答案, 合计 {_v2fp} 次; 其次中性句翻转读数) —— V1 的 16 条是「两问法恰好一致」的假象。"
                           "三条预测: P1(>=12 条过)未中 · P2(V1 落选里 >=3 条过)未中 · P3(V1 入选里 >=2 条不过)中。"
                           "★ 这只证明「指定的局部行为测试通过」: 【做】satisfied = 检出一句在做, unsatisfied = **未检出**(不是证明没做); 不是真实草稿上的准确率(无个体金标), 前瞻闭环攒 n>=40 再判; "
                           "★★★ 2026-09-30 V3 取代 V2(多题项口径; 预注册 tests/data/align_atoms_v3_prereg.json): 每个条目用 5 个冻结题面去问, 报在场/不在场/不清的全占比, "
                           "主值要 ≥4 票同侧且 0 票相反; 第 6 个不相交题面只作审计。准入按分布口径(重读漂移 / 中性句漂移 / 见证响应 / 难负例 / 审计题面差, 容差 0.05 / 0.05 / 0.90 / 0.05 / 0.10, 按底稿自助的单侧 95% 界), "
                         + f"在 116 条没用过的真实回复上({_v3['requests']} 次 Jev, {sum(_v3['errors'].values())} 次调用失败按最坏值计): **{_v3['summary']['validated']}/{_v3['summary']['items']}** 通过 —— {' · '.join(_v3ok)}; "
                           f"没过的 {' · '.join(k + '(' + '/'.join(c for c, ok in v['criteria'].items() if not ok) + ')' for k, v in _v3['per_atom'].items() if v['verdict'] != 'VALIDATED')}。"
                           f"⇒ 生产名单 {len(_v3ok) + 1} 条(加机械条目 reward#0), 覆盖 {len({k.split('#')[0] for k in _v3ok} | {'reward'})}/9 个结; display 结没有条目过 ⇒ 整结扣发; reward#1 在 V2 过、V3 的难负例上界 0.0552 擦线不过 ⇒ 按规则拿掉。"
                           f"更严的类别口径(确定值不许变也不许失去确定, 至多 1 条)只有 {_v3['summary']['strict_tier_pass']} 条过 —— Jev 对逐字相同的原文重读就有约 4% 的单票变动, 所以准入看占比漂移而不是看确定值翻不翻。"
                           "三条预测全中(P1 >=15 条过 · P2 suspend#0/belong#1/display#2 不过 · P3 类别口径 <=8 条)。"
                           "★ 占比 = 这五个题面里的支持度, 不是真值概率; 审计只有一个题面, 只代表这一族措辞; 逐条口径, 未做多重性校正。"
                           "线上端到端: V2 判官已在 runner 上跑通(archive/36713557903, 读者 top-1 5/5 稳, pain_seek#1 判出, 17 次请求); 前一次(archive/36712867977)读者 top-1 4/5 不稳 ⇒ 按规则整条扣发, 没走到判官"),
                "文件": "scripts/cce_align_atoms.py · scripts/reply_loop.py · results/align_atoms_v3.json · results/align_atoms_v2.json · results/align_atoms_jev.json · results/align_atoms_jev_reward.json · results/align_atoms_v5.json"})

    # ── 媒体 ──────────────────────────────────────────────────────────
    out.append({"组件": "媒体**存在**声明", "状态": USABLE,
                "证据": f"能力 {cap['media_presence_declaration']['status']}; 出站两档入口必填, FAIL_CLOSED",
                "文件": ".github/prepare.py"})
    mc = _j("tests/data/media_chain_on_history.json")
    out.append({"组件": "媒体**内容**测量(P3 链路)", "状态": USABLE,
                "证据": (f"★ 已在 {mc['files']} 个真实解析产物上整链跑通: "
                         f"{mc['result'].get('pass')} 通过 → {mc['observations']['total']} observations "
                         f"→ {mc['events']['total']} events, **合同全部合法**(含跨模态同步事件)。"
                         f"语言 {mc['language_mix']}。"
                         "★ 2026-09-03 **已进生产**: profile `media_ingest`, 全链回放 complete=true。"
                         "★ 但其中两项**具名扣发**: 抽取质量(ASR/OCR 准确率, 语言相关, 未测) "
                         "与跨域标定(across_domains=NOT_ESTABLISHED)。"
                         "observation 里的文字可作证据引用, **不得当作已验收的转写**。"
                         "★ 2026-09-04 图片链**已晋升 production_github**"
                         "(本机真实素材 6/6 + CI run 33840200869 全链回放, CI 上真跑了 OCR): "
                         "静态图与视频帧共用同一条链、同一份视觉合同, 未分建两套。"
                         "抽取质量: **中文域已有实测**(真实 n=6 中位 0.900, 零文字对照无中生有 0 次)"
                         "+ 合成上界曲线; **英文域仍无一张标注素材 ⇒ 那一半仍未测**, 扣发不变"),
                "文件": ".github/workflows/cce-submit.yml(profile media_ingest)"})

    # ── s1 分布层 ─────────────────────────────────────────────────────
    # ★ 2026-09-28: 此前是一句写死的「同侧 K=3 JS 0.02–0.09」, 生产存档与之矛盾(诊断 #3)。改为从存档现算逐层扣发率。
    import glob as _gl
    _wm = _j("results/within_js_monitor.json")      # 由监测脚本写出, 闸钉它与现算一致
    from cce_full_run import WITHIN_JS_MAX_DEFAULT as WITHIN_JS_MAX, within_js_max
    _n, _over = 0, {k: 0 for k in WITHIN_JS_MAX}
    _cur, _ncur, _ocur = "d4cce4c745f3f991", 0, {k: 0 for k in WITHIN_JS_MAX}   # 现行 k=3 仪器单列(2026-09-30 起阈值按仪器取)
    for _f in _gl.glob(os.path.join(ROOT, "archive", "**", "*s1_readout.json"), recursive=True):
        try:
            _d = json.load(open(_f, encoding="utf-8")); _js = _d["stage1"].get("within_js")
        except Exception:
            continue
        if _js:
            _ih = ((_d.get("stage2") or {}).get("instrument") or {}).get("instrument_hash")
            _mx = within_js_max(_ih)
            _n += 1
            for _k, _v in _js.items():
                _over[_k] = _over.get(_k, 0) + (_v > _mx.get(_k, 1.0))
            if _ih == _cur:
                _ncur += 1
                for _k, _v in _js.items():
                    _ocur[_k] = _ocur.get(_k, 0) + (_v > _mx.get(_k, 1.0))
    out.append({"组件": "s1 四层分布", "状态": USABLE,
                "证据": (f"逐次运行由组内散布闸判: 超噪声底的层扣发 top。存档 {_n} 份读数的逐层扣发率 "
                         + " · ".join(f"{k.replace('_vec', '')} {_over[k]}/{_n}" for k in WITHIN_JS_MAX)
                         + f"(按各自仪器的阈值); 其中现行 k=3 仪器 {_cur} 的 {_ncur} 份: "
                         + " · ".join(f"{k.replace('_vec', '')} {_ocur[k]}/{_ncur}" for k in WITHIN_JS_MAX)
                         + "。★ 2026-09-30 该仪器阈值按原规则(median+2×MAD)重标并过留出检验(results/within_js_recalibration.json): "
                         + " · ".join(f"{k.replace('_vec', '')} {v['old_threshold']}→{v['new_threshold']}(留出扣发 {v['holdout_exceed_new']}, 预示跨次不稳 ρ={v['gate_validity_spearman']})"
                                      for k, v in _j("results/within_js_recalibration.json")["holdout"].items())
                         + "。k=5 仪器 c4419c3e 自采 20+10×2 次同社区帖子重标(results/within_js_recalibration_k5.json): "
                         + " · ".join(f"{k.replace('_vec', '')} {'采纳 ' + str(v['new_threshold']) if v['adopt'] else '留旧 ' + str(v['old_threshold'])}(留出扣发 {v['holdout_exceed_new']}, ρ={v['gate_validity_spearman']})"
                                      for k, v in _j("results/within_js_recalibration_k5.json")["holdout"].items())
                         + " —— k=5 上只有 emotion 层的组内散布明显预示跨次不稳, 其余三层弱(留出仅 10 帖 × 2 次)"
                         + "。★ 撤回: 此前采纳新阈值用的「留出扣发率在 5–25% 带内」只建立在 16 / 10 条文本上, 撑不住(区间整个落在带内至少要 54 条独立文本); "
                           "阈值照用, 带内与否改由零调用序贯监测判(tests/data/within_js_monitor_prereg.json: 文本级, 60/120/180 三次查看, 精确区间)。现状: "
                         + " · ".join(f"{v['instrument']} {v['n_texts']} 条文本 ⇒ {'/'.join(sorted({x['verdict'] for x in v['per_layer'].values()}))}" for v in _wm.values())
                         + "。★ 标定时 s1 的语境串**不含** s0 的【情境】后缀, 生产现在带 —— 2026-09-30 已测(预注册, results/s1_context_suffix_ab.json, "
                           "16 条真实文本 × 带/不带 × 2 次): 四层 "
                         + " · ".join(f"{k.replace('_vec', '')} 超噪 {v['mean_excess_js']}" for k, v in _j("results/s1_context_suffix_ab.json")["result"]["per_layer"].items())
                         + "(判据 >= 0.05)⇒ 全部 NEUTRAL, 后缀不把读数挪出标定条件; desire 有 3/16 条两臂稳定 top-1 不同(分布差仍在噪声内)"),
                "文件": "scripts/cce_knot_classify.py(stage1) · scripts/cce_full_run.py(WITHIN_JS_MAX)"})

    # ── 链上其余段(2026-09-28 补: 表里此前没有它们, 诊断 #33) ─────────
    _pv = _j("results/s0_planted_validity.json")["per_facet"]
    _pp = _j("results/s0_planted_profile.json")["per_facet"]
    _rr = _j("results/s0_residue_referent.json")["arms"]
    _rp = _j("results/s0_residue_profile.json")["arms"]
    # 2026-09-30: 「准确率未测」只是一个字段, 不是整个组件的状态(网页 GPT 第三次复审; Messick / AERA 的证据类别) ⇒ 按面拆成两行, 各自给行为合格与否的判决
    _sp = _j("results/s0_selective_plants.json")["result"]
    _good = [k for k, v in _pp.items() if k != "情绪余温" and v["verdict"] == "RESPONSIVE"]; _weak = [k for k, v in _pp.items() if k != "情绪余温" and v["verdict"] != "RESPONSIVE"]
    _scope = "★ 这是「明说句上的响应与选择性」的行为合格; 自然文本上读得准不准**按设计不估**(没有人类金标, owner 2026-09-23)。重测一致性见 results/s0_retest.json。后端 Jev, 失败回退 MiniMax 并列入 degraded"
    out.append({"组件": "s0 情境读出 · " + " / ".join(_good), "状态": USABLE,
                "证据": ("植入信号(预注册, results/s0_planted_profile.json, 全占比): "
                         + " · ".join(f"{k} 位移 {_pp[k]['dp_target']}, 净连带 TVD {_pp[k]['net_off_target_tvd']}" for k in _good)
                         + f" ⇒ RESPONSIVE。★ 关系位置 对一句无关的话也会动: 两句假句之间 TVD {_sp['sham_floor_tvd']['关系位置'][0]} —— 其中一句(「我通常晚上看这些帖子」)本身蕴含长期关注, 是读出了言外之意, 不是随机噪声, 但下游要知道它对顺口一提很敏感。"
                         + _scope),
                "文件": "scripts/cce_full_run.py(s0) · scripts/cce_s0_jev.py · scripts/cce_workflow_manifest.py"})
    out.append({"组件": "s0 情境读出 · " + " / ".join(_weak), "状态": FAILED,
                "证据": ("目标响应够, 但**会带动邻面**。原植入句(results/s0_planted_profile.json): "
                         + " · ".join(f"{k} 位移 {_pp[k]['dp_target']}, 净连带 TVD {_pp[k]['net_off_target_tvd']}" for k in _weak)
                         + f"。归因确认(预注册, results/s0_selective_plants.json, {_sp['n_roots_complete']} 条没用过的真实评论, 对照 = 等长假句): 换成刻意避开邻面的新植入句后 "
                         + " · ".join(f"{k} {v['verdict']}(目标位移下界 {min(x['target_shift'][1] for x in v['per_wording'].values())}, 邻面净变化上界最大 {max(o['net'][2] for x in v['per_wording'].values() for g, o in x['off_target'].items() if g != '关系位置')})" for k, v in _sp["selective"].items())
                         + "(判据: 每套措辞邻面净变化上界 <= 0.05)⇒ 串扰是真的, 不全是植入句的问题; 原句上更大的那部分连带来自句子自己蕴含邻面: "
                         + " · ".join(f"{k} {v['verdict']}" for k, v in _sp["entailing"].items())
                         + "。⇒ 这两面照常读出, 但下游**不得**把它们与 进程位置/触发事件/资源状态/身体状态 里的邻面当成相互独立的证据。预测 P1/P2(两面都 SELECTIVE)未中, P3(四条蕴含全 NESTED)未中(3/4)。"
                         + _scope),
                "文件": "scripts/cce_full_run.py(s0) · scripts/cce_s0_jev.py · probes/s0_selective_plants.py"})
    out.append({"组件": "s0 情绪余温 读出", "状态": FAILED,
                "证据": ("留出指代最小对(预注册, results/s0_residue_referent.json): 对我方回复的情绪召回 "
                         + " / ".join(f"{a} {v['recovery_pos']}/{v['recovery_neg']}" for a, v in _rr.items())
                         + ", 但别人回复/无关事件被读成余温 "
                         + " / ".join(f"{a} {v['false_attribution']}" for a, v in _rr.items())
                         + "(判据 <= 0.05)⇒ 2026-09-29 起任何模式都**扣发**(cce_s0_jev.READ_WITHHELD), 未声明即 未知; 冷读模式仍是结构冷读 首轮无余温。"
                         "★ 分布口径复测(results/s0_residue_profile.json, 全占比、不取 top-1): 只读回应 泄漏比 "
                         + " / ".join(str(v["leak_ratio"]) for v in _rp["v1"]["shift"].values())
                         + " ⇒ " + _rp["v1"]["verdict"] + "; **成对读(把我方上一条消息一起给)泄漏比 "
                         + " / ".join(str(v["leak_ratio"]) for v in _rp["paired"]["shift"].values())
                         + " ⇒ " + _rp["paired"]["verdict"] + "**。2026-09-29 owner 同意加合同字段 ⇒ **已接线**: response_source.responses[].prior_turn"
                           "(我方上一条消息逐字+sha256) 给了才成对读出、完整分布落 s0_context.json 与 manifest; 没给仍扣发。闸 tests/test_cce_s0_paired_residue.py。"
                           "线上 canary: #1(archive/36572885138)抓到截断 bug(长 prior 把回应截掉, 8 条同为 未知≈0.65), 修后 #2(archive/36580963929)8/8 complete、"
                           "分布彼此分开(正向 1.0×4 / 正向 0.46–0.73×3 / 负向 0.70×1)。自然文本准确率仍未测(无个体金标), 前瞻闭环攒 n>=40 再判"),
                "文件": "scripts/cce_s0_jev.py(READ_WITHHELD) · scripts/cce_full_run.py(s0)"})
    out.append({"组件": "s2b 引用证书(影子段)", "状态": UNMEASURED,
                "证据": ("线上开着(仓库变量 CCE_CITATION_CERT, 未设=开), 只把 top-1=display 且稳定的读数升到 ③′ CITED_UNVERIFIED, "
                         "citable_as_confirmed 恒 False、不改任何判决; 证书语义校验器的准确度未测"),
                "文件": "scripts/cce_citation_certificate.py"})
    out.append({"组件": "s4 出站守卫", "状态": USABLE,
                "证据": ("按 guard_profile 查合规词表 + 破折号纪律 + P7 生成物闸(2026-09-28 接入: 引用未达标机制或 K1 未达标强度读数即拦, "
                         "只认 [[mech:]] / [[knot_intensity|delta:]] 标记)。★ 已知缺口: 合规表读不到或 profile 不存在时静默放行(诊断 P2, 未修)"),
                "文件": "scripts/cce_outbound_guard.py · scripts/cce_strategy_gate.py"})
    return out


def main() -> int:
    rs = rows()
    print("=" * 74)
    print("CCE 投产逐项清单 —— 「能不能投产」不是一句话, 是这张表")
    print("=" * 74)
    w = max(len(r["组件"]) for r in rs)
    for r in rs:
        mark = {"可用": "✓", "已测·不达标": "✗", "未测": "?", "已具备·未接入": "◐"}[r["状态"]]
        print(f" {mark} {r['组件']:<{w}}  {r['状态']}")
        print(f"     {r['证据']}")
        print(f"     └─ {r['文件']}")
    n = {s: sum(1 for r in rs if r["状态"] == s) for s in (USABLE, FAILED, UNMEASURED, NOT_WIRED)}
    print("-" * 74)
    print(f"可用 {n[USABLE]} · 已测不达标 {n[FAILED]} · 已具备未接入 {n[NOT_WIRED]} · **未测 {n[UNMEASURED]}**")
    print("★ 「未测」不是「弱证据」, 是没有读数。它与「已测不达标」「已具备未接入」是三种状态, 修法都不同。")
    print("★ 标「可用」的读数, 其可用性是**逐次运行**由闸在运行时判的, **不是系统的固有属性**。")
    print("  2026-09-04 重验实证: 信封逐位相同、闸代码早于两次 run, 可用集仍然变了 ——")
    print("  post 的 s1.tops.need 与 s2.playbook_primary 双双转扣发; reply 的 playbook **反向**转可用。")
    print("  ⇒ 下游**不得**假定某个读数下次还在。(n=2 无预注册, 是观察不是翻转率:")
    print("   tests/data/phase2/readout_usability_flip_obs.json)")
    import glob as _g
    _n = len(_g.glob(os.path.join(ROOT, "tests", "test_*.py")))
    _g8 = len(_g.glob(os.path.join(ROOT, "tests", "test_cce_*gate*.py")))
    # ★ 2026-09-28: 此前写「{_n} 个测试·{_g8} 道闸 PASS」—— 本表不运行它们, 那是没跑过的 PASS。
    print(f"★ 仓里有 {_n} 个测试文件、{_g8} 个闸测试(本表**不运行**它们, 结果看 CI 合同 job)。引擎跑得动 != 这些读数能用。")
    print("★ 这张表由仓库现算, 不是我说的 —— 见 2026-08-07 立的汇报纪律。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
