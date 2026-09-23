"""★★★ 进 prompt 的**环境变量**必须被写进产物 —— 零 API, AST 现算。

## 怎么发现的
2026-09-08 要拿 run_a_repeat 的读数与新臂配对比较, 于是去核「那次 body 截断是 700 吗」——
**产物里没记**。`CCE_BODY_CHARS` 与 `CCE_UNIT_LABEL` 都是环境变量, 都进 prompt,
两次运行(run_a_repeat / run_c_confirm)的产物里**一个都没有**。
⇒ 「两次运行可比」在那之前只能**假设**, 不能核实。

## ★★ 这是「修了一个实例, 没修那一类」
manifest 早就写明同族洞: 「只钉文件 sha 有一个抓不到的洞: **MEASUREMENT_MODEL 是环境变量**,
换它就换仪器, 却一个文件都不动」—— 那个洞用「现算 instrument_hash」修了。
**但同一类的另外两个实例(截断长度、单元标签)一直没修。**
⇒ 本闸不钉这两个名字, 而是**现算**「哪些环境变量流进了 prompt」, 逐个要求被记录。
   下一次有人再加一个环境变量进 prompt, 这条闸会自己发现。
"""
import ast
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC_PATH = ROOT / "accuracy" / "run_gates.py"
SRC = SRC_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SRC)

# 语料路径不流经模块级 Name(条目是函数参数), AST 追不到, 但它决定**测的是哪批文本** ⇒ 硬性要求
MUST_RECORD_EVEN_IF_AST_CANNOT_SEE_IT = {"CCE_CORPUS"}


def _env_reads(node):
    """这棵子树里读了哪些环境变量名。"""
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr == "get" and isinstance(n.func.value, ast.Attribute) \
                and n.func.value.attr == "environ" and n.args \
                and isinstance(n.args[0], ast.Constant):
            out.add(n.args[0].value)
        if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Attribute) \
                and n.value.attr == "environ" and isinstance(n.slice, ast.Constant):
            out.add(n.slice.value)
    return out


def _module_level_env_vars():
    """模块级变量名 → 它源自哪个环境变量(1 层链: X = f(os.environ[...]))。"""
    m = {}
    for node in TREE.body:
        if isinstance(node, ast.Assign):
            e = _env_reads(node.value)
            if e:
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        m[t.id] = e
    return m


def _names_reaching_prompt_format():
    """每一处 `<模板>.format(...)` 的实参里出现的所有模块级名字。"""
    tmpl = {n.id for n in ast.walk(TREE) if isinstance(n, ast.Name) and n.id.endswith("_TMPL")}
    used = set()
    for n in ast.walk(TREE):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr == "format" and isinstance(n.func.value, ast.Name) \
                and n.func.value.id in tmpl:
            for a in list(n.args) + [k.value for k in n.keywords]:
                used |= {x.id for x in ast.walk(a) if isinstance(x, ast.Name)}
    return used


def _load_run_gates():
    """★★★ 2026-09-11: 原先这里直接 `import run_gates`, 而它 import 时就读
    `os.environ["MINIMAX_API_KEY"]` ⇒ **没有 key 就整条判红**, 闸变成「有没有配 key」的探测器,
    而不是它自称要测的东西。走已建好的离线装置(先设假环境变量再 import), 零网络。"""
    import sys as _s
    _s.path.insert(0, str(ROOT / "probes"))
    import accuracy_offline_harness as H
    with H._Tripwire() as tw:
        m = H.load()
    assert not tw.tripped, f"★★★ 加载闸模块时发生了网络连接: {tw.tripped}"
    return m


def _recorded():
    return set(_load_run_gates().RUN_PARAMS)


def test_every_env_var_that_reaches_a_prompt_is_recorded():
    """★★★ 核心: 流进 prompt 的环境变量, 一个都不许不记。"""
    envmap, reaching, rec = _module_level_env_vars(), _names_reaching_prompt_format(), _recorded()
    leaks = {}
    for var, envs in envmap.items():
        if var in reaching:
            missing = envs - rec
            if missing:
                leaks[var] = sorted(missing)
    assert not leaks, (
        f"★★★ 这些环境变量**进了 prompt 却没被写进产物**: {leaks}\n"
        "⇒ 换掉它就换了刺激, 而事后无从核实两次运行是否可比。"
        "把它加进 run_gates.RUN_PARAMS。")


def test_corpus_path_is_recorded_even_though_ast_cannot_trace_it():
    """★ CCE_CORPUS 决定**测的是哪批文本**, 但条目是函数参数 ⇒ AST 追不到。硬性要求记录。"""
    missing = MUST_RECORD_EVEN_IF_AST_CANNOT_SEE_IT - _recorded()
    assert not missing, f"★ {missing} 未被记录 —— 它决定测的是哪批文本, 比截断长度更要紧"


def test_both_artifacts_carry_the_params_not_just_one():
    """★ 聚合产物与逐条产物**都要**带 —— 只带一个, 另一个被单独引用时照样查不到。"""
    for art in ("gates_result", "raw_annotations"):
        i = SRC.index(f'"{art}.json"') if f'"{art}.json"' in SRC else -1
        assert i > 0, f"★ 找不到 {art} 的写盘点"
    n = SRC.count('"run_params": RUN_PARAMS')
    assert n == 3, (
        "★ RUN_PARAMS 必须写进**三处**: gates_result 正常路径、gates_result **扣发**路径、"
        f"raw_annotations。现在 {n} 处。"
        "★ 扣发路径尤其不能漏 ——「哪批语料、哪个截断下没人合格」本身就是要复核的事实。")


def test_the_two_historical_runs_are_flagged_as_unverifiable():
    """★★ 已有的两次运行**补不回来**。必须留档说它们的可比性是**假设**, 不是核实。"""
    doc = ROOT / "tests" / "data" / "run_params_gap.json"
    assert doc.exists(), "★ 缺 tests/data/run_params_gap.json"
    d = json.loads(doc.read_text(encoding="utf-8"))
    s = json.dumps(d, ensure_ascii=False)
    assert "run_a_repeat" in s and "run_c_confirm" in s, "★ 必须点名是哪两次运行"
    assert "假设" in s and "不是核实" in s, "★ 必须写明那两次的可比性是假设而非核实"


def test_probes_that_collect_readings_stamp_their_params():
    """★★ 闸不能只管 run_gates —— **探针复用同一批参数构造 prompt, 继承同一个缺陷**。

    ★ 第一版的判据是「引用了 RG.BODY_CHARS/UNIT_LABEL 就必须盖章」——
      **它误判了一个零 API 探针**(taxonomy_field_reach_ledger 只读源码、不采读数, 没有「运行」可盖)。
      ⇒ 判据改精确: **采读数的**(真发网络请求的)才必须盖章。
      ★ 修法不是加豁免名单 —— 本仓被「名单里的东西没人再看」坑过四次。判据本身改准。
    """
    import glob
    # ★ 判据用「**写进 cce_runs/ 运行目录**」认「采读数」——
    #   比找 urlopen 稳: 实测两个探针(belong_*)既无 urlopen 也无 RG.call, 走的是别的调用路径,
    #   靠列举网络原语一定会漏。而「产出了一个运行目录」正是需要盖章的那件事本身。
    bad = []
    for f in sorted(glob.glob(str(ROOT / "probes" / "*.py"))):
        src = pathlib.Path(f).read_text(encoding="utf-8")
        uses_params = "RG.BODY_CHARS" in src or "RG.UNIT_LABEL" in src
        collects = "cce_runs" in src
        if uses_params and collects and "stamp_params" not in src:
            bad.append(pathlib.Path(f).name)
    assert not bad, (
        f"★★ 这些探针**采读数**且用了进 prompt 的环境参数, 却没盖章: {bad}\n"
        "⇒ 它们的产物事后无法核实与别的运行是否可比。写 raw 之前加 RG.stamp_params(OUT)。")


def test_the_rule_really_excludes_only_zero_api_probes():
    """★ 灵敏度自证: 上一条若把「采读数」判宽了, 它就成了恒绿的假闸。

    现算确认: 确有探针**同时**满足「用参数 + 产出运行目录」(因而被真正约束),
    且那个零 API 探针确实**不**产出运行目录(因而被正当排除)。
    ★ 第一版用「源码里有 urlopen」认采读数 —— **漏了两个** belong 探针(它们既无 urlopen
      也无 RG.call), 于是被约束的只剩 4 个。列举网络原语一定会漏, 改用「写进 cce_runs/」。
    """
    import glob
    constrained, zero_api = [], []
    for f in sorted(glob.glob(str(ROOT / "probes" / "*.py"))):
        src = pathlib.Path(f).read_text(encoding="utf-8")
        if not ("RG.BODY_CHARS" in src or "RG.UNIT_LABEL" in src):
            continue
        (constrained if "cce_runs" in src else zero_api).append(pathlib.Path(f).name)
    assert len(constrained) >= 5, f"★★ 只有 {len(constrained)} 个探针被约束 —— 判据可能判宽了, 成了假闸"
    assert "taxonomy_field_reach_ledger.py" in zero_api, (
        "★ 零 API 探针不再被识别为零 API —— 若它开始采读数了, 就该盖章; 请复核")


def test_stamp_helper_writes_the_same_params_not_a_second_copy():
    """★ 单一真值: 盖的章必须**来自 RUN_PARAMS 本身**, 不许探针另抄一份(会静默漂移)。"""
    src = SRC[SRC.index("def stamp_params"):]
    assert "dict(RUN_PARAMS)" in src[:600], \
        "★ stamp_params 必须以 RUN_PARAMS 为源 —— 另抄一份就是本仓栽过的『两份实现悄悄漂移』"


def test_no_probe_hardcodes_a_truncation_length():
    """★★★ 截断长度不许硬编在探针里 —— 硬编 ⇒ **盖的章会说谎**。

    实测(2026-09-08): 三个探针写死 `body=it["b"][:2000]`, 而 RG.BODY_CHARS 是 700。
    若它们照 RUN_PARAMS 盖章, 产物会记「700」而实际截在 2000 ——
    **一个比不记更坏的结果: 从「查不到」变成「查到的是错的」。**
    ⇒ 三个都改走 `os.environ.setdefault("CCE_BODY_CHARS","2000")` + `RG.BODY_CHARS`,
      prompt **逐字不变**, 但单一真值。
    """
    import glob
    bad = []
    for f in sorted(glob.glob(str(ROOT / "probes" / "*.py"))):
        t = ast.parse(pathlib.Path(f).read_text(encoding="utf-8"))
        for n in ast.walk(t):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "format"):
                continue
            for kw in n.keywords:
                if kw.arg != "body":
                    continue
                v = kw.value
                if isinstance(v, ast.Subscript) and isinstance(v.slice, ast.Slice) \
                        and isinstance(v.slice.upper, ast.Constant) \
                        and isinstance(v.slice.upper.value, int):
                    bad.append(f"{pathlib.Path(f).name}:{v.lineno} [:{v.slice.upper.value}]")
    assert not bad, (
        f"★★★ 这些探针把截断长度**硬编**在 prompt 里: {bad}\n"
        "⇒ 盖的章会记成 RUN_PARAMS 的值, 与实际不符 —— **查到的是错的**, 比查不到更坏。\n"
        '改法: 在 import run_gates 之前 os.environ.setdefault("CCE_BODY_CHARS","<那个数>"), '
        "再用 RG.BODY_CHARS。prompt 逐字不变。")


def test_probes_with_extra_annotators_declare_the_real_panel():
    """★★ 「盖章」机制**第一次真用就漏了一个字段** —— 章里只有 run_gates 的五员,
    漏了跨家族的 glm-4.5-flash, 而那正是本轮跨家族臂跑的模型。

    ⇒ **新机制本身也要被检查, 不能因为是新的就当它对。**
    本条现算: 探针源码里出现 glm/其它非 run_gates 模型名的, 必须传 annotators_actually_used。
    """
    import glob
    bad = []
    for f in sorted(glob.glob(str(ROOT / "probes" / "*.py"))):
        src = pathlib.Path(f).read_text(encoding="utf-8")
        if "stamp_params" not in src:
            continue
        extra_model = ("glm-4." in src or "glm-5" in src or "qwen" in src.lower())
        if extra_model and "annotators_actually_used" not in src:
            bad.append(pathlib.Path(f).name)
    assert not bad, (
        f"★★ 这些探针用了 run_gates 面板之外的标注者却没自报: {bad}\n"
        '⇒ 章里会只写 run_gates 的五员。改法: RG.stamp_params(OUT, extra={"annotators_actually_used": [...]})')


def _reverse_checks():
    n, g = 0, globals()
    saved_rec, saved_reach = g["_recorded"], g["_names_reaching_prompt_format"]

    # ① 有环境变量进 prompt 却没记 ⇒ 红
    g["_recorded"] = lambda: {"CCE_CORPUS"}
    try:
        test_every_env_var_that_reaches_a_prompt_is_recorded()
        raise SystemExit("★ 反向验证失败: 漏记 BODY_CHARS/UNIT_LABEL 后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_recorded"] = saved_rec

    # ② 语料路径没记 ⇒ 红
    g["_recorded"] = lambda: saved_rec() - {"CCE_CORPUS"}
    try:
        test_corpus_path_is_recorded_even_though_ast_cannot_trace_it()
        raise SystemExit("★ 反向验证失败: 漏记 CCE_CORPUS 后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_recorded"] = saved_rec

    # ③ AST 真的看得见 —— 否则第①条是空转的假闸
    envmap, reaching = _module_level_env_vars(), _names_reaching_prompt_format()
    seen = {v for v in envmap if v in reaching}
    assert {"BODY_CHARS", "UNIT_LABEL"} <= seen, (
        f"★★ AST 追不到 BODY_CHARS/UNIT_LABEL(只看到 {seen}) —— "
        "那第①条断言永远为真, 是**零灵敏度的假闸**")
    n += 1
    return n


if __name__ == "__main__":
    test_every_env_var_that_reaches_a_prompt_is_recorded()
    test_corpus_path_is_recorded_even_though_ast_cannot_trace_it()
    test_both_artifacts_carry_the_params_not_just_one()
    test_the_two_historical_runs_are_flagged_as_unverifiable()
    test_probes_that_collect_readings_stamp_their_params()
    test_the_rule_really_excludes_only_zero_api_probes()
    test_stamp_helper_writes_the_same_params_not_a_second_copy()
    test_no_probe_hardcodes_a_truncation_length()
    test_probes_with_extra_annotators_declare_the_real_panel()
    n = _reverse_checks()
    envmap, reaching = _module_level_env_vars(), _names_reaching_prompt_format()
    print(f"test_cce_run_params_recorded: OK ("
          f"进 prompt 的环境变量 {sorted(v for v in envmap if v in reaching)} 全部已记录 | "
          f"CCE_CORPUS 硬性记录 | 三处写盘点都带(含扣发路径) | 两次历史运行已标注为**不可核实** | "
          f"采读数的探针全部盖章(零 API 探针**按判据**排除, 不靠豁免名单) | **零硬编截断** | 跨家族探针自报真实面板 | "
          f"{n} 条反向验证判红(含一条**灵敏度自证**))")
