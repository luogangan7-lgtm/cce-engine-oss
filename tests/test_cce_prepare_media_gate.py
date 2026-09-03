#!/usr/bin/env python3
"""生产入口的媒体声明闸 —— 出站必填, 形状同 guard_profile。

★ 为什么放在入口而不是下游兜底:
  旧 post 档的教训 —— 靠 manifest.chain 在下游判红只是兜底, **入口直接拒绝**
  才让复发结构上不可能(那次复发了三次才根治)。
★ 为什么「闸不可用」也要红:
  闸缺席就是缺席, 不是通过。降级放行等于这条闸不存在。
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREP = os.path.join(ROOT, ".github", "prepare.py")
BASE = {"CONTEXT": "ctx", "GUARD_PROFILE": "g", "PATH": os.environ["PATH"]}


def run(**env):
    e = {**BASE, **env}
    r = subprocess.run([sys.executable, PREP], cwd=ROOT, capture_output=True, text=True,
                       env={**os.environ, **e})
    return r.returncode, r.stdout + r.stderr


IMG = 'see ![x](https://s.io/a.png)'
GOOD = ('{"media_present":true,"items":[{"ref":"https://s.io/a.png",'
        '"state":"not_measured_no_capability","why":"OCR 未进生产路径"}]}')

# ── 出站缺声明 -> 红 ──────────────────────────────────────────────────
for mode in ("outbound_post", "reply"):
    rc, out = run(MODE=mode, TEXT="正文一段")
    assert rc == 1 and "缺 media_declaration" in out, (mode, rc, out[:200])

# ── 有图却声明无图 -> 红 ──────────────────────────────────────────────
rc, out = run(MODE="outbound_post", TEXT=IMG, MEDIA_DECLARATION='{"media_present":false}')
assert rc == 1 and "声明与输入不符" in out, out[:200]

# ── 漏项 -> 红 ────────────────────────────────────────────────────────
rc, out = run(MODE="outbound_post", TEXT=IMG,
              MEDIA_DECLARATION='{"media_present":true,"items":[]}')
assert rc == 1 and ("未出现在声明 items 里" in out or "没有 items" in out), out[:200]

# ── 非法 JSON -> 红(而不是当成没给) ───────────────────────────────────
rc, out = run(MODE="outbound_post", TEXT="正文", MEDIA_DECLARATION="{不是json")
assert rc == 1 and "不是合法 JSON" in out, out[:200]

# ── 如实声明「有图但没能力测」-> 绿 ───────────────────────────────────
rc, out = run(MODE="outbound_post", TEXT=IMG, MEDIA_DECLARATION=GOOD)
assert rc == 0, out[:300]
rc, out = run(MODE="outbound_post", TEXT="纯文本", MEDIA_DECLARATION='{"media_present":false}')
assert rc == 0, out[:300]

# ── ★ 闸不可用不许降级放行 ────────────────────────────────────────────
SRC = open(PREP, encoding="utf-8").read()
assert "不降级放行" in SRC and "errs.append(f\"媒体声明闸不可用" in SRC, \
    "★ ImportError 必须进 errs —— 闸缺席就是缺席, 不是通过"
assert "入口拒绝才让复发结构上不可能" in SRC, \
    "★ 为什么设在入口而非下游, 这个理由要留在原地"

print("test_cce_prepare_media_gate: OK (出站两档缺声明/声明不符/漏项/非法JSON 各自 rc=1 | "
      "如实声明放行 | 闸不可用不降级)")
