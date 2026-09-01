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
assert MAN["instrument_generation"] == 4

# Core 与 Parser 不许有交集(否则把 Core 文件塞进 Parser 就能蒙混过关)
assert not (set(MAN["core_files"]) & set(MAN["parser_plane"]))

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
