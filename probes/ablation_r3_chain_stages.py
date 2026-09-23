#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""消融审计 v3 第三轮(2026-09-23) —— 生产主链里从未消融的编排段, **零 API**。

被测面(全部在 scripts/cce_full_run.py, 外加 scripts/exp_crossmodel_desire.py 的生产消费面):
  S0  s0_context: Jev 优先/回退 MiniMax/read_backend/已声明>读出>未知/非法值归未知/miss 防呆/fill==0/【情境】追加/body[:2000]/可读面过滤/无需读出时零调用
  S2  s2_knots: CCE_TAXO_VERSION 钉与守卫 · top1_stable is True 才发 playbook_primary · 两种扣发理由 · [:120] · playbook_unscored_guidance · label_qualification · evidence_quote 逐字核
  S3  s3_emotion_policy: distribution_only · top4 · EMOTIONS 标签绑定
  OV  reader_baseline ∥ s1_readout 重叠编排: context 快照 · 兜底收回 · 失败归名 · CCE_SERIAL_STAGES · DEFER_UNTIL 目标 · 收回后的 manifest 同形 · ctx["reader_cce"]
  XM  exp_crossmodel_desire 在生产链上的消费面: s0 MiniMax 回退臂 call_model(2026-09-23 新增消费者) · 未用 import · sys.path.insert · RESULTS

方法: probes/ablation_harness_v3.py 的量具(M1–M8)。判官先过 positive_control(); L1 数值差分 + L2 判决差分;
      **L3 哈希/ID 显式剔除**; 凡判无差异必跑荒谬值注入臂; L4 在 rsync 冻结快照上真写磁盘 + 递归清 __pycache__ + python3 -B
      (绝不 symlink), 并以空操作臂减去伪红。
零 API: 全程 socket 绊线; s0 的 Jev / MiniMax 调用全部桩掉(桩只回放存量 s0_context.json 的读出面, **不落语料原文**, 产物只有统计量与指针)。
用法: python3 probes/ablation_r3_chain_stages.py            # L1/L2/注入, 写 scratch/l12_results.json(收口后进 tests/data/ablation_v3/<cluster>.json)
      python3 probes/ablation_r3_chain_stages.py --l4      # L4 农场(慢): 有 __main__ 的测试文件脚本跑, 无 __main__ 的走 pytest, 写 scratch/farm/l4_results.json
      python3 probes/ablation_r3_chain_stages.py --l4-pytest-only   # 只补跑无 __main__ 的 106 个 pytest 文件
"""
import argparse, collections, contextlib, copy, datetime, glob, hashlib, importlib.util, io, json, os, pathlib, re, shutil, subprocess, sys, tempfile, time, types

ROOT = pathlib.Path(__file__).resolve().parent.parent
TARGET = "scripts/cce_full_run.py"
XM = "scripts/exp_crossmodel_desire.py"
WATCH = ("scripts/cce_full_run.py", "scripts/cce_s0_jev.py", "scripts/exp_crossmodel_desire.py",
         "config/context_taxonomy.json", "scripts/cce_label_qualification.py", "scripts/cce_k1_status.py")
OUT_DIR = ROOT / "tests/data/ablation_v3"
SCRATCH = pathlib.Path(os.environ.get("ABL_R3_SCRATCH") or tempfile.gettempdir()) / "abl_r3_chain_stages"

_spec = importlib.util.spec_from_file_location("ablation_harness_v3", ROOT / "probes/ablation_harness_v3.py")
H = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(H)

# ★ 绝不 export 真 key: 进程内一律假 key(只为让 import 期的 os.environ[...] 不炸), 桩永不开 socket。
FAKE_KEY = "OFFLINE-FAKE-KEY-NOT-A-SECRET"
os.environ["MINIMAX_API_KEY"] = FAKE_KEY
os.environ["TYPESAFE_API_KEY"] = ""          # 默认 NOKEY 场景; KEY 场景临时置假值
os.environ.setdefault("CCE_SKIP_GK2", "1")
sys.path.insert(0, str(ROOT / "scripts"))


def _sha(o):
    return hashlib.sha256(json.dumps(o, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _strip_sec(m):
    return {k: ({kk: vv for kk, vv in v.items() if kk != "sec"} if isinstance(v, dict) else v) for k, v in m.items()}


# ═══════════════════════════ 变异臂(源码级, 每臂恰好命中一次) ═════════════════════
ARMS = {
    # ── S0 ──
    "S0_A1_jev_precedence_off": (TARGET, 'if jr is not None:\n            read, backend = jr, "jev"', 'if False:\n            read, backend = jr, "jev"'),
    "S0_A2_fallback_mislabeled_as_jev": (TARGET, 'backend = "minimax_fallback(%s)" % jerr', 'backend = "jev"'),
    "S0_A3_read_overrides_declared": (TARGET,
        '        if k in decl:\n            merged[k], src[k] = decl[k], "已声明"\n        elif read.get(k) not in CTX_UNKNOWN and read.get(k) in f["values"]:\n            merged[k], src[k] = read[k], "读出"\n',
        '        if read.get(k) not in CTX_UNKNOWN and read.get(k) in f["values"]:\n            merged[k], src[k] = read[k], "读出"\n        elif k in decl:\n            merged[k], src[k] = decl[k], "已声明"\n'),
    "S0_A4_illegal_value_not_mapped_to_unknown": (TARGET, 'elif read.get(k) not in CTX_UNKNOWN and read.get(k) in f["values"]:', 'elif read.get(k) not in CTX_UNKNOWN:'),
    "S0_A5_miss_guard_removed": (TARGET, '    if miss:\n        raise RuntimeError(f"情境声明未生效: {miss} —— 传参链路断了, 拒绝用读出值冒充声明值")', '    if miss:\n        pass'),
    "S0_A6_fill_zero_guard_removed": (TARGET, '    if fill == 0:\n        raise RuntimeError("情境九面全未知且无声明 —— 引擎拒答: 缺必要输入时不硬给结论")', '    if fill == 0:\n        pass'),
    "S0_A7_context_append_removed": (TARGET, '    ctx["context"] = ctx["context"] + " 【情境】" + json.dumps(\n        {k: v for k, v in merged.items() if v != "未知"}, ensure_ascii=False)', '    ctx["context"] = ctx["context"]'),
    "S0_A8_body_not_truncated": (TARGET, 'body = open(ctx["text_file"], encoding="utf-8").read()[:2000]', 'body = open(ctx["text_file"], encoding="utf-8").read()'),
    "S0_A9_readable_filter_removed": (TARGET, 'if f["key"] not in decl and f.get("readable_from_text") in (True, "partial")]', 'if f["key"] not in decl]'),
    "S0_A2i_read_backend_absurd_999": (TARGET, 'backend = "minimax_fallback(%s)" % jerr', 'backend = 999'),
    "S0_A12_backend_called_even_if_nothing_to_read": (TARGET, '    if need_read:\n        body = open', '    if True:\n        body = open'),
    # ── S2 ──
    "S2_B1_taxo_pin_literal_1_3_0": (TARGET, 'PINNED_TAXO = os.environ.get("CCE_TAXO_VERSION", "1.3.1")', 'PINNED_TAXO = os.environ.get("CCE_TAXO_VERSION", "1.3.0")'),
    "S2_B2_taxo_guard_removed": (TARGET, '        raise RuntimeError(f"taxonomy版本漂移: {taxo.get(\'version\')} != {PINNED_TAXO}")', '        pass'),
    "S2_B3_top1_is_not_False": (TARGET,
        '"playbook_primary": (knots[0].get("playbook", "")[:120]\n                                 if knots and top1_stable is True else None),',
        '"playbook_primary": (knots[0].get("playbook", "")[:120]\n                                 if knots and top1_stable is not False else None),'),
    "S2_B4_withheld_reason_collapsed": (TARGET,
        '                (f"top1 一致性**不可判**(可投票 draw < 2, 一个观测点上观察不到一致性): "\n                 f"{samp.get(\'top1_draws\')}" if top1_stable is None else\n                 f"top1 不稳: {samp.get(\'top1_draws\')}")),',
        '                f"top1 不稳: {samp.get(\'top1_draws\')}"),'),
    "S2_B5_playbook_cut_10": (TARGET, '"playbook_primary": (knots[0].get("playbook", "")[:120]', '"playbook_primary": (knots[0].get("playbook", "")[:10]'),
    "S2_B6_unscored_guidance_removed": (TARGET, '"playbook_unscored_guidance": (_unscored_guidance(taxo, knots[0]["key"])\n                                           if knots and top1_stable is True else None),', '"playbook_unscored_guidance": None,'),
    "S2_B7_label_qualification_removed": (TARGET, '"label_qualification": _s2_label_qualification(ctx, knots)}', '"label_qualification": None}'),
    "S2_B8_verbatim_check_removed": (TARGET, '"evidence_quote_verbatim": bool(quote) and quote in text,', '"evidence_quote_verbatim": bool(quote),'),
    # ── S3 ──
    "S3_C1_top3": (TARGET, 'dist = sorted(zip(EMOTIONS, vec), key=lambda x: -x[1])[:4]', 'dist = sorted(zip(EMOTIONS, vec), key=lambda x: -x[1])[:3]'),
    "S3_C2_labels_reversed": (TARGET, 'dist = sorted(zip(EMOTIONS, vec), key=lambda x: -x[1])[:4]', 'dist = sorted(zip(list(reversed(EMOTIONS)), vec), key=lambda x: -x[1])[:4]'),
    # ── OV ──
    "OV_O1_lazy_context_no_snapshot": (TARGET, 'fut = _DEFER_EX.submit(run_knot_classify, rf, context, ctx["k"], out)', 'fut = _DEFER_EX.submit(lambda: run_knot_classify(rf, ctx["context"], ctx["k"], out))'),
    "OV_O2_fallback_join_removed": (TARGET,
        '    for dn in list(ctx.get("_deferred", {})):\n        try:\n            _join_deferred(ctx, dn)\n        except Exception:\n            failed = dn\n',
        '    pass\n'),
    "OV_O3_failure_attributed_to_trigger_stage": (TARGET, '                    _join_deferred(ctx, dn)\n                except Exception:\n                    failed = dn\n', '                    _join_deferred(ctx, dn)\n                except Exception:\n                    failed = fn.stage_name\n'),
    "OV_O4_overlap_off_by_default": (TARGET, 'ctx["_overlap"] = os.environ.get("CCE_SERIAL_STAGES") != "1"', 'ctx["_overlap"] = os.environ.get("CCE_SERIAL_STAGES") == "1"'),
    "OV_O5_defer_target_s2": (TARGET, 'DEFER_UNTIL = {"reader_baseline": "s1_readout"}', 'DEFER_UNTIL = {"reader_baseline": "s2_knots"}'),
    "OV_O5i_defer_target_absurd": (TARGET, 'DEFER_UNTIL = {"reader_baseline": "s1_readout"}', 'DEFER_UNTIL = {"reader_baseline": "NO_SUCH_STAGE"}'),
    "OV_O6_join_drops_reader_out": (TARGET, '"overlapped_with": DEFER_UNTIL[name], **_reader_out(d, body)}', '"overlapped_with": DEFER_UNTIL[name]}'),
    "OV_O6i_reader_manifest_absurd_999": (TARGET, '"overlapped_with": DEFER_UNTIL[name], **_reader_out(d, body)}', '"overlapped_with": DEFER_UNTIL[name], "tops": 999, "within_js": 999, "knots": 999, "reader_chars": 999, "file": 999}'),
    "OV_O7_reader_cce_absurd": (TARGET, '    ctx["reader_cce"] = d\n    MANIFEST[name] = {"status": "OK"', '    ctx["reader_cce"] = 999\n    MANIFEST[name] = {"status": "OK"'),
    # ── XM ──
    "XM_E2_unused_import_re_removed": (XM, "import os, sys, json, time, math, re\n", "import os, sys, json, time, math\n"),
    "XM_E3_syspath_insert_removed": (XM, "sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n", "pass\n"),
    "XM_E4_results_dir_renamed": (XM, 'RESULTS = os.path.join(ROOT, "results")\n', 'RESULTS = os.path.join(ROOT, "results_abl_r3_tmp")\n'),
    # ── 空操作对照(L4 用) ──
    "NOOP_full_run": (TARGET, "MANIFEST = {}\n", "MANIFEST = {}  # noop\n"),
    "NOOP_xm": (XM, 'RESULTS = os.path.join(ROOT, "results")\n', 'RESULTS = os.path.join(ROOT, "results")  # noop\n'),
}


def mutator(name):
    f, old, new = ARMS[name]
    return f, H.replace_once(old, new)


# ═══════════════════════════ 语料(只统计量与指针, 不落原文) ═══════════════════
def _items_for(run):
    out = {}
    for f in glob.glob(str(ROOT / "archive" / run / "*items.json")):
        try:
            for i, it in enumerate(json.loads(pathlib.Path(f).read_text(encoding="utf-8"))):
                out[i] = it
        except Exception:
            pass
    return out


def s0_corpus():
    """50 份存量 s0_context.json → (指针, decl, 读出面, body 长度/哈希)。body 用同 run items.json 的原文(15 份), 否则用装置固定探针文本。"""
    recs = []
    for f in sorted(glob.glob(str(ROOT / "archive/*/*s0_context.json"))):
        d = json.loads(pathlib.Path(f).read_text(encoding="utf-8"))
        run = f.split("/")[-2]; base = os.path.basename(f)
        m = re.search(r"item-(\d+)-", base)
        it = _items_for(run).get(int(m.group(1))) if m else None
        body = (it or {}).get("text") or H._PROBE_TEXT
        decl = {k: v for k, v in d["facets"].items() if d["source"].get(k) == "已声明"}
        read = {k: v for k, v in d["facets"].items() if d["source"].get(k) == "读出"}
        recs.append({"ptr": os.path.relpath(f, ROOT), "decl": decl, "read": read, "body": body,
                     "body_real": it is not None, "body_len": len(body), "body_sha16": hashlib.sha256(body.encode()).hexdigest()[:16],
                     "archived_fill": d["fill_rate"]})
    return recs


def text_corpus():
    """52 条 items.json 原文(只量后端收到的字节数面) —— 不落原文。"""
    out = []
    for f in sorted(glob.glob(str(ROOT / "archive/*/*items.json"))):
        for i, it in enumerate(json.loads(pathlib.Path(f).read_text(encoding="utf-8"))):
            t = it.get("text") or ""
            if t:
                out.append({"ptr": "%s[%d]" % (os.path.relpath(f, ROOT), i), "body": t, "len": len(t),
                            "decl": it.get("context_decl")})
    return out


def s2_corpus():
    """79 份带 stage2.knots 的 s1_readout / reader_baseline; 配同 run 的原文(逐字核用)与同 item 的 manifest(出口闸的 s1 段)。"""
    recs = []
    for f in sorted(glob.glob(str(ROOT / "archive/*/*s1_readout.json")) + glob.glob(str(ROOT / "archive/*/*reader_baseline.json"))):
        d = json.loads(pathlib.Path(f).read_text(encoding="utf-8"))
        if not (d.get("stage2") or {}).get("knots"):
            continue
        run = f.split("/")[-2]; base = os.path.basename(f)
        m = re.search(r"item-(\d+)-", base); it = _items_for(run).get(int(m.group(1))) if m else None
        text = None
        if it:
            text = it.get("reader_text") if base.endswith("reader_baseline.json") else it.get("text")
        mani = None
        mp = f.rsplit("__", 1)[0] + "__manifest.json"
        if os.path.exists(mp):
            try:
                mani = json.loads(pathlib.Path(mp).read_text(encoding="utf-8"))
            except Exception:
                mani = None
        recs.append({"ptr": os.path.relpath(f, ROOT), "d": d, "text": text, "text_real": bool(text),
                     "s1m": ((mani or {}).get("stages") or {}).get("s1_readout"),
                     "s3_archived": ((mani or {}).get("stages") or {}).get("s3_emotion_policy")})
    return recs


# ═══════════════════════════ 桩(零 socket) ═══════════════════════════════════
class Backends:
    """Jev / MiniMax 两个后端的记录型桩。answers 由调用方按 case 设定(回放存量读出面)。"""

    def __init__(self):
        self.answers = {}; self.probs = {}; self.calls = []; self.illegal = None; self.over_answer = False; self.poison_minimax = False

    def jev_post(self, body, key):
        asked = list(body["questions"])
        self.calls.append({"backend": "jev", "n_chars": len(body["state"]), "asked": asked})
        ans = {}
        for k in asked:
            v = self.answers.get(k, "未知")
            if self.illegal and k == self.illegal[0]:
                v = self.illegal[1]
            ans[k] = {"choice": v, "probabilities": self.probs.get(k, {})}
        if self.over_answer:
            for k, v in self.answers.items():
                ans.setdefault(k, {"choice": v, "probabilities": {}})
        return {"answers": ans}, None

    def minimax_call(self, mkey, prompt, temperature=0.0, timeout=300, max_retries=3):
        if self.poison_minimax:
            raise RuntimeError("POISONED_CALL_MODEL")
        asked = [ln.strip().split(":")[0] for ln in prompt.split("\n") if ln.startswith("  ") and ":" in ln]
        body = prompt.split("【内容】\n", 1)[1].rsplit("\n\n只输出JSON", 1)[0]
        self.calls.append({"backend": "minimax", "n_chars": len(body), "asked": asked, "model": mkey, "temperature": temperature})
        out = {k: self.answers.get(k, "未知") for k in asked}
        if self.illegal and self.illegal[0] in out:
            out[self.illegal[0]] = self.illegal[1]
        if self.over_answer:
            out.update(self.answers)
        return json.dumps(out, ensure_ascii=False), {"stub": True}


@contextlib.contextmanager
def patched_backends(bk):
    import cce_s0_jev, exp_crossmodel_desire as xm
    o1, o2 = cce_s0_jev.s0_jev_read, xm.call_model
    cce_s0_jev.s0_jev_read = lambda body, facets: o1(body, facets, post=bk.jev_post)
    xm.call_model = bk.minimax_call
    try:
        yield
    finally:
        cce_s0_jev.s0_jev_read, xm.call_model = o1, o2


@contextlib.contextmanager
def env(**kv):
    saved = {k: os.environ.get(k) for k in kv}
    for k, v in kv.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ═══════════════════════════ S0 观测 ═════════════════════════════════════════
def observe_s0(fr, recs, keyed, bk_tweak=None, decl_tweak=None):
    out = []
    with env(TYPESAFE_API_KEY=(FAKE_KEY if keyed else "")):
        for r in recs:
            bk = Backends(); bk.answers = dict(r["read"])
            if bk_tweak:
                bk_tweak(bk, r)
            tmp = tempfile.mkdtemp(dir=SCRATCH)
            tf = os.path.join(tmp, "in.txt"); pathlib.Path(tf).write_text(r["body"], encoding="utf-8")
            decl = dict(r["decl"])
            if decl_tweak:
                decl = decl_tweak(decl, r)
            ctx = {"text_file": tf, "context": "C0", "outdir": tmp, "context_decl": json.dumps(decl, ensure_ascii=False) if decl is not None else None}
            fr.MANIFEST.clear(); err = None
            with patched_backends(bk):
                try:
                    fr.s0(ctx)
                except Exception as e:
                    err = "%s: %s" % (type(e).__name__, str(e)[:90])
            layer = ctx.get("ctx_layer"); stage = _strip_sec(fr.MANIFEST).get("s0_context")
            written = None
            p = os.path.join(tmp, "s0_context.json")
            if os.path.exists(p):
                written = _sha(json.loads(pathlib.Path(p).read_text(encoding="utf-8")))
            out.append({"ptr": r["ptr"],
                        "L1_layer": layer, "L1_context_sha": _sha(ctx["context"]), "L1_context_has_scene": "【情境】" in ctx["context"],
                        "L1_backend_calls": bk.calls, "L1_written_sha": written, "L1_stage": stage,
                        "L2_raised": err, "L2_read_backend": (layer or {}).get("read_backend"), "L2_source": (layer or {}).get("source"),
                        "L2_fill": (layer or {}).get("fill_rate"), "L2_hint": (stage or {}).get("置信提示")})
            shutil.rmtree(tmp, ignore_errors=True)
    return out


def s0_split(obs):
    L1 = [{k: v for k, v in o.items() if k.startswith("L1") or k == "ptr"} for o in obs]
    L2 = [{k: v for k, v in o.items() if k.startswith("L2") or k == "ptr"} for o in obs]
    return L1, L2


def diff_count(a, b, prefix):
    n = 0; changed = []
    for x, y in zip(a, b):
        xa = {k: v for k, v in x.items() if k.startswith(prefix)}; ya = {k: v for k, v in y.items() if k.startswith(prefix)}
        if _sha(xa) != _sha(ya):
            n += 1; changed.append(x["ptr"])
    return {"n_changed": n, "n": len(a), "changed_ptrs": changed[:6]}


def observe_len_face(fr, texts, keyed):
    """只量「后端收到多少字节」这一面。"""
    out = []
    with env(TYPESAFE_API_KEY=(FAKE_KEY if keyed else "")):
        for t in texts:
            bk = Backends(); tmp = tempfile.mkdtemp(dir=SCRATCH)
            tf = os.path.join(tmp, "in.txt"); pathlib.Path(tf).write_text(t["body"], encoding="utf-8")
            ctx = {"text_file": tf, "context": "C0", "outdir": tmp, "context_decl": None}
            fr.MANIFEST.clear()
            with patched_backends(bk):
                try:
                    fr.s0(ctx)
                except Exception as e:
                    pass
            out.append({"ptr": t["ptr"], "text_len": t["len"], "L1_n_chars_sent": [c["n_chars"] for c in bk.calls]})
            shutil.rmtree(tmp, ignore_errors=True)
    return out


# ═══════════════════════════ S2 / S3 观测 ═══════════════════════════════════
def observe_s2s3(fr, recs, taxo_env=None):
    out = []
    with env(CCE_TAXO_VERSION=taxo_env):
        for r in recs:
            tmp = tempfile.mkdtemp(dir=SCRATCH)
            tf = os.path.join(tmp, "in.txt"); pathlib.Path(tf).write_text(r["text"] or H._PROBE_TEXT, encoding="utf-8")
            ctx = {"text_file": tf, "context": "C0", "outdir": tmp, "cce": copy.deepcopy(r["d"])}
            fr.MANIFEST.clear()
            fr.MANIFEST["s1_readout"] = r["s1m"] or {"status": "OK", "tops": r["d"]["stage1"].get("tops"), "within_js": r["d"]["stage1"].get("within_js")}
            e2 = e3 = eq = None
            try:
                fr.s2(ctx)
            except Exception as e:
                e2 = "%s: %s" % (type(e).__name__, str(e)[:90])
            try:
                fr.s3(ctx)
            except Exception as e:
                e3 = "%s: %s" % (type(e).__name__, str(e)[:90])
            try:
                fr.qualified(ctx)
            except Exception as e:
                eq = "%s: %s" % (type(e).__name__, str(e)[:90])
            m = _strip_sec(fr.MANIFEST); s2 = m.get("s2_knots") or {}; q = m.get("qualified_readout") or {}
            out.append({"ptr": r["ptr"],
                        "L1_s2": s2, "L1_s3": m.get("s3_emotion_policy"),
                        "L2_s2_raised": e2, "L2_s3_raised": e3, "L2_q_raised": eq,
                        "L2_playbook_primary_issued": bool(s2.get("playbook_primary")),
                        "L2_withheld_reason": s2.get("playbook_withheld_reason"),
                        "L2_usable_keys": q.get("usable_keys"), "L2_withheld": q.get("withheld"),
                        "L2_label_state": (s2.get("label_qualification") or {}).get("state") if s2.get("label_qualification") else None,
                        "L2_verbatim": (s2.get("label_qualification") or {}).get("evidence_quote_verbatim") if s2.get("label_qualification") else None})
            shutil.rmtree(tmp, ignore_errors=True)
    return out


# ═══════════════════════════ OV 观测(整条 main() 在进程内跑, 全部子进程段桩化) ═══
class LateExecutor:
    """把「工作线程晚启动」这一合法调度做成确定性的: submit 只登记, result() 时才跑。"""

    class _F:
        def __init__(self, fn, a, k): self.fn, self.a, self.k = fn, a, k
        def result(self): return self.fn(*self.a, **self.k)

    def submit(self, fn, *a, **k):
        return LateExecutor._F(fn, a, k)


def run_chain(fr, mode, serial=False, fail_reader=False, fail_s0=False, late=False, s1_rec=None, sleep=0.05, keyed=True):
    tmp = tempfile.mkdtemp(dir=SCRATCH); d = pathlib.Path(tmp)
    (d / "in.txt").write_text("draft text", encoding="utf-8"); (d / "reader.txt").write_text("reader text", encoding="utf-8")
    calls = []
    fake_rec = copy.deepcopy(s1_rec)

    def fake(tf, context, k, out):
        calls.append({"out": os.path.basename(out), "context": context, "k": k, "t": round(time.time(), 4)})
        if fail_reader and out.endswith("reader_baseline.json"):
            raise RuntimeError("READER_BOOM")
        time.sleep(sleep)
        json.dump(fake_rec, open(out, "w")); return copy.deepcopy(fake_rec)

    saved = {n: getattr(fr, n) for n in ("run_knot_classify", "s4", "_DEFER_EX", "CHAINS")}
    fr.run_knot_classify = fake
    fr.s4 = fr.stage("s4_guard")(lambda ctx: {"clean": True, "strict": True, "em_dash": 0})
    if fail_s0:
        real_s0 = fr.s0
        fr.s0 = fr.stage("s0_context")(lambda ctx: (_ for _ in ()).throw(RuntimeError("S0_BOOM")))
    if late:
        fr._DEFER_EX = LateExecutor()
    fr.CHAINS = {"reply": [fr.reader_baseline, fr.s0, fr.s1, fr.s2, fr.s3, fr.s4, fr.qualified],
                 "outbound_post": [fr.s0, fr.s1, fr.s2, fr.s3, fr.s4, fr.qualified]}
    bk = Backends(); bk.answers = {"进程位置": "在找方案"}
    argv = [TARGET, "--mode", mode, "--text-file", str(d / "in.txt"), "--context", "C0", "--outdir", tmp,
            "--reader-file", str(d / "reader.txt"), "--context-decl", json.dumps({"关系位置": "首次接触"}, ensure_ascii=False)]
    rc = None; t0 = time.time(); fr.MANIFEST.clear()
    with env(CCE_SERIAL_STAGES=("1" if serial else "0"), TYPESAFE_API_KEY=(FAKE_KEY if keyed else "")), patched_backends(bk), contextlib.redirect_stdout(io.StringIO()):
        sa = sys.argv; sys.argv = argv
        try:
            fr.main()
        except SystemExit as e:
            rc = e.code
        finally:
            sys.argv = sa
    wall = round(time.time() - t0, 3)
    if fail_s0:
        fr.s0 = real_s0
    for n, v in saved.items():
        setattr(fr, n, v)
    m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    shutil.rmtree(tmp, ignore_errors=True)
    rb = next((c for c in calls if c["out"] == "reader_baseline.json"), None)
    s1 = next((c for c in calls if c["out"] == "s1_readout.json"), None)
    return {"L2_rc": rc, "L2_complete": m["complete"], "L2_failed_at": m["failed_at"], "L2_chain": m["chain"],
            "L2_usable_keys": (m["stages"].get("qualified_readout") or {}).get("usable_keys"), "L2_withheld_keys": sorted((m["stages"].get("qualified_readout") or {}).get("withheld") or {}),
            "L1_s0_read_backend": (m["stages"].get("s0_context") or {}).get("read_backend"),
            "L2_stage_keys": list(m["stages"]), "L2_status": {k: v.get("status") for k, v in m["stages"].items()},
            "L2_stages_stripped": {k: sorted(kk for kk in v if kk not in ("sec",)) for k, v in m["stages"].items()},
            "L2_reader_error": (m["stages"].get("reader_baseline") or {}).get("error"),
            "L1_reader_context": rb and rb["context"], "L1_s1_context": s1 and s1["context"], "L1_reader_k": rb and rb["k"],
            "L1_reader_manifest": {k: v for k, v in (m["stages"].get("reader_baseline") or {}).items() if k != "sec"},
            "L1_n_calls": len(calls), "wall_excluded_from_sha": wall,
            "L1_overlapped": bool(rb and s1 and abs(rb["t"] - s1["t"]) < sleep)}


SCENARIOS = [("reply_overlap", dict(mode="reply")), ("reply_serial", dict(mode="reply", serial=True)), ("reply_overlap_nokey", dict(mode="reply", keyed=False)),
             ("reply_fail_reader", dict(mode="reply", fail_reader=True)), ("reply_fail_s0", dict(mode="reply", fail_s0=True)),
             ("reply_overlap_late_thread", dict(mode="reply", late=True)), ("outbound_post", dict(mode="outbound_post"))]


def observe_ov(fr, s1_rec):
    return {name: run_chain(fr, s1_rec=s1_rec, **kw) for name, kw in SCENARIOS}


def ov_split(obs):
    L1 = {n: {k: v for k, v in o.items() if k.startswith("L1")} for n, o in obs.items()}
    L2 = {n: {k: v for k, v in o.items() if k.startswith("L2")} for n, o in obs.items()}
    return L1, L2


# ═══════════════════════════ 主流程 ═══════════════════════════════════════════
def load_fr(arm=None, extra_env=None):
    mut = None
    if arm:
        f, mut = mutator(arm)
        assert f == TARGET, arm
    mod = H.load(TARGET, mut, env=dict({"TYPESAFE_API_KEY": os.environ.get("TYPESAFE_API_KEY", "")}, **(extra_env or {})))
    if arm:
        assert mod._ABL_MUTATED, "★ 空臂: %s" % arm
    return mod


def main_l12():
    SCRATCH.mkdir(parents=True, exist_ok=True)
    res = {"block": "ABLATION_V3_CLUSTER_r3_主链编排段_s0_s2_s3_overlap_xm", "cluster": "r3_主链编排段", "round": "v3-第三轮(主链编排段)",
           "methodology": H.METHODOLOGY, "evidence_scope": H.EVIDENCE_SCOPE, "observable_note": H.OBSERVABLE_NOTE, "injection_note": H.INJECTION_NOTE,
           "targets": [TARGET, "scripts/cce_s0_jev.py", XM], "started_at": datetime.datetime.now().isoformat(timespec="seconds")}
    with H.file_integrity(list(H.FROZEN) + list(WATCH)) as fi, H.Tripwire() as tw:
        res["tripwire_scope"] = tw.scope
        # ── M1: 先验收判官 ──
        pc = H.positive_control()
        res["positive_control"] = {k: pc[k] for k in ("passed", "failed_gates", "gates", "checks", "judge_verdict_on_dead_constant")}
        assert pc["passed"], "★★★ 阳性对照未过, 不出任何判决: %r" % pc["failed_gates"]
        import cce_s0_jev, exp_crossmodel_desire, exp_v4_full_validation, exp_v4_causal_chain, cce_label_qualification, cce_k1_status  # noqa
        recs0 = s0_corpus(); texts = text_corpus(); recs2 = s2_corpus()
        # ── 工况 ──
        res["operating_point"] = {
            "OP_s0_archive50": {"n_s0_context_files": len(recs0), "n_with_real_body": sum(r["body_real"] for r in recs0),
                                "n_body_gt_2000": sum(r["body_len"] > 2000 for r in recs0), "n_need_read_empty(全声明)": sum(1 for r in recs0 if not [f for f in json.loads((ROOT / "config/context_taxonomy.json").read_text(encoding="utf-8"))["facets"] if f["key"] not in r["decl"] and f.get("readable_from_text") in (True, "partial")]),
                                "archived_source_hist": dict(collections.Counter(s for r in recs0 for s in (["已声明"] * len(r["decl"]) + ["读出"] * len(r["read"])))),
                                "archived_fill_hist": dict(collections.Counter(str(r["archived_fill"]) for r in recs0)),
                                "corpus_sha256": hashlib.sha256("".join(H.sha256_file(ROOT / r["ptr"]) for r in recs0).encode()).hexdigest(),
                                "★读出面的循环性": "存量 s0_context.json 只存**过了非法值守卫之后**的读出值 ⇒ 回放桩永远只回放合法值; 非法值守卫在本语料上结构性满足, 只能靠注入臂判活。",
                                "scenarios": ["KEY(TYPESAFE_API_KEY=假值, Jev 桩)", "NOKEY(空串 ⇒ NO_TYPESAFE_API_KEY ⇒ MiniMax 桩)"]},
            "OP_text52": {"n_texts": len(texts), "n_gt_2000": sum(t["len"] > 2000 for t in texts), "max_len": max(t["len"] for t in texts),
                          "corpus_sha256": hashlib.sha256("".join(hashlib.sha256(t["body"].encode()).hexdigest() for t in texts).encode()).hexdigest(),
                          "★只量一面": "后端收到的字节数(桩记录), 不量语义"},
            "OP_s2_archive79": {"n_files": len(recs2), "n_reader_baseline": sum(r["ptr"].endswith("reader_baseline.json") for r in recs2),
                                "n_with_real_text": sum(r["text_real"] for r in recs2), "n_with_archived_s1_manifest": sum(bool(r["s1m"]) for r in recs2),
                                "top1_stable_hist": dict(collections.Counter(repr(((r["d"]["stage2"].get("sampling") or {}).get("top1_stable"))) for r in recs2)),
                                "top1_key_hist": dict(collections.Counter(r["d"]["stage2"]["knots"][0]["key"] for r in recs2)),
                                "taxonomy_version": json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8")).get("version"),
                                "CCE_TAXO_VERSION": "未设 ⇒ 默认 1.3.1",
                                "corpus_sha256": hashlib.sha256("".join(H.sha256_file(ROOT / r["ptr"]) for r in recs2).encode()).hexdigest()},
            "OP_ov6": {"scenarios": [n for n, _ in SCENARIOS], "classifier": "桩(sleep 0.05s, 返回一份真实存量 s1_readout 的深拷贝)", "s4": "桩(不起子进程)",
                       "s0": "真 s0 + 后端桩(KEY 场景)", "s2/s3/qualified": "真代码", "★晚启动调度": "reply_overlap_late_thread 用 LateExecutor(submit 只登记, join 时才跑) 把线程晚启动做成确定性; 真线程池场景另跑一次"},
            "market": H._market_facts(), "decided_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "drift_rule": "以上任一项变化 ⇒ 基于本工况的判决当场失效, 必须重跑。"}
        # ── 基线 + 噪声底 ──
        fr = load_fr(); fr2 = load_fr()
        base = {"s0_KEY": observe_s0(fr, recs0, True), "s0_NOKEY": observe_s0(fr, recs0, False),
                "len_KEY": observe_len_face(fr, texts, True), "len_NOKEY": observe_len_face(fr, texts, False),
                "s2s3": observe_s2s3(fr, recs2), "ov": observe_ov(fr, recs2[0]["d"])}
        again = {"s0_KEY": observe_s0(fr2, recs0, True), "s2s3": observe_s2s3(fr2, recs2), "ov": observe_ov(fr2, recs2[0]["d"])}
        noise = {k: {"L1_same": _sha(strip_L(again[k], "L1")) == _sha(strip_L(base[k], "L1")), "L2_same": _sha(strip_L(again[k], "L2")) == _sha(strip_L(base[k], "L2"))} for k in again}
        res["baseline_noise_floor(base_vs_base, fresh reload)"] = noise
        assert all(v["L1_same"] and v["L2_same"] for v in noise.values()), "★ 基线不确定, 判官作废: %r" % noise
        # 接线检查: 回放能否复现存盘
        res["wiring_checks"] = {
            "s0_replay_reproduces_archived_facets": "%d/%d" % (sum(1 for o, r in zip(base["s0_KEY"], recs0) if (o["L1_layer"] or {}).get("facets") == json.loads((ROOT / r["ptr"]).read_text(encoding="utf-8"))["facets"]), len(recs0)),
            "s0_replay_reproduces_archived_fill": "%d/%d" % (sum(1 for o, r in zip(base["s0_KEY"], recs0) if o["L2_fill"] == r["archived_fill"]), len(recs0)),
            "s3_replay_reproduces_archived_distribution(s1_readout only; reader_baseline 无自己的 s3 段)": "%d/%d" % (sum(1 for o, r in zip(base["s2s3"], recs2) if r["s3_archived"] and not r["ptr"].endswith("reader_baseline.json") and o["L1_s3"] and o["L1_s3"].get("emotion_distribution") == r["s3_archived"].get("emotion_distribution")), sum(1 for r in recs2 if r["s3_archived"] and not r["ptr"].endswith("reader_baseline.json"))),
            "s2_replay_reproduces_archived_playbook_primary(s1_readout only)": "%d/%d" % (sum(1 for o, r in zip(base["s2s3"], recs2) if r["s1m"] is not None and not r["ptr"].endswith("reader_baseline.json") and ((json.loads((ROOT / (r["ptr"].rsplit("__", 1)[0] + "__manifest.json")).read_text(encoding="utf-8"))["stages"].get("s2_knots") or {}).get("playbook_primary")) == o["L1_s2"].get("playbook_primary")), sum(1 for r in recs2 if r["s1m"] is not None and not r["ptr"].endswith("reader_baseline.json"))),
            "s2_replay_mismatch_explained_by_code_history": "存档 s2 段按 (taxonomy, top1_stable, playbook 是否发出) 分组: 1.2.0 时代 9 份(旧代码无 sampling 也发) · 1.3.1 且 top1_stable=None 却发出 18 份(2026-09-06 `is not False`→`is True` 收紧之前) · False 却发出 2 份(同上更早) · 无 s2 段 4 份 ⇒ 回放复现的是**现行**语义, 不匹配的全部落在收紧之前的存档上。",
            "s0_base_KEY_backend_hist": dict(collections.Counter(o["L2_read_backend"] for o in base["s0_KEY"])),
            "s0_base_NOKEY_backend_hist": dict(collections.Counter(o["L2_read_backend"] for o in base["s0_NOKEY"])),
            "s2_base_playbook_issued": "%d/%d" % (sum(o["L2_playbook_primary_issued"] for o in base["s2s3"]), len(recs2)),
            "s2_base_verbatim_true": "%d/%d(有原文 %d)" % (sum(1 for o in base["s2s3"] if o["L2_verbatim"]), len(recs2), sum(r["text_real"] for r in recs2)),
            "s2_base_label_state_hist": dict(collections.Counter(o["L2_label_state"] for o in base["s2s3"])),
            "s2_base_unscored_guidance_nonnull": sum(1 for o in base["s2s3"] if o["L1_s2"].get("playbook_unscored_guidance")),
            "ov_base": {n: {"rc": o["L2_rc"], "failed_at": o["L2_failed_at"], "overlapped": o["L1_overlapped"], "reader_ctx": o["L1_reader_context"], "s1_ctx_has_scene": bool(o["L1_s1_context"] and "【情境】" in o["L1_s1_context"]), "wall": o["wall_excluded_from_sha"]} for n, o in base["ov"].items()},
        }
        res["arms"] = {}
        for arm in ARMS:
            f, _ = mutator(arm)
            if f != TARGET or arm.startswith("NOOP"):
                continue
            m = load_fr(arm)
            rec = {"patch": {"old": ARMS[arm][1], "new": ARMS[arm][2]}, "source_sha16": m._ABL_SRC_SHA}
            if arm.startswith("S0"):
                if arm == "S0_A2i_read_backend_absurd_999":
                    o = observe_ov(m, recs2[0]["d"]); bL1, bL2 = ov_split(base["ov"]); aL1, aL2 = ov_split(o)
                    rec["ov"] = {"L1_scenarios_changed": sorted(n for n in bL1 if _sha(bL1[n]) != _sha(aL1[n])), "L2_scenarios_changed": sorted(n for n in bL2 if _sha(bL2[n]) != _sha(aL2[n])),
                                 "nokey_read_backend": o["reply_overlap_nokey"]["L1_s0_read_backend"], "nokey_rc_complete_usable": [o["reply_overlap_nokey"]["L2_rc"], o["reply_overlap_nokey"]["L2_complete"], o["reply_overlap_nokey"]["L2_usable_keys"]]}
                for sc, keyed in (("s0_KEY", True), ("s0_NOKEY", False)):
                    o = observe_s0(m, recs0, keyed)
                    rec[sc] = {"L1": diff_count(base[sc], o, "L1"), "L2": diff_count(base[sc], o, "L2"),
                               "backend_hist": dict(collections.Counter(x["L2_read_backend"] for x in o)),
                               "raised_hist": dict(collections.Counter((x["L2_raised"] or "").split(":")[0] for x in o)),
                               "n_backend_calls": sum(len(x["L1_backend_calls"]) for x in o),
                               "asked_hist": dict(collections.Counter(len(c["asked"]) for x in o for c in x["L1_backend_calls"]))}
                if arm in ("S0_A8_body_not_truncated",):
                    for sc, keyed in (("len_KEY", True), ("len_NOKEY", False)):
                        o = observe_len_face(m, texts, keyed)
                        rec[sc] = {"L1": diff_count(base[sc], o, "L1"), "n_texts_gt_2000": sum(t["len"] > 2000 for t in texts),
                                   "base_sent_hist": dict(collections.Counter(c for x in base[sc] for c in x["L1_n_chars_sent"] if c >= 2000)),
                                   "arm_sent_gt_2000": sorted(c for x in o for c in x["L1_n_chars_sent"] if c > 2000)}
            elif arm.startswith("S2") or arm.startswith("S3"):
                o = observe_s2s3(m, recs2)
                rec["s2s3"] = {"L1": diff_count(base["s2s3"], o, "L1"), "L2": diff_count(base["s2s3"], o, "L2"),
                               "L1_s2_changed": diff_count(base["s2s3"], o, "L1_s2"), "L1_s3_changed": diff_count(base["s2s3"], o, "L1_s3"),
                               "L2_usable_changed": diff_count(base["s2s3"], o, "L2_usable"), "L2_withheld_changed": diff_count(base["s2s3"], o, "L2_withheld"),
                               "L2_playbook_issued": "%d/%d" % (sum(x["L2_playbook_primary_issued"] for x in o), len(o)),
                               "raised_hist": dict(collections.Counter((x["L2_s2_raised"] or x["L2_s3_raised"] or x["L2_q_raised"] or "").split(":")[0] for x in o)),
                               "verbatim_true": sum(1 for x in o if x["L2_verbatim"]), "unscored_nonnull": sum(1 for x in o if x["L1_s2"].get("playbook_unscored_guidance"))}
            elif arm.startswith("OV"):
                o = observe_ov(m, recs2[0]["d"])
                bL1, bL2 = ov_split(base["ov"]); aL1, aL2 = ov_split(o)
                rec["ov"] = {"L1_scenarios_changed": sorted(n for n in bL1 if _sha(bL1[n]) != _sha(aL1[n])),
                             "L2_scenarios_changed": sorted(n for n in bL2 if _sha(bL2[n]) != _sha(aL2[n])),
                             "per_scenario": {n: {"rc": x["L2_rc"], "failed_at": x["L2_failed_at"], "complete": x["L2_complete"], "reader_status": x["L2_status"].get("reader_baseline"),
                                                  "reader_manifest_keys": sorted(x["L1_reader_manifest"]), "reader_ctx": x["L1_reader_context"], "overlapped": x["L1_overlapped"], "wall": x["wall_excluded_from_sha"]} for n, x in o.items()}}
            res["arms"][arm] = rec
        # ── 注入臂(M6): 无差异族必须再判活 ──
        inj = {}
        # A3/A5: 后端多答(把已声明的面也答了) ⇒ 基线: 声明优先; A3 臂: 读出覆盖 ⇒ miss 防呆 raise
        def over(bk, r): bk.over_answer = True; bk.answers = {**{k: v for k, v in r["decl"].items()}, **r["read"]}
        bj = observe_s0(fr, recs0, True, bk_tweak=over); a3j = observe_s0(load_fr("S0_A3_read_overrides_declared"), recs0, True, bk_tweak=over)
        b = observe_s0(fr, recs0, False, bk_tweak=over); a3 = observe_s0(load_fr("S0_A3_read_overrides_declared"), recs0, False, bk_tweak=over)
        a3g = observe_s0(load_fr("S0_A5_miss_guard_removed"), recs0, False, bk_tweak=over)
        a3_a5 = observe_s0(H.load(TARGET, lambda src: mutator("S0_A5_miss_guard_removed")[1](mutator("S0_A3_read_overrides_declared")[1](src))), recs0, False, bk_tweak=over)
        inj["A3_over_answer"] = {"★Jev 路径": {"KEY_base_vs_arm_L2": diff_count(bj, a3j, "L2"), "why_zero": "scripts/cce_s0_jev.py:45 `{k: ans[k]['choice'] for k in qs}` 只取问过的面 ⇒ Jev 适配器结构上不会多答, 精度翻转在 Jev 路径不可达"},
                                 "★MiniMax 路径(NOKEY)": {"base_vs_arm_L2": diff_count(b, a3, "L2")},
                                 "n_cases_with_decl_and_backend_call": sum(1 for x, r in zip(b, recs0) if x["L1_backend_calls"] and r["decl"]),
                                 "A3_plus_A5_both_removed_L2_vs_base": diff_count(b, a3_a5, "L2"), "A3_plus_A5_facets_source_read_overrides": sum(1 for x in a3_a5 if x["L2_source"] and "读出" in [x["L2_source"].get(k) for k in x["L2_source"]] and any(x["L2_source"].get(k) == "读出" for k in recs0[0]["decl"] or {})), "base_raised_hist": dict(collections.Counter((x["L2_raised"] or "OK").split(":")[0] for x in b)), "A3_raised_hist": dict(collections.Counter((x["L2_raised"] or "OK").split(":")[0] for x in a3)),
                                 "★读法": "多答面时基线仍判「已声明」(0 raise); A3 臂读出覆盖声明 ⇒ 每个多答且被声明的面都触发 miss 防呆 RuntimeError ⇒ 精度守卫与防呆是一对: 精度坏了防呆当场抓。",
                                 "A5_guard_removed_on_same_input": diff_count(b, a3g, "L2")}
        # A4: 非法值
        def ill(bk, r):
            k = next(iter(r["read"]), None) or "进程位置"; bk.illegal = (k, "★非法值★")
        b = observe_s0(fr, recs0, True, bk_tweak=ill); a4 = observe_s0(load_fr("S0_A4_illegal_value_not_mapped_to_unknown"), recs0, True, bk_tweak=ill)
        inj["A4_illegal_value"] = {"base_vs_arm_L1": diff_count(b, a4, "L1"), "base_vs_arm_L2": diff_count(b, a4, "L2"),
                                   "base_illegal_kept": sum(1 for x in b if "★非法值★" in json.dumps((x["L1_layer"] or {}).get("facets", {}), ensure_ascii=False)),
                                   "arm_illegal_kept": sum(1 for x in a4 if "★非法值★" in json.dumps((x["L1_layer"] or {}).get("facets", {}), ensure_ascii=False))}
        # A5: 声明里带一个分类学外的面名
        def stray(decl, r): d = dict(decl); d["★不存在的面"] = "x"; return d
        b = observe_s0(fr, recs0, True, decl_tweak=stray); a5 = observe_s0(load_fr("S0_A5_miss_guard_removed"), recs0, True, decl_tweak=stray)
        inj["A5_stray_decl_key"] = {"base_raised": sum(1 for x in b if x["L2_raised"]), "arm_raised": sum(1 for x in a5 if x["L2_raised"]), "L2": diff_count(b, a5, "L2"),
                                    "★上游闸": ".github/prepare.py:58 在 cce_full_run 之前已拒绝分类学外的面名 ⇒ 生产(cce-submit)路径上此 raise 是第二道; 本地 CLI 直呼时是唯一一道。"}
        # A6: 空声明 + 全未知
        def allunk(bk, r): bk.answers = {}
        def nodecl(decl, r): return {}
        b = observe_s0(fr, recs0, True, bk_tweak=allunk, decl_tweak=nodecl); a6 = observe_s0(load_fr("S0_A6_fill_zero_guard_removed"), recs0, True, bk_tweak=allunk, decl_tweak=nodecl)
        inj["A6_empty_decl_all_unknown"] = {"base_raised": sum(1 for x in b if x["L2_raised"]), "arm_raised": sum(1 for x in a6 if x["L2_raised"]), "arm_fill_hist": dict(collections.Counter(x["L2_fill"] for x in a6)), "L2": diff_count(b, a6, "L2")}
        # A10: Jev 概率被丢弃 —— 荒谬概率注入, 全部观测面不变
        def absurd_probs(bk, r): bk.probs = {k: {"x": 999.0} for k in r["read"]}
        b = observe_s0(fr, recs0, True, bk_tweak=absurd_probs)
        inj["A10_jev_probs_absurd"] = {"L1": diff_count(base["s0_KEY"], b, "L1"), "L2": diff_count(base["s0_KEY"], b, "L2")}
        # A2 荒谬标签注入(消费面): read_backend 改成 999 ⇒ 下游 s2/s3/qualified 不看它(结构上: 它们只读 ctx["cce"]/MANIFEST["s1_readout"/"s2_knots"])
        inj["A2_read_backend_consumers"] = {"grep_scripts_github_accuracy": sorted(set(l.split(":")[0] for l in subprocess.run(["grep", "-rln", "--include=*.py", "--include=*.yml", "read_backend", "scripts", ".github", "accuracy"], cwd=ROOT, capture_output=True, text=True).stdout.split())),
                                            "★读法": "除 cce_full_run.py 自己与 cce_open_items.py(报告文本)外, 生产代码零读者; probes/stage_overlap_bench.py 与 tests/test_cce_s0_wiring.py 是 G 侧。"}
        # B2: 环境钉 9.9.9 ⇒ 基线全 raise, 臂全过
        b = observe_s2s3(fr, recs2, taxo_env="9.9.9"); a = observe_s2s3(load_fr("S2_B2_taxo_guard_removed"), recs2, taxo_env="9.9.9")
        inj["B2_env_pin_absurd"] = {"base_raised": sum(1 for x in b if x["L2_s2_raised"]), "arm_raised": sum(1 for x in a if x["L2_s2_raised"]), "L2": diff_count(b, a, "L2")}
        # B5: [:10] 已是荒谬臂(见 arms); 分类学 playbook 最长
        taxo = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
        inj["B5_playbook_lengths"] = {k["key"]: len(k.get("playbook", "")) for k in taxo["knots"]}
        # B6/B7/C*: 荒谬值注入到 s2/s3 产出后, 出口闸 usable/withheld 是否动
        def absurd_after(fr_, key, val):
            out = []
            for r in recs2:
                tmp = tempfile.mkdtemp(dir=SCRATCH); tf = os.path.join(tmp, "in.txt"); pathlib.Path(tf).write_text(r["text"] or H._PROBE_TEXT, encoding="utf-8")
                ctx = {"text_file": tf, "context": "C0", "outdir": tmp, "cce": copy.deepcopy(r["d"])}
                fr_.MANIFEST.clear(); fr_.MANIFEST["s1_readout"] = r["s1m"] or {"status": "OK", "tops": r["d"]["stage1"].get("tops")}
                try:
                    fr_.s2(ctx); fr_.s3(ctx)
                    st, fld = key
                    fr_.MANIFEST[st][fld] = val
                    fr_.qualified(ctx)
                    q = fr_.MANIFEST.get("qualified_readout") or {}
                    out.append({"ptr": r["ptr"], "L2_usable_keys": q.get("usable_keys"), "L2_withheld": q.get("withheld")})
                except Exception as e:
                    out.append({"ptr": r["ptr"], "L2_err": type(e).__name__})
                shutil.rmtree(tmp, ignore_errors=True)
            return out
        b = [{"ptr": x["ptr"], "L2_usable_keys": x["L2_usable_keys"], "L2_withheld": x["L2_withheld"]} for x in base["s2s3"]]
        for label, key, val in (("B6_unscored_guidance_999", ("s2_knots", "playbook_unscored_guidance"), 999),
                                ("B7_label_qualification_999", ("s2_knots", "label_qualification"), 999),
                                ("C1_emotion_distribution_999", ("s3_emotion_policy", "emotion_distribution"), 999),
                                ("C3_policy_string_999", ("s3_emotion_policy", "policy"), 999),
                                ("B4_withheld_reason_999", ("s2_knots", "playbook_withheld_reason"), "999")):
            inj[label] = diff_count(b, absurd_after(fr, key, val), "L2")
        inj["B4_note"] = "withheld_reason 荒谬值会**逐字进入**出口闸 withheld['s2.playbook_primary'] ⇒ 它有消费者(出口闸台账), 但只改台账文本不改 usable/withheld 成员。"
        # B7 附: evidence=None 恒候选 —— 把 evidence_quote 当证据传进去, 状态会不会升
        def state_with_evidence(r):
            t = r["text"] or H._PROBE_TEXT; k0 = r["d"]["stage2"]["knots"][0]
            q = (k0.get("evidence_quote") or "").strip()
            q1 = cce_label_qualification.qualify(k0["key"], t, evidence=None, required_conjuncts=None)
            try:
                e = cce_label_qualification.EvidenceSpan(q, "P", t, about="obj")   # 逐字核不过 ⇒ ValueError
                q2 = cce_label_qualification.qualify(k0["key"], t, evidence=[e], required_conjuncts=None)
                q3 = cce_label_qualification.qualify(k0["key"], t, evidence=[e], required_conjuncts=["P"])
                return q1["state"], q2["state"], q3["state"]
            except Exception as e:
                return q1["state"], "ERR:" + type(e).__name__, "-"
        st = collections.Counter(state_with_evidence(r) for r in recs2)
        inj["B7_evidence_none_vs_quote_as_evidence(state: evidence=None → EvidenceSpan(quote) → +required_conjuncts=[P])"] = {" → ".join(k): v for k, v in st.items()}
        # O7: reader_cce 消费者
        inj["O7_reader_cce_readers"] = sorted(set(l.split(":")[0] for l in subprocess.run(["grep", "-rln", "--include=*.py", "--include=*.yml", "reader_cce", "scripts", ".github", "accuracy", "probes", "tests"], cwd=ROOT, capture_output=True, text=True).stdout.split()) - {"probes/ablation_r3_chain_stages.py"})
        # XM_E1: s0 MiniMax 回退臂对 exp_crossmodel_desire.call_model 的真实消费(2026-09-23 新增消费者)
        def poison(bk, r): bk.poison_minimax = True
        b = observe_s0(fr, recs0, False); p = observe_s0(fr, recs0, False, bk_tweak=poison)
        inj["XM_E1_call_model_poisoned_in_fallback"] = {"base_raised": sum(1 for x in b if x["L2_raised"]), "poison_raised": sum(1 for x in p if x["L2_raised"]),
                                                       "poison_raised_hist": dict(collections.Counter((x["L2_raised"] or "OK")[:40] for x in p)), "L2": diff_count(b, p, "L2"),
                                                       "n_cases_that_call_backend": sum(1 for x in b if x["L1_backend_calls"]),
                                                       "KEY_scenario_poisoned_unaffected": diff_count(base["s0_KEY"], observe_s0(fr, recs0, True, bk_tweak=poison), "L2")}
        # XM_E2/E3/E4: 内存内变异 exp_crossmodel_desire, 看 import 是否成立与 s0 回退面是否变
        xmres = {}
        for arm in ("XM_E2_unused_import_re_removed", "XM_E3_syspath_insert_removed", "XM_E4_results_dir_renamed"):
            f, mut = mutator(arm)
            try:
                mx = H.load(XM, mut, env={"VSE_ROOT": str(SCRATCH / ("vse_root_%s" % arm))})
                ok = mx._ABL_MUTATED; err = None
                has_re = hasattr(mx, "re")
                # 在变异模块上跑 s0 回退面(通过 as_import 让 `from exp_crossmodel_desire import call_model` 拿到变异版)
                with H.as_import({"exp_crossmodel_desire": mx}):
                    o = observe_s0(fr, recs0, False)
                xmres[arm] = {"import_ok": bool(ok), "has_attr_re": has_re, "s0_NOKEY_L1": diff_count(base["s0_NOKEY"], o, "L1"), "s0_NOKEY_L2": diff_count(base["s0_NOKEY"], o, "L2"),
                              "js_divergence_same": (mx.js_divergence([0.5, 0.5], [0.9, 0.1]) == exp_crossmodel_desire.js_divergence([0.5, 0.5], [0.9, 0.1])),
                              "RESULTS_basename": os.path.basename(mx.RESULTS) if hasattr(mx, "RESULTS") else None}
                if arm == "XM_E4_results_dir_renamed":
                    created = pathlib.Path(mx.CAL); xmres[arm]["side_effect_dir_created(under VSE_ROOT=scratch)"] = created.exists()
            except Exception as e:
                xmres[arm] = {"import_ok": False, "error": "%s: %s" % (type(e).__name__, str(e)[:120])}
        # E3 注入: 从一个 sys.path 里没有 scripts/ 的解释器状态 import 变异版 ⇒ calibration_framework 找不到
        def import_without_scripts(mut):
            src = (ROOT / XM).read_text(encoding="utf-8"); src = mut(src) if mut else src
            saved_path = list(sys.path); saved_mods = {k: sys.modules.get(k) for k in ("calibration_framework",)}
            sys.path[:] = [p for p in sys.path if not p.rstrip("/").endswith("scripts")]
            sys.modules.pop("calibration_framework", None)
            mod = types.ModuleType("xm_e3_probe"); mod.__file__ = str(ROOT / XM)
            try:
                exec(compile(src, str(ROOT / XM), "exec"), mod.__dict__); return "IMPORT_OK"
            except Exception as e:
                return type(e).__name__ + ": " + str(e)[:60]
            finally:
                sys.path[:] = saved_path
                for k, v in saved_mods.items():
                    if v is not None: sys.modules[k] = v
        xmres["XM_E3_injection_import_from_bare_syspath"] = {"base": import_without_scripts(None), "arm": import_without_scripts(mutator("XM_E3_syspath_insert_removed")[1])}
        # E4 荒谬路径 ⇒ import 期 makedirs 炸(那是 v3-183 的面, 不是读数消费面)
        try:
            H.load(XM, H.replace_once('RESULTS = os.path.join(ROOT, "results")\n', 'RESULTS = "/nonexistent_root_abl_r3/x"\n')); xmres["XM_E4_absurd_unwritable_path"] = "IMPORT_OK(意外)"
        except Exception as e:
            xmres["XM_E4_absurd_unwritable_path"] = "import 期 %s ⇒ 整条链在 import 就死(v3-183 makedirs 的面)" % type(e).__name__
        xmres["XM_consumers_of_exp_crossmodel_desire(grep, 不含 tests/data)"] = sorted(set(l.split(":")[0] for l in subprocess.run(["grep", "-rln", "--include=*.py", "--include=*.yml", "--include=*.json", "exp_crossmodel_desire", "scripts", ".github", "accuracy", "probes", "tests", "config"], cwd=ROOT, capture_output=True, text=True).stdout.split() if not l.startswith("tests/data")) - {"probes/ablation_r3_chain_stages.py"})
        res["injection_arms"] = inj; res["xm"] = xmres
        res["tripwire_tripped"] = list(tw.tripped)
    res["file_integrity"] = {"identical": fi["identical"], "changed": fi["changed"], "before": {os.path.relpath(k, ROOT): v[:16] for k, v in fi["before"].items()}}
    res["decided_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    return res


def strip_L(obs, prefix):
    if isinstance(obs, dict):
        return {n: {k: v for k, v in o.items() if k.startswith(prefix)} for n, o in obs.items()}
    return [{k: v for k, v in o.items() if k.startswith(prefix) or k == "ptr"} for o in obs]


# ═══════════════════════════ L4 农场(rsync 冻结快照, 绝不 symlink) ═══════════════
def l4_farm(arms=None, workers=8, pytest_only=False):
    farm = SCRATCH / "farm"; snap = farm / "repo"; farm.mkdir(parents=True, exist_ok=True)
    if not snap.exists():
        subprocess.run(["rsync", "-a", "--delete", "--exclude", ".git", "--exclude", "__pycache__", "--exclude", "probes/ablation_r3_chain_stages.py", str(ROOT) + "/", str(snap) + "/"], check=True)
    pristine = {f: (snap / f).read_text(encoding="utf-8") for f in (TARGET, XM)}
    tests = sorted(p.name for p in (snap / "tests").glob("test_*.py"))
    # ★ 127/225 个测试文件带 `def test_`(pytest 风格): `python3 -B tests/test_x.py` 对其中没有 __main__ 跑测试的文件是**空跑**(0 断言执行) ——
    #   第一版农场只用脚本方式, 把 test_cce_stage_overlap / test_cce_s0_wiring 这类真正守本文件行为的闸漏掉了。
    #   有 `def test_` 的一律 `python3 -B -m pytest -p no:cacheprovider` 单文件跑(仍在磁盘副本上, 仍清 pyc); 模块级断言式的文件脚本跑。
    #   pytest_only=True ⇒ 只补跑 def test_ 那 127 个。
    no_main = {t for t in tests if re.search(r"^def test_", (snap / "tests" / t).read_text(encoding="utf-8"), re.M)}
    if pytest_only:
        tests = sorted(no_main)

    def clean_pyc():
        for p in snap.rglob("__pycache__"):
            shutil.rmtree(p, ignore_errors=True)

    def run_one(t):
        cmd = [sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", str(snap / "tests" / t)] if t in no_main else [sys.executable, "-B", str(snap / "tests" / t)]
        p = subprocess.run(cmd, capture_output=True, text=True, cwd=snap, timeout=900,
                           env=dict(os.environ, MINIMAX_API_KEY=FAKE_KEY, TYPESAFE_API_KEY="", PYTHONDONTWRITEBYTECODE="1"))
        return t, p.returncode, (p.stdout + p.stderr)[-600:]

    def suite():
        import concurrent.futures as cf
        red = {}
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            for t, rc, out in ex.map(run_one, tests):
                if rc:
                    red[t] = out
        real = {}
        for t in red:                                  # 串行复验一次, 只留真红
            if run_one(t)[1]:
                real[t] = red[t]
        return real

    results = {"n_tests": len(tests), "runner": "pytest-per-file(no __main__ files)" if pytest_only else "python3 -B script (files with __main__) + pytest-per-file (files without)", "arms": {}}
    out_p = farm / ("l4_pytest_results.json" if pytest_only else "l4_results.json")
    for name in (arms or list(ARMS)):
        f, old, new = ARMS[name]
        src = pristine[f]; assert src.count(old) == 1, name
        (snap / f).write_text(src.replace(old, new), encoding="utf-8")
        assert (snap / f).read_text(encoding="utf-8") != src
        clean_pyc(); t0 = time.time()
        try:
            reds = suite()
        finally:
            (snap / f).write_text(pristine[f], encoding="utf-8"); clean_pyc()
        results["arms"][name] = {"file": f, "reds": sorted(reds), "tails": {k: v[-300:] for k, v in reds.items()}, "sec": round(time.time() - t0, 1)}
        out_p.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
        print(name, sorted(reds), round(time.time() - t0, 1), flush=True)
    for f in (TARGET, XM):
        assert (snap / f).read_text(encoding="utf-8") == pristine[f]
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--l4", action="store_true"); ap.add_argument("--l4-pytest-only", action="store_true"); ap.add_argument("--arms", nargs="*"); ap.add_argument("--out", default=str(SCRATCH / "l12_results.json"))
    a = ap.parse_args()
    SCRATCH.mkdir(parents=True, exist_ok=True)
    if a.l4 or a.l4_pytest_only:
        l4_farm(a.arms, pytest_only=a.l4_pytest_only)
    else:
        r = main_l12()
        pathlib.Path(a.out).write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps({"positive_control": r["positive_control"]["passed"], "noise": r["baseline_noise_floor(base_vs_base, fresh reload)"], "tripwire": r["tripwire_tripped"], "integrity": r["file_integrity"]["identical"], "written": a.out}, ensure_ascii=False))
