# -*- coding: utf-8 -*-
"""开发工具(零 API): 并行跑全部 tests/test_*.py, 红的串行复验, 只报真红。用法: python3 probes/dev_runsuite.py"""
import subprocess, pathlib, concurrent.futures as cf, sys
ROOT=pathlib.Path("/Volumes/data/cce-engine"); tests=sorted((ROOT/"tests").glob("test_*.py"))
def run(t):
    p=subprocess.run([sys.executable,"-B",str(t)],capture_output=True,text=True,cwd=ROOT,timeout=900); return t,p.returncode,p.stdout+p.stderr
red=[]
with cf.ThreadPoolExecutor(max_workers=8) as ex:
    for t,rc,out in ex.map(run,tests):
        if rc: red.append((t,out))
print("[并行] 绿 %d / 红 %d"%(len(tests)-len(red),len(red)))
real=[]
for t,_ in red:
    p=subprocess.run([sys.executable,"-B",str(t)],capture_output=True,text=True,cwd=ROOT,timeout=900)
    if p.returncode: real.append((t,p.stdout+p.stderr))
print("[串行复验后] 真红 %d"%len(real))
for t,out in real: print("\n### %s\n%s"%(t.name,"\n".join(out.strip().splitlines()[-6:])))
