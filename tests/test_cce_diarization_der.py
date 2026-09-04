#!/usr/bin/env python3
"""说话人分离: 从「拿不到凭据」变成有实测 —— 我原来的判断错在两处。

## 错在哪
登记「pyannote 是受限模型, 需 HF token ⇒ 拿不到凭据 ⇒ BLOCKED_EXTERNAL」。
① `pyannote.audio` 是 **MIT 开源包**, 受限的是**权重** —— 包与权重不是一回事, 装包无需 token
② 3D-Speaker 的默认路径 `include_overlap=False` **根本不碰** pyannote 权重
   (源码已核: 只有 include_overlap=True 才 require hf_access_token)
⇒ 无账号、无 token、无点击条款即可跑。

## 三条不许越过的线
· DER 的两档 profile 参数不同 ⇒ **禁止跨档比较**
· 官方 DER **未注明 profile** ⇒ 只作量级参考, **不作验收线**
· DER 低 ≠ 说话人数对 ⇒ **不许拿 DER 给说话人数背书**
"""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = json.load(open(os.path.join(ROOT, "tests/data/phase2/diarization_der.json"), encoding="utf-8"))
M = json.load(open(os.path.join(ROOT, "config/cce_eval_benchmarks_v1.json"), encoding="utf-8"))

# ── ① 四个准入字段分开且全为「无」 ──────────────────────────────────
a = D["★access_fields_kept_separate"]
assert a["account_required"] is False and a["token_required"] is False \
    and a["click_through_terms_required"] is False and a["license_restriction"] == "无(ModelScope 权重, Apache-2.0 代码)", \
    f"★ 准入字段不合格: {a}"
assert "四件事" in D["★why_four_fields"], "★ 「四字段不许合并」的理由要留在原地"

# ── ② 两档 profile 都在, 参数不同, 且禁止跨档比 ─────────────────────
P = D["der_profiles"]
assert set(P) == {"STRICT", "LEGACY"} and P["STRICT"]["params"] != P["LEGACY"]["params"]
assert "禁止" in D["★no_cross_profile_ranking"]
assert P["STRICT"]["params"]["collar"] == 0.0 and P["STRICT"]["params"]["skip_overlap"] is False
# STRICT 必须比 LEGACY 差 —— 若不然, 说明打分器参数没生效
assert P["STRICT"]["aggregate"] > P["LEGACY"]["aggregate"], \
    "★ STRICT 不比 LEGACY 差 ⇒ collar/overlap 参数没生效, 先查打分器"

# ── ③ 官方数只作量级参考 ────────────────────────────────────────────
o = D["official_reference"]
assert "不作验收线" in o["★profile_unknown"], "★ 未注明 profile 的数不许当验收线"
assert "不能说" in D["★reading"], "★ 只能说同量级, 不能说「我们更好」"

# ── ④ DER 低 ≠ 说话人数对 ───────────────────────────────────────────
s = D["★speaker_count_accuracy"]
assert s["correct"] < s["n"], "★ 若说话人数全对, 这条断言要换 —— 但别删掉这个区分"
assert "不许拿 DER 给说话人数背书" in s["★note"]

# ── ⑤ 结构性代价要写明 ──────────────────────────────────────────────
assert "不检测重叠语音" in D["★structural_limit"], \
    "★ include_overlap=False 的代价要写明, 不能只报好数字"

# ── ⑥ manifest 与实测一致(选中的实现、冻结的配置) ───────────────────
sel = M["diarization_implementations"]["3d_speaker"]
assert sel["status"] == "SELECTED"
assert sel["config_frozen"] == {"include_overlap": False, "hf_access_token": None}
assert "include_overlap=False" in D["implementation"] or "include_overlap=False" in D["★structural_limit"]

# ── ⑦ RTF 必须本机铸值, 不许引用网上的数 ────────────────────────────
assert "本机实测铸值" in D["rtf_cpu"]["★measured_locally"], \
    "★ CPU RTF 官方无同口径数字 ⇒ 必须本机测, 不许引用网上的"

print(f"test_cce_diarization_der: OK (3D-Speaker 无 token 路径 · VoxConverse dev n={D['n']} | "
      f"STRICT {P['STRICT']['aggregate']} / LEGACY {P['LEGACY']['aggregate']}(**禁止跨档比**) | "
      f"官方 {o['value']} 未注明 profile ⇒ 只作量级参考 | "
      f"说话人数正确 {s['correct']}/{s['n']} —— **DER 低不等于人数对** | "
      f"CPU RTF 中位 {D['rtf_cpu']['median']}(本机铸值) | 不检测重叠是如实代价)")
