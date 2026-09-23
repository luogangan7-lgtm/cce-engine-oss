# -*- coding: utf-8 -*-
"""闸: 生产 s0 的 Jev 接线(owner 2026-09-23 点头)。零调用: Jev 与 MiniMax 都用桩。

守四件事: ① 题目集与重测证据逐字相同 ② 有 key 走 Jev, 产物写 read_backend=jev ③ 无 key/失败 回退 MiniMax **且写明回退**
④ MiniMax 回退分支的提示词与接线前逐字相同(sha 与 results/s0_jev_shadow.json 一致) · 生产模块不读仓外路径。
"""
import hashlib, importlib, importlib.util, json, os, pathlib, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
import cce_s0_jev, cce_full_run as fr
_s = importlib.util.spec_from_file_location("_shadow", ROOT / "probes/s0_jev_shadow.py"); shadow = importlib.util.module_from_spec(_s); _s.loader.exec_module(shadow)
SHADOW = json.loads((ROOT / "results/s0_jev_shadow.json").read_text(encoding="utf-8"))


def _sha(o): return hashlib.sha256(json.dumps(o, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def _ctx(tmp, decl=None):
    tf = pathlib.Path(tmp) / "t.txt"; tf.write_text("I have worn these aids for two years and the battery died again yesterday.", encoding="utf-8")
    return {"text_file": str(tf), "outdir": tmp, "context": "ctx", "context_decl": (json.dumps(decl, ensure_ascii=False) if decl else None)}


def _run_s0(ctx):
    """@stage 把返回值放进 MANIFEST, 不返回。"""
    fr.s0(ctx); return fr.MANIFEST["s0_context"]


def test_question_set_identical_to_retest_evidence():
    """生产题目集 sha == 影子/重测轮登记的 sha; 否则 κ 证据不再适用。"""
    assert _sha(cce_s0_jev.jev_questions(shadow.READABLE)) == SHADOW["★Jev 题目集 sha"] == shadow.question_sha()


def test_jev_path_when_key_present(monkeypatch):
    calls = []
    def fake_post(body, key): calls.append((body, key)); return {"answers": {k: {"choice": "首轮无余温" if k == "情绪余温" else "未知", "probabilities": {"x": 1.0}} for k in body["questions"]}}, None
    monkeypatch.setenv("TYPESAFE_API_KEY", "unit-test-key"); monkeypatch.setattr(cce_s0_jev, "s0_jev_read", lambda body, facets: _orig(body, facets, post=fake_post))
    with tempfile.TemporaryDirectory() as tmp:
        out = _run_s0(_ctx(tmp)); layer = json.loads((pathlib.Path(tmp) / "s0_context.json").read_text(encoding="utf-8"))
    assert out["read_backend"] == "jev" and layer["read_backend"] == "jev"
    assert calls and calls[0][1] == "unit-test-key" and calls[0][0]["model"] == cce_s0_jev.MODEL
    assert layer["facets"]["情绪余温"] == "首轮无余温" and layer["source"]["情绪余温"] == "读出"
    assert not any(v == "已声明" for v in layer["source"].values())


_orig = cce_s0_jev.s0_jev_read


def test_fallback_to_minimax_when_no_key_and_prompt_unchanged(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    seen = {}
    def fake_call(model, p, temperature=0.0, **kw): seen["p"] = p; seen["model"] = model; return json.dumps({"进程位置": "在找方案"}, ensure_ascii=False), {}
    import exp_crossmodel_desire; monkeypatch.setattr(exp_crossmodel_desire, "call_model", fake_call)
    with tempfile.TemporaryDirectory() as tmp:
        out = _run_s0(_ctx(tmp)); body = open(_ctx(tmp)["text_file"], encoding="utf-8").read()[:2000]
    assert out["read_backend"] == "minimax_fallback(NO_TYPESAFE_API_KEY)" and seen["model"] == "M3"
    # ④ 回退提示词与接线前逐字相同: 用影子探针的 s0_prompt(闸已核其等于旧生产提示词)
    assert seen["p"] == shadow.s0_prompt(body)
    assert hashlib.sha256(shadow.s0_prompt("").encode()).hexdigest()[:16] == SHADOW["★MiniMax 提示词 sha"]


def test_fallback_on_jev_error_is_labeled(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k"); monkeypatch.setattr(cce_s0_jev, "s0_jev_read", lambda body, facets: _orig(body, facets, post=lambda b, k: (None, "HTTP 503")))
    import exp_crossmodel_desire; monkeypatch.setattr(exp_crossmodel_desire, "call_model", lambda *a, **k: (json.dumps({"触发事件": "受挫/出故障"}, ensure_ascii=False), {}))
    with tempfile.TemporaryDirectory() as tmp: out = _run_s0(_ctx(tmp))
    assert out["read_backend"] == "minimax_fallback(HTTP 503)"


def test_declared_still_wins_over_jev(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    monkeypatch.setattr(cce_s0_jev, "s0_jev_read", lambda body, facets: _orig(body, facets, post=lambda b, k: ({"answers": {q: {"choice": "受挫/出故障" if q == "触发事件" else "未知", "probabilities": {}} for q in b["questions"]}}, None)))
    with tempfile.TemporaryDirectory() as tmp:
        out = _run_s0(_ctx(tmp, decl={"触发事件": "刚花过钱"})); layer = json.loads((pathlib.Path(tmp) / "s0_context.json").read_text(encoding="utf-8"))
    assert layer["facets"]["触发事件"] == "刚花过钱" and layer["source"]["触发事件"] == "已声明" and out["read_backend"] == "jev"


def test_no_offrepo_path_no_key_literal_in_production_module():
    src = (ROOT / "scripts/cce_s0_jev.py").read_text(encoding="utf-8")
    # ★ ".env" 裸串会命中 os.environ(grep 不是闸); 查的是**路径字面量**
    assert "/Volumes/" not in src and "/Users/" not in src and "/.env" not in src and "'.env'" not in src and '".env"' not in src and "apikey_" not in src
    assert 'os.environ.get("TYPESAFE_API_KEY"' in src
    assert "TYPESAFE_API_KEY: ${{ secrets.TYPESAFE_API_KEY }}" in (ROOT / ".github/workflows/cce-submit.yml").read_text(encoding="utf-8")
