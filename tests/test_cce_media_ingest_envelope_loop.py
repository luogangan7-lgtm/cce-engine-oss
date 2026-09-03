#!/usr/bin/env python3
"""从 **envelope** 起的闭环 —— 这条测试为两个漏网 bug 而设。

## 我之前的测试为什么没抓到
`test_cce_media_ingest_production.py` 从**手造的 normalized item** 开始,
于是完全跳过了 `cce_submission.py`。而两个 bug 都在那里:
  ① `PROFILES` 是写死的三档 ⇒ media_ingest envelope **在打包就被拒**, prep 会失败
  ② 逐 item 规范化块被 `if profile in {"outbound_post","outbound_reply"}` 罩着
     ⇒ 我加的分支是**死代码**, 打包**静默产出 0 个 item**(矩阵为空, 下游跑 0 个 job 却「成功」)
★ 我却已经声称「P3 进生产」。**从真入口起的闭环才算测过。**

## 修法都是同一条: 单一真相源
profile 白名单与逐 item 必填字段**都改为从契约现读**, 不再在代码里写第二张表。
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cce_submission as SUB  # noqa: E402

CONTRACT = json.load(open(os.path.join(ROOT, "config/cce_submission_contract_v1.json"),
                          encoding="utf-8"))

# ── ① profile 白名单必须**现读契约**, 不许写死 ────────────────────────
assert SUB.PROFILES == set(CONTRACT["profiles"]), \
    f"★ 白名单与契约不一致: {sorted(SUB.PROFILES)} vs {sorted(CONTRACT['profiles'])}"
src = open(os.path.join(ROOT, "scripts", "cce_submission.py"), encoding="utf-8").read()
assert 'PROFILES = {"outbound_post"' not in src, "★ 写死的白名单不得复活"
assert "_CONTRACT[\"profiles\"][profile][\"required_per_item\"]" in src, \
    "★ 必填字段也必须现读契约 —— 两张表必然漂移"

# ── ② 造一个真 envelope, 走完整打包 ───────────────────────────────────
def envelope(profile="media_ingest", text=None):
    tmpl = json.load(open(os.path.join(ROOT, "examples/cce_submission_outbound_post_v1.json"),
                          encoding="utf-8"))
    it = json.loads(json.dumps(tmpl["items"][0]))
    it.pop("guard_profile", None)          # 媒体档没有稿子, 不挂合规闸
    body = text if text is not None else json.dumps(
        {"duration": 9.5, "audio": {"present": True, "transcript": "x"},
         "ocr": {"0.5": ["a"]}, "frames": [{"ts": 0.5, "path": "/tmp/f.jpg"}]})
    it.update({"job_id": "job:media:loop", "content_id": "content:media_parse:loop",
               "text": body, "text_sha256": "sha256:" + hashlib.sha256(body.encode()).hexdigest()})
    return {**tmpl, "profile": profile, "submission_id": "media:loop:test", "items": [it]}


def package(env):
    d = tempfile.mkdtemp()
    fd, p = tempfile.mkstemp(suffix=".json"); os.close(fd)
    json.dump(env, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    try:
        r = subprocess.run([sys.executable, "scripts/cce_submission.py", p, "--outdir", d],
                           cwd=ROOT, capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr, d
    finally:
        os.unlink(p)


rc, out, pkg = package(envelope())
assert rc == 0, f"★ media_ingest envelope 打不了包 —— prep 会失败, 根本走不到 measure: {out[-400:]}"
items = json.load(open(os.path.join(pkg, "items.json"), encoding="utf-8"))
assert len(items) == 1, f"★ 打包产出 {len(items)} 个 item —— 空矩阵 = 下游跑 0 个 job 却「成功」"
assert items[0]["mode"] == "media_ingest", items[0]
assert "guard_profile" not in items[0] and "media_declaration" not in items[0], \
    "★ 媒体档不该带 guard_profile / media_declaration"
assert json.load(open(os.path.join(pkg, "normalized.json"),
                      encoding="utf-8"))["profile"] == "media_ingest"

# ── ③ ★ 反向: 静默空矩阵必须红(这正是漏掉的那个 bug 的形状) ───────────
bad = envelope(); bad["items"] = []
rc2, out2, _ = package(bad)
assert rc2 != 0, "★ 空 items 竟然打包成功 —— 静默空矩阵"

# ── ④ 打包出来的 item 真能过入口 ──────────────────────────────────────
fd, ip = tempfile.mkstemp(suffix=".json"); os.close(fd)
json.dump(items, open(ip, "w", encoding="utf-8"), ensure_ascii=False)
try:
    r = subprocess.run([sys.executable, ".github/prepare.py"], cwd=ROOT,
                       capture_output=True, text=True,
                       env={**os.environ, "ITEMS_FILE": ip, "ITEM_INDEX": "0"})
    assert r.returncode == 0, f"★ 打包产物过不了入口: {(r.stdout + r.stderr)[-300:]}"
    assert open(os.path.join(ROOT, "run", "mode"), encoding="utf-8").read().strip() == "media_ingest"
finally:
    os.unlink(ip)
    import shutil
    shutil.rmtree(os.path.join(ROOT, "run"), ignore_errors=True)

print("test_cce_media_ingest_envelope_loop: OK "
      "(从 envelope 起: 打包→items→入口 全通 · profile/必填 均现读契约 | "
      "空矩阵见红 | 媒体档不带 guard/媒体声明)")
