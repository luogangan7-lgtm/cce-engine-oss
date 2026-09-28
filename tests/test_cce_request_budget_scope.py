#!/usr/bin/env python3
"""生产链每次运行的付费请求上限(2026-09-28 诊断 #25)。零真实调用。

此前 cce_request_budget 在生产链上零调用方: call_model 每个 draw 最多 3×3 次 POST, 整条链没有显式上限。
现在 cce_full_run / reply_loop 各开一个作用域(环境变量, 子进程继承), 三个出站口(MiniMax call_model、
Jev _post、对齐 _call)每次真正发请求前扣一次, 扣在各自的 try 之外 —— 撞上限必须停, 不能被重试的 except 吞掉。
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_request_budget as B  # noqa: E402
import exp_crossmodel_desire as X  # noqa: E402
import cce_s0_jev as J  # noqa: E402
import cce_align_v2 as AL  # noqa: E402


def fresh_scope(limit):
    for k in (B.SCOPE_ID, B.SCOPE_LIMIT, B.SCOPE_STATE):
        os.environ.pop(k, None)
    st = Path(tempfile.mkdtemp()) / "request_budget.json"
    B.open_scope("test", limit, st)
    return st


posts = []


class _Boom(Exception):
    pass


def _fail_post(*a, **k):
    posts.append(1)
    raise _Boom("offline")


X.requests.post = _fail_post
X.time.sleep = lambda s: None
os.environ.setdefault("MINIMAX_API_KEY", "offline-test")

# ① 失控: 一直失败的调用方反复重试 ⇒ 第 limit 次 POST 之后抛 BudgetExceeded, 不再发
st = fresh_scope(5)
stopped = None
for i in range(10):
    try:
        X.call_model("M3", "p")          # 每次内部 3 次重试
    except B.BudgetExceeded as e:
        stopped = e
        break
assert stopped is not None, "★ 撞上限没停"
assert len(posts) == 5, f"★ 上限 5, 实发 {len(posts)}"
assert B.scope_status() == {"limit": 5, "used": 5}

# ② 没开作用域 ⇒ 不计数(研究探针各有授权单)
for k in (B.SCOPE_ID, B.SCOPE_LIMIT, B.SCOPE_STATE):
    os.environ.pop(k, None)
posts.clear()
X.call_model("M3", "p")
assert len(posts) == 3 and B.scope_status() is None

# ③ Jev 与对齐诊断的出站口同样扣
st = fresh_scope(100)
J.urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(OSError("offline"))
J._post({"x": 1}, "k")
AL.urllib.request.urlopen = J.urllib.request.urlopen
AL._call("p")
assert B.scope_status()["used"] == 1 + 3, B.scope_status()      # Jev 非 HTTPError 立即返回(1 次); 对齐 3 次重试

# ④ 子进程继承作用域, 计入同一本账(knot_classify 就是子进程)
code = "import sys; sys.path.insert(0, %r); import cce_request_budget as B; B.reserve_in_scope('child'); B.reserve_in_scope('child')" % str(ROOT / "scripts")
subprocess.run([sys.executable, "-c", code], check=True, env=os.environ.copy())
assert B.scope_status()["used"] == 6

# ⑤ 外层作用域优先: 嵌套 open_scope 不覆盖(外层上限管住整棵进程树)
outer = os.environ[B.SCOPE_ID]
assert B.open_scope("inner", 999, "/tmp/nope.json") == outer and os.environ[B.SCOPE_LIMIT] == "100"

# ⑥ 生产入口真的开了作用域, 且运行日志摘要带出实际用量
src = (ROOT / "scripts/cce_full_run.py").read_text(encoding="utf-8")
assert 'open_scope("cce_full_run"' in src and '"request_budget": meta.get("request_budget")' in src
assert 'open_scope("reply_loop"' in (ROOT / "scripts/reply_loop.py").read_text(encoding="utf-8")
import cce_full_run as F  # noqa: E402
assert F.run_log_summary({"request_budget": {"limit": 200, "used": 17}})["request_budget"] == {"limit": 200, "used": 17}

for k in (B.SCOPE_ID, B.SCOPE_LIMIT, B.SCOPE_STATE):
    os.environ.pop(k, None)
print("test_cce_request_budget_scope: OK (失控在上限处停且不被重试吞 | 无作用域不计 | Jev/对齐口同扣 | 子进程共账 | 外层优先 | 入口已接)")
