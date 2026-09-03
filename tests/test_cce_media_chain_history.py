#!/usr/bin/env python3
"""P3 链路吃真实多模态产物的能力证据 —— 275 个历史解析, 零 API 调用。

## 这条测试为一次**方法论错误**而设
我把 276 个历史视频解析判为「域不同, 不能当能力证据」。
★ owner 2026-08-12 的裁定是「随便投入一篇文章/一段聊天, 能够分析动态占比」,
  并当场用**一段与助听器毫无关系的中文聊天**实证通用性; 同时**否决了我三版
  「每个域配一套容器」的方案**。我这次是同一个错换件衣服 —— 又拿「域」当准入容器。

## 三件事必须拆开(混在一起就是我犯的那个错)
· **能不能读**(capability): 域无关 —— 本测试就是它的证据
· **抽取质量**(ASR/OCR 在不同语言上的准确率): 语言相关, **仍未测**
· **分辨率/阈值**(calibration): 域相关, across_domains=NOT_ESTABLISHED, **禁止跨域搬**
我原来是拿第三条的约束去否了第一条。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "probes"))
from media_chain_on_history import run  # noqa: E402

ART = json.load(open(os.path.join(ROOT, "tests/data/media_chain_on_history.json"),
                     encoding="utf-8"))

# ── 能力: 绝大多数历史产物能整链跑通且合同合法 ────────────────────────
res = ART["result"]
assert res.get("pass", 0) >= 270, f"★ 通过数 {res.get('pass')} 偏低, 能力结论要重估"
assert res.get("chain_error", 0) == 0, f"★ 链路异常 {res.get('chain_error')} 个"
assert res.get("contract_fail", 0) == 0, f"★ 合同不合法 {res.get('contract_fail')} 个"
assert ART["observations"]["total"] > 10000 and ART["events"]["total"] > 10000

# ── 五类观察 / 六类事件都真的出现过(不是只跑通一种) ───────────────────
assert set(ART["observation_kinds"]) >= {
    "audio_tags", "on_screen_text", "shot_boundary",
    "speech_transcript", "visual_frame_description"}, ART["observation_kinds"]
assert "cross_modal_synchronization" in ART["event_types"], \
    "★ 跨模态同步事件没出现 —— 那是多模态相对纯文本的唯一增量"

# ── ★ 抽样会骗人: 全量语言分布必须落盘 ────────────────────────────────
#    我抽样 80 个得出 en=2, 全量是 en=32。**抽样结论不许当全量结论。**
lm = ART["language_mix"]
_skipped = res.get("not_a_parse_artifact", 0)
assert sum(lm.values()) == ART["files"] - _skipped, \
    f"★ 语言分布必须覆盖全量(减去 {_skipped} 个非解析产物), 不是抽样"
assert lm.get("en", 0) >= 20, \
    f"★ 英文样本 {lm.get('en')} —— 若真的极少, 「域不是问题」的论证要另找依据"

# ── ★ 定位: 能力 != 已接入, 也 != 标定可搬 ────────────────────────────
assert ART["★status"].startswith("CAPABILITY_DEMONSTRATED")
assert "抽取质量" in ART["★what_it_does_not_show"] and \
       "NOT_ESTABLISHED" in ART["★what_it_does_not_show"], \
    "★ 必须写明它**不**证明什么 —— 否则下一个人会拿它当标定证据"

# ── 可重跑, 结论稳定 ──────────────────────────────────────────────────
live = run(limit=20)
assert live["result"].get("chain_error", 0) == 0 and live["result"].get("contract_fail", 0) == 0

print(f"test_cce_media_chain_history: OK ({res['pass']}/{ART['files']} 整链跑通 · "
      f"{ART['observations']['total']} obs → {ART['events']['total']} events 合同全合法 | "
      f"全量语言 {lm} (抽样曾误报 en=2) | "
      "定位: 能力已实证, 但抽取质量未测 · 标定禁跨域搬)")
