#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""消融装置 v3 —— **可复用**、**先验收判官再用判官**。

★ 这份模块只提供**量具**, 不下任何判决。判决由调用方按 M5 词表给出, 并且
  **只有 positive_control() 返回 passed=True 时才允许出判决**。

★★★ 三轮实践钉住的方法论(不要重新发明, 见 docstring 常量 METHODOLOGY):
  M1 先验收判官(死常量阳性对照 + 液性对照)  M2 L3=instrument_hash 是重言, 零证据力
  M3 共享迭代器喂线程池 ⇒ 伪差异; 扫描面漏 accuracy/ ⇒ 把消费者判成没有消费者
  M4 引用计数是词碰撞不是引用, 报粗计/严计两个数   M5 判决词表(deletable 是独立字段)
  M6 无差异族必须再跑注入检验   M7 工况随判决同行   M8 存量消融天然把保险丝判成装饰
"""
import builtins, contextlib, copy, glob, hashlib, io, json, os, pathlib, re, socket, sys, types

ROOT = pathlib.Path(__file__).resolve().parent.parent

# ── 字符串化的自我声明(要求: 「我不覆盖什么」必须是代码里的字符串, 不是注释) ────────
METHODOLOGY = (
    "M1 先验收判官再用判官 · M2 L3(instrument_hash)是重言零证据力 · "
    "M3 按 tag 索引重放(不用共享迭代器)且扫描面含 accuracy/ · M4 引用计数报粗计与严计两个数 · "
    "M5 判决词表 LOAD_BEARING_L2 / LOAD_BEARING_L1_ONLY / UNREACHABLE / NO_CONSUMER / COULD_NOT_RUN / "
    "CIRCULAR / INCONCLUSIVE, deletable 是独立字段不由 verdict 推导 · "
    "M6 凡判无差异必跑荒谬值注入臂 · M7 工况(market/profile/k分布/语料sha/时点)随判决同行 · "
    "M8 存量消融天然把保险丝判成装饰: NO_CONSUMER 必须区分真死与本工况未触发")

EVIDENCE_SCOPE = (
    "本装置能支持的结论**仅限**: 在**存量语料重放 + 内存内源码变异**这一工况下, "
    "某常量/字段是否改变数值输出(L1)与判决面(L2)。"
    "它**不能**证明: 真实模型的语义判断准确率 · 重复稳定性 · 线上工况下的行为 · "
    "该常量在**其它 k / 其它 market / 其它 profile** 下是否承重。")

# 冻结生产件: 动一个字都算事故。
FROZEN = ("scripts/cce_knot_classify.py", "config/knot_taxonomy.json",
          "config/cce_core_manifest.json", "accuracy/run_gates.py")

# M3-② 扫描面必须含 accuracy/ tests/ .github/ config/ —— 上一轮只扫 scripts/+probes/,
# 于是把 accuracy/run_gates.py:145 的真实消费者判成了「零引用」。
SCAN_DIRS = ("scripts", "probes", "accuracy", "tests", ".github", "config")
SCAN_SUFFIXES = (".py", ".json", ".yml", ".yaml", ".md", ".txt", ".sh")
# M4 严计限定词: 同一行里出现这些词才算「疑似真引用」。
STRICT_HINTS = ("taxo", "knot", "self", "stage1", "stage2", "_S1_", "gate")


# ═══════════════════════════ 绊线 ═══════════════════════════════════════════
class NetworkTripwire(AssertionError):
    """任何**新建 socket 连接**都是失败, 不是警告。"""


class Tripwire:
    """socket 绊线。`scope` 如实说明覆盖什么、**不覆盖**什么。"""

    COVERS = "覆盖: 本进程内**经 socket.socket.connect 新建**的连接(含 urllib/requests/http.client)。"
    DOES_NOT_COVER = ("**不覆盖**: ① 进入本上下文**之前已建立**的连接 "
                      "② 不走 socket 的传输(共享内存 / 本机文件 / unix pipe 以外的自带通道) "
                      "③ **子进程**(subprocess / os.system 另起进程, 有自己的 socket 模块) "
                      "④ **C 扩展自带的网络栈**(不经 Python socket 对象) "
                      "⑤ 本进程外的任何东西。")
    CLAIM = ("⇒ 证据只能说「**本进程内经 socket 新建的连接被拦截, 且整段运行中一次都没被触发**」, "
             "**不能**说「全进程所有网络出口都已关闭」。")

    def __init__(self):
        self._orig = None
        self.tripped = []

    def __enter__(self):
        self._orig = socket.socket.connect
        tw = self

        def _guard(s, addr, *a, **k):
            tw.tripped.append(repr(addr))
            raise NetworkTripwire(f"★★★ 离线隔离被突破: {addr}")

        socket.socket.connect = _guard
        # 加载期就断言未触发(要求: 绊线必须在加载期装上并断言未触发)
        assert not self.tripped, "★ 绊线装上时就已被触发 —— 不可能, 装置坏了"
        return self

    def __exit__(self, *exc):
        socket.socket.connect = self._orig
        return False

    @property
    def scope(self):
        return f"{self.COVERS} {self.DOES_NOT_COVER} {self.CLAIM}"

    @property
    def armed(self):
        return socket.socket.connect is not self._orig and self._orig is not None


# ═══════════════════════════ 文件完整性 ═════════════════════════════════════
def sha256_file(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


@contextlib.contextmanager
def file_integrity(paths):
    """进出各取一次 sha256, 退出时**逐一断言相同**。rec 里留下两组哈希供写进产物。"""
    paths = [str(ROOT / p) if not os.path.isabs(str(p)) else str(p) for p in paths]
    rec = {"before": {p: sha256_file(p) for p in paths}, "after": None,
           "identical": None, "changed": []}
    try:
        yield rec
    finally:
        rec["after"] = {p: sha256_file(p) for p in paths}
        rec["changed"] = [p for p in paths if rec["before"][p] != rec["after"][p]]
        rec["identical"] = not rec["changed"]
        assert rec["identical"], f"★★★ 仓内被测文件被改动(R2 违反): {rec['changed']}"


# ═══════════════════ 配置注入 / 到达面(CE-21-b · CE-21-c · N1) ═════════════
INJECTION_NOTE = (
    "★ N1 注入作用域 ≠ 观测面作用域 —— 第三/四/五轮各复发一次。"
    "(b) 仓内 48 个模块在 **import 期自己再从磁盘读一份 config**(两种写法都有: "
    "`json.load(open(...))` 与 `Path.read_text()`→`io.open`), 只注内存字典**到不了**它们; "
    "(c) 变异模块不进 `sys.modules`, 跨模块 `import X` 拿到的是**磁盘原件**, 消融臂静默绑回基线。"
    "两者都让「注入后下游不变」被读成「没有消费者」—— **假阴性, 且读起来像最强的证据**。"
    "⇒ 到不了的面只能标 blind + INCONCLUSIVE, **不许**拿来支撑无差异结论。")


def _reader_frame():
    """找出**真正发起这次读**的那一帧 —— 跳过 pathlib / io / json / 本装置自己。"""
    hop = (os.path.dirname(pathlib.__file__ or ""), os.path.dirname(json.__file__ or ""))
    f = sys._getframe(1)
    while f is not None:
        fn = f.f_code.co_filename
        if not (fn == __file__ or fn.startswith(hop) or "importlib" in fn or fn.startswith("<")):
            return {"module": f.f_globals.get("__name__"), "file": fn, "line": f.f_lineno}
        f = f.f_back
    return {"module": None, "file": None, "line": None}


@contextlib.contextmanager
def config_injection(overrides):
    """把**指定配置文件路径**的读取重定向到内存内容, 其余读操作**原样放行**。

    overrides: {path: str | bytes | 任意可 json.dumps 的对象}; path 相对 ROOT 或绝对。
    ★ 路径不存在 ⇒ **当场抛**。错拼的路径 = 没注入, 却读起来像注入了 —— 那正是本缺陷的形状。
    ★ 只拦 **读** 模式; 写/追加/独占一律走真 open(装置绝不代写仓内文件)。
    ★ 退出时 `builtins.open` 与 `io.open` 逐一还原(两个都要: `Path.read_text` 走 `io.open`)。
    ★ 不传(或传空) ⇒ **一个钩子都不装**, 行为与本次修改前逐字相同。
    """
    resolved, declared = {}, {}
    for k, v in (overrides or {}).items():
        p = pathlib.Path(k)
        p = (p if p.is_absolute() else ROOT / p).resolve()
        if not p.is_file():
            raise FileNotFoundError(
                "★★★ 配置注入路径不存在: %r → %s —— 错拼的路径 = 没注入, "
                "但产物会读起来像注入过(CE-21-b 的形状)" % (k, p))
        resolved[str(p)] = v if isinstance(v, str) else (
            v.decode("utf-8") if isinstance(v, bytes) else json.dumps(v, ensure_ascii=False))
        declared[str(p)] = k
    rec = {"paths": sorted(declared.values()), "opened": [], "note": INJECTION_NOTE,
           "★这个日志能证明什么": "只能证明「有人读了那个路径」。**证明不了**读到的值进了哪个符号 —— "
                            "那要用 injection_reach() 直接读被加载模块的属性。"}
    if not resolved:
        yield rec                      # 默认路径: 不装钩子
        return

    b_open, i_open = builtins.open, io.open

    def _patched(file, mode="r", *a, **k):
        try:
            key = str(pathlib.Path(file).resolve())
        except (TypeError, ValueError, OSError):
            return b_open(file, mode, *a, **k)
        text = resolved.get(key)
        if text is None or any(c in mode for c in "wax+"):
            return b_open(file, mode, *a, **k)
        rec["opened"].append(dict(path=declared[key], mode=mode, **_reader_frame()))
        return io.BytesIO(text.encode("utf-8")) if "b" in mode else io.StringIO(text)

    builtins.open = io.open = _patched
    try:
        yield rec
    finally:
        builtins.open, io.open = b_open, i_open


@contextlib.contextmanager
def as_import(mapping):
    """把变异模块**临时**绑进 `sys.modules`, 跨模块 `import X` 才拿得到消融版(CE-21-c)。

    mapping: {import_name: module}, 或单个模块(名字取源文件 stem)。
    退出时逐键还原(原来有 ⇒ 还原原对象; 原来没有 ⇒ 删掉) ⇒ **不污染主进程后续 import**。
    """
    if isinstance(mapping, types.ModuleType):
        mapping = {pathlib.Path(mapping.__file__).stem: mapping}
    miss = object()
    saved = {n: sys.modules.get(n, miss) for n in mapping}
    try:
        sys.modules.update(mapping)
        yield mapping
    finally:
        for n, old in saved.items():
            sys.modules.pop(n, None) if old is miss else sys.modules.__setitem__(n, old)


MISSING = object()


def injection_reach(symbol, modules, needle):
    """★ 注入**到达面**自检: 给定符号与注入哨兵, 报出哪些模块**实际持有**被注入的值。

    modules: {label: module} 或模块序列(label 取 `__file__` 的 stem)。
    判据 = **读被加载模块上那个符号本身**, 不是「我拦截过一次 open」——
    拦截日志只能证明有人读了那个路径, 证明不了读到的值进了这个符号。
    ⇒ 谎报(把没到的说成到了)当场被这条判据翻掉。
    """
    if not isinstance(modules, dict):
        modules = {pathlib.Path(getattr(m, "__file__", "?%d" % i)).stem: m
                   for i, m in enumerate(modules)}
    per = {}
    for label, mod in modules.items():
        val = getattr(mod, symbol, MISSING)
        if val is MISSING:
            per[label] = {"status": "NO_SUCH_SYMBOL", "needle_found": False, "value_sha16": None}
            continue
        blob = _canon(val)
        per[label] = {"status": "REACHED" if needle in blob else "BLIND",
                      "needle_found": needle in blob, "value_sha16": _sha(val)}
    return {
        "symbol": symbol, "needle": needle, "per_module": per,
        "reached": sorted(l for l, v in per.items() if v["status"] == "REACHED"),
        "blind": sorted(l for l, v in per.items() if v["status"] != "REACHED"),
        "★blind 怎么读": ("blind = 本次注入**没到达**这个模块 ⇒ 它那一面只能标 blind + INCONCLUSIVE。"
                      "**列了 blind 就不许再拿那一面支撑「无差异 / 没有消费者」**(M6 · CE-3)。"),
        "★判据来自哪": "getattr(模块, 符号) 的实际值里找哨兵 —— 不读拦截日志, 不读任何自报字段。",
        "★不覆盖": ("① 符号在模块里被改名/拆散后本查询看不见 ② 只在函数体内临时读配置的消费者"
                  "(值不落到模块属性)查不到 ③ 经 JSON 传给子进程/外部工具的那一段。"),
    }


# ═══════════════════════════ 内存内加载 ═════════════════════════════════════
_LOAD_SEQ = [0]


def load(module_path, source_mutator=None, env=None, config_overrides=None):
    """**内存内**改源码后 exec, 返回独立模块实例。仓里文件一字不改。

    顺序铁律: **先设环境 → 再编译 → 再 exec** —— 不给「顶层 import 后再补 env」留空间。
    绊线在整个加载期间是**装上的**, 退出前断言未触发。

    config_overrides(CE-21-b, 可选, **默认不传 = 行为与修改前逐字相同**):
      {config 路径: 内容} —— 让「import 期自己从磁盘再读一份 config」的模块也看得见注入。
      退出 load() 即完整还原。到达面用 `injection_reach()` 查, **不许假定它到了**。
    """
    p = pathlib.Path(module_path)
    if not p.is_absolute():
        p = ROOT / p
    src = p.read_text(encoding="utf-8")
    mutated = False
    if source_mutator is not None:
        new = source_mutator(src)
        mutated = (new != src)
        src = new

    keys = ("MINIMAX_API_KEY", "CCE_MEASUREMENT_MODEL", "CCE_KNOT_N", "CCE_SKIP_GK2",
            "CCE_CORPUS", "CCE_OUT_DIR", "VSE_ROOT", "PYTHONHASHSEED")
    keys = tuple(set(keys) | set((env or {}).keys()))
    saved = {k: os.environ.get(k) for k in keys}
    # ★ 绝不 export 真 key。假 key 只是为了让 import 期的 os.environ[...] 不炸。
    os.environ["MINIMAX_API_KEY"] = "OFFLINE-FAKE-KEY-NOT-A-SECRET"
    os.environ.setdefault("CCE_SKIP_GK2", "1")
    for k, v in (env or {}).items():
        os.environ[k] = v

    _LOAD_SEQ[0] += 1
    mod = types.ModuleType(f"{p.stem}__abl{_LOAD_SEQ[0]}")
    mod.__file__ = str(p)          # 让被测模块的 ROOT 推导与真仓一致
    added = [str(ROOT / "scripts"), str(ROOT / "accuracy")]
    for d in added:
        sys.path.insert(0, d)
    try:
        with Tripwire() as tw, config_injection(config_overrides) as cfg:
            exec(compile(src, str(p), "exec"), mod.__dict__)
            assert not tw.tripped, f"★★★ 加载期发生网络连接: {tw.tripped}"
        mod._ABL_TRIPWIRE = tw
        mod._ABL_CONFIG_INJECTION = cfg
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        for d in added:
            if d in sys.path:
                sys.path.remove(d)
    mod._ABL_MUTATED = mutated
    mod._ABL_SRC_SHA = hashlib.sha256(src.encode()).hexdigest()[:16]
    return mod


def replace_once(old, new):
    """构造一个 source_mutator, 且**断言恰好命中一次** —— 空变异臂是假消融。"""
    def _m(src):
        n = src.count(old)
        assert n == 1, f"★ 变异锚点命中 {n} 次(要求恰好 1 次): {old[:60]!r}"
        return src.replace(old, new)
    return _m


# ═══════════════════════════ 重放 stub(M3-①) ═══════════════════════════════
REPLAY_NOTE = ("★ 按 **tag** 索引, **不是**共享迭代器。"
               "`_stage2_aggregate` 用 ThreadPoolExecutor(5) 并发调 `_stage2_draw(prompt, taxo, f'd{i}')`; "
               "若 stub 写成 `it=iter(draws); next(it)`, 线程抢迭代器 ⇒ draw 与序号随机错配 ⇒ "
               "**纯文档字段也会被判成 L1 变化**(上一轮 changelog_* 被判 1/8~5/8 随机数)。")


def replay_draws(tags_to_draws):
    """按 tag 索引的重放 stub, 用来 monkeypatch `_stage2_draw(prompt, taxo, tag)`。

    未知 tag **直接抛** —— 静默返回 None 会被聚合层当成「本次抽样失败」而吞掉。
    每次返回 deepcopy: `_stage2_draw` 的真实实现会往返回值里塞 `_weight_shim_fired`,
    共享同一个 dict 会让两次重放互相污染(确定性自检会因此变红, 但根因难找)。
    """
    calls = []

    def stub(prompt, taxo, tag):
        calls.append(tag)
        if tag not in tags_to_draws:
            raise KeyError(f"★ 重放 stub 收到未登记的 tag={tag!r}; 已登记 {sorted(tags_to_draws)[:8]}")
        return copy.deepcopy(tags_to_draws[tag])

    stub.calls = calls
    stub.note = REPLAY_NOTE
    return stub


# ═══════════════════════════ 引用扫描(M3-② / M4) ═══════════════════════════
def scan_refs(symbol, hints=STRICT_HINTS):
    """返回 (coarse, strict) 两个数, 作为**区间两端**。

    coarse = 裸词频(词边界匹配) —— 判决用它(保守: 虚高只会把 NO_CONSUMER 推成 INCONCLUSIVE)。
    strict = 同一行里还出现限定词(taxo|knot|self|stage1|stage2|_S1_|gate)的那部分。
    ★ 两个都是**词碰撞统计**, 不是引用图。coarse 高不等于有消费者, strict 低不等于没有。
    """
    pat = re.compile(r"(?<![\w])" + re.escape(symbol) + r"(?![\w])")
    coarse = strict = 0
    files = 0
    for d in SCAN_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file() or p.suffix not in SCAN_SUFFIXES:
                continue
            if "__pycache__" in p.parts or p.name == pathlib.Path(__file__).name:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if symbol not in text:
                continue
            files += 1
            for line in text.splitlines():
                n = len(pat.findall(line))
                if not n:
                    continue
                coarse += n
                if any(h in line for h in hints):
                    strict += n
    return coarse, strict


def scan_surface():
    return {"dirs": list(SCAN_DIRS), "suffixes": list(SCAN_SUFFIXES),
            "blind_spot_note": ("扫描面**不含**仓外任何目录, 也不含 .git/ 与 __pycache__/。"
                                "它是**词碰撞统计**, 不是调用图: 动态 getattr / 字符串拼出来的键 / "
                                "经 JSON 传给外部工具的字段, 本扫描**看不见**。")}


# ═══════════════════════════ 存量语料 ═══════════════════════════════════════
def corpus(pattern="archive/*/*.json"):
    """返回 [(path, record)] —— 只要 stage2.draw_ledger 非空的那些。自己数, 不沿用任何旧数字。"""
    out = []
    for f in sorted(glob.glob(str(ROOT / pattern))):
        try:
            d = json.loads(pathlib.Path(f).read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(d, dict) and isinstance(d.get("stage2"), dict) and d["stage2"].get("draw_ledger"):
            out.append((f, d))
    return out


def corpus_sha(recs):
    """对参与本次判决的语料文件取一个合成 sha256(按路径排序, 逐份内容哈希再哈希)。"""
    h = hashlib.sha256()
    for f, _ in recs:
        h.update(os.path.relpath(f, ROOT).encode())
        h.update(sha256_file(f).encode())
    return h.hexdigest()



def _market_facts():
    """★★★ CE-21(a) 2026-09-12 修: 这里原本**硬编**一句
    「N/A —— 仓内无 market 字段(已实扫 scripts/ config/ accuracy/)」。

    **那句话是假的**, 而且它是 CE-2 的**源头** —— 凡直接把 operating_point() 落进产物的
    agent 都会再抄一遍。第三轮、第四轮各被指出一次, 两轮都没人改。
    四个消融单元各自独立重扫, 分别得 33 / 44 / 56 / 61 处命中(口径不同: 是否含
    probes/ .github/ tests/data), **没有一个是 0**。

    ⇒ 改成**真扫**。扫不动就说扫不动, **不回落到任何预写结论** ——
      把「我没查」写成「我查过, 没有」是本仓登记过的错误族里最贵的一种。
    """
    import re as _re
    dirs = ["scripts", "config", "accuracy", "probes"]
    hits, per = [], {}
    try:
        for d in dirs:
            root = pathlib.Path(ROOT) / d
            if not root.exists():
                per[d] = "目录不存在"
                continue
            n = 0
            for f in root.rglob("*"):
                if f.suffix not in (".py", ".json") or "__pycache__" in f.parts:
                    continue
                try:
                    txt = f.read_text(encoding="utf-8")
                except Exception:
                    continue
                c = len(_re.findall(r"\bmarket\b", txt))
                if c:
                    n += c
                    hits.append("%s:%d" % (f.relative_to(ROOT), c))
            per[d] = n
    except Exception as e:                      # 扫不动就如实说
        return {"★口径": "实扫失败", "★错误": "%s: %s" % (type(e).__name__, e),
                "★不许": "**不回落到任何预写结论** —— 「没查」不等于「查过没有」。"}
    return {
        "★口径": "词边界 \\bmarket\\b, 扫 %s 下的 *.py 与 *.json(不含 __pycache__)" % "/".join(dirs),
        "总命中": sum(v for v in per.values() if isinstance(v, int)),
        "逐目录": per,
        "命中最多的前几处": sorted(hits, key=lambda x: -int(x.rsplit(":", 1)[1]))[:6],
        "★这条曾经是假的": "本函数替换掉的硬编串写着「仓内无 market 字段(已实扫)」——**假**, "
                      "它是 CE-2 的源头, 被指出两轮未改。真消费点见 "
                      "scripts/cce_strategy_gate.py(含 CCE_MARKET 环境变量)与 scripts/cce_outbound_guard.py。",
        "★仍成立的那一半": "存量语料按 archive/<run_id> 归档, **不带市场维度** ⇒ "
                      "基于存量的判决仍**不能**外推到按市场分层的工况。"
                      "★ 但那是**语料**的性质, 不是「仓内没有 market」。两句话被我先前混成了一句。",
    }

def operating_point(recs, extra=None):
    """M7: 工况随判决同行。工况漂移 ⇒ 判决当场失效, 这不是免责声明是判据的一部分。"""
    import collections, datetime
    k = collections.Counter((r.get("stage1") or {}).get("k_requested") for _, r in recs)
    n = collections.Counter(len(r["stage2"]["draw_ledger"]) for _, r in recs)
    temps = collections.Counter()
    for _, r in recs:
        for dr in ((r.get("stage1") or {}).get("draws") or []):
            if isinstance(dr, dict) and "from_temperature" in dr:
                temps[dr["from_temperature"]] += 1
    inst = collections.Counter(json.dumps((r.get("instrument") or {}), ensure_ascii=False,
                                          sort_keys=True) for _, r in recs)
    op = {
        "market": _market_facts(),
        "profile": sorted(inst),
        "n_archive_files": len(recs),
        "k_distribution": {str(kk): vv for kk, vv in sorted(k.items(), key=lambda x: str(x[0]))},
        "n_draws_per_file": {str(kk): vv for kk, vv in sorted(n.items())},
        "s1_temperature_distribution": {str(kk): vv for kk, vv in sorted(temps.items())},
        "corpus_sha256": corpus_sha(recs),
        "decided_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "drift_rule": "以上任一项变化 ⇒ 基于本工况的判决当场失效, 必须重跑。",
        "M8_structural_bias": ("只在存量数据上做的消融**天然把所有保险丝判成装饰** —— "
                               "保险丝的定义就是「平时永远不动」。故 NO_CONSUMER 必须区分"
                               "「真死」与「在本存量工况下没被触发」(后者应判 UNREACHABLE 并写明复活条件)。"),
    }
    op.update(extra or {})
    return op


# ═══════════════════════════ 观测量 L1 / L2 ═════════════════════════════════
OBSERVABLE_NOTE = ("★ 只用 L1(数值输出改变) 与 L2(判决改变)。"
                   "**明确排除 L3 = instrument_hash**: 它覆盖 ontology_version / s1_prompt_sha256 / "
                   "s2_prompt_sha256 / model / endpoint / sampling_policy, 改**任何**被覆盖的常量它都会变, "
                   "**包括改一个永不取用的死常量** ⇒ 用它判必然 100% 承重, 是重言。")

_PROBE_TEXT = ("我最近换了工作，整晚睡不着，一直在想是不是选错了。"
               "朋友都说挺好的，可我心里那块石头一直放不下，想找个人说说。"
               "有没有人也是这样过来的？我该怎么判断自己到底是不是做错了决定。")
_PROBE_CONTEXT = "离线消融探针的固定合成输入(非真实个体)"


def _stub_call_parse(mod):
    """确定性桩: 读数**只由温度决定**。

    ★ 这是最灵敏的检波器: 温度表一动, 拿到的读数就全变;
      温度表不动(改的是永不取用的档), 读数逐值不变。
    ★ 它**不模拟真实模型**, 只把「取了哪几档温度」放大成可观测的数值差异。
    """
    sizes = [("desire_vec", len(mod.DESIRES)), ("need_vec", len(mod.NEED_KEYS)),
             ("emotion_vec", len(mod.EMOTIONS)), ("action_vec", len(mod.ACTIONS))]

    def call_parse(mk, case_input, temperature, note):
        seed = int(hashlib.sha256(f"T={temperature!r}".encode()).hexdigest(), 16)
        pv = {}
        for salt, (name, n) in enumerate(sizes):
            raw = [((seed >> ((i + salt * 7) % 200)) & 0x3F) + 1 for i in range(n)]
            tot = sum(raw)
            pv[name] = [round(x / tot, 6) for x in raw]
        pv["appraisal"] = {"attribution": "none", "target_layer": "consumption_goal"}
        return "{}", {}, pv, {"n_calls": 1, "elapsed": 0.0}, True

    return call_parse


def _canon(o):
    return json.dumps(o, ensure_ascii=False, sort_keys=True, default=str)


def _sha(o):
    return hashlib.sha256(_canon(o).encode()).hexdigest()[:16]


def observe_stage1(mod, ks):
    """L1a/L1b: 真跑 `stage1()`(桩化 call_parse), 逐 k 记录**实际取用的温度**与四层读数。"""
    orig = mod.call_parse
    mod.call_parse = _stub_call_parse(mod)
    try:
        out = {}
        for k in ks:
            r = mod.stage1(_PROBE_TEXT, _PROBE_CONTEXT, k)
            out[str(k)] = {
                "temps_used": [d["from_temperature"] for d in r.get("draws", [])],
                "L1_layers_sha": _sha(r.get("layers")),
                "L1_within_js": r.get("within_js"),
                "L2_tops": r.get("tops"),
                "L2_measurement_status": r.get("measurement_status"),
                "L2_k_valid": r.get("k_valid"),
            }
        return out
    finally:
        mod.call_parse = orig


def observe_reach(mod, recs):
    """L1c: 存量 s1 draw 在当前温度表下**还取不取得到**。液性臂应在这里大面积翻。"""
    base = list(mod._S1_BASE_TEMPS)
    per_k = {}
    for f, r in recs:
        k = (r.get("stage1") or {}).get("k_requested")
        sched = set(base[:k]) if isinstance(k, int) and k <= len(base) else set(base)
        for dr in ((r.get("stage1") or {}).get("draws") or []):
            if not isinstance(dr, dict) or "from_temperature" not in dr:
                continue
            slot = per_k.setdefault(str(k), {"reachable": 0, "unreachable": 0})
            slot["reachable" if dr["from_temperature"] in sched else "unreachable"] += 1
    total_un = sum(v["unreachable"] for v in per_k.values())
    total = sum(v["reachable"] + v["unreachable"] for v in per_k.values())
    return {"per_k": per_k, "n_draws": total, "n_unreachable": total_un}


def observe_stage2(mod, recs, taxo):
    """L1d/L2: 用存量 draw_ledger 按 tag 重放 `_stage2_aggregate`。"""
    orig = mod._stage2_draw
    out = []
    try:
        for f, r in recs:
            ledger = r["stage2"]["draw_ledger"]
            tags = {f"d{i}": _row_to_draw(row) for i, row in enumerate(ledger)}
            stub = replay_draws(tags)
            mod._stage2_draw = stub
            agg = mod._stage2_aggregate("<PROMPT>", taxo, n=len(ledger))
            out.append({
                "file": os.path.relpath(f, ROOT),
                "L1_intensity": agg.get("intensity"),
                "L1_families": agg.get("families"),
                "L1_weights": {k["key"]: k["weight"] for k in agg.get("knots", [])},
                "L2_measurement_status": agg.get("measurement_status"),
                "L2_knot_order": [k["key"] for k in agg.get("knots", [])],
                "L2_top1_mode": (agg.get("sampling") or {}).get("top1_mode"),
                "L2_top1_unanimous": (agg.get("sampling") or {}).get("top1_unanimous"),
                "_tags_seen": sorted(stub.calls),
            })
        return out
    finally:
        mod._stage2_draw = orig


def _row_to_draw(row):
    """把存量 9 维台账行还原成 `_stage2_draw` 的返回形状。缺席(0)不进 knots —— 与生产一致。"""
    if row.get("abstained"):
        return {"knots": []}
    return {"knots": [{"key": k, "intensity": v}
                      for k, v in row["knot_vector"].items() if v > 0]}


def observe_all(mod, recs, taxo, ks):
    return {"stage1": observe_stage1(mod, ks),
            "reach": observe_reach(mod, recs),
            "stage2": observe_stage2(mod, recs, taxo)}


def _split_L1_L2(obs):
    """把观测量拆成 L1 面与 L2 面, 各出一个 sha —— 判决读这两个数, 不读 L3。"""
    L1 = {"stage1": {k: {kk: vv for kk, vv in v.items() if kk.startswith("L1") or kk == "temps_used"}
                     for k, v in obs["stage1"].items()},
          "reach": obs["reach"],
          "stage2": [{kk: vv for kk, vv in row.items() if kk.startswith("L1") or kk == "file"}
                     for row in obs["stage2"]]}
    L2 = {"stage1": {k: {kk: vv for kk, vv in v.items() if kk.startswith("L2")}
                     for k, v in obs["stage1"].items()},
          "stage2": [{kk: vv for kk, vv in row.items() if kk.startswith("L2") or kk == "file"}
                     for row in obs["stage2"]]}
    return L1, L2


def l3_instrument_hash(mod, taxo, k=3):
    """★ 只为**证明 L3 是重言**而提供, 绝不作为判据。"""
    try:
        return _sha(mod.instrument_id(taxo, k))
    except Exception:
        return _sha({"temps": list(mod._S1_BASE_TEMPS), "model": mod.MEASUREMENT_MODEL})


# ═══════════════════════════ 阳性对照 ═══════════════════════════════════════
TARGET = "scripts/cce_knot_classify.py"
_TEMPS_LINE = "_S1_BASE_TEMPS = [0.0, 0.3, 0.6, 0.9, 0.15, 0.45, 0.75]"

ARMS = {
    # M1 阳性对照(死常量): 第 6/7 档在 k∈{3,5} 下永不取用 ⇒ 判据**必须**判成非承重。
    "dead_swap":   _TEMPS_LINE.replace("0.45, 0.75", "0.11, 0.22"),
    # M6 注入检验: 同一位置塞荒谬值, 下游**仍然**必须不变。
    "dead_absurd": _TEMPS_LINE.replace("0.45, 0.75", "999.0, -999.0"),
    # M1 液性对照: 第 1 档 0.0→0.99, k=3 确实取用 ⇒ L1 **必须**大面积改变。
    "liquid":      _TEMPS_LINE.replace("[0.0,", "[0.99,"),
    # 空操作对照臂(L4 用): 只加一个空行, 任何差异都是伪红。
    "noop":        _TEMPS_LINE + "  # noop",
}


def positive_control(ks=(3, 5), extra_k=7):
    """跑死常量臂 + 液性臂 + 确定性自检, 返回结构化结果。

    通过条件(缺一即 passed=False, 且**不得出任何判决**):
      ① 死常量臂(swap 与 absurd 注入) L1 与 L2 **都不变** ⇒ 判据非重言
      ② 液性臂 L1 **改变** ⇒ 消融面确实接上
      ③ 同输入连跑两次的 stage2 聚合**逐字节相同** ⇒ 装置不抖(M3-①)
      ④ 全程绊线未触发 · 仓内被测文件 sha256 进出一致
      ⑤ L3 对照: 同一个死常量下 instrument_hash **会变** ⇒ 证实 L2 中说的重言, 并证实本判据避开了它
    """
    import datetime
    recs = corpus()
    assert recs, "★ 存量语料为空 —— 装置没法验收"
    taxo = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
    ks_obs = tuple(sorted({int(k) for k in ks} |
                          {int((r.get("stage1") or {}).get("k_requested"))
                           for _, r in recs
                           if isinstance((r.get("stage1") or {}).get("k_requested"), int)}))
    result = {"block": "ABLATION_V3_POSITIVE_CONTROL",
              "methodology": METHODOLOGY,
              "evidence_scope": EVIDENCE_SCOPE,
              "observable_note": OBSERVABLE_NOTE,
              "replay_note": REPLAY_NOTE,
              "injection_note": INJECTION_NOTE,   # M7 同理: 注入到达面的口径必须随判决同行
              "scan_surface": scan_surface(),
              "operating_point": operating_point(recs, {"ks_observed": list(ks_obs)}),
              "arms": {}, "checks": {}, "passed": None}

    with file_integrity(FROZEN) as fi:
        with Tripwire() as tw:
            result["tripwire_scope"] = tw.scope

            base_mod = load(TARGET)
            base_obs = observe_all(base_mod, recs, taxo, ks_obs)
            base_L1, base_L2 = _split_L1_L2(base_obs)

            # ③ 确定性自检: 同一输入连跑两次, 聚合输出必须逐字节相同
            again = observe_stage2(base_mod, recs, taxo)
            det_ok = _canon(again) == _canon(base_obs["stage2"])
            result["checks"]["determinism_same_module_twice"] = det_ok

            base_mod2 = load(TARGET)
            obs2 = observe_all(base_mod2, recs, taxo, ks_obs)
            det_ok2 = _canon(_split_L1_L2(obs2)) == _canon((base_L1, base_L2))
            result["checks"]["determinism_fresh_reload"] = det_ok2

            # 基线重放是否复现存盘数值(接线检查, 不是通过条件)
            repro = sum(1 for row, (f, r) in zip(base_obs["stage2"], recs)
                        if row["L1_intensity"] == (r["stage2"].get("intensity") or {}))
            result["checks"]["baseline_replay_reproduces_archived_intensity"] = \
                f"{repro}/{len(recs)}"

            result["checks"]["tags_indexed_not_iterator"] = all(
                row["_tags_seen"] == sorted(f"d{i}" for i in range(len(row["_tags_seen"])))
                for row in base_obs["stage2"])

            base_L3 = l3_instrument_hash(base_mod, taxo)

            for name, newline in ARMS.items():
                mod = load(TARGET, replace_once(_TEMPS_LINE, newline))
                assert mod._ABL_MUTATED, f"★ {name} 臂源码未变 —— 空臂"
                obs = observe_all(mod, recs, taxo, ks_obs)
                L1, L2 = _split_L1_L2(obs)
                result["arms"][name] = {
                    "source_sha16": mod._ABL_SRC_SHA,
                    "L1_changed": _canon(L1) != _canon(base_L1),
                    # 液性对照要的是「**大面积**改变」, 一个总布尔看不出面积 —— 逐面报
                    "L1_surfaces_changed": {k: _canon(L1[k]) != _canon(base_L1[k])
                                            for k in base_L1},
                    "L2_surfaces_changed": {k: _canon(L2[k]) != _canon(base_L2[k])
                                            for k in base_L2},
                    "L2_changed": _canon(L2) != _canon(base_L2),
                    "L1_sha": _sha(L1), "L2_sha": _sha(L2),
                    "temps_used": {k: v["temps_used"] for k, v in obs["stage1"].items()},
                    "n_unreachable_archived_draws": obs["reach"]["n_unreachable"],
                    "unreachable_share": round(obs["reach"]["n_unreachable"]
                                               / max(1, obs["reach"]["n_draws"]), 4),
                    "L3_instrument_hash": l3_instrument_hash(mod, taxo),
                    "L3_changed_TAUTOLOGY_NOT_EVIDENCE": l3_instrument_hash(mod, taxo) != base_L3,
                }

            # ⑤ 死常量在什么条件下会活 —— M5 要求 UNREACHABLE 必须写明复活条件, 这里给实证
            dead_mod = load(TARGET, replace_once(_TEMPS_LINE, ARMS["dead_absurd"]))
            hi_base = observe_stage1(base_mod, (extra_k,))
            hi_dead = observe_stage1(dead_mod, (extra_k,))
            result["checks"]["dead_constant_revives_at_k"] = {
                "k": extra_k,
                "base_temps": hi_base[str(extra_k)]["temps_used"],
                "dead_arm_temps": hi_dead[str(extra_k)]["temps_used"],
                "L1_changed_at_this_k": _canon(hi_base) != _canon(hi_dead),
            }

            result["checks"]["tripwire_tripped"] = list(tw.tripped)

    result["file_integrity"] = {"before": fi["before"], "after": fi["after"],
                                "identical": fi["identical"]}

    a = result["arms"]
    gates = {
        "dead_swap_not_load_bearing": not a["dead_swap"]["L1_changed"] and not a["dead_swap"]["L2_changed"],
        "dead_absurd_injection_still_no_diff": not a["dead_absurd"]["L1_changed"] and not a["dead_absurd"]["L2_changed"],
        "liquid_L1_changed": a["liquid"]["L1_changed"],
        "liquid_changed_broadly": a["liquid"]["n_unreachable_archived_draws"] > 0,
        "noop_no_diff": not a["noop"]["L1_changed"] and not a["noop"]["L2_changed"],
        "determinism": bool(result["checks"]["determinism_same_module_twice"]
                            and result["checks"]["determinism_fresh_reload"]),
        "tags_indexed": bool(result["checks"]["tags_indexed_not_iterator"]),
        "tripwire_never_tripped": not result["checks"]["tripwire_tripped"],
        "repo_files_untouched": result["file_integrity"]["identical"],
        "L3_is_tautology_confirmed": a["dead_absurd"]["L3_changed_TAUTOLOGY_NOT_EVIDENCE"],
        "dead_constant_is_UNREACHABLE_not_NO_CONSUMER":
            result["checks"]["dead_constant_revives_at_k"]["L1_changed_at_this_k"],
    }
    result["gates"] = gates
    result["passed"] = all(gates.values())
    result["failed_gates"] = [k for k, v in gates.items() if not v]
    result["judge_verdict_on_dead_constant"] = (
        "UNREACHABLE(本工况 k≤5 下第 6/7 档永不取用; k≥6 即复活 —— 实证见 "
        "checks.dead_constant_revives_at_k)。M5 词表下**不是** NO_CONSUMER, 更**不是**承重。"
        if result["passed"] else "★ 判官未验收通过, 不出判决")
    result["decided_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    return result


if __name__ == "__main__":
    r = positive_control()
    out = ROOT / "tests/data/ablation_v3/_positive_control.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"passed": r["passed"], "failed_gates": r["failed_gates"],
                      "gates": r["gates"], "checks": r["checks"],
                      "operating_point": r["operating_point"],
                      "arms": {k: {kk: vv for kk, vv in v.items() if kk != "temps_used"}
                               for k, v in r["arms"].items()},
                      "written": str(out)}, ensure_ascii=False, indent=1))
