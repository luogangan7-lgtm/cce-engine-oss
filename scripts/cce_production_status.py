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
    out.append({"组件": "s0 情境读出(5 面)", "状态": UNMEASURED,
                "证据": ("**没有人类金标**(owner 2026-09-23), 自然文本准确度无从测; 重测一致性见 results/s0_retest.json。"
                         "植入信号必要条件(预注册, results/s0_planted_validity.json, 明说句): "
                         + " · ".join(f"{k} {v['verdict']}(召回 {v['recovery']}, 净连带 {v['net_off_target']})" for k, v in _pv.items() if k != "情绪余温")
                         + "(top-1 口径, 已被下面的分布口径取代)。★ 分布口径复测(预注册, results/s0_planted_profile.json, 全占比): "
                         + " · ".join(f"{k} {v['verdict']}(位移 {v['dp_target']}, 净连带 TVD {v['net_off_target_tvd']})" for k, v in _pp.items() if k != "情绪余温")
                         + "。WEAK 两面的连带集中在 进程位置↔触发事件↔资源状态(植入句本身蕴含, 事后分析)。后端 Jev, 失败回退 MiniMax 并列入 degraded"),
                "文件": "scripts/cce_full_run.py(s0) · scripts/cce_s0_jev.py · scripts/cce_workflow_manifest.py"})
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
