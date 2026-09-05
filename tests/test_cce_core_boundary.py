#!/usr/bin/env python3
"""§44.9 P3 的验收 gate: 新增 Parser 后 CCE Core 文件 diff = 0。

反向测试(文档指定): 故意在 Core 里改一行, CI 必须拦。
"""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cce_core_boundary as cb  # noqa: E402

MANIFEST = os.path.join(ROOT, "config", "cce_core_manifest.json")
MAN = json.load(open(MANIFEST, encoding="utf-8"))

# ── 正向 ───────────────────────────────────────────────────────────────
ok, errors, info = cb.check()
assert ok, f"基线: Core 边界闸当前必须通过: {errors}"
assert info["core_n"] >= 4 and info["parser_n"] >= 3
# ★ 2026-09-05 gen4 → gen6: s1 指纹从 238 字外壳扩到 4403 字完整 prompt。
#   gen5 是被回退的 qwen3.7-max 那代(配额耗尽), 故本代是 6 不是 5。
assert MAN["instrument_generation"] == 6

# Core 与 Parser 不许有交集(否则把 Core 文件塞进 Parser 就能蒙混过关)
assert not (set(MAN["core_files"]) & set(MAN["parser_plane"]))

# ── ★ 新增: 现算仪器哈希必须与清单相符(抓 env 改仪器) ──────────────────
#    只钉文件 sha 有个抓不到的洞: MEASUREMENT_MODEL 是**环境变量**,
#    换它就换仪器却一个文件都不动 ⇒ 旧闸全绿。
exp = MAN["instrument_expected"]
assert exp["instrument_hash"] == "d4cce4c745f3f991"   # gen6
_saved_model = os.environ.get("CCE_MEASUREMENT_MODEL")
import importlib  # noqa: E402
import json as _j  # noqa: E402
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cce_knot_classify as _kc  # noqa: E402
_taxo = _j.load(open(os.path.join(ROOT, "config", "knot_taxonomy.json"), encoding="utf-8"))
_live = _kc.instrument_id(_taxo, k=3, knot_n=5, s1_pairing="round_robin_over_3_s1_draws")
assert _live["instrument_hash"] == exp["instrument_hash"], "现算仪器哈希必须与清单相符"
assert _live["qualification_policy_hash"] == exp["qualification_policy_hash"]

# 反向: 清单里的期望值被改坏 -> 闸必须红
with tempfile.TemporaryDirectory() as td:
    alt = os.path.join(td, "man.json")
    m = json.loads(json.dumps(MAN))
    m["instrument_expected"]["instrument_hash"] = "deadbeefdeadbeef"
    json.dump(m, open(alt, "w"), ensure_ascii=False)
    ok_i, err_i, _ = cb.check(alt)
    assert not ok_i and any("仪器变了" in e for e in err_i), \
        "★ 反向失败: 现算仪器哈希与清单不符却放行 —— 换 env 换模型就抓不到了"
# 反向: 清单缺 instrument_expected -> 红
with tempfile.TemporaryDirectory() as td:
    alt = os.path.join(td, "man.json")
    m = json.loads(json.dumps(MAN)); m.pop("instrument_expected")
    json.dump(m, open(alt, "w"), ensure_ascii=False)
    assert not cb.check(alt)[0], "★ 缺 instrument_expected 必须红"

# ── ★ 新增: 纯重构走 refactor_log, 且必须带行为证据 ────────────────────
log = MAN["refactor_log"]
assert log and all(e.get("reason") and e.get("behavior_evidence") for e in log)
for e in log:
    for t in e["behavior_evidence"]:
        assert os.path.exists(os.path.join(ROOT, t)), f"行为证据 {t} 不存在"
    assert "不足以" in e["★evidence_is_required_because"], \
        "★ 必须写明「仪器哈希没变不足以证明行为没变」, 否则下次就会拿哈希当证据"

# 反向: refactor_log 条目缺行为证据 -> 红(用一个真实漂移来触发)
core_file = "scripts/cce_knot_classify.py"
abs_core = os.path.join(ROOT, core_file)
backup = abs_core + ".coreguard_bak2"
shutil.copy2(abs_core, backup)
try:
    with open(abs_core, "a", encoding="utf-8") as fh:
        fh.write("\n# refactor log reverse test\n")
    live_sha = cb.sha256_of(core_file)
    for bad_entry, want in (
        ({"file": core_file, "to_sha": live_sha, "reason": "x", "behavior_evidence": []},
         "没写 behavior_evidence"),
        ({"file": core_file, "to_sha": live_sha, "reason": "x",
          "behavior_evidence": ["tests/does_not_exist.py"]}, "不存在"),
        ({"file": core_file, "to_sha": live_sha, "reason": "",
          "behavior_evidence": ["tests/test_cce_knot_stability.py"]}, "没写 reason"),
    ):
        with tempfile.TemporaryDirectory() as td:
            alt = os.path.join(td, "man.json")
            m = json.loads(json.dumps(MAN))
            bad_entry["from_sha"] = MAN["core_files"][core_file]
            m["refactor_log"] = [bad_entry]
            json.dump(m, open(alt, "w"), ensure_ascii=False)
            ok_r, err_r, _ = cb.check(alt)
            assert not ok_r and any(want in e for e in err_r), \
                f"★ 反向失败: refactor_log 条目 {want} 却放行"
    # ★ 反向: 只对上 to_sha 但 from_sha 不符 -> 不得豁免(否则 pin 可以被改成垃圾)
    with tempfile.TemporaryDirectory() as td:
        alt = os.path.join(td, "man.json")
        m = json.loads(json.dumps(MAN))
        m["core_files"][core_file] = "0" * 16
        m["refactor_log"] = [{"file": core_file, "from_sha": MAN["core_files"][core_file],
                              "to_sha": live_sha, "reason": "r",
                              "behavior_evidence": ["tests/test_cce_knot_stability.py"]}]
        json.dump(m, open(alt, "w"), ensure_ascii=False)
        assert not cb.check(alt)[0], \
            "★ 反向失败: from_sha 与当前 pin 不符时仍被豁免 —— pin 可被改成任意值"

    # 正向: 补齐的条目应当放行
    with tempfile.TemporaryDirectory() as td:
        alt = os.path.join(td, "man.json")
        m = json.loads(json.dumps(MAN))
        m["refactor_log"] = [{"file": core_file, "from_sha": MAN["core_files"][core_file],
                              "to_sha": live_sha, "reason": "refactor",
                              "behavior_evidence": ["tests/test_cce_knot_stability.py"]}]
        json.dump(m, open(alt, "w"), ensure_ascii=False)
        assert cb.check(alt)[0], "★ 条目补齐(有理由+存在的行为证据)应当放行"
finally:
    shutil.move(backup, abs_core)
assert cb.check()[0], "还原后闸应恢复绿"

# ── 反向 1: 故意在 Core 里改一行 -> 必须红 ─────────────────────────────
core_file = "scripts/cce_knot_classify.py"
abs_core = os.path.join(ROOT, core_file)
backup = abs_core + ".coreguard_bak"
shutil.copy2(abs_core, backup)
try:
    with open(abs_core, "a", encoding="utf-8") as fh:
        fh.write("\n# core boundary reverse test\n")
    ok2, errors2, _ = cb.check()
    assert not ok2, "★ 反向失败: 在 CCE Core 里改了一行, 闸却是绿的 —— 静默换仪器"
    assert any("静默换仪器" in e for e in errors2)
    assert any("无 refactor_log 记录" in e for e in errors2), \
        "★ 报错必须指出「没有 refactor_log」这条路也没走"
    assert any(core_file in e for e in errors2), "报错必须指出是哪个文件漂了"
finally:
    shutil.move(backup, abs_core)
assert cb.check()[0], "还原后闸应恢复绿"

# ── 反向 2: 改了 Core 但同时正当换代 -> 允许 ───────────────────────────
with tempfile.TemporaryDirectory() as td:
    alt = os.path.join(td, "man.json")
    man2 = json.loads(json.dumps(MAN))
    man2["core_files"][core_file] = "0" * 16          # 假装 pin 是旧的
    man2["instrument_generation"] = 5                  # 但同时换代了
    json.dump(man2, open(alt, "w"), ensure_ascii=False)
    ok3, errors3, _ = cb.check(alt)
    # 换代本身不豁免 hash 不符 —— 换代要求的是把 pin 也更新掉。
    assert not ok3, "pin 没更新就换代也不算数: 判据是 pin 与实文件一致"
    man2["core_files"][core_file] = cb.sha256_of(core_file)
    json.dump(man2, open(alt, "w"), ensure_ascii=False)
    assert cb.check(alt)[0], "pin 与 generation 都更新后必须绿"

# ── 反向 3: 把 Core 文件从清单里删掉 -> 不许当成通过 ───────────────────
with tempfile.TemporaryDirectory() as td:
    alt = os.path.join(td, "man.json")
    man3 = json.loads(json.dumps(MAN))
    man3["core_files"]["scripts/does_not_exist.py"] = "deadbeefdeadbeef"
    json.dump(man3, open(alt, "w"), ensure_ascii=False)
    ok4, errors4, _ = cb.check(alt)
    assert not ok4 and any("不是绕过闸的办法" in e for e in errors4), \
        "★ 反向失败: Core 清单里的文件不存在却放行"

# ── 反向 4: Core 与 Parser 重叠 -> 必须红 ──────────────────────────────
with tempfile.TemporaryDirectory() as td:
    alt = os.path.join(td, "man.json")
    man5 = json.loads(json.dumps(MAN))
    man5["parser_plane"] = sorted(set(man5["parser_plane"]) | {core_file})
    json.dump(man5, open(alt, "w"), ensure_ascii=False)
    ok5, errors5, _ = cb.check(alt)
    assert not ok5 and any("同时被声明为 Core 与 Parser" in e for e in errors5), \
        "★ 反向失败: 把 Core 文件也塞进 Parser 清单却放行"

# ── 反向 5: 「新增 Parser」这个动作本身不得让闸变红 ────────────────────
new_parser = os.path.join(ROOT, "scripts", "cce_parser_probe_tmp.py")
with open(new_parser, "w", encoding="utf-8") as fh:
    fh.write('"""临时 parser, 用于验证新增 Parser 不影响 Core 闸。"""\n'
             "def parse(raw):\n    return {'text': raw}\n")
try:
    assert cb.check()[0], \
        "★ 反向失败: 只是新增了一个 Parser, Core 闸却红了 —— 闸把 Parser 层也管进去了"
finally:
    os.remove(new_parser)

print("test_cce_core_boundary: OK "
      f"(Core {info['core_n']} 文件已钉 hash | 改 Core 一行见红且指名道姓 | "
      "移出清单/塞进 Parser/未更新 pin 就换代 各自见红 | 新增 Parser 不受影响)")
