# -*- coding: utf-8 -*-
"""闸: reply 链 reader_baseline ∥ s1_readout 重叠执行(owner 2026-09-23「把两次 knot_classify 并发化」)。零调用: 分类器用 sleep 桩。

守: ① 真的重叠(墙钟 < 两段之和) ② 产出与串行**同形同值**, manifest.chain 顺序不变 ③ reader 输入 = s0 之前的 context(与串行逐字相同)
    ④ 后台段失败 ⇒ failed_at=reader_baseline · complete=false · 退出码 1 ⑤ CCE_SERIAL_STAGES=1 ⇒ 无后台, 逐段串行 ⑥ 无后台段的链(outbound_post)不受影响。
"""
import json, os, pathlib, subprocess, sys, tempfile, textwrap, time

ROOT = pathlib.Path(__file__).resolve().parents[1]
SLEEP = 0.6


def _fake_classify_src(fail_reader=False, fail_s0=False):
    return textwrap.dedent(f'''
        import json, sys, time, os
        sys.path.insert(0, {str(ROOT / "scripts")!r})
        import cce_full_run as fr
        calls = []
        def fake(tf, context, k, out):
            calls.append({{"text_file": tf, "context": context, "k": k, "out": out, "t": time.time()}})
            if {fail_reader!r} and out.endswith("reader_baseline.json"): raise RuntimeError("READER_BOOM")
            time.sleep({SLEEP})
            d = {{"stage1": {{"k_ok": k, "tops": {{"desire": "x"}}, "within_js": {{"desire": 0.01, "need": 0.01, "emotion": 0.01, "action": 0.01}}, "layers": {{"emotion_vec": [0.5, 0.5] + [0.0] * 11}}, "k_requested": k, "k_attempted": k, "k_valid": k, "k_abstained": 0}},
                 "stage2": {{"knots": [{{"key": "K1", "weight": 1.0}}], "sampling": {{"top1_stable": True}}}}}}
            json.dump(d, open(out, "w")); return d
        fr.run_knot_classify = fake
        def _s0(ctx):
            if {fail_s0!r}: raise RuntimeError("S0_BOOM")
            ctx["context"] = ctx["context"] + " 【情境】{{}}"; return {{"fill_rate": 0.5}}
        fr.s0 = fr.stage("s0_context")(_s0)
        for name in ("s2_knots", "s3_emotion_policy", "s4_guard", "qualified_readout"):
            setattr(fr, {{"s2_knots": "s2", "s3_emotion_policy": "s3", "s4_guard": "s4", "qualified_readout": "qualified"}}[name], fr.stage(name)(lambda ctx: {{}}))
        fr.CHAINS["reply"] = [fr.reader_baseline, fr.s0, fr.s1, fr.s2, fr.s3, fr.s4, fr.qualified]
        fr.CHAINS["outbound_post"] = [fr.s0, fr.s1, fr.s2, fr.s3, fr.s4, fr.qualified]
        t0 = time.time()
        try: fr.main()
        except SystemExit as e: rc = e.code
        json.dump({{"rc": rc, "wall": time.time() - t0, "calls": calls}}, open(os.path.join(sys.argv[sys.argv.index("--outdir") + 1], "_probe.json"), "w"))
    ''')


def _run(mode, serial=False, fail_reader=False, fail_s0=False):
    tmp = tempfile.mkdtemp(); d = pathlib.Path(tmp)
    (d / "in.txt").write_text("draft text", encoding="utf-8"); (d / "reader.txt").write_text("reader text", encoding="utf-8"); (d / "h.py").write_text(_fake_classify_src(fail_reader, fail_s0), encoding="utf-8")
    env = dict(os.environ, CCE_SERIAL_STAGES="1" if serial else "0")
    subprocess.run([sys.executable, str(d / "h.py"), "--mode", mode, "--text-file", str(d / "in.txt"), "--context", "C0", "--outdir", tmp, "--reader-file", str(d / "reader.txt")], capture_output=True, text=True, cwd=ROOT, env=env, timeout=120)
    return json.loads((d / "_probe.json").read_text()), json.loads((d / "manifest.json").read_text(encoding="utf-8"))


def test_overlap_is_real_and_output_same_as_serial():
    po, mo = _run("reply"); ps, ms = _run("reply", serial=True)
    assert po["rc"] == 0 and ps["rc"] == 0 and mo["complete"] and ms["complete"]
    assert po["wall"] < 2 * SLEEP - 0.1 and ps["wall"] >= 2 * SLEEP - 0.05, (po["wall"], ps["wall"])           # ① 真的重叠
    assert mo["chain"] == ms["chain"] == ["reader_baseline", "s0_context", "s1_readout", "s2_knots", "s3_emotion_policy", "s4_guard", "qualified_readout"]
    assert list(mo["stages"]) == list(ms["stages"])                                                             # ② stages 键序不变
    strip = lambda r: {k: v for k, v in r.items() if k not in ("sec", "overlapped_with")}
    assert strip(mo["stages"]["reader_baseline"]) == strip(ms["stages"]["reader_baseline"]) and "deferred_until" not in mo["stages"]["reader_baseline"]
    assert mo["stages"]["reader_baseline"]["overlapped_with"] == "s1_readout" and "overlapped_with" not in ms["stages"]["reader_baseline"]
    rc_o = next(c for c in po["calls"] if c["out"].endswith("reader_baseline.json")); rc_s = next(c for c in ps["calls"] if c["out"].endswith("reader_baseline.json"))
    assert rc_o["context"] == rc_s["context"] == "C0" and rc_o["k"] == rc_s["k"] == 3                        # ③ reader 输入 = s0 之前 context
    s1_o = next(c for c in po["calls"] if c["out"].endswith("s1_readout.json")); assert s1_o["context"].startswith("C0 【情境】")


def test_deferred_failure_is_attributed_to_reader_baseline():
    p, m = _run("reply", fail_reader=True)
    assert p["rc"] == 1 and m["complete"] is False and m["failed_at"] == "reader_baseline"
    assert m["stages"]["reader_baseline"]["status"] == "FAIL" and "READER_BOOM" in m["stages"]["reader_baseline"]["error"]
    assert m["stages"]["s1_readout"]["status"] == "OK"     # s1 已跑完才收后台段


def test_chain_without_deferred_stage_unaffected():
    p, m = _run("outbound_post")
    assert p["rc"] == 0 and m["complete"] and "reader_baseline" not in m["stages"] and len(p["calls"]) == 1


def test_serial_env_has_no_background_and_single_mode_never_defers():
    src = (ROOT / "scripts/cce_full_run.py").read_text(encoding="utf-8")
    assert 'ctx["_overlap"] = os.environ.get("CCE_SERIAL_STAGES") != "1"' in src
    assert src.count('"_overlap"') == 2, "★ _overlap 只在 main() 置位; 单环节模式(main_single)与其他调用方默认不重叠"
    assert "DEFER_UNTIL = {\"reader_baseline\": \"s1_readout\"}" in src


def test_early_exit_still_joins_background_stage():
    """s0 失败 ⇒ 链在 s1 之前退出, 但后台 reader 段必须被收回: 条目是真产出(overlapped_with), 不是占位(deferred_until), 且 failed_at 仍是链序最早的失败段。"""
    p, m = _run("reply", fail_s0=True)
    assert p["rc"] == 1 and m["failed_at"] == "s0_context"
    rb = m["stages"]["reader_baseline"]; assert rb["status"] == "OK" and "overlapped_with" in rb and "deferred_until" not in rb and "tops" in rb


def test_reader_binds_context_snapshot_before_s0():
    """★ 静态守: 后台段的 context 必须是 submit 时绑定的快照(位置实参), 不能是 lambda 里延迟读 ctx["context"] —— 那会与 s0 的追加竞态, 行为测试抓不住。"""
    src = (ROOT / "scripts/cce_full_run.py").read_text(encoding="utf-8")
    assert 'context = ctx["context"]' in src and '_DEFER_EX.submit(run_knot_classify, rf, context, ctx["k"], out)' in src
    assert 'submit(lambda' not in src
