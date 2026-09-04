#!/usr/bin/env python3
"""静态图片入本体 + 2026-08-15 那个 P0 的闭合。

## 两条边界由 2026-08-15 的否决划定, 本测试逐条钉住
· 否决「**静态图片与视频帧各建一套视觉合同**」⇒ 必须共用 cce.visual_observation.v1,
  图片只是 selector 退化(whole / t=null)
· 否决「因视觉描述已走 outbound_post 就声称图片全链生产可用」⇒ 状态仍须是 component_only

## P0(2026-08-15 登记): OCR 原始 box 被丢弃 ⇒ 结论不能回指图像区域
两段都要闭合: ① 解析器保住 box ② box 进到 Foundation observation。
★ 老产物没有区域时必须记 None 并标注, **不许补零** —— 补零会让「没有区域」看起来像「区域在原点」。
"""
import json
import os
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from cce_foundation_adapter import adapt                      # noqa: E402
from cce_image_ingest import to_parse_artifact, validate      # noqa: E402
from cce_video_parse import _norm_box, _ocr_rows              # noqa: E402

CAPS = {c["id"]: c for c in json.load(
    open(os.path.join(ROOT, "config/cce_capability_registry_v1.json"), encoding="utf-8")
)["capabilities"]}

# ── ① 解析器保住 box(P0 前半段) ───────────────────────────────────────
rows = _ocr_rows([[[[1, 2], [9, 2], [9, 6], [1, 6]], "hello", "0.93"]])
assert rows == [("hello", 0.93, [1, 2, 8, 4])], rows
assert _norm_box([[10, 20], [110, 20], [110, 60], [10, 60]]) == [10, 20, 100, 40]
assert _norm_box([[10, 20], [10, 20]]) is None, "★ 退化框必须记 None, 不许当成 0 宽高的区域"
assert _norm_box("nope") is None

# ── ② 合同共用: 图片是 selector 退化, 不是另一套 ───────────────────────
SCHEMA = json.load(open(os.path.join(ROOT, "config/cce_visual_observation_v1.schema.json"),
                        encoding="utf-8"))
assert SCHEMA["properties"]["asset"]["properties"]["media_type"]["enum"] == \
    ["image", "video_frame"], "★ 图片与视频帧必须在**同一个** media_type 枚举里"
assert "不是两套合同" in SCHEMA["properties"]["asset"]["properties"]["media_type"]["description"]
assert SCHEMA["properties"]["selector"]["properties"]["type"]["enum"] == ["whole", "temporal"]

vo = {"kind": "cce.visual_observation.v1",
      "asset": {"media_type": "image", "sha256": "a" * 64,
                "width": 100, "height": 50, "orientation": None},
      "selector": {"type": "whole", "t": None},
      "observations": [{"channel": "ocr_text", "assertion": "observed", "value": "hi",
                        "confidence": 0.9, "language": None, "model": "RapidOCR",
                        "region": {"unit": "pixel", "xywh": [1, 2, 8, 4]}}],
      "provenance": {"activity": "cce_image_ingest", "agent": None,
                     "generated_at": "2026-09-03T00:00:00", "source_path": "x.png"},
      "rights": {"c2pa": "absent", "iptc": "absent"},
      "completeness": {"status": "ok", "conf_unparsed": 0, "box_unparsed": 0, "error": None}}
ok, errs = validate(vo)
assert ok, errs
# ★ 反向: 区域缺 unit / 断言词自造 / 完整性态自造 —— 各自不合合同
for mut, why in (
        (lambda v: v["observations"][0]["region"].pop("unit"), "region 缺 unit"),
        (lambda v: v["observations"][0].update(assertion="guessed"), "自造断言词"),
        (lambda v: v["completeness"].update(status="mostly_ok"), "自造完整性态")):
    bad = json.loads(json.dumps(vo)); mut(bad)
    assert not validate(bad)[0], f"★ {why} 竟然过了合同"

# ── ③ P0 后半段: 区域必须进 Foundation observation ────────────────────
import tempfile
art = to_parse_artifact(vo, "x.png")
_fd, _tmp = tempfile.mkstemp(suffix=".json"); os.close(_fd)
open(_tmp, "w", encoding="utf-8").write(json.dumps(art, ensure_ascii=False))
case = adapt(art, Path(_tmp))
ost = [o for o in case["observations"] if o["kind"] == "on_screen_text"]
assert ost and ost[0]["regions"] == [{"unit": "pixel", "xywh": [1, 2, 8, 4]}], ost[:1]
assert ost[0]["region_unresolved"] == 0

# ★ 老产物(无 ocr_regions): 记 None 并标注, **不许补零**
old = {"name": "old", "duration": 5.0, "ocr": {"0.5": ["a", "b"]}, "audio": {}}
old_case = adapt(old, Path(_tmp))
oo = [o for o in old_case["observations"] if o["kind"] == "on_screen_text"][0]
assert oo["regions"] is None, "★ 无区域必须记 None"
assert "不得" in oo["★regions_absent_why"], "★ 必须写明不得声称能回指区域"
assert not any(isinstance(r, dict) and r.get("xywh") == [0, 0, 0, 0]
               for r in (oo["regions"] or [])), "★ 不许补零"

# ── ★ 权利/来源三态: 「查不了」不许写成「查过没有」 ────────────────────
#    2026-09-03: 我最初硬编码 rights={"c2pa":"absent","iptc":"absent"} —— **根本没查过**。
#    `absent` 的意思是「查过、没有」。库里早有通则:
#    empty_verified(查过确实为空) 与 missing_parse_failed(不知道) 必须分开。
from cce_image_ingest import rights_state  # noqa: E402
_src_ii = open(os.path.join(ROOT, "scripts", "cce_image_ingest.py"), encoding="utf-8").read()
assert '"c2pa": "absent"' not in _src_ii and "'c2pa': 'absent'" not in _src_ii, \
    "★ C2PA 不得被硬编码成 absent —— 没有解析器时那是在断言未经核实的事"
assert "rights_state(path)" in _src_ii, "★ 必须真查, 不是写死"

_r = rights_state(os.path.join(ROOT, "config", "cce_visual_observation_v1.schema.json"))
assert set(_r) == {"iptc", "c2pa"} and all(
    v in ("present", "absent", "not_available") for v in _r.values()), _r

# ★ 不对称判定: C2PA 官方库不在时, **未命中标记必须记 not_available 而非 absent**
try:
    import c2pa  # noqa: F401
    _HAS_C2PA = True
except Exception:
    _HAS_C2PA = False
if not _HAS_C2PA:
    assert _r["c2pa"] != "absent", \
        "★ 没有 C2PA 解析器却报 absent —— 「找不到标记」不等于「没有来源信息」"
    assert "阳性证据可信" in _src_ii and "不等于「没有」" in _src_ii, \
        "★ 不对称判定的理由要留在原地"

# ── ④ 边界: 图片链**不得**被声称为生产可用 ────────────────────────────
cap = CAPS["standalone_image_ingest"]
# ★ 2026-09-04 晋升 production_github。但 2026-08-15 那条否决**不因晋升而失效** ——
#   它否决的是「因视觉描述已走 outbound_post 就**顺带声称**图片全链可用」。
#   现在可以声称, 靠的是**两半各自实测**, 不是顺带。所以要钉住的是「凭据是什么」。
assert cap["status"] == "production_github", f"★ 状态未晋升: {cap['status']}"
assert cap["fallback_policy"] == "WITHHOLD", "★ 晋升后仍要扣发未测的读数"
_ev = " ".join(cap["evidence_required"])
assert "6/6" in _ev and "本机真实素材" in _ev, "★ 本机真实素材那一半的实测结果要写明"
assert "33840200869" in _ev, "★ CI 那一半必须给出**具体 run id**, 否则「CI 验过」不可复核"
assert "真跑了 OCR" in _ev, "★ 要写明 CI 上跑的是真 OCR 而非降级路径"
assert "文本闸" in _ev and "看不见" in _ev, \
    "★ 「为什么真实素材不能进 CI」这个理由必须留下 —— 否则下一个人会去补这一半"
assert "具名扣发" in _ev, "★ 晋升不等于抽取质量已测"
# 晋升了, 但抽取质量与 VLM 仍在 missing —— 不许被顺带划掉
_m = " ".join(cap["missing"])
assert "抽取质量" in _m and "刻意不照现状接" in _m, \
    "★ 晋升只覆盖「链能不能跑」, 不覆盖抽取质量与 VLM"
# ★ 2026-09-04: C2PA 已接官方库做真解析 ⇒ 它离开 missing 进入 implemented。
#   但**边界不随之消失** —— 三态都不得据以推断媒体为假, 这条要跟着搬, 不是随实现一起删掉。
_all = " ".join(cap["missing"]) + " " + " ".join(cap.get("implemented") or [])
assert "C2PA" in _all and "真解析" in _all, "★ C2PA 的状态(未做/已做)必须在注册表里说清"
assert "C2PA" not in " ".join(cap["missing"]), \
    "★ 已接真解析就不该还留在 missing —— 那会让下一个人重做"
assert "不得据此推断媒体为假" in _all, \
    "★ 换了实现, 边界不变: 三态都不得用来推断媒体为假(2026-08-15 调研结论)"
import cce_image_ingest as _II
assert _II.c2pa_state(os.path.join(os.path.dirname(_tmp), os.path.basename(_tmp))) in \
    ("present", "absent", "not_available"), "★ c2pa_state 必须只出这三态"

os.unlink(_tmp)

print("test_cce_image_ingest: OK (P0 两段闭合: 解析器保 box + 区域进 observation | "
      "图片与视频帧**共用**合同(selector 退化) · 三条反向不合合同各自见红 | "
      "老产物记 None 不补零 | 图片链已晋升 production_github(本机 6/6 + CI run 33840200869 真跑 OCR), 但抽取质量与 VLM 仍在 missing, 未被顺带划掉)")
