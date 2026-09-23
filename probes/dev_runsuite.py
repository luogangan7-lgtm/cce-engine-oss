# -*- coding: utf-8 -*-
"""开发工具(零 API): 并行跑全部 tests/test_*.py(有 def test_ 的走 pytest, 其余脚本跑), 红的串行复验, 只报真红。用法: python3 probes/dev_runsuite.py"""
import subprocess, pathlib, concurrent.futures as cf, sys
ROOT=pathlib.Path("/Volumes/data/cce-engine"); tests=sorted((ROOT/"tests").glob("test_*.py"))
# ★ 2026-09-24 修: 有 `def test_` 的文件(pytest 风格)用 `python3 -B tests/test_x.py` 是**空跑**(0 断言执行, 恒绿; 模块级断言式的文件脚本跑才对) ——
#   消融第三轮的 L4 农场沿用本脚本的跑法, 把 test_cce_stage_overlap / test_cce_s0_wiring 这类真正守行为的闸整批漏掉。有 `def test_` 的一律走 pytest, 其余脚本跑。
import re
def cmd(t): return [sys.executable,"-B","-m","pytest","-q","-p","no:cacheprovider",str(t)] if re.search(r"^def test_",t.read_text(encoding="utf-8"),re.M) else [sys.executable,"-B",str(t)]
def run(t):
    p=subprocess.run(cmd(t),capture_output=True,text=True,cwd=ROOT,timeout=900); return t,p.returncode,p.stdout+p.stderr
red=[]
with cf.ThreadPoolExecutor(max_workers=8) as ex:
    for t,rc,out in ex.map(run,tests):
        if rc: red.append((t,out))
print("[并行] 绿 %d / 红 %d"%(len(tests)-len(red),len(red)))
real=[]
for t,_ in red:
    p=subprocess.run(cmd(t),capture_output=True,text=True,cwd=ROOT,timeout=900)
    if p.returncode: real.append((t,p.stdout+p.stderr))
print("[串行复验后] 真红 %d"%len(real))
for t,out in real: print("\n### %s\n%s"%(t.name,"\n".join(out.strip().splitlines()[-6:])))
