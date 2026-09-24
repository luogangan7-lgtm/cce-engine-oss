# -*- coding: utf-8 -*-
"""闸: 消融 v3 第三轮(tests/data/ablation_v3/r3_主链编排段.json ★acceptance_gaps_found)浮出的 12 个「承重/保险丝却零行为闸」位点, 逐个补行为闸。
零调用: s0 的后端用桩, s2/s3 用桩 ctx。每个用例名末尾带 gap id; 变异验证直接复用 r3 产物里各臂的 patch(old→new)。
"""
import ast, json, os, pathlib, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
import cce_full_run as fr, cce_s0_jev
_ORIG_READ = cce_s0_jev.s0_jev_read
READABLE = [f for f in fr.CTX_FACETS if f.get("readable_from_text") in (True, "partial")]
GAPS = json.loads((ROOT / "tests/data/ablation_v3/r3_主链编排段.json").read_text(encoding="utf-8"))["★acceptance_gaps_found"]
GAP_IDS = sorted(x["id"] for v in GAPS.values() if isinstance(v, list) for x in v)


def _s0(monkeypatch, text, decl=None, jev_read=None, want_calls=None):
    """跑生产 s0: 桩掉 Jev 后端(记录 body), 返回 (stage 返回, ctx_layer, ctx, calls)。"""
    calls = []
    def fake(body, facets):
        calls.append({"body": body, "facets": [f["key"] for f in facets]})
        read = dict(jev_read or {}); return ({k: read.get(k, "未知") for k in [f["key"] for f in facets]} | {k: v for k, v in read.items()}, None, None) if jev_read is not None else (None, None, "NO_TYPESAFE_API_KEY")
    monkeypatch.setenv("TYPESAFE_API_KEY", "k"); monkeypatch.setattr(cce_s0_jev, "s0_jev_read", fake)
    with tempfile.TemporaryDirectory() as tmp:
        tf = pathlib.Path(tmp) / "t.txt"; tf.write_text(text, encoding="utf-8")
        ctx = {"text_file": str(tf), "outdir": tmp, "context": "C0", "context_decl": (json.dumps(decl, ensure_ascii=False) if decl else None)}
        fr.MANIFEST.clear(); fr.s0(ctx); layer = json.loads((pathlib.Path(tmp) / "s0_context.json").read_text(encoding="utf-8"))
    return fr.MANIFEST["s0_context"], layer, ctx, calls


# ── s0 ────────────────────────────────────────────────────────────────────────
def test_declared_wins_even_if_backend_also_returns_that_key__v3_312(monkeypatch):
    out, layer, _, _ = _s0(monkeypatch, "text", decl={"触发事件": "刚花过钱"}, jev_read={"触发事件": "受挫/出故障", "进程位置": "在找方案"})
    assert layer["facets"]["触发事件"] == "刚花过钱" and layer["source"]["触发事件"] == "已声明" and out["status"] == "OK"


def test_illegal_backend_value_maps_to_unknown_not_readout__v3_313(monkeypatch):
    _, layer, _, _ = _s0(monkeypatch, "text", jev_read={"进程位置": "BOGUS_VALUE", "触发事件": "受挫/出故障"})
    assert layer["facets"]["进程位置"] == "未知" and layer["source"]["进程位置"] == "未知(走先验)" and layer["facets"]["触发事件"] == "受挫/出故障"


def test_miss_guard_still_raises_structurally__v3_314():
    """保险丝: `if miss:` 体内必须是 raise(它防的是「声明没落到 已声明」这个内部不变量被破坏, 行为上构造不出来 ⇒ 用 AST 守)。"""
    tree = ast.parse((ROOT / "scripts/cce_full_run.py").read_text(encoding="utf-8"))
    ifs = [n for n in ast.walk(tree) if isinstance(n, ast.If) and isinstance(n.test, ast.Name) and n.test.id == "miss"]
    assert ifs and all(any(isinstance(b, ast.Raise) for b in n.body) for n in ifs)


def test_all_unknown_and_no_declaration_refuses__v3_315(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        tf = pathlib.Path(tmp) / "t.txt"; tf.write_text("text", encoding="utf-8")
        monkeypatch.setenv("TYPESAFE_API_KEY", "k"); monkeypatch.setattr(cce_s0_jev, "s0_jev_read", lambda body, facets: ({f["key"]: "未知" for f in facets}, None, None))
        fr.MANIFEST.clear()
        try: fr.s0({"text_file": str(tf), "outdir": tmp, "context": "C0", "context_decl": None}); raised = False
        except RuntimeError as e: raised = "拒答" in str(e)
    assert raised and fr.MANIFEST["s0_context"]["status"] == "FAIL"


def test_context_gets_situation_appended__v3_316(monkeypatch):
    _, layer, ctx, _ = _s0(monkeypatch, "text", jev_read={"进程位置": "在找方案"})
    assert ctx["context"].startswith("C0 【情境】") and '"进程位置": "在找方案"' in ctx["context"] and "未知" not in ctx["context"]


def test_body_sent_to_backend_is_truncated_to_2000__v3_317(monkeypatch):
    _, _, _, calls = _s0(monkeypatch, "x" * 3000, jev_read={"进程位置": "在找方案"})
    assert len(calls) == 1 and len(calls[0]["body"]) == 2000


def test_backend_not_called_when_everything_declared__v3_320(monkeypatch):
    decl = {f["key"]: f["values"][0] for f in READABLE}
    out, layer, _, calls = _s0(monkeypatch, "text", decl=decl, jev_read={"进程位置": "在找方案"})
    assert calls == [] and out["read_backend"] == "none" and layer["read_backend"] == "none"


# ── s2 / s3 ───────────────────────────────────────────────────────────────────
def _s2(monkeypatch, top1_stable, playbook="p" * 300, taxo_env=None):
    if taxo_env is not None: monkeypatch.setenv("CCE_TAXO_VERSION", taxo_env)
    with tempfile.TemporaryDirectory() as tmp:
        tf = pathlib.Path(tmp) / "t.txt"; tf.write_text("Been wearing it daily.", encoding="utf-8")
        ctx = {"text_file": str(tf), "outdir": tmp, "context": "c",
               "cce": {"stage2": {"knots": [{"key": "display", "weight": 1.0, "evidence_quote": "daily", "playbook": playbook}],
                                  "sampling": {"n_ok": 5, "top1_stable": top1_stable, "top1_mode_share": 0.6, "top1_mode": "display", "top1_draws": ["display", "reward"], "max_range": 0.1, "per_knot": {}},
                                  "intensity": {}, "families": {}, "drive_brake": {}, "instrument": {"instrument_hash": "x"}}}}
        fr.MANIFEST.clear(); fr.s2(ctx); return fr.MANIFEST["s2_knots"]


def test_taxonomy_version_drift_raises__v3_323(monkeypatch):
    fr.MANIFEST.clear(); raised = False
    try: _s2(monkeypatch, True, taxo_env="9.9.9")
    except RuntimeError as e: raised = "漂移" in str(e)
    assert raised and fr.MANIFEST["s2_knots"]["status"] == "FAIL"


def test_playbook_only_when_top1_stable_is_exactly_true__v3_324(monkeypatch):
    assert _s2(monkeypatch, True)["playbook_primary"] is not None
    assert _s2(monkeypatch, False)["playbook_primary"] is None and _s2(monkeypatch, None)["playbook_primary"] is None
    assert _s2(monkeypatch, None)["playbook_unscored_guidance"] is None


def test_two_withheld_reasons_stay_distinct__v3_325(monkeypatch):
    r_none = _s2(monkeypatch, None)["playbook_withheld_reason"]; r_false = _s2(monkeypatch, False)["playbook_withheld_reason"]
    assert "不可判" in r_none and "不稳" not in r_none and "不稳" in r_false and "不可判" not in r_false and _s2(monkeypatch, True)["playbook_withheld_reason"] is None


def test_playbook_primary_cut_at_120__v3_326(monkeypatch):
    assert len(_s2(monkeypatch, True)["playbook_primary"]) == 120


def test_s3_reports_top4_distribution_only():
    from exp_v4_causal_chain import EMOTIONS
    vec = [0.0] * len(EMOTIONS); vec[2], vec[5], vec[7], vec[9], vec[11] = 0.5, 0.2, 0.15, 0.1, 0.05
    fr.MANIFEST.clear(); fr.s3({"cce": {"stage1": {"layers": {"emotion_vec": vec}}}}); out = fr.MANIFEST["s3_emotion_policy"]
    assert [l for l, _ in out["emotion_distribution"]] == [EMOTIONS[2], EMOTIONS[5], EMOTIONS[7], EMOTIONS[9]] and out["policy"].startswith("distribution_only")


# ── exp_crossmodel_desire ──────────────────────────────────────────────────────
def test_xm_imports_from_any_cwd_without_pythonpath__v3_340():
    """sys.path.insert(scripts/) 让 `from calibration_framework import …` 在任何 cwd 下成立(生产链 cce_full_run 也是先 insert 再 import)。"""
    code = ("import sys, importlib.util; sys.path = [p for p in sys.path if 'cce-engine/scripts' not in p]; "
            "s = importlib.util.spec_from_file_location('xm', %r); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); print(m.extract_json_robust is not None)"
            % str(ROOT / "scripts/exp_crossmodel_desire.py"))
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=tempfile.gettempdir(), env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"})
    assert p.returncode == 0 and "True" in p.stdout, p.stderr[-300:]


def test_every_gap_id_has_a_gate_here_and_is_registered_closed():
    src = (ROOT / __file__).read_text(encoding="utf-8") if not pathlib.Path(__file__).is_absolute() else pathlib.Path(__file__).read_text(encoding="utf-8")
    for gid in GAP_IDS: assert ("__" + gid.replace("-", "_")) in src, "★ %s 没有闸" % gid
    closed = json.loads((ROOT / "tests/data/ablation_verdicts_v3.json").read_text(encoding="utf-8")).get("★acceptance_gaps_closed_2026_09_24") or {}
    assert set(closed.get("ids", [])) == set(GAP_IDS) and closed.get("gate") == "tests/test_cce_r3_acceptance_gaps.py"
