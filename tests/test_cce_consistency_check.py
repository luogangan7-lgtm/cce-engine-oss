#!/usr/bin/env python3
"""配置↔代码一致性自检的守卫 —— 它在 CI 生产路径上每次执行，此前零测试。

`.github/workflows/cce-submit.yml:117` 每次出站前跑 `consistency_check.py`。
它自称抓四类缺陷（C1 字段无引用 / C2 版本不一致 / C3 硬编码版本漂移 /
C4 键集合副本），根因是「配置声明的东西代码里引用数为 0，人工 review 抓不住」。

**一个自称能抓四类缺陷的检查器，必须逐类造一个缺陷证明它真抓得到。**
否则它和「永远绿」无法区分 —— 而它恰恰是那种平时永远绿的检查。

做法：把 config/ + scripts/ + accuracy/ 复制到临时目录再注入缺陷，
**绝不在真仓库上做变异**（变异测试自己崩了会把仓库留在坏状态）。
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_in(root):
    return subprocess.run([sys.executable, str(root / "scripts" / "consistency_check.py")],
                          capture_output=True, text=True)


def sandbox():
    """复制一份最小可运行的树。调用方负责清理。"""
    tmp = Path(tempfile.mkdtemp(prefix="cc_"))
    for d in ("config", "scripts", "accuracy"):
        src = ROOT / d
        if src.exists():
            shutil.copytree(src, tmp / d,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return tmp


# ── 基线：干净副本必须绿（否则下面每个变异都会"红"，测不出东西）────────────
base = sandbox()
try:
    r = run_in(base)
    assert r.returncode == 0, \
        f"★ 干净副本就已经红了，本文件的四个变异测试全部失去意义：\n{r.stdout[-600:]}"
finally:
    shutil.rmtree(base, ignore_errors=True)

# ── 逐类注入缺陷，每类都必须让它变红 ────────────────────────────────────────
cases = []

# C1 字段引用：给分类学加一个代码里没人引用的字段
def inj_c1(t):
    p = t / "config" / "knot_taxonomy.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["knots"][0]["never_referenced_field_xyz"] = 1
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
cases.append(("C1 配置字段无代码引用", inj_c1))

# C2 内部版本一致：把 taxonomy.version 改掉
def inj_c2(t):
    p = t / "config" / "knot_taxonomy.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["version"] = "9.9.9-mutant"
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
cases.append(("C2 taxonomy/protocol 版本不一致", inj_c2))

# C4 键集合副本：在一个非豁免文件里塞 >=4 个九结键的字面量
def inj_c4(t):
    p = t / "scripts" / "cce_population.py"
    p.write_text(p.read_text(encoding="utf-8") +
                 '\n_MUTANT_COPY = ["pain_seek", "injustice", "belong", "reward", "display"]\n',
                 encoding="utf-8")
cases.append(("C4 九结键集合另存副本", inj_c4))

# C3 硬编码版本号：在 taxonomy 语境下写一个 != 真值的版本字面量
def inj_c3(t):
    p = t / "scripts" / "cce_population.py"
    p.write_text(p.read_text(encoding="utf-8") +
                 '\n_MUTANT_TAXONOMY_VERSION = "0.0.1"   # taxonomy 版本(故意漂移)\n',
                 encoding="utf-8")
cases.append(("C3 代码里硬编码的 taxonomy 版本漂移", inj_c3))

for name, inject in cases:
    t = sandbox()
    try:
        inject(t)
        r = run_in(t)
        assert r.returncode != 0, \
            (f"★ 注入「{name}」后 consistency_check 仍然绿 —— 该检查项抓不到它声称要抓的东西。\n"
             f"stdout 尾部：{r.stdout[-500:]}")
    finally:
        shutil.rmtree(t, ignore_errors=True)

print(f"test_cce_consistency_check: OK (干净副本绿 · {len(cases)} 类注入缺陷全部见红: "
      + " / ".join(n.split()[0] for n, _ in cases) + ")")
