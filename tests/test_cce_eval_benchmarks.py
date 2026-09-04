#!/usr/bin/env python3
"""评测基准 manifest: 四个准入字段**永不合并**, 评分口径**逐库分开**。

## 为什么每一列都单列
它们都是「压缩会出错」的实例, 2026-09-04 逐条核实过:
· sherpa-onnx reverb 权重: 可匿名直链下载(前三项全 false), 但许可 **non-commercial**
· NeMo/NGC: 可匿名 curl, 但**下载即视为接受条款**
· Sortformer: HF 非受限, 但 **CC-BY-NC** ⇒ 商用不可用
· pyannote.audio: **包** MIT 开源, 受限的是**权重** —— 我原来就是把这两个混了, 才误判 BLOCKED
· CORD: 许可与可得性都好, 但它是**印尼**收据 ⇒ 语种不对, 差点被选中
· SpeechBrain: 权重开放, 但没有 turnkey diarizer ⇒ **开放不等于适合当验收实现**
"""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M = json.load(open(os.path.join(ROOT, "config/cce_eval_benchmarks_v1.json"), encoding="utf-8"))
FIELDS = ("account_required", "token_required", "click_through_terms", "license_restriction")

# ── ① 四字段必须逐个存在, 不许被合并 ────────────────────────────────
for name, d in list(M["datasets"].items()) + list(M["diarization_implementations"].items()):
    if d.get("status") in ("EXCLUDED", "NOT_USED", "EXCLUDED_FROM_ENGLISH_AGGREGATE") \
            and not all(f in d for f in FIELDS):
        assert "★excluded_why" in d, f"★ {name}: 排除的必须写明理由"
        continue
    for f in FIELDS:
        assert f in d, f"★ {name} 缺字段 {f} —— 四个准入字段不许合并"
    assert not any(k.lower() in ("open", "is_open", "free") for k in d), \
        f"★ {name} 出现了合并字段 —— 四字段压成一个布尔正是本文件要防的"

# ── ② 反例必须在, 否则这条规则没有证据支撑 ──────────────────────────
cx = M["★four_access_fields_never_collapse"]["counterexamples_verified_2026-09-04"]
assert len(cx) >= 4, "★ 「不许合并」这条规则必须自带反例, 否则是空话"
assert any("non-commercial" in c for c in cx), "★ 缺「可匿名下载但非商用」这个反例"
assert any("包" in c and "权重" in c for c in cx), \
    "★ 缺「包开源但权重受限」这个反例 —— 我自己就栽在这上面"

# ── ③ 被选中的实现必须冻结配置 ──────────────────────────────────────
sel = [k for k, v in M["diarization_implementations"].items() if v.get("status") == "SELECTED"]
assert len(sel) == 1, f"★ 应恰好选一个验收实现, 实际 {sel}"
s = M["diarization_implementations"][sel[0]]
assert s["config_frozen"] == {"include_overlap": False, "hf_access_token": None}, \
    "★ 配置必须冻结 —— 只写实现名不够, 配置不同准入结论就不同"
assert "profile_unknown" in json.dumps(s, ensure_ascii=False), \
    "★ 官方 DER 未注明 profile 这件事必须写明, 否则会被当成验收线"
assert "★structural_limit" in s, "★ 不检测重叠语音这个代价要写明"

# ── ④ DER profile 冻结且禁止跨档比较 ────────────────────────────────
P = M["der_scorer_profiles"]
assert "禁止" in P["★no_cross_profile_ranking"]
for prof in ("STRICT", "LEGACY"):
    for sw in ("collar_sec", "score_overlap", "oracle_vad", "oracle_num_speakers"):
        assert sw in P[prof], f"★ {prof} 缺开关 {sw} —— 四个开关任一不同 DER 就不可比"
assert P["STRICT"] != P["LEGACY"], "★ 两档必须真的不同"

# ── ⑤ 语料不许进仓 ──────────────────────────────────────────────────
assert "不入仓" in M["★corpora_never_in_repo"]
import subprocess
r = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
if r.returncode == 0:
    bad = [p for p in r.stdout.split("\n")
           if any(x in p for x in ("cce-eval-corpora", "LibriSpeech", "textocr_val", "voxconverse"))]
    assert not bad, f"★ 语料进仓了: {bad[:3]}"

# ── ⑥ 排除的每一项都要有理由(不许静默排除) ──────────────────────────
for name, d in list(M["datasets"].items()) + list(M["diarization_implementations"].items()):
    if str(d.get("status", "")).startswith(("EXCLUDED", "NOT_USED")):
        assert d.get("★excluded_why"), f"★ {name} 被排除但没写为什么"

print(f"test_cce_eval_benchmarks: OK ({len(M['datasets'])} 个数据集 · "
      f"{len(M['diarization_implementations'])} 个实现 | 四个准入字段逐个在位, 未被合并 | "
      f"{len(cx)} 条反例支撑「不许合并」(含「包开源但权重受限」——我自己栽过的那条) | "
      f"验收实现 {sel[0]} 配置已冻结 | DER 两档 profile 冻结且禁止跨档比 | "
      "排除项各自写明理由 | 语料零入仓)")
