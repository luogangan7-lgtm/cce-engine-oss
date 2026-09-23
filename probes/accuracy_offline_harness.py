#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""accuracy/run_gates.py 的离线隔离装置 —— 让「判断仪器准不准的那道闸」自己可被测。

★ 背景: 该目录被零 API 纪律**结构性排除**两轮 —— 它 import 时就 `os.environ["MINIMAX_API_KEY"]`。
  见 tests/data/accuracy_testability_blocked.json。

★★★ 按 web GPT 第九轮的三条实现要求:
  ① **不要在测试文件顶层先导入目标模块, 再期待函数级 fixture 补环境变量**
     ⇒ 本装置在 `load()` 内部**先设环境, 再 import**, 且每次给独立模块实例。
  ② **替换对象必须位于被测代码实际查找它的命名空间**
     ⇒ run_gates 写的是 `import urllib.request` 然后 `urllib.request.urlopen(...)`,
        即它在**调用时**去 `urllib.request` 模块对象上取 `urlopen`
        ⇒ 替换点就是 `urllib.request.urlopen`。**不是** `run_gates.urlopen`(那个名字不存在)。
  ③ **socket 拦截只控制指定库, 不能当成「全进程所有网络出口都已关闭」的证明**
     ⇒ 本装置装的是 `socket.socket.connect` 绊线, 覆盖**走 socket 的**出口(含 urllib)。
        它**不覆盖**: 已建立的连接、不走 socket 的传输、子进程、C 扩展自带的栈。
        ⇒ 证据只能说「**本进程内经 socket 的新建连接被拦截且未被触发**」。

★★★ 证据范围必须与替换边界一致(GPT 的分层表):
  本装置只替换**传输结果**, 构造/解析/断言/汇总代码**逐字未改**
  ⇒ 它能支持的结论**仅限**: **对这份闸实现的离线软件验证**。
  它**不能**证明真实模型的语义判断准确率或重复稳定性。
"""
import importlib.util, json, os, pathlib, socket, sys, types

ROOT = pathlib.Path(__file__).resolve().parent.parent
RG_PATH = ROOT / "accuracy" / "run_gates.py"


class NetworkTripwire(AssertionError):
    """★ 任何**新建 socket 连接**都是失败, 不是警告。"""


class _Tripwire:
    """① 装 socket 绊线; ② 记录是否被触发。**不声称覆盖全进程所有出口。**"""
    def __init__(self):
        self._orig = socket.socket.connect
        self.tripped = []

    def __enter__(self):
        tw = self
        def guard(self_sock, address, *a, **kw):
            tw.tripped.append(address)
            raise NetworkTripwire(f"★★★ 离线隔离被突破: 试图连接 {address}")
        socket.socket.connect = guard
        return self

    def __exit__(self, *exc):
        socket.socket.connect = self._orig
        return False

    @property
    def scope(self):
        return ("覆盖: 本进程内**经 socket.socket.connect 新建**的连接(含 urllib)。"
                "**不覆盖**: 已建立连接 · 不走 socket 的传输 · 子进程 · C 扩展自带网络栈。")


def load(source_mutator=None, responses=None, env=None):
    """加载一份**独立的** run_gates 实例。

    source_mutator: 可选, 对源码做字符串替换(变异测试用)。**内存替换, 仓里文件一字不改。**
    responses:      call() 的确定性回放 —— dict[model] -> str, 或 callable(model, prompt) -> str
    env:            额外环境变量

    ★ 顺序: **先设环境 → 再编译 → 再 exec** —— 不给「顶层 import 后再补 env」留任何空间。
    """
    src = RG_PATH.read_text(encoding="utf-8")
    mutated = False
    if source_mutator:
        new = source_mutator(src)
        mutated = (new != src)
        src = new

    saved = {k: os.environ.get(k) for k in
             ("MINIMAX_API_KEY", "CCE_CORPUS", "CCE_SKIP_GK2", "CCE_OUT_DIR", "VSE_ROOT")}
    os.environ["MINIMAX_API_KEY"] = "OFFLINE-FAKE-KEY-NOT-A-SECRET"
    os.environ.setdefault("CCE_SKIP_GK2", "1")
    for k, v in (env or {}).items():
        os.environ[k] = v

    sys.path.insert(0, str(ROOT / "scripts"))
    sys.path.insert(0, str(ROOT / "accuracy"))
    mod = types.ModuleType("run_gates_offline")
    mod.__file__ = str(RG_PATH)          # ★ 让 ROOT 推导与真仓一致
    try:
        with _Tripwire() as tw:
            exec(compile(src, str(RG_PATH), "exec"), mod.__dict__)
            # ② 替换点 = 被测代码**调用时实际查找**的那个名字
            if responses is not None:
                fn = responses if callable(responses) else (lambda m, p: responses.get(m, ""))
                mod.urllib.request.urlopen = _make_urlopen(fn, mod)
            mod._OFFLINE_TRIPWIRE = tw
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        for p in (str(ROOT / "accuracy"), str(ROOT / "scripts")):
            if p in sys.path:
                sys.path.remove(p)
    mod._OFFLINE_MUTATED = mutated
    return mod


def _make_urlopen(fn, mod):
    """★ 只替换**传输结果** —— call() 的重试、错误处理、base_resp 判定、
    reasoning_content 回退, 全部走**原代码**。"""
    class _Resp:
        def __init__(self, body): self._b = body
        def read(self): return self._b
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def urlopen(req, timeout=None):
        payload = json.loads(req.data.decode())
        content = fn(payload["model"], payload["messages"][0]["content"])
        return _Resp(json.dumps({
            "base_resp": {"status_code": 0},
            "choices": [{"message": {"content": content}}]}).encode())
    return urlopen


if __name__ == "__main__":
    m = load(responses=lambda model, prompt: '{"knots":[{"key":"suspend","weight":1.0}]}')
    out = {
        "block": "ACCURACY_OFFLINE_HARNESS",
        "★加载成功": hasattr(m, "annot_dist"),
        "★import 期不再需要真 key": True,
        "★绊线作用域(如实写, 不夸大)": m._OFFLINE_TRIPWIRE.scope,
        "★绊线是否被触发": m._OFFLINE_TRIPWIRE.tripped,
        "★替换边界": "只替换**传输结果**(urlopen); 构造/解析/断言/汇总**逐字未改**",
        "★★★据此能支持的结论": "**对这份闸实现的离线软件验证** —— "
                     "**不能**证明真实模型的语义判断准确率或重复稳定性",
        "冒烟": m.annot_dist(("MiniMax-M3", {"id": "smoke", "b": "text"})),
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))
