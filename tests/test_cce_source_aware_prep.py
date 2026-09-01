#!/usr/bin/env python3
"""source-aware preparation: 在拼成一段之前按来源分流。

GPT 裁决的 P1 项。语义分类器**不接生产删除链**(SHADOW_ONLY) ——
误删真实个人表达的损害高于漏摘, 且分类器的误删发生在测量之前, 下游无从知道
自己吃到的是被错误裁切过的样本。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from cce_structural_gate import (  # noqa: E402
    ProvenanceRequiredError, SEMANTIC_CLASSIFIER_STATUS, SOURCE_TYPE_ROUTING,
    preparation_id, source_aware_preparation, source_aware_preparation_id,
    structural_gate,
)

PERSONAL = "I keep missing what people say in meetings and it wears me out."
TAIL = "Also my left ear feels blocked lately."
SPEC = "Battery life: 48 hours. IP68. Bluetooth 5.3."
TERMS = "By using this service you agree to binding arbitration."

# ── 1. 已知来源直接定性, 不推断 ────────────────────────────────────────
r = source_aware_preparation([
    {"text": PERSONAL, "source_type": "user_authored", "source_ref": "comment_body"},
    {"text": SPEC, "source_type": "product_specification", "source_ref": "spec_sheet"},
    {"text": TERMS, "source_type": "terms", "source_ref": "tos.pdf"},
    {"text": TAIL, "source_type": None},
])
assert r["verdict"] == "MEASURE"
assert PERSONAL in r["subject_text"] and TAIL in r["subject_text"]
assert SPEC not in r["subject_text"] and TERMS not in r["subject_text"], \
    "★ 已声明来源为规格/条款的段落必须被摘掉"
assert r["span_counts"] == {"PERSONAL": 1, "NONPERSONAL": 2, "AMBIGUOUS": 1}
assert [s["basis"] for s in r["spans"]] == [
    "declared_provenance", "declared_provenance", "declared_provenance", "no_provenance"]

# ── 2. 这正是纯结构闸抓不到的那一类 ───────────────────────────────────
flat = "\n\n".join([PERSONAL, SPEC, TERMS, TAIL])
plain = structural_gate(flat)
assert SPEC in (plain["subject_text"] or ""), \
    "前提失效: 无标记的产品规格本来就该穿透纯结构闸, 否则这个测试没有意义"
assert SPEC not in r["subject_text"], "source-aware 必须拦下纯结构闸拦不住的那一类"

# ── 3. 不认识的 source_type 不许猜 —— 退回结构闸, 证不出就保留 ─────────
unk = source_aware_preparation([
    {"text": PERSONAL, "source_type": "some_future_source"},
    {"text": SPEC, "source_type": "product_metadata"},
])
assert unk["spans"][0]["basis"] == "unrecognized_source_type"
assert PERSONAL in unk["subject_text"], \
    "★ 反向失败: 遇到不认识的来源就把个人表达删了 —— 误删方向反了"
assert SPEC not in unk["subject_text"]

# ── 4. 禁止先拼成一段再让下游猜来源 ───────────────────────────────────
try:
    source_aware_preparation([{"text": flat}])
except ProvenanceRequiredError:
    pass
else:
    raise AssertionError("★ 反向失败: 上游先拼成一段没传来源, 却被静默放行")
# 显式声明确实无来源信息 -> 允许, 但那是另一种制备
loose = source_aware_preparation([{"text": flat}], require_provenance=False)
assert loose["verdict"] == "MEASURE"

# ── 5. 全非个人 -> 0 次调用弃权 ───────────────────────────────────────
none = source_aware_preparation([
    {"text": SPEC, "source_type": "product_specification"},
    {"text": TERMS, "source_type": "terms"},
])
assert none["verdict"] == "ABSTAIN_NO_INFERABLE_SUBJECT" and none["subject_text"] is None

# ── 6. 制备身份: 与纯结构闸必须不同, 且不传 provenance 时旧路径不受影响 ─
assert source_aware_preparation_id() != preparation_id(), \
    "★ 反向失败: 换了制备却是同一个 preparation_id"
assert source_aware_preparation_id().startswith("prep_src_")
assert structural_gate(flat)["preparation_id"] == preparation_id(), \
    "★ 反向失败: 加了新路径把原有结构闸的 preparation_id 也改了 —— 已算好的标定桥接会作废"

# ── 7. 语义分类器不得接进生产删除链 ───────────────────────────────────
assert SEMANTIC_CLASSIFIER_STATUS == "SHADOW_ONLY"
assert r["semantic_classifier"] == "SHADOW_ONLY"
# 制备必须是 0 次调用的确定性过程。查的是**真的发起网络请求**, 不是字符串里出现 http
# (链接正则里本来就有 https?://, 拿裸 "http" 当判据是假检查)。
import ast as _ast  # noqa: E402
_tree = _ast.parse(open(os.path.join(ROOT, "scripts", "cce_structural_gate.py"), encoding="utf-8").read())
_imports = {n.names[0].name.split(".")[0] for n in _ast.walk(_tree)
            if isinstance(n, _ast.Import)} | {n.module.split(".")[0] for n in _ast.walk(_tree)
            if isinstance(n, _ast.ImportFrom) and n.module}
_net = {"requests", "httpx", "urllib", "urllib3", "http", "socket", "openai", "aiohttp"}
assert not (_imports & _net), \
    f"★ 反向失败: 制备层 import 了网络模块 {sorted(_imports & _net)} —— 制备必须 0 次调用"
# 只查 import: 不导入任何网络模块就发不出请求。按方法名(.get/.post)判是假检查 ——
# dict.get 会命中, 第一版就是这么误报的。
assert _imports <= {"hashlib", "re", "json", "sys", "cce_preparation_bridge"}, \
    f"★ 制备层 import 了预期之外的模块: {sorted(_imports - {'hashlib','re','json','sys','cce_preparation_bridge'})}"

# ── 8. 路由表: 只有 user_authored 走 PERSONAL ─────────────────────────
assert [k for k, v in SOURCE_TYPE_ROUTING.items() if v == "PERSONAL"] == ["user_authored"], \
    "★ 反向失败: 多了一个被当成个人表达的来源类型 —— 那是误删风险的反面, 会把非个人内容当主体测量"

print("test_cce_source_aware_prep: OK "
      "(已知来源不推断 | 拦下纯结构闸拦不住的规格/条款 | 不认识的来源不猜 | "
      "禁止先拼再猜 | 新制备另立 preparation_id 且不动旧的 | 分类器 SHADOW_ONLY)")
