#!/usr/bin/env python3
"""模块边界守卫：哪些是生产内核、哪些是一次性探针，必须能被机器区分。

## 起因（2026-09-01 我自己的误判）
我在整链审计里把「实验脚本占仓库过半（5352/9794 行）」列为重构债，
建议清理。**前提是错的**：

- `scripts/exp_*.py`（1885 行）**不是实验脚本**，是生产内核 ——
  它持有本体常量（DESIRES / NEED_KEYS / EMOTIONS / ACTIONS）、
  LLM 调用管道（call_parse / call_model / extract_json_robust）与距离函数
  （js_divergence），被 **6 个生产文件 + 5 个探针**共用。删它 = 拆引擎。
- `probes/*.py`（3467 行）**才是**一次性探针，且已验证生产不 import 它们。

一个叫 `exp_` 的文件承载生产内核，下一个审计者会做出和我一样的误判。
没有改名（会动 11 处 import，并切断文档/记忆里按名引用的可追溯性），
改为**把依赖钉死**：删它、改名、少导出一个符号，都立刻见红。
"""
import ast
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS, PROBES = ROOT / "scripts", ROOT / "probes"


def imports_from(path, prefix):
    """返回 {模块: {符号}}，只看 `from <prefix>... import ...`。"""
    out = defaultdict(set)
    for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(n, ast.ImportFrom) and n.module and n.module.startswith(prefix):
            out[n.module] |= {a.name for a in n.names}
    return out


# ── ① exp_* 是生产内核：**逐文件**钉死依赖面 ─────────────────────────────
# ⚠️ 2026-09-01 首版钉的是"并集"，反向测试暴露它是假检查：
#    从 cce_response_chain 删掉 EMOTIONS，因 cce_full_run 也导入它，并集不变 ⇒ 仍绿。
#    **聚合掩盖了细节。** 改为逐文件 —— 任一文件的依赖变化都必须重新报数。
PER_FILE = {
    "cce_full_run.py": {
        "exp_crossmodel_desire": ["call_model"],
        "exp_v4_causal_chain": ["EMOTIONS"],
        "exp_v4_full_validation": ["extract_json_robust"]},
    "cce_knot_classify.py": {
        "exp_crossmodel_desire": ["MODELS", "call_model"],
        "exp_v4_causal_chain": ["ACTIONS", "EMOTIONS"],
        "exp_v4_full_validation": ["DESIRES", "NEED_KEYS",
                                   # ★ 2026-09-05 gen6 新增: 指纹要哈希**真实 prompt**,
                                   #   就必须用产 prompt 的那个函数, 不能另抄一份 ——
                                   #   另抄一份正是 gen1→gen4 那个洞的成因。
                                   "build_prompt", "call_parse",
                                   "extract_json_robust", "js_divergence", "top_label"]},
    "cce_response_chain.py": {
        "exp_v4_causal_chain": ["ACTIONS", "EMOTIONS"],
        "exp_v4_full_validation": ["DESIRES", "NEED_KEYS"]},
    "distill_subjects.py": {
        "exp_crossmodel_desire": ["call_model"],
        "exp_v4_full_validation": ["extract_json_robust"]},
    "reply_loop.py": {
        "exp_crossmodel_desire": ["DESIRES"],
        "exp_v4_causal_chain": ["ACTIONS", "EMOTIONS"]},
    "simulate_subjects.py": {
        "exp_crossmodel_desire": ["call_model"],
        "exp_v4_full_validation": ["extract_json_robust"]},
}
actual = {}
for f in sorted(SCRIPTS.glob("*.py")):
    if f.name.startswith("exp_"):
        continue
    got = imports_from(f, "exp_")
    if got:
        actual[f.name] = {m: sorted(v) for m, v in sorted(got.items())}
assert actual == PER_FILE, (
    "★ 生产对 exp_* 的依赖面变了（逐文件）。\n"
    f"  多出/变化：{ {k: v for k, v in actual.items() if PER_FILE.get(k) != v} }\n"
    f"  缺失：{ {k: v for k, v in PER_FILE.items() if actual.get(k) != v} }\n"
    "  这三个模块是**生产内核**（本体常量 + LLM 调用管道 + 距离函数），不是实验脚本。"
    "删除/改名/归档会拆掉引擎；依赖面变化必须重新报数。")
for m in {mod for v in PER_FILE.values() for mod in v}:
    assert (SCRIPTS / f"{m}.py").exists(), f"★ 生产内核 {m}.py 不见了"

# ── ② probes/ 必须与生产单向隔离 ───────────────────────────────────────────
# 探针可以依赖生产（取被测对象），生产**绝不可**依赖探针。
leaked = []
for f in sorted(SCRIPTS.glob("*.py")):
    t = f.read_text(encoding="utf-8")
    if "from probes" in t or "import probes" in t:
        leaked.append(f.name)
assert not leaked, \
    (f"★ 生产代码 import 了探针：{leaked}。探针是一次性的、判决线写死在文件头的脚本，"
     "生产依赖它们等于把一次性实验焊进产线。")

# 反向是允许的，且确实存在 —— 钉住数量，防它悄悄涨到"探针即生产"
probe_deps = [f.name for f in sorted(PROBES.glob("*.py"))
              if imports_from(f, "exp_") or "from cce_" in f.read_text(encoding="utf-8")]
assert probe_deps, "★ 探针一个都不依赖被测对象？那它们测的不是这台引擎"

print(f"test_cce_module_boundary: OK (exp_* 生产内核 {len({m for v in PER_FILE.values() for m in v})} 模块/"
      f"{sum(len(x) for v in PER_FILE.values() for x in v.values())} 处导入/{len(PER_FILE)} 个引用方逐文件已钉 · "
      f"生产→探针泄漏 0 · 探针依赖被测对象 {len(probe_deps)} 个)")
