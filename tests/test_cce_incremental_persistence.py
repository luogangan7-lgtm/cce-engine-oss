"""长跑脚本必须**逐条落盘**, 不许只在最后写一次。零 API, 静态扫描。

## ★★★ 今天犯了两次, 而且中间还救过一次
① **救过一次**: Run B 在 405 次标注**之后**崩了(SKIP_GK2 的下游 bug)。
   **一条数据没丢** —— 因为同日早些时候把逐条原始标注的落盘**挪到了 G-K2 之前**。
② **又犯一次**: 锚例批量标注脚本(240 条 × ~54s ≈ 3.5 小时)**只在最后 write_text 一次**。
   跑到 200/240 挂掉就全丢。是 owner 问「还没跑完？」时我自己查出来的。

★ 「聚合是判决要的, **逐条是复核要的**」这条我今天说了三次, 写脚本时还是漏。
  ⇒ **靠记性无效, 要有闸。**

## 规则
`probes/` 与 `accuracy/` 下, 凡是**在循环里发网络请求**的脚本, 必须满足其一:
· 循环**内部**有写盘(逐条/分批 checkpoint), 或
· 明确声明为短跑(总调用数 < 30, 崩了重跑成本可忽略)

★ 本闸用 AST 判断「写盘是否在请求循环内」, 不用字符串猜。
"""
import ast
import re
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DIRS = ("probes", "accuracy")
# ★ 只留**真正发包**的原语。第一版把 "get"/"post" 也放进来 —— 而 `dict.get()` 到处都是,
#   ⇒ 半个仓被判成「发网络」, 连 js_div/kappa 都中招。**通用词不能当网络原语。**
NET_PRIMITIVES = {"urlopen", "urlretrieve"}
WRITE = {"write_text", "dump", "writelines", "write"}
RETRY_MAX = 12          # ★ `for _ in range(k)` 且 k<=12 视为**重试/短固定循环**, 不要求 checkpoint
SHORT_RUN_MAX = 30      # ★ 迭代对象是模块级字面量且元素数 <= 30 ⇒ 短跑


def _module_level_lengths(tree):
    """模块级 NAME = [...] / (...) 的元素数, 用来认「短跑」。"""
    out = {}
    for n in tree.body:
        if isinstance(n, ast.Assign) and isinstance(n.value, (ast.List, ast.Tuple, ast.Set)):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    out[t.id] = len(n.value.elts)
    return out


def _net_bearing_funcs(tree):
    """1 层调用图: 直接发包的函数名 + 调用了它们的函数名。"""
    direct = set()
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        for c in ast.walk(fn):
            if isinstance(c, ast.Call):
                nm = getattr(c.func, "attr", None) or getattr(c.func, "id", None)
                if nm in NET_PRIMITIVES:
                    direct.add(fn.name)
    wrappers = set(direct)
    for _ in range(2):                       # 传播两层
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            for c in ast.walk(fn):
                if isinstance(c, ast.Call):
                    nm = getattr(c.func, "attr", None) or getattr(c.func, "id", None)
                    if nm in wrappers:
                        wrappers.add(fn.name)
    return wrappers


def _is_retry_or_short(node, lens):
    """★ 区分**重试循环**与**条目循环** —— 这是本闸不误报的关键。"""
    it = node.iter if isinstance(node, ast.For) else None
    if it is None:
        return True                          # while: 不判(通常是重试)
    if (isinstance(it, ast.Call) and getattr(it.func, "id", None) == "range"
            and it.args and isinstance(it.args[0], ast.Constant)
            and isinstance(it.args[0].value, int) and it.args[0].value <= RETRY_MAX):
        return True                          # for _ in range(<=12) ⇒ 重试
    base = it
    if isinstance(base, ast.Call) and getattr(base.func, "id", None) in ("enumerate", "sorted", "list"):
        base = base.args[0] if base.args else base
    if isinstance(base, ast.Name) and lens.get(base.id, 10 ** 9) <= SHORT_RUN_MAX:
        return True                          # 迭代模块级小字面量 ⇒ 短跑
    return False


def test_long_running_network_loops_checkpoint():
    bad = []
    for d in DIRS:
        for f in sorted((ROOT / d).glob("*.py")):
            src = f.read_text(encoding="utf-8")
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            netfn = _net_bearing_funcs(tree)
            if not netfn:
                continue
            lens = _module_level_lengths(tree)
            for node in ast.walk(tree):
                if not isinstance(node, (ast.For, ast.While)):
                    continue
                if _is_retry_or_short(node, lens):
                    continue
                calls, writes = set(), False
                for n in ast.walk(node):
                    if isinstance(n, ast.Call):
                        nm = getattr(n.func, "attr", None) or getattr(n.func, "id", None)
                        if nm:
                            calls.add(nm)
                            if nm in WRITE:
                                writes = True
                if (calls & netfn) and not writes:
                    bad.append(f"{d}/{f.name}:{node.lineno} (调用 {sorted(calls & netfn)})")
    assert not bad, (
        "★★ 这些脚本在**网络循环内没有写盘** —— 长跑挂掉会全丢:\n  "
        + "\n  ".join(bad)
        + "\n★ 修法: 循环内每 N 条 checkpoint 一次; 或若确为短跑(<30 次调用), "
          "具名登记进 SHORT_RUN 并写明理由。")


def test_run_gates_persists_before_the_part_that_crashed():
    """★★★ 具体钉住那次救了 405 次调用的顺序: 落盘必须在 G-K2 **之前**。"""
    src = (ROOT / "accuracy" / "run_gates.py").read_text(encoding="utf-8")
    i_raw = src.index("raw_annotations.json")
    i_gk2 = src.index("# ── G-K2 v2")
    assert i_raw < i_gk2, (
        "★★★ 逐条原始标注的落盘被挪到 G-K2 **之后**了 —— "
        "2026-09-07 Run B 正是在 G-K2 段崩的(SKIP_GK2 下游 IndexError), "
        "落盘在前才保住了 405 次调用的数据")



def test_worker_isolates_per_item_exceptions():
    """★★★ 一条坏读数不许掀翻整轮 —— 落盘救得回**已花的钱**, 救不回**没跑完的活**。

    实测(2026-09-08): arm B 在 339/405 处**整轮崩掉** —— 某个模型在 JSON 里回了字面 `...`,
    被修复成 Python `Ellipsis`, `k.get` 抛 AttributeError, 异常穿过 worker 掀翻了 `ex.map`。
    ★ 逐条落盘让 339 条一条没丢(那条闸生效了), **但剩下的 66 条根本没跑** ——
      「不丢数据」与「跑得完」是两件事, 此前只有前者有闸。
    ★ 同型隐患当时还有 3 个探针(cross_family_reference_81 / suspend_factorial_challenge /
      suspend_fix_confirmation), 全部已补。

    判据: 采读数的探针里, 被 `ex.map`/`ex.submit` 调用的 worker 必须含 try —— 现算, 无豁免名单。
    """
    bad = []
    for f in sorted((ROOT / "probes").glob("*.py")):
        src = f.read_text(encoding="utf-8")
        if "cce_runs" not in src:          # 不采读数的探针不受本条约束
            continue
        t = ast.parse(src)
        workers = {a.id for n in ast.walk(t)
                   if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                   and n.func.attr in ("map", "submit")
                   for a in n.args if isinstance(a, ast.Name)}
        for n in ast.walk(t):
            if isinstance(n, ast.FunctionDef) and n.name in workers \
                    and not any(isinstance(x, ast.Try) for x in ast.walk(n)):
                bad.append(f"{f.name}::{n.name}")
    # ★ 灵敏度自证: 判据必须真的能认出「被 ex.map 调用的函数」, 否则是恒绿假闸
    seen = 0
    for f in sorted((ROOT / "probes").glob("*.py")):
        src = f.read_text(encoding="utf-8")
        if "cce_runs" not in src:
            continue
        t = ast.parse(src)
        seen += len({a.id for n in ast.walk(t)
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                     and n.func.attr in ("map", "submit")
                     for a in n.args if isinstance(a, ast.Name)})
    assert seen >= 3, f"★★ 只认出 {seen} 个 worker —— AST 判据可能失效, 本条会恒绿"
    assert not bad, (
        f"★★★ 这些 worker 没有逐条异常隔离: {bad}\n"
        "⇒ 任何一条读数抛异常都会掀翻整轮(实测发生过: arm B 崩在 339/405)。"
        "把取读数那几行包进 try, 失败就记 None —— **解析失败是一条读数没读到, 不是整轮失败**。")


def test_reading_probes_persist_the_raw_model_response():
    """★★★ 只落盘**解析后**的分布, 等于把「模型没答」和「解析器坏了」永久混在一起。

    2026-09-09 网页版 GPT 指出: 重试在方法学上分三类, 最干净的一类是
    「原始响应已含完整答案、只是解析器有缺陷 ⇒ 用**同一确定性修复重新解析所有原始响应**」——
    那**不算重新抽样**。★ 而我的探针没存 raw text, **这条路根本走不了**,
    只能重新调 API(= 重新抽样, 需要事前重试规则才站得住)。

    ⇒ 「聚合是判决要的, 逐条是复核要的」再深一层:
      **逐条 parsed 是复核要的, raw 是重解析要的。**
    """
    bad = []
    for f in sorted((ROOT / "probes").glob("*.py")):
        src = f.read_text(encoding="utf-8")
        # ★ 判据: **声明了 cce_runs 下的输出目录**才算「采读数」。
        #   第一版用「源码里提到 cce_runs」⇒ 把两个零 API 的**判决脚本**也判红了
        #   (它们只是读 raw.json)。判宽的闸会诱使人去改被判的东西迎合闸。
        if not re.search(r'OUT\s*=\s*VAULT\s*/\s*"cce_runs"', src) or '"top1"' not in src:
            continue
        if '"raw"' not in src:
            bad.append(f.name)
    assert not bad, (
        f"★★★ 这些采读数的探针**没有落盘模型原始响应**: {bad}\n"
        "⇒ 解析失败时无法区分「模型没答」与「解析器坏了」, 也无法用确定性重解析恢复观测, "
        "只能重新调 API —— 而那是**重新抽样**, 需要事前重试规则才站得住。\n"
        '改法: 取 txt = RG.call(...) 后再 parse(txt), 并在行里存 "raw": txt[:4000]。')


if __name__ == "__main__":
    test_worker_isolates_per_item_exceptions()
    test_reading_probes_persist_the_raw_model_response()
    test_long_running_network_loops_checkpoint()
    test_run_gates_persists_before_the_part_that_crashed()
    n = 0
    # ★ 反向验证 1: 重试循环**不该**被判红
    t = ast.parse("def call(p):\n    for a in range(8):\n        urlopen(p)\n")
    lp = [x for x in ast.walk(t) if isinstance(x, ast.For)][0]
    assert _is_retry_or_short(lp, {}), "★ 反向验证失败: `for a in range(8)` 被当成条目循环"
    n += 1
    # ★ 反向验证 2: 大集合上的条目循环**该**被判红
    t2 = ast.parse("ITEMS=[1]*100\ndef call(p):\n    urlopen(p)\nfor x in ITEMS:\n    call(x)\n")
    lp2 = [x for x in ast.walk(t2) if isinstance(x, ast.For)][0]
    assert not _is_retry_or_short(lp2, _module_level_lengths(t2)), \
        "★ 反向验证失败: 100 条的条目循环被当成短跑"
    n += 1
    # ★ 反向验证 3: 1 层调用图要能把 wrapper 认出来
    assert "call" in _net_bearing_funcs(t2), "★ 反向验证失败: 调用 urlopen 的 call() 没被认出"
    t3 = ast.parse("def call(p):\n    urlopen(p)\ndef label(p):\n    return call(p)\n")
    assert "label" in _net_bearing_funcs(t3), \
        "★★ 反向验证失败: 间接调用(label→call→urlopen)没被认出 —— "\
        "这正是本闸第一版漏掉真正违规脚本的原因"
    n += 1
    print(f"test_cce_incremental_persistence: OK ("
          f"★★★网络循环内必须 checkpoint —— 今天犯了**两次**(Run B 靠落盘在前救回 405 次调用; "
          f"锚例批量标注只在最后写一次, 3.5 小时的活挂了就全丢) | "
          f"AST 判断写盘是否在循环内, 不靠字符串猜 | "
          f"重试循环(range<=12)与短跑(模块级<=30 元素)自动排除, **不靠人工豁免名单** | "
          f"★钉住 run_gates 的落盘必须在 G-K2 **之前** | "
          f"★★worker 逐条隔离异常(**不丢数据 ≠ 跑得完**; arm B 曾崩在 339/405) | "
          f"★★★采读数探针落盘**原始响应**(否则「模型没答」与「解析器坏了」永久混在一起) | "
          f"{n} 条反向验证)")
