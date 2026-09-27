# -*- coding: utf-8 -*-
"""闸: 生产 s0 的 Jev 接线(owner 2026-09-23 点头)。零调用: Jev 与 MiniMax 都用桩。

守四件事: ① 题目与重测证据逐题相同 ② 有 key 走 Jev, 产物写 read_backend=jev ③ 无 key/失败 回退 MiniMax **且写明回退**
④ MiniMax 回退分支的提示词 = 接线前原文减去 情绪余温 那一行(其余逐字) · 生产模块不读仓外路径。
★ 2026-09-27 owner「做吧」: 情绪余温 结构冷读 —— 不问 Jev/MiniMax, 未声明 ⇒ 首轮无余温; 声明优先; 模型多答不采用;
  STRUCTURAL 与候选合同 experiments/jev/tasks/s0_context.v2.json 的 structural_facets 由本闸钉等。
"""
import hashlib, importlib, importlib.util, json, os, pathlib, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
import cce_s0_jev, cce_full_run as fr
_s = importlib.util.spec_from_file_location("_shadow", ROOT / "probes/s0_jev_shadow.py"); shadow = importlib.util.module_from_spec(_s); _s.loader.exec_module(shadow)
SHADOW = json.loads((ROOT / "results/s0_jev_shadow.json").read_text(encoding="utf-8"))


def _sha(o): return hashlib.sha256(json.dumps(o, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def _ctx(tmp, decl=None, mode="outbound_post"):
    tf = pathlib.Path(tmp) / "t.txt"; tf.write_text("I have worn these aids for two years and the battery died again yesterday.", encoding="utf-8")
    return {"mode": mode, "text_file": str(tf), "outdir": tmp, "context": "ctx", "context_decl": (json.dumps(decl, ensure_ascii=False) if decl else None)}


def _run_s0(ctx):
    """@stage 把返回值放进 MANIFEST, 不返回。"""
    fr.s0(ctx); return fr.MANIFEST["s0_context"]


SENT = [f for f in shadow.READABLE if f["key"] not in cce_s0_jev.STRUCTURAL]   # 生产实际发给 Jev/MiniMax 的面


def test_question_set_identical_to_retest_evidence():
    """钉生产**实际发出的**题: 逐题与影子/重测轮相同, 集合 = 重测集合 − {情绪余温}; 历史集合 sha 仍与存档一致。"""
    assert _sha(cce_s0_jev.jev_questions(shadow.READABLE)) == SHADOW["★Jev 题目集 sha"] == shadow.question_sha()   # 历史: 函数未变
    sent, old = cce_s0_jev.jev_questions(SENT), shadow.jev_questions()
    assert set(old) - set(sent) == {"情绪余温"} and all(sent[k] == old[k] for k in sent) and list(sent) == [k for k in old if k != "情绪余温"]


def test_structural_rule_is_one_source_of_truth():
    task = json.loads((ROOT / "experiments/jev/tasks/s0_context.v2.json").read_text(encoding="utf-8"))
    assert cce_s0_jev.STRUCTURAL == {k: v["value"] for k, v in task["structural_facets"].items()}
    tax = {f["key"]: f for f in json.loads((ROOT / "config/context_taxonomy.json").read_text(encoding="utf-8"))["facets"]}
    assert all(v in tax[k]["values"] for k, v in cce_s0_jev.STRUCTURAL.items())


def test_jev_path_when_key_present(monkeypatch):
    calls = []
    def fake_post(body, key): calls.append((body, key)); return {"answers": {k: {"choice": "受挫/出故障" if k == "触发事件" else "未知", "probabilities": {"x": 1.0}} for k in body["questions"]}}, None
    monkeypatch.setenv("TYPESAFE_API_KEY", "unit-test-key"); monkeypatch.setattr(cce_s0_jev, "s0_jev_read", lambda body, facets: _orig(body, facets, post=fake_post))
    with tempfile.TemporaryDirectory() as tmp:
        out = _run_s0(_ctx(tmp)); layer = json.loads((pathlib.Path(tmp) / "s0_context.json").read_text(encoding="utf-8"))
    assert out["read_backend"] == "jev" and layer["read_backend"] == "jev"
    assert calls and calls[0][1] == "unit-test-key" and calls[0][0]["model"] == cce_s0_jev.MODEL
    assert "情绪余温" not in calls[0][0]["questions"] and len(calls[0][0]["questions"]) == 5          # 不问 情绪余温
    assert layer["facets"]["情绪余温"] == "首轮无余温" and layer["source"]["情绪余温"] == "结构冷读" and out["结构冷读"] == ["情绪余温"]
    assert layer["source"]["触发事件"] == "读出" and out["结构冷读提示"] and "context.declaration" in out["结构冷读提示"]
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
    # ④ 回退提示词 = 接线前原文(影子探针 s0_prompt, sha 与存档一致)减去 情绪余温 那一行, 其余逐字
    emo = next(f for f in shadow.READABLE if f["key"] == "情绪余温")
    line = f"\n  情绪余温: {emo['values']}"
    assert line in shadow.s0_prompt(body) and seen["p"] == shadow.s0_prompt(body).replace(line, "", 1) and "情绪余温" not in seen["p"]
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


def test_declared_emotion_residue_wins_and_is_not_asked(monkeypatch):
    calls = []
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    monkeypatch.setattr(cce_s0_jev, "s0_jev_read", lambda body, facets: (calls.append([f["key"] for f in facets]), _orig(body, facets, post=lambda b, k: ({"answers": {q: {"choice": "在找方案" if q == "进程位置" else "未知", "probabilities": {}} for q in b["questions"]}}, None)))[1])
    with tempfile.TemporaryDirectory() as tmp:
        out = _run_s0(_ctx(tmp, decl={"情绪余温": "负向余温"})); layer = json.loads((pathlib.Path(tmp) / "s0_context.json").read_text(encoding="utf-8"))
    assert layer["facets"]["情绪余温"] == "负向余温" and layer["source"]["情绪余温"] == "已声明" and "情绪余温" not in calls[0]
    assert out["结构冷读"] == [] and out["结构冷读提示"] is None


def test_all_non_structural_declared_means_no_backend_call(monkeypatch):
    monkeypatch.setattr(cce_s0_jev, "s0_jev_read", lambda *a, **k: (_ for _ in ()).throw(AssertionError("backend called")))
    decl = {"进程位置": "在找方案", "触发事件": "受挫/出故障", "关系位置": "已购买", "身体状态": "未提及", "资源状态": "未提及"}
    with tempfile.TemporaryDirectory() as tmp:
        out = _run_s0(_ctx(tmp, decl=decl))
    assert out["read_backend"] == "none" and out["结构冷读"] == ["情绪余温"]


def test_minimax_over_answer_on_emotion_residue_is_ignored(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    import exp_crossmodel_desire
    monkeypatch.setattr(exp_crossmodel_desire, "call_model", lambda *a, **k: (json.dumps({"进程位置": "在找方案", "情绪余温": "正向余温"}, ensure_ascii=False), {}))
    with tempfile.TemporaryDirectory() as tmp:
        _run_s0(_ctx(tmp)); layer = json.loads((pathlib.Path(tmp) / "s0_context.json").read_text(encoding="utf-8"))
    assert layer["facets"]["情绪余温"] == "首轮无余温" and layer["source"]["情绪余温"] == "结构冷读"


def test_structural_alone_does_not_satisfy_the_refusal(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    monkeypatch.setattr(cce_s0_jev, "s0_jev_read", lambda body, facets: _orig(body, facets, post=lambda b, k: ({"answers": {q: {"choice": "未知", "probabilities": {}} for q in b["questions"]}}, None)))
    with tempfile.TemporaryDirectory() as tmp:
        try:
            _run_s0(_ctx(tmp)); raise AssertionError("refusal did not fire")
        except RuntimeError as e:
            assert "拒答" in str(e)
        layer = json.loads((pathlib.Path(tmp) / "s0_context.json").read_text(encoding="utf-8"))
    assert layer["fill_rate"] > 0 and layer["source"]["情绪余温"] == "结构冷读"          # fill>0 仍拒答: 结构冷读不是输入


def test_response_mode_keeps_model_reading_emotion_residue(monkeypatch):
    """response = 对我方内容的进站回复, 有上一轮 ⇒ 不是冷读: 照旧问 6 题(与重测集合逐字相同), 读出的 情绪余温 照用。"""
    calls = []
    def fake_post(body, key): calls.append(body); return {"answers": {k: {"choice": "负向余温" if k == "情绪余温" else "未知", "probabilities": {}} for k in body["questions"]}}, None
    monkeypatch.setenv("TYPESAFE_API_KEY", "k"); monkeypatch.setattr(cce_s0_jev, "s0_jev_read", lambda body, facets: _orig(body, facets, post=fake_post))
    with tempfile.TemporaryDirectory() as tmp:
        out = _run_s0(_ctx(tmp, mode="response")); layer = json.loads((pathlib.Path(tmp) / "s0_context.json").read_text(encoding="utf-8"))
    assert list(calls[0]["questions"]) == list(shadow.jev_questions()) and _sha(calls[0]["questions"]) == SHADOW["★Jev 题目集 sha"]
    assert layer["source"]["情绪余温"] == "读出" and layer["facets"]["情绪余温"] == "负向余温" and out["结构冷读"] == []   # 只读出 情绪余温 也不拒答


def test_structural_only_in_cold_read_modes():
    assert cce_s0_jev.COLD_READ_MODES == {"outbound_post", "reply"} and cce_s0_jev.COLD_READ_MODES <= set(fr.CHAINS)
    assert "response" not in cce_s0_jev.COLD_READ_MODES
    src = (ROOT / "scripts/cce_full_run.py").read_text(encoding="utf-8")
    assert 'ctx = {"mode": a.mode,' in src                                     # main 把模式交给 s0


def test_unknown_mode_keeps_pre_change_behaviour(monkeypatch):
    calls = []
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    monkeypatch.setattr(cce_s0_jev, "s0_jev_read", lambda body, facets: (calls.append([f["key"] for f in facets]), _orig(body, facets, post=lambda b, k: ({"answers": {q: {"choice": "在找方案" if q == "进程位置" else "未知", "probabilities": {}} for q in b["questions"]}}, None)))[1])
    with tempfile.TemporaryDirectory() as tmp:
        out = _run_s0(_ctx(tmp, mode=None))
    assert "情绪余温" in calls[0] and out["结构冷读"] == []


def test_no_offrepo_path_no_key_literal_in_production_module():
    src = (ROOT / "scripts/cce_s0_jev.py").read_text(encoding="utf-8")
    # ★ ".env" 裸串会命中 os.environ(grep 不是闸); 查的是**路径字面量**
    assert "/Volumes/" not in src and "/Users/" not in src and "/.env" not in src and "'.env'" not in src and '".env"' not in src and "apikey_" not in src
    assert 'os.environ.get("TYPESAFE_API_KEY"' in src
    assert "TYPESAFE_API_KEY: ${{ secrets.TYPESAFE_API_KEY }}" in (ROOT / ".github/workflows/cce-submit.yml").read_text(encoding="utf-8")
