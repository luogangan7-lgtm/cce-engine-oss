#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CE-21(b)(c) 的闸 —— **注入到达面**。

## 它守的是哪一条
N1「注入作用域 ≠ 观测面作用域」——第三轮、第四轮、第五轮各复发一次。形状固定:
  (b) 仓内**48 个** .py 在 import 期自己从磁盘再读一份 config
      (`json.load(open(...))` 与 `Path.read_text()`→`io.open` 两种写法都有)。
      只把内存字典注毒 ⇒ 它们**照样读磁盘原件** ⇒「注入后下游不变」被读成「没有消费者」。
  (c) 变异模块不进 `sys.modules` ⇒ 跨模块 `import X` 拿到**磁盘原件**, 消融臂静默绑回基线。
两者都是**假阴性, 且读起来像最强的证据** —— 所以必须有一条闸专门验「注入到底到没到」。

## 为什么反向占绝大多数
正向断言「注入到了」是**恒绿风险最高**的写法: 一个根本没接上的注入通道,
只要它返回的字典里有「reached: [...]」就照样全绿 —— 那比不修更糟。
⇒ 下面每一条反向都**先把通道打断一根**, 再断言「断了之后确实看得见」。看不见 = 这条闸是空的。

## 五条反向(全部实际见红, 见 __main__ 的 _RED 清单)
① 关掉配置注入 ⇒ 到达面从 2 个模块缩到 0
② 不注册 sys.modules ⇒ 跨模块消费者(cce_k1_status→cce_knot_classify)绑回基线
③ 装了钩子不还原 ⇒ 主进程从此读到毒(可观察); 正常退出后必须仍是磁盘原件
④ 注入路径写错 ⇒ 必须当场抛; 「路径对但文件不对」⇒ 必须落成 blind, 不许读成 NO_CONSUMER
⑤ 到达面查询**谎报** ⇒ 判红(N3: 弄坏它声称在核的对象, 看它翻不翻)

## 本闸不覆盖什么
不证明真实模型的语义准确率; 不证明**全部** 48 个自读模块都能被注入到
(本闸实测的是 cce_align_v2 与 accuracy/run_gates 两处, 其余未测 ⇒ 按 blind 处理);
不覆盖只在函数体内临时读配置、值不落到模块属性的消费者。
"""
import builtins
import contextlib
import hashlib
import io
import json
import os
import pathlib
import socket
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "probes"))
import ablation_harness_v3 as H          # noqa: E402

# R1 零 API: 进程级 socket 绊线, 收尾断言 tripped == []
_TRIPPED = []
_REAL_CONNECT = socket.socket.connect


def _guard(s, address, *a, **k):
    _TRIPPED.append(repr(address))
    raise AssertionError("★★★ 离线隔离被突破: %r" % (address,))


# ★★★ 2026-09-13 修**顺序依赖**(独立复核点出, 已复现):
#   原来这里是 `socket.socket.connect = _guard` —— **在 import 期就全局装上, 从不摘**。
#   后果有两层, 都不是本模块自己的问题却都记到本模块头上:
#     ① 同进程内**别的**测试(如 test_cce_audio_prosody 在 import 期下载 demucs 模型)
#        的连接会被记进 _TRIPPED, 于是收尾断言判红, 文案说的却是「本模块发了网络请求」;
#     ② 更糟: 它**打断了别人的连接** —— 那是把自己的纪律强加给整个进程。
#   ★ 仓的 CI 口径是**每文件独立进程**(`for t in tests/test_*.py; do python3 "$t"; done`),
#     所以这条在 CI 里不显形; 但在 pytest 单进程下会显形, 而**一道只在某种跑法下才对的闸不算对**。
#   ⇒ 改成只在**本模块自己的测试执行期间**装, 用完就摘。
@contextlib.contextmanager
def _offline():
    """作用域: 本进程内经 socket.socket.connect 新建的连接, **且只在本上下文内**。
    不覆盖: 已建立连接 · 不走 socket 的传输 · 子进程 · C 扩展自带网络栈。"""
    orig = socket.socket.connect
    socket.socket.connect = _guard
    try:
        yield
    finally:
        socket.socket.connect = orig


def _guarded(fn):
    """把每个 test_ 包进 _offline() —— pytest 与 __main__ 两种跑法都生效。"""
    import functools

    @functools.wraps(fn)
    def w(*a, **k):
        with _offline():
            return fn(*a, **k)
    return w
_REAL_OPEN = builtins.open

# R2 四个冻结件
# ★ 2026-09-13 k=5 边登记后更新两个值(cce_knot_classify f2cef2f9→0a740ba1 · manifest 9d9e1229→1f15a013)。
#   变更走的是仓自己的合法 Core 路径: core_files pin + refactor_log(from/to/reason/behavior_evidence)。
#   ★ 这不是把闸改宽 —— 冻结的**对象**没变, 只是它的当前值变了, 且变更本身另有 refactor_log 在管。
# ★ 2026-09-14 附件 A 升为合同后再更新 manifest 一格(93c6d769→4c3d6d4e)。
#   改动是**向 refactor_log 追加一条** CONTRACT_CHANGE_ANNEX_A_PROMOTED,
#   **core_files 六个 pin 与 parser_plane 四件逐字未动**(instrument_generation 仍 6) ——
#   现算已在 tests/data/ablation_verdicts_v3.json 的 ★frozen_files_更新记录 里逐条留档。
FROZEN_SHA8 = {
    "scripts/cce_knot_classify.py": "0a740ba16e80dc54",
    "config/knot_taxonomy.json": "56a1c1977bf8d18c",
    # ★ 2026-09-15 更新(第三次): 向 refactor_log 追加 ANNEX_A_MADE_OBSERVABLE。
    #   core_files 六个 pin 与 parser_plane 四件**逐一现算未变**, instrument_generation 仍 6。
    #   ★ 这格防的是「消融期间真仓被写穿」, **防未经记录的改动**, 不是禁止一切改动 ——
    #     所以更新它必须同时在 tests/data/ablation_verdicts_v3.json 的更新记录里留一条。
        # ★ 2026-09-15 第二次更新: 追加 R5_PREREG_REJECTED_AND_FOUR_REAL_DEFECTS_FIXED。
    #   core_files 六个 pin 逐一现算未变, instrument_generation 仍 6。
    # ★ 2026-09-15 第三次: 追加 R5V2_BLOCKED_ON_CORPUS_AND_REALITY_ANCHOR_ESTABLISHED。
    #   core_files 六个 pin 逐一现算未变, instrument_generation 仍 6。
    # ★ 2026-09-15 第四次: 追加 R5_RUN_68_CALLS_MAIN_CRITERION_NOT_MET(测量轮次)。
    # ★ 2026-09-15 第五次: 追加 SLOT_FILLABILITY_AUDIT_AND_A_CORRECTION。
    # ★ 2026-09-15 第六次: 追加 DECISION_DO_NOT_WIRE_CLAIM_FRAME_INTO_PRODUCTION。
    # ★ 2026-09-16: 追加 DEGRADED_CAPACITY_ON_REAL_CERTS_DEBT_PAID。
    # ★ 2026-09-17: 追加 CORPUS_BALANCE_SECOND_REFERENCE_REAL_REDDIT。
    # ★ 2026-09-17 第二次: 追加 THREE_DECISIONS_SETTLED_AND_ROLLED_UP。
    #   ★★★ 这次的「没动别处」不是口头保证: 把追加的那一条**摘掉后重算 sha = 75c6b968cd62f00d**,
    #     与上一钉**逐字节相同** ⇒ manifest 里除这一条之外一个字节都没动。
    #   ★ 不要拿 `git show HEAD:` 做对照 —— 本仓 HEAD 落后很多(refactor_log 10 条 vs 现 30 条),
    #     那样比会得出「core_files 变了」的**假结论**。回滚重算才是有效核法。
        # ★ 2026-09-17 第三次: 追加 REAL_CORPUS_PILOT_42_CALLS_TRANSFERS_NOT_HIGHER。
    #   摘掉那一条重算 sha = 60c4240352c8230f, 与上一钉逐字节相同 ⇒ 别处一个字节没动。
        # ★ 2026-09-17 第四次: 追加 REAL_CORPUS_PILOT_R2_...。摘掉那条重算 = b12aed730f97b9f8, 与上一钉逐字节相同。
        # ★ 2026-09-23: 追加 P2_FAIL_ANATOMY_THREE_FAMILIES。摘掉那条重算 = 8685b4c321fd588d, 与上一钉逐字节相同。
        # ★ 2026-09-23 第二次: 追加 CONTRACT_PAIRS_V4_...。摘掉那条重算 = 4237ab5d33b71818, 与上一钉逐字节相同。
        # ★ 2026-09-23 第三次: 追加 R6_...。摘掉那条重算 = 1aae065acd0461da, 与上一钉逐字节相同。
        # ★ 2026-09-23 第四次: 追加 R6_JEV_ARM_...。摘掉那条重算 = 564d17240095c7ef, 与上一钉逐字节相同。
        # ★ 2026-09-23 第五次: 追加 POSSESSION_ARTIFACT_JEV_INVENTORY_S0_SHADOW。摘掉那条重算 = b2c25b30865bfea3, 与上一钉逐字节相同。
        # ★ 2026-09-23 第六次: 追加 S0_RETEST_NO_GOLD_OWNER_RULING。摘掉那条重算 = 3b01a12c8711249a, 与上一钉逐字节相同。
        # ★ 2026-09-23 第七次: 追加 S0_JEV_WIRED_INTO_PRODUCTION_OWNER_NOD。摘掉那条重算 = f97efbdf66cc19a3, 与上一钉逐字节相同。
        # ★ 2026-09-23 第八次: 追加 REPLY_CHAIN_READER_BASELINE_OVERLAPS_S1。摘掉那条重算 = a6b894f1e0deda23, 与上一钉逐字节相同。
        # ★ 2026-09-23 第九次: 追加 SAMPLING_REDUCTION_PREREG_STEP1_H0_STOP。摘掉那条重算 = 54911191632e3128, 与上一钉逐字节相同。
        # ★ 2026-09-23 第十次: 追加 P2_BINDING_V2_WITNESS_INTERSECTION_DELEGATED_RULING。摘掉那条重算 = 913cae2d2009d813, 与上一钉逐字节相同。
        # ★ 2026-09-23 第十一次: 追加 SLOT_FILLING_SCORE_POLICY_V2_POSSESSION_EQUIVALENCE_PREREG。摘掉那条重算 = 901ad57baf5c15fe, 与上一钉逐字节相同。
        # ★ 2026-09-23 第十二次: 追加 FIVE_KINDS_ANNEX_D_CANDIDATE_AND_S2_LABEL_QUALIFICATION_WIRED。摘掉那条重算 = a4e3455aaf509c7a, 与上一钉逐字节相同。
        # ★ 2026-09-23 第十三次: 追加 ABLATION_V3_ROUND3_CHAIN_STAGES_S0_S2_S3_OVERLAP_XM_JUDGED(消融第三轮 32 条判决登记)。摘掉那条重算 = 44c06d8db21d43c0, 与上一钉逐字节相同。
    "config/cce_core_manifest.json": "0fdc0d07dc206b75",
    "accuracy/run_gates.py": "b758e6676a94acf3",
}


def _sha16(rel):
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()[:16]


_FROZEN_BEFORE = {p: _sha16(p) for p in FROZEN_SHA8}

TAXO_REL = "config/knot_taxonomy.json"
NEEDLE = "ZZ_CE21_INJECTED_SENTINEL_ZZ"
# CE-3/CE-16 点名的就是这个字段: cce_align_v2:19 DISCR → :87 DISSOLVE_PROMPT.format(discr=…)
FIELD = "hard_discriminant"
INST_INHERITED = "d4cce4c745f3f991"       # 未登记仪器, 只能经 SCOPE_WIDENINGS 继承
KC_ANCHOR = '"to_instrument": "d4cce4c745f3f991",'

_RED = []


def _must_raise(what, fn, *a, **k):
    try:
        fn(*a, **k)
    except Exception as e:
        _RED.append((what, "%s: %s" % (type(e).__name__, str(e)[:110])))
        return e
    raise AssertionError("★ 反向测试没见红: %s —— 通道被打断了却照样绿, 这条闸是空的" % what)


def _poisoned_taxo():
    t = json.loads((ROOT / TAXO_REL).read_text(encoding="utf-8"))
    for k in t["knots"]:
        k[FIELD] = NEEDLE
    return t


# ── 前置: 基线必须先是绿的(M3-⑤, 实测踩到两次) ───────────────────────────────
def test_baseline_is_green_before_any_reverse_arm():
    """反向臂的红只有在**基线绿**时才是证据。基线红 ⇒ 所有判红都是假证据。"""
    assert _FROZEN_BEFORE == FROZEN_SHA8, "★★★ R2: 冻结件在开跑前就已不是档案值 %r" % _FROZEN_BEFORE
    disk = (ROOT / TAXO_REL).read_text(encoding="utf-8")
    assert NEEDLE not in disk, "★ 哨兵串已在磁盘原件里 —— 换一个哨兵, 否则正向臂是重言"
    assert FIELD in disk, "★ %s 字段不在 taxonomy 里 —— 工况漂了, 本闸的锚点失效" % FIELD
    base = H.load("scripts/cce_align_v2.py")
    assert NEEDLE not in json.dumps(base.DISCR, ensure_ascii=False), "★ 未注入的基线里就有毒"
    # 默认参数(不传 config_overrides)必须一个钩子都不装
    assert base._ABL_CONFIG_INJECTION["opened"] == [], "★ 默认路径装了钩子 —— 现有行为被改了"
    assert builtins.open is _REAL_OPEN and io.open is _REAL_OPEN, "★ load() 后 open 没还原"


# ── 正向 1(b): 配置注入到达 import 期自读 config 的模块 ──────────────────────
def test_positive_config_injection_reaches_import_time_readers():
    """端到端: 注 config/knot_taxonomy.json 的 hard_discriminant ⇒ cce_align_v2 看得见。

    ★ 这正是 CE-21(b) 的实例: cce_align_v2:19 在 import 期 `json.load(open(TAXO))`
      自己再读一份, 内存字典注毒**到不了它**。
    """
    poison = _poisoned_taxo()
    inj = H.load("scripts/cce_align_v2.py", config_overrides={TAXO_REL: poison})
    rg = H.load("accuracy/run_gates.py", config_overrides={TAXO_REL: poison})

    r = H.injection_reach("DISCR", {"cce_align_v2": inj}, NEEDLE)
    assert r["reached"] == ["cce_align_v2"] and r["blind"] == [], "★ 注入没到达 cce_align_v2: %r" % r
    r2 = H.injection_reach("TAXO", {"run_gates": rg}, NEEDLE)
    assert r2["reached"] == ["run_gates"], "★ 注入没到达 accuracy/run_gates: %r" % r2

    # 到达要有**出处**: 拦截日志必须指到真正发起读的那一行, 不是笼统一句「注入了」
    opened = inj._ABL_CONFIG_INJECTION["opened"]
    assert any(o["path"] == TAXO_REL and o["file"].endswith("scripts/cce_align_v2.py")
               and o["line"] == 19 for o in opened), "★ 拦截日志指不到 cce_align_v2:19: %r" % opened

    # 下游真的用上了: :87 DISSOLVE_PROMPT.format(discr=DISCR[...]) —— 桩掉 _call, 零 API
    seen = []
    inj._call = lambda p, **kw: (seen.append(p), "")[1]
    inj.dissolve_hit(sorted(inj.DISCR)[0], "离线探针合成输入", votes=1)
    assert seen and NEEDLE in seen[0], "★ 毒进了 DISCR 却没进生产 prompt —— 观测面还是断的"

    # R2: 磁盘原件一字未改(注入只在内存)
    assert NEEDLE not in (ROOT / TAXO_REL).read_text(encoding="utf-8"), "★★★ 注入把毒写进了仓内文件"
    assert _sha16(TAXO_REL) == FROZEN_SHA8[TAXO_REL], "★★★ R2: 冻结件 sha 在注入后变了"


# ── 正向 2(c): 跨模块 import 拿到的是消融版 ──────────────────────────────────
def _k1_chain():
    """真实链路: cce_k1_status:84 `import cce_knot_classify` → SCOPE_WIDENINGS → 继承判定路径。

    ★ 必须让磁盘原件**可导入**, 否则 arm A 的 None 是 ImportError 造成的假红。
    """
    if str(ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(ROOT / "scripts"))
    kc = H.load("scripts/cce_knot_classify.py",
                H.replace_once(KC_ANCHOR, '"to_instrument": "ZZ_ABLATED_INSTRUMENT_ZZ",'))
    k1 = H.load("scripts/cce_k1_status.py")
    return kc, k1


def test_positive_sys_modules_registration_reaches_cross_module_consumer():
    kc, k1 = _k1_chain()
    assert kc._ABL_MUTATED, "★ 空臂: cce_knot_classify 源码没变"
    with H.as_import({"cce_knot_classify": kc}):
        assert sys.modules["cce_knot_classify"] is kc, "★ as_import 没把变异模块绑到导入名下"
        ablated = k1.verdict_path_for(INST_INHERITED)
    assert ablated is None, (
        "★ 消融没到达: 砍掉 SCOPE_WIDENINGS 的 to_instrument 之后, "
        "cce_k1_status 竟然还继承得到判定 —— 跨模块 import 还是绑在磁盘原件上")
    # 单模块也能注册(名字取源文件 stem)
    with H.as_import(kc):
        assert sys.modules["cce_knot_classify"] is kc, "★ 单模块形式的 as_import 没按 stem 绑名"


# ── 反向 ①: 关掉配置注入 ⇒ 到达面缩小 ───────────────────────────────────────
def test_reverse_disabling_config_injection_shrinks_the_reach_surface():
    poison = _poisoned_taxo()
    mods_on = {"cce_align_v2": H.load("scripts/cce_align_v2.py", config_overrides={TAXO_REL: poison}),
               "run_gates": H.load("accuracy/run_gates.py", config_overrides={TAXO_REL: poison})}
    # ← 上一轮的写法: 只注内存字典, 不 patch 配置读取
    mods_off = {"cce_align_v2": H.load("scripts/cce_align_v2.py"),
                "run_gates": H.load("accuracy/run_gates.py")}
    on = (H.injection_reach("DISCR", {"cce_align_v2": mods_on["cce_align_v2"]}, NEEDLE)["reached"]
          + H.injection_reach("TAXO", {"run_gates": mods_on["run_gates"]}, NEEDLE)["reached"])
    off = (H.injection_reach("DISCR", {"cce_align_v2": mods_off["cce_align_v2"]}, NEEDLE)["reached"]
           + H.injection_reach("TAXO", {"run_gates": mods_off["run_gates"]}, NEEDLE)["reached"])
    assert len(on) == 2, "★ 开着注入也只到达 %r —— 通道没接上" % on
    assert off == [], "★ 反向没见红: 关掉配置注入后它们竟然也看得见毒, 这条闸验不到 CE-21(b)"
    _RED.append(("关掉配置注入", "到达面 %d 个模块 → 0 个; 而 off 臂的「无差异」正是假阴性的来源" % len(on)))
    # ★ 关键: off 臂必须被标成 blind, 不是 NO_CONSUMER
    blind = H.injection_reach("DISCR", {"cce_align_v2": mods_off["cce_align_v2"]}, NEEDLE)
    assert blind["blind"] == ["cce_align_v2"], "★ off 臂没被标成 blind: %r" % blind
    assert "blind" in "".join(blind.keys()) or any("blind" in k for k in blind), "★ 没有 blind 口径"
    assert "INCONCLUSIVE" in blind["★blind 怎么读"], "★ blind 的读法里没写「不许支撑无差异结论」"


# ── 反向 ②: 不注册 sys.modules ⇒ 跨模块消费者绑回基线 ───────────────────────
def test_reverse_without_sys_modules_the_consumer_binds_back_to_baseline():
    kc, k1 = _k1_chain()
    bound_back = k1.verdict_path_for(INST_INHERITED)          # 不注册
    with H.as_import({"cce_knot_classify": kc}):
        reached = k1.verdict_path_for(INST_INHERITED)
    assert reached is None, "★ 注册之后消融仍没到达 —— 通道没接上"
    assert bound_back is not None, (
        "★ 反向没见红: 不注册 sys.modules 时消融竟然也到达了 —— 这条闸验不到 CE-21(c)")
    assert os.path.basename(bound_back) == "k1_reliability_verdict.json", \
        "★ 不注册时拿到的不是磁盘原件那条判定路径: %r" % bound_back
    _RED.append(("不注册 sys.modules",
                 "cce_k1_status.verdict_path_for(%s): 不注册 → %s(磁盘原件) · 注册 → None(消融真的到了)"
                 % (INST_INHERITED[:8], os.path.basename(bound_back))))


# ── 反向 ③: 还原后主进程仍拿到磁盘原件 ──────────────────────────────────────
def test_reverse_incomplete_restore_leaks_into_the_main_process():
    poison = _poisoned_taxo()
    # 正常路径: 进去是毒, 出来是磁盘原件, 两个 open 都还原
    with H.config_injection({TAXO_REL: poison}):
        assert NEEDLE in (ROOT / TAXO_REL).read_text(encoding="utf-8"), "★ 注入期内没读到毒"
        assert NEEDLE in json.load(open(ROOT / TAXO_REL, encoding="utf-8"))["knots"][0][FIELD], \
            "★ json.load(open(...)) 这条路径没被拦到 —— 48 个自读模块里一半是这么写的"
    assert NEEDLE not in (ROOT / TAXO_REL).read_text(encoding="utf-8"), "★ 退出后仍读到毒"
    assert builtins.open is _REAL_OPEN and io.open is _REAL_OPEN, "★ open 没逐一还原"

    # 弄坏的对照: 装了钩子**不还原** ⇒ 污染可观察(这就是红)
    ctx = H.config_injection({TAXO_REL: poison})
    ctx.__enter__()
    leaked = NEEDLE in (ROOT / TAXO_REL).read_text(encoding="utf-8")
    ctx.__exit__(None, None, None)
    assert leaked, "★ 反向没见红: 不还原竟然也读不到毒 —— 这条闸验不到污染"
    assert NEEDLE not in (ROOT / TAXO_REL).read_text(encoding="utf-8"), "★ 手工 __exit__ 后仍读到毒"
    _RED.append(("还原", "未还原时主进程 Path.read_text 直接读到毒; 正常退出后 open/io.open 逐一复位"))

    # sys.modules 同理: 退出后既不留新键, 也不覆盖原有对象
    kc, _ = _k1_chain()
    before = sys.modules.get("cce_knot_classify")
    with H.as_import({"cce_knot_classify": kc, "ZZ_never_seen_before_ZZ": kc}):
        pass
    assert sys.modules.get("cce_knot_classify") is before, "★ as_import 覆盖了原有对象没还原"
    assert "ZZ_never_seen_before_ZZ" not in sys.modules, "★ as_import 留下了新键, 污染后续 import"


# ── 反向 ④: 注入路径写错 ⇒ 报错, 不是静默没注入 ──────────────────────────────
def test_reverse_a_wrong_injection_path_must_raise_not_silently_miss():
    _must_raise("注入路径写错必须当场抛",
                H.load, "scripts/cce_align_v2.py",
                config_overrides={"config/knot_taxonomy_TYPO.json": {}})
    _must_raise("绝对路径写错同样必须抛",
                H.config_injection({"/nope/does/not/exist.json": "{}"}).__enter__)
    # 「路径存在但注错了文件」不会抛(它是合法调用), 但**必须**落成 blind —— 不许被读成 NO_CONSUMER
    wrong = H.load("scripts/cce_align_v2.py",
                   config_overrides={"config/need_taxonomy.json": {"x": NEEDLE}})
    r = H.injection_reach("DISCR", {"cce_align_v2": wrong}, NEEDLE)
    assert r["blind"] == ["cce_align_v2"], "★ 注错文件却报成到达 —— 到达面查询是装饰"
    _RED.append(("注入路径写错", "不存在的路径 → FileNotFoundError; 存在但注错文件 → blind(不是 NO_CONSUMER)"))


# ── 反向 ⑤: 到达面查询谎报 ⇒ 判红(N3) ───────────────────────────────────────
def test_reverse_the_reach_query_cannot_be_lied_to():
    """N3: 验「它返回 True」≠ 验「它真的在证」。**弄坏它声称在核的对象**, 看它翻不翻。"""
    base = H.load("scripts/cce_align_v2.py")                  # 没注入
    claim = {"cce_align_v2": base}

    # 谎报形态 ①: 伪造拦截日志, 声称读过那个路径
    base._ABL_CONFIG_INJECTION["opened"].append(
        {"path": TAXO_REL, "mode": "r", "module": "cce_align_v2",
         "file": str(ROOT / "scripts/cce_align_v2.py"), "line": 19})
    r = H.injection_reach("DISCR", claim, NEEDLE)
    assert r["reached"] == [] and r["blind"] == ["cce_align_v2"], (
        "★ 反向没见红: 伪造一条拦截日志就把「没到」说成了「到了」—— 到达面查询在读自报字段")
    _RED.append(("谎报·伪造拦截日志", "opened 里加一条假记录, injection_reach 仍判 BLIND(它只读符号本身)"))

    # 谎报形态 ②: 符号根本不存在 ⇒ NO_SUCH_SYMBOL, 归 blind, 不许当成「没变化 ⇒ 没消费者」
    r2 = H.injection_reach("ZZ_NO_SUCH_SYMBOL_ZZ", claim, NEEDLE)
    assert r2["per_module"]["cce_align_v2"]["status"] == "NO_SUCH_SYMBOL", \
        "★ 符号不存在时没报 NO_SUCH_SYMBOL: %r" % r2
    assert r2["blind"] == ["cce_align_v2"] and r2["reached"] == [], \
        "★ 符号不存在却没归 blind: %r" % r2
    _RED.append(("谎报·符号不存在", "NO_SUCH_SYMBOL 归 blind, 不会被读成「到达了但没差异」"))

    # ★ N3 正手: 弄坏它声称在核的对象(模块上那个符号本身) ⇒ 判决必须当场翻
    base.DISCR = {"belong": NEEDLE}
    r3 = H.injection_reach("DISCR", claim, NEEDLE)
    assert r3["reached"] == ["cce_align_v2"], (
        "★ 把符号本身换成毒, 到达面查询竟然还判 BLIND —— 它没在读它声称在核的对象")
    _RED.append(("N3 正手", "直接把 mod.DISCR 换成毒 ⇒ BLIND→REACHED 当场翻 ⇒ 判据确实读的是符号本身"))


# ── 空操作对照: 不产生伪阳性 ────────────────────────────────────────────────
def test_noop_control_produces_no_false_positive():
    """注入一份**与磁盘逐字节相同**的内容 + 注册一个未变异的模块 ⇒ 任何差异都是伪红。"""
    same = (ROOT / TAXO_REL).read_text(encoding="utf-8")
    a = H.load("scripts/cce_align_v2.py")
    b = H.load("scripts/cce_align_v2.py", config_overrides={TAXO_REL: same})
    assert json.dumps(a.DISCR, sort_keys=True) == json.dumps(b.DISCR, sort_keys=True), \
        "★ 伪阳性: 注入同样的内容竟然产生了差异"
    assert b._ABL_CONFIG_INJECTION["opened"], "★ 空操作臂连钩子都没触发 —— 它验不到伪阳性"
    assert H.injection_reach("DISCR", {"a": a, "b": b}, NEEDLE)["reached"] == [], "★ 空操作臂见到了毒"

    kc_noop = H.load("scripts/cce_knot_classify.py")           # 未变异
    _, k1 = _k1_chain()
    with H.as_import({"cce_knot_classify": kc_noop}):
        noop = k1.verdict_path_for(INST_INHERITED)
    assert noop is not None and os.path.basename(noop) == "k1_reliability_verdict.json", \
        "★ 伪阳性: 注册一个未变异的模块就让判定扣发了"


# ── 收尾: R1 / R2 ───────────────────────────────────────────────────────────
def test_offline_and_frozen_files_untouched():
    assert _TRIPPED == [], ("★★★ R1: 绊线在**本模块自己的测试期间**被触发 %r" % _TRIPPED)
    after = {p: _sha16(p) for p in FROZEN_SHA8}
    assert after == FROZEN_SHA8, "★★★ R2: 冻结件被改动 %r" % after
    # ★ 不再断言「绊线仍挂着」—— 它现在是**按测试装卸**的, 挂着才不正常。


# ★ 统一加壳: 放在所有 test_ 定义之后, pytest 收集到的就是加壳版
for _n, _f in list(globals().items()):
    if _n.startswith("test_") and callable(_f) and not getattr(_f, "__wrapped__", None):
        globals()[_n] = _guarded(_f)

if __name__ == "__main__":
    for name, fn in sorted((n, f) for n, f in globals().items() if n.startswith("test_")):
        fn()
    print("test_cce_ablation_harness_injection_reach: OK")
    print("  ★ 实际见红 %d 处:" % len(_RED))
    for what, how in _RED:
        print("    · %s → %s" % (what, how))
