#!/usr/bin/env python3
"""产出方 → 入口 的媒体声明闭环 —— 这条测试为一次真实事故而设。

## 事故(2026-09-03)
我给 `.github/prepare.py` 加了 `media_declaration` 必填, **却没同步 cce_submission.py**。
`normalized_items` 两档(outbound_post / reply)都不带这个字段
⇒ **每一次出站都会在入口红**。生产被我打断了一小时。

★ 通用教训: **给入口加必填字段, 必须同时改产出方**, 否则就是把生产打断。
   这条测试跑的是**真闭环**: 产出方造 item → 喂给入口 → 入口必须放行。
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cce_submission as S  # noqa: E402

PREP = os.path.join(ROOT, ".github", "prepare.py")


def through_entry(item):
    """把产出方造的 item 真喂给生产入口, 返回 (rc, 输出)。"""
    fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd)
    json.dump([item], open(path, "w", encoding="utf-8"), ensure_ascii=False)
    try:
        r = subprocess.run([sys.executable, PREP], cwd=ROOT, capture_output=True, text=True,
                           env={**os.environ, "ITEMS_FILE": path, "ITEM_INDEX": "0"})
        return r.returncode, r.stdout + r.stderr
    finally:
        os.unlink(path)


BASE = {"mode": "outbound_post", "context": "r/HearingAids 技术讨论",
        "guard_profile": "daerdo", "ref_tag": "t"}

# ── 闭环 1: 纯文本 —— 产出方自动填 media_present=false, 入口放行 ────────
txt = "Your aids keep the mics on while you are streaming."
item = {**BASE, "text": txt, "media_declaration": S._media_declaration(txt)}
assert item["media_declaration"]["media_present"] is False
rc, out = through_entry(item)
assert rc == 0, f"★ 纯文本出站被入口拦了 —— 生产断了: {out[:300]}"

# ── 闭环 2: 带图 —— 自动填出 items 且标 not_measured, 入口仍放行 ────────
txt2 = "before/after ![x](https://i.redd.it/abc123)"
item2 = {**BASE, "text": txt2, "media_declaration": S._media_declaration(txt2)}
d = item2["media_declaration"]
assert d["media_present"] is True and len(d["items"]) == 1, d
assert d["items"][0]["state"] == "not_measured_no_capability"
assert d["items"][0]["why"], "★ 标未测必须写为什么"
rc, out = through_entry(item2)
assert rc == 0, f"★ 带图但如实声明的出站被拦了: {out[:300]}"

# ── ★ 反向: 产出方漏填 -> 入口必须红(闸没被自动填架空) ─────────────────
rc, out = through_entry({**BASE, "text": txt})
assert rc == 1 and "缺 media_declaration" in out, \
    "★ 漏填时入口必须红 —— 否则自动填就把这道闸架空了"

# ── ★ 反向: 谎报无媒体 -> 入口必须红(自动填不是橡皮图章) ───────────────
rc, out = through_entry({**BASE, "text": txt2,
                         "media_declaration": {"media_present": False}})
assert rc == 1 and "声明与输入不符" in out, \
    "★ 手写谎报必须红 —— 检测器与入口用的是同一份判断"

# ── 产出方两档都必须填(reply 也不能漏) ────────────────────────────────
src = open(os.path.join(ROOT, "scripts", "cce_submission.py"), encoding="utf-8").read()
assert src.count("_media_declaration(") >= 3, \
    "★ outbound_post 与 reply 两档都要填(加上定义共 3 处)"
assert "加必填字段必须同时改产出方" in src, \
    "★ 这次事故的教训要留在原地, 不能只写在提交信息里"

print("test_cce_submission_media_roundtrip: OK "
      "(产出方→入口 真闭环: 纯文本/带图 各自放行 | "
      "漏填与谎报 各自见红(自动填没架空闸) | 两档都填)")
