# -*- coding: utf-8 -*-
"""闸: 情绪余温 成对读出(2026-09-29 owner 同意加合同字段)。零调用: Jev 用桩。

守: ① 生产请求与实测(probes/s0_residue_profile.py, 预注册 5dc6031)逐字相同 —— state 版式、题集、题面
② 只在 response 模式 + 有 prior_turn 时走; 主值 = Jev 选中值, 完整分布落盘(全占比) ③ 读出「未知」/ 调用失败 ⇒ 未知, 不编
④ 声明优先且不调用 ⑤ 入口: prior_turn 逐字 + sha256 + 身份闸, 经 build_dispatch → prepare → full_run 一路透传; 非 response 拒收。
"""
import copy, hashlib, importlib.util, json, os, pathlib, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
import cce_s0_jev, cce_full_run as fr                                    # noqa: E402
from cce_submission import validate_submission, text_sha256                # noqa: E402
_p = importlib.util.spec_from_file_location("_rp", ROOT / "probes/s0_residue_profile.py"); rp = importlib.util.module_from_spec(_p); _p.loader.exec_module(rp)
READABLE = [f for f in fr.CTX_FACETS if f.get("readable_from_text") in (True, "partial")]
PRIOR, REPLY = "Try lowering the feedback manager.", "That worked, thank you so much for the tip!"
_orig_read = cce_s0_jev.s0_jev_read
_orig_paired = cce_s0_jev.s0_residue_paired


def _ctx(tmp, mode="response", prior=True, decl=None):
    t = pathlib.Path(tmp); (t / "t.txt").write_text(REPLY, encoding="utf-8")
    ctx = {"mode": mode, "text_file": str(t / "t.txt"), "outdir": tmp, "context": "ctx",
           "context_decl": json.dumps(decl, ensure_ascii=False) if decl else None}
    if prior:
        (t / "p.txt").write_text(PRIOR, encoding="utf-8"); ctx["prior_turn_file"] = str(t / "p.txt")
    return ctx


def _run(ctx):
    fr.s0(ctx); return fr.MANIFEST["s0_context"], json.loads((pathlib.Path(ctx["outdir"]) / "s0_context.json").read_text(encoding="utf-8"))


def _stub(monkeypatch, residue_choice="正向余温", fail=False):
    calls = []
    def post(body, key):
        calls.append(body)
        if fail and "OUR PREVIOUS MESSAGE" in body["state"]: return None, "HTTP 503"
        ans = {k: {"choice": "未知", "probabilities": {"未知": 1.0}} for k in body["questions"]}
        if "情绪余温" in body["questions"]:
            ans["情绪余温"] = {"choice": residue_choice, "probabilities": {residue_choice: 0.9, "未知": 0.1}}
        if "触发事件" in body["questions"]: ans["触发事件"] = {"choice": "受挫/出故障", "probabilities": {"受挫/出故障": 1.0}}
        return {"answers": ans}, None
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    monkeypatch.setattr(cce_s0_jev, "s0_jev_read", lambda body, facets: _orig_read(body, facets, post=post))
    monkeypatch.setattr(cce_s0_jev, "s0_residue_paired", lambda prior, reply, facets: _orig_paired(prior, reply, facets, post=post))
    return calls


def test_production_request_is_the_measured_request():
    assert cce_s0_jev.PAIRED_RESIDUE_Q == rp.PAIRED_Q
    assert cce_s0_jev.paired_state(rp.PREV, "x") == rp.state("paired", "x")
    assert [f["key"] for f in READABLE] == [f["key"] for f in rp.FACETS]            # 同一六面题集
    assert cce_s0_jev.PAIRED_READ <= cce_s0_jev.READ_WITHHELD                        # 成对读只救被扣发的面


def test_paired_read_in_response_mode(monkeypatch):
    calls = _stub(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        out, layer = _run(_ctx(tmp))
    paired = [c for c in calls if "OUR PREVIOUS MESSAGE" in c["state"]]
    assert len(paired) == 1 and paired[0]["state"] == cce_s0_jev.paired_state(PRIOR, REPLY)
    assert paired[0]["questions"]["情绪余温"]["instructions"] == cce_s0_jev.PAIRED_RESIDUE_Q and len(paired[0]["questions"]) == 6
    single = [c for c in calls if c not in paired]
    assert single and "情绪余温" not in single[0]["questions"]                          # 只读回应的那次仍不问
    assert layer["facets"]["情绪余温"] == "正向余温" and layer["source"]["情绪余温"] == "成对读出"
    assert layer["成对读出分布"]["情绪余温"] == {"正向余温": 0.9, "未知": 0.1}           # 完整分布落盘(全占比)
    assert out["扣发"] == [] and out["成对读出"] == ["情绪余温"] and out["成对读出分布"] == layer["成对读出分布"]   # 归档只收 manifest


def test_paired_unknown_or_failure_stays_unknown(monkeypatch):
    _stub(monkeypatch, residue_choice="未知")
    with tempfile.TemporaryDirectory() as tmp:
        out, layer = _run(_ctx(tmp))
    assert layer["facets"]["情绪余温"] == "未知" and layer["成对读出分布"]["情绪余温"] and out["扣发"] == []
    _stub(monkeypatch, fail=True)
    with tempfile.TemporaryDirectory() as tmp:
        out, layer = _run(_ctx(tmp))
    assert layer["facets"]["情绪余温"] == "未知" and out["成对读出错误"] == "HTTP 503" and out["扣发"] == ["情绪余温"]


def test_no_prior_turn_keeps_withhold_and_declared_wins(monkeypatch):
    calls = _stub(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        out, _ = _run(_ctx(tmp, prior=False))
    assert out["扣发"] == ["情绪余温"] and not any("OUR PREVIOUS MESSAGE" in c["state"] for c in calls)
    calls = _stub(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        out, layer = _run(_ctx(tmp, decl={"情绪余温": "负向余温"}))
    assert layer["source"]["情绪余温"] == "已声明" and not any("OUR PREVIOUS MESSAGE" in c["state"] for c in calls)


def test_cold_modes_never_pair(monkeypatch):
    calls = _stub(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        _, layer = _run(_ctx(tmp, mode="reply"))
    assert layer["source"]["情绪余温"] == "结构冷读" and not any("OUR PREVIOUS MESSAGE" in c["state"] for c in calls)


# ── 入口 ──
_env = json.loads((ROOT / "examples/cce_submission_subject_chain_v1.json").read_text(encoding="utf-8"))


def _with_prior(mut=None):
    env = copy.deepcopy(_env)
    env["subject_chain"] = json.loads((ROOT / env.pop("subject_chain_path")).read_text(encoding="utf-8")); env.pop("subject_chain_sha256")
    src = json.loads((ROOT / env.pop("response_source_path")).read_text(encoding="utf-8")); env.pop("response_source_sha256")
    src["responses"][0]["prior_turn"] = {"text": PRIOR, "text_sha256": text_sha256(PRIOR)}
    if mut: mut(src["responses"][0]["prior_turn"])
    env["response_source"] = src
    return validate_submission(env)


def test_submission_accepts_and_dispatches_prior_turn():
    v = _with_prior()
    assert v["ok"], v["errors"]
    items = v["normalized"]["subject_dispatch"]["client_payload"]["items"]
    assert items[0]["prior_turn_text"] == PRIOR and all("prior_turn_text" not in it for it in items[1:])


def test_submission_rejects_bad_prior_turn():
    v = _with_prior(lambda p: p.__setitem__("text_sha256", text_sha256("other")))
    assert not v["ok"] and any("prior_turn.text_sha256 does not match" in e for e in v["errors"])
    # 身份闸必须在 **路径引用** 的 source 上也生效(信封级身份闸只看内联内容 —— 这正是本处单独过闸的理由)
    fake = "zq_realhandle_77"; bad = "as u/" + fake + " said"          # 运行时拼(源码里不出现 u/… 字面, 过边界闸)
    src = json.loads((ROOT / _env["response_source_path"]).read_text(encoding="utf-8"))
    src["responses"][0]["prior_turn"] = {"text": bad, "text_sha256": text_sha256(bad)}
    with tempfile.TemporaryDirectory(dir=ROOT) as d:
        f = pathlib.Path(d) / "src.json"; raw = json.dumps(src, ensure_ascii=False); f.write_text(raw, encoding="utf-8")
        env = copy.deepcopy(_env); env["response_source_path"] = str(f.relative_to(ROOT))
        env["response_source_sha256"] = "sha256:" + hashlib.sha256(f.read_bytes()).hexdigest()
        v = validate_submission(env)
    assert not v["ok"] and any("prior_turn" in e and "non-pseudonymous" in e for e in v["errors"]), v["errors"]
    assert not any(fake in e for e in v["errors"])


def _prep(item):
    with tempfile.TemporaryDirectory() as cwd:
        f = pathlib.Path(cwd) / "items.json"; f.write_text(json.dumps([item], ensure_ascii=False), encoding="utf-8")
        r = subprocess.run([sys.executable, str(ROOT / ".github/prepare.py")], cwd=cwd, capture_output=True, text=True,
                           env={**os.environ, "ITEMS_FILE": str(f), "ITEM_INDEX": "0"})
        p = pathlib.Path(cwd) / "run/prior_turn.txt"
        return r.returncode, r.stdout + r.stderr, (p.read_text(encoding="utf-8") if p.exists() else None)


def test_prepare_materializes_prior_turn_only_for_response():
    rc, out, pt = _prep({"mode": "response", "text": REPLY, "context": "ctx", "prior_turn_text": PRIOR})
    assert rc == 0 and pt == PRIOR, out
    rc, out, pt = _prep({"mode": "outbound_post", "text": REPLY, "context": "ctx", "guard_profile": "g", "prior_turn_text": PRIOR})
    assert rc == 1 and "prior_turn_text 只用于 response" in out


def test_workflow_passes_prior_turn_to_response_chain():
    wf = (ROOT / ".github/workflows/cce-submit.yml").read_text(encoding="utf-8")
    assert '$(test -f run/prior_turn.txt && echo "--prior-turn-file run/prior_turn.txt")' in wf


def test_prospective_scorer_reads_manifest_and_withholds_until_n():
    _q = importlib.util.spec_from_file_location("_fs", ROOT / "probes/residue_followup_score.py"); fs = importlib.util.module_from_spec(_q); _q.loader.exec_module(fs)
    assert fs.score([{"score": 0.5, "followed_up": True}] * 5)["verdict"] == "INSUFFICIENT"
    rs = [{"score": 0.9, "followed_up": True}] * 20 + [{"score": -0.5, "followed_up": False}] * 20
    assert fs.score(rs)["verdict"] == "PREDICTIVE"
    rs = [{"score": s, "followed_up": f} for s in (0.1, 0.2) for f in (True, False) for _ in range(10)]
    assert fs.score(rs)["verdict"] == "NOT_PREDICTIVE"
    with tempfile.TemporaryDirectory() as tmp:           # 写包: 逐条 observed_at 进 _meta(记分要用)
        from cce_submission import write_package
        env = copy.deepcopy(_env)
        write_package(env, pathlib.Path(tmp))
        items = json.loads((pathlib.Path(tmp) / "items.json").read_text(encoding="utf-8"))
        assert all(it["_meta"]["observed_at"] for it in items)


def test_prior_turn_canary_example_is_valid():
    env = json.loads((ROOT / "examples/cce_submission_subject_chain_prior_v1.json").read_text(encoding="utf-8"))
    v = validate_submission(env)
    assert v["ok"], v["errors"]
    items = v["normalized"]["subject_dispatch"]["client_payload"]["items"]
    assert len(items) == 8 and all(it.get("prior_turn_text") for it in items)
    assert hashlib.sha1(items[0]["prior_turn_text"].encode()).hexdigest()[:12] == "e925c908bee0"   # = 发布前测量的 post6 正文
