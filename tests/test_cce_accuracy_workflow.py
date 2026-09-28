#!/usr/bin/env python3
"""付费回归台 accuracy.yml 的四道闸(2026-09-28, 诊断项 I/H)。零真实调用。

① push paths == G-K 实际依赖闭包(run_gates.py/compare.py 的仓内 import 闭包 + 它们读的 config), 不多不少
② 只在公开仓跑(同一 push 进两个仓 ⇒ 付两次)
③ shell: bash(带 pipefail; 否则 `run_gates.py | tail` 崩了也是绿)
④ 每次 HTTP 请求先扣预算, 撞上限抛出 —— 不被 call() 里的 except 吞掉; compare 无结果时退出码非 0
⑤ 共享 JSON 解析器不返回非标准 JSON 值(Ellipsis/inf/NaN/set)
"""
import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REPO = "luogangan7-lgtm/cce-engine-oss"
wf = yaml.safe_load((ROOT / ".github/workflows/accuracy.yml").read_text(encoding="utf-8"))
on = wf.get(True) or wf.get("on")


def closure():
    seen, todo = set(), ["accuracy/run_gates.py", "accuracy/compare.py"]
    while todo:
        f = todo.pop()
        if f in seen:
            continue
        seen.add(f)
        for n in ast.walk(ast.parse((ROOT / f).read_text(encoding="utf-8"))):
            mods = [a.name for a in n.names] if isinstance(n, ast.Import) else \
                [n.module] if isinstance(n, ast.ImportFrom) and n.module else []
            for m in mods:
                for d in ("scripts", "accuracy"):
                    p = f"{d}/{m.replace('.', '/')}.py"
                    if (ROOT / p).is_file():
                        todo.append(p)
    cfg = set()
    for f in seen:
        src = (ROOT / f).read_text(encoding="utf-8")
        cfg |= {f"config/{c}" for c in re.findall(r'"config",\s*"([^"]+\.json)"', src)}
        cfg |= set(re.findall(r'["\'/](config/[a-z_0-9]+\.json)', src))
    return {f for f in seen if f.startswith("scripts/")} | cfg


want = closure() | {".github/workflows/accuracy.yml", "accuracy/**", "requirements.txt"}
got = set(on["push"]["paths"])
assert got == want, f"push paths 与依赖闭包不符: 缺 {sorted(want - got)} · 多 {sorted(got - want)}"
assert "scripts/cce_request_budget.py" in want and "config/knot_taxonomy.json" in want

assert wf["jobs"]["gates"].get("if") == f"github.repository == '{REPO}'", "付费 job 必须只在公开仓跑"
jev = yaml.safe_load((ROOT / ".github/workflows/cce-jev-contract.yml").read_text(encoding="utf-8"))
assert all(j.get("if") == f"github.repository == '{REPO}'" for j in jev["jobs"].values())

assert (wf.get("defaults") or {}).get("run", {}).get("shell") == "bash", "没有 pipefail ⇒ 管道前段崩了也是绿"

# ④ 预算: 撞上限必须抛出, 而不是被 call() 的 except 吞成空串
os.environ.setdefault("MINIMAX_API_KEY", "offline-test")
sys.path.insert(0, str(ROOT / "accuracy"))
sys.path.insert(0, str(ROOT / "scripts"))
import cce_request_budget as B  # noqa: E402
import run_gates as G  # noqa: E402

tmp = Path(tempfile.mkdtemp())
B.STATE = tmp / "budget.json"
sent = []
G.urllib.request.urlopen = lambda *a, **k: sent.append(1) or (_ for _ in ()).throw(OSError("offline"))
G.BUDGET_LIMIT, G.BUDGET_ID = 4, "test"
assert G.call("MiniMax-M3", "x") == ""          # 3 次尝试都失败 ⇒ 空串, 扣 3
try:
    G.call("MiniMax-M3", "x")
    raise AssertionError("★ 撞上限没停: 预算闸被 except 吞掉了")
except B.BudgetExceeded:
    pass
assert len(sent) == 4, f"撞上限后不得再发请求: 实发 {len(sent)}"
assert G.structural_max_requests() <= 1600, "结构上限超预算: 先改 BUDGET_LIMIT 并报估算"
assert re.search(r"^BUDGET_LIMIT = 1600$", (ROOT / "accuracy/run_gates.py").read_text(encoding="utf-8"), re.M)

# compare: 没有结果 ⇒ 退出码非 0
(tmp / "accuracy").mkdir(); (tmp / "config").mkdir()
shutil.copy(ROOT / "accuracy/compare.py", tmp / "accuracy/compare.py")
shutil.copy(ROOT / "config/knot_taxonomy.json", tmp / "config/knot_taxonomy.json")
r = subprocess.run([sys.executable, str(tmp / "accuracy/compare.py")], capture_output=True, text=True)
assert r.returncode != 0 and "未产出结果" in r.stdout, (r.returncode, r.stdout[-200:])
shutil.rmtree(tmp)

# ⑤ 2026-09-27 run 36333005971 的根因: 宽松解析把模型照抄的 `...` 读成 Ellipsis ⇒ json.dump 写到一半崩。
#   共享解析器(62 处调用)只许返回能写成标准 JSON 的值。
import json  # noqa: E402
import calibration_framework as CF  # noqa: E402
from calibration_framework import extract_json_robust  # noqa: E402
CF.JSON_FAIL_LOG = os.devnull   # 构造的坏输入不许写进真实失败日志(会混进存量回放)
for bad in ("{'pairs':[{'pair':'a|b','ambiguity':...}]}", "{'x': 1e999}", '{"x": NaN}', "{'x': {1, 2}}"):
    assert extract_json_robust(bad, log_note="test_cce_accuracy_workflow") is None, bad
got = extract_json_robust("{'a': (1, 2), 'b': None}", log_note="test_cce_accuracy_workflow")
assert got == {"a": [1, 2], "b": None} and json.dumps(got, allow_nan=False)

print(f"test_cce_accuracy_workflow: OK (push 路径 = 依赖闭包 {len(want)} 项 | 仅公开仓 | pipefail | 撞上限即停 · 无结果即红 | 解析器只出标准 JSON)")
