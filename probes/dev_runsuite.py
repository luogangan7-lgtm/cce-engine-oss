# -*- coding: utf-8 -*-
"""开发工具(零 API): 并行跑全部 tests/test_*.py(有 def test_ 的走 pytest, 其余脚本跑), 红的串行复验, 只报真红。用法: .venv/bin/python probes/dev_runsuite.py(解释器须与 .python-version 一致)"""
import subprocess, pathlib, concurrent.futures as cf, sys
ROOT=pathlib.Path(__file__).resolve().parents[1]; tests=sorted((ROOT/"tests").glob("test_*.py"))
# ★ 2026-09-24 第二次空跑: ROOT 曾写死本机绝对路径 ⇒ 公仓/私仓 CI runner 上 glob 为空 ⇒「绿 0 / 红 0」退出 0, contract job 恒绿。找不到测试必须非零退出。
if not tests: print("[空跑] %s 下找不到 tests/test_*.py —— 拒绝当绿"%ROOT); sys.exit(2)
# ★ 2026-09-29 owner「Python版本需要同步」: 本机 3.14 与 CI 3.11 在浮点 sum 上结果不同(3.12 起补偿求和), 本机绿、CI 红。
#   单一真相源 .python-version(CI 的 setup-python 读同一个文件); 解释器对不上就拒跑 —— 本机用: .venv/bin/python probes/dev_runsuite.py
_want=(ROOT/".python-version").read_text(encoding="utf-8").strip(); _have="%d.%d"%sys.version_info[:2]
if _have!=_want: print("[版本不符] 本解释器 Python %s, .python-version 要求 %s —— 拒跑。本机用 .venv/bin/python(uv venv --python %s .venv)"%(_have,_want,_want)); sys.exit(3)
import os
# 子进程里写死的 `python3` 也要落到同一个解释器: 把它所在目录放到 PATH 最前
_ENV=dict(os.environ, PATH=os.path.dirname(sys.executable)+os.pathsep+os.environ.get("PATH",""))
# macOS: uv 装的独立版 Python 不搜 Homebrew 的库目录(FFmpeg 在那), torchcodec 解码会 OSError; Homebrew 自带的 Python 不受影响。只补回退搜索路径, 不改优先级
if sys.platform=="darwin" and os.path.isdir("/opt/homebrew/lib"): _ENV["DYLD_FALLBACK_LIBRARY_PATH"]=os.pathsep.join(filter(None,[os.environ.get("DYLD_FALLBACK_LIBRARY_PATH"),"/opt/homebrew/lib"]))
# ★ 2026-09-24 修: 有 `def test_` 的文件(pytest 风格)用 `python3 -B tests/test_x.py` 是**空跑**(0 断言执行, 恒绿; 模块级断言式的文件脚本跑才对) ——
#   消融第三轮的 L4 农场沿用本脚本的跑法, 把 test_cce_stage_overlap / test_cce_s0_wiring 这类真正守行为的闸整批漏掉。有 `def test_` 的一律走 pytest, 其余脚本跑。
import re
def cmd(t): return [sys.executable,"-B","-m","pytest","-q","-rs","-p","no:cacheprovider",str(t)] if re.search(r"^def test_",t.read_text(encoding="utf-8"),re.M) else [sys.executable,"-B",str(t)]
# ★ 2026-09-28 (诊断 #44): 以前一个测试超时 ⇒ TimeoutExpired 直接把整个跑批炸掉, 不出红绿汇总, 其余真红一个都报不出来。
#   超时记为真红(124), 并点名。
def _once(t):
    try:
        p=subprocess.run(cmd(t),capture_output=True,text=True,cwd=ROOT,timeout=900,env=_ENV); return p.returncode,p.stdout+p.stderr
    except subprocess.TimeoutExpired as e:
        out=e.stdout.decode(errors="replace") if isinstance(e.stdout,bytes) else (e.stdout or "")
        return 124,"TIMEOUT after 900s\n"+out[-2000:]
def run(t):
    rc,out=_once(t); return t,rc,out
red=[]; skipped=[]
with cf.ThreadPoolExecutor(max_workers=8) as ex:
    for t,rc,out in ex.map(run,tests):
        skipped += ["%s: %s"%(t.name,l) for l in re.findall(r"^SKIPPED .*$",out,re.M)]
        if rc: red.append((t,out))
print("[并行] 绿 %d / 红 %d"%(len(tests)-len(red),len(red)))
# 跳过不算绿: 选择性开启的重闸(如 CCE_JEV_HEAVY)被跳过时必须看得见
if skipped: print("[跳过] %d 条(不计入绿):\n  "%len(skipped)+"\n  ".join(skipped[:20]))
real=[]; par_only=[]
for t,out0 in red:
    rc,out=_once(t)
    if rc: real.append((t,out))
    else: par_only.append((t,out0))
print("[串行复验后] 真红 %d"%len(real))
# ★ 2026-09-27: 并行红/串行绿的测试以前被静默吞掉(两次「并行红 1 / 真红 0」查不出是谁) ⇒ 点名 + 并行那次的输出尾巴。不改退出码: 它是并发互扰的线索, 不是真红。
if par_only: print("[仅并行红] %d(并发互扰嫌疑: 共享文件/临时目录/全局状态 —— 查根因, 别重试了事)"%len(par_only))
for t,out in par_only: print("\n### [仅并行红] %s\n%s"%(t.name,"\n".join(out.strip().splitlines()[-12:])))
for t,out in real: print("\n### %s\n%s"%(t.name,"\n".join(out.strip().splitlines()[-6:])))
sys.exit(1 if real else 0)   # ★ CI 用: 有真红就非零退出
