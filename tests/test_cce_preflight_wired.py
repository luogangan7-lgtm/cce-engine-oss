#!/usr/bin/env python3
"""钉住「design_preflight 真的接在产生 API 成本的入口上」。

## 为什么单独一个文件
`design_preflight.py` 与它的守卫测试从 2026-08-27 就在仓库里，但直到 2026-09-01
**没有任何 workflow 调用它** —— 一道谁也没接的门，与没有这道门等价。
本仓库自己记过这条：「新 gate 不接 CI = 形同虚设」（同族缺陷已出现过三次）。

外审的判定是：前两轮长度实验的设计缺陷「理论上都应该在 **0 次 API 调用阶段**被 CI 拒绝」。
那个拒绝点只有一个地方能放 —— `probe.yml`，因为它是唯一持有 `MINIMAX_API_KEY`、
唯一会真烧钱的入口。

## 守三件事
① 门确实写在 probe.yml 里
② 门在 **API key 出现之前**执行（放在后面等于烧完钱再检查）
③ 门的判据本身有效：已知坏设计非零退出、已知好设计零退出
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WF = (ROOT / ".github" / "workflows" / "probe.yml").read_text(encoding="utf-8")

# ── ① 门在 probe.yml 里 ────────────────────────────────────────────────────
# ★ 只认**非注释行的实际调用**。首版写的是 `"design_preflight.py" in WF`,
#   而我自己在 workflow 注释里也写了这个串 —— 把执行行删掉后断言照样为真。
#   同一个文件里这是第二次栽在「断言命中的是散文不是代码」(另一处见 i_key)。
INVOKE = [ln for ln in WF.splitlines()
          if "design_preflight.py" in ln and not ln.lstrip().startswith("#")]
assert INVOKE, \
    ("★ probe.yml 里没有任何**非注释**的 design_preflight 调用 —— 那道门又变成孤儿了。"
     "它是唯一能在 0 次 API 调用阶段拒绝坏设计的地方。")
assert any("python3" in ln for ln in INVOKE), \
    f"★ 找到 design_preflight 但不是可执行调用: {INVOKE}"
assert "design:" in WF, "★ probe.yml 缺少 design 输入，门无从取到规格"

# ── ② 门必须在 API key 之前 ────────────────────────────────────────────────
i_gate = WF.index(INVOKE[0])
# 找**真正注入密钥**的那一处, 不是文件头注释里提到它的地方
# (首版就栽在这: WF.index("MINIMAX_API_KEY") 命中的是第 3 行注释, 于是误判顺序)
i_key = WF.index("MINIMAX_API_KEY: ${{ secrets.")
assert i_gate < i_key, \
    ("★ 设计门出现在 MINIMAX_API_KEY 之后 —— 那是烧完钱再检查。"
     "门的全部意义是它在花钱之前。")

# ── ③ 判据本身有效：坏设计红、好设计绿 ─────────────────────────────────────
SCRIPT = ROOT / "scripts" / "design_preflight.py"
CASES = {
    "designs/EXAMPLE_rejected_2x2.json": 1,        # 我第二轮真实犯过的 2x2
    "designs/EXAMPLE_accepted_orthogonal.json": 0,  # 外审给的最小 confirmatory 形状
}
for rel, want in CASES.items():
    path = ROOT / rel
    assert path.exists(), f"★ 示例设计 {rel} 不见了，门的判别力无从演示"
    rc = subprocess.run([sys.executable, str(SCRIPT), str(path)],
                        capture_output=True).returncode
    assert rc == want, (
        f"★ {rel} 期望退出码 {want}，实得 {rc}。"
        + ("坏设计不再被拒 = 门失效。" if want else
           "好设计被拒 = 永远红，与永远绿同样失效。"))

# ── ④ 「design=none」这条旁路必须留有可见告警 ──────────────────────────────
# 它是为纯重算探针留的，但同时也是唯一能绕过门的路径 —— 必须自己喊出来。
i_none = WF.index('inputs.design }}" = "none"')
assert "::warning::" in WF[i_none:i_none + 400], \
    "★ design=none 旁路没有告警。唯一能绕过门的路径必须自己喊出来，否则它就是静默后门。"

print("test_cce_preflight_wired: OK (门在 probe.yml / 在 API key 之前 / "
      "坏设计红好设计绿 / none 旁路带告警)")
