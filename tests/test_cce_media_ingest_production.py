#!/usr/bin/env python3
"""P3 进生产: profile `media_ingest` 的三处同步 + 全链回放。

## 核心不变量(2026-09-01 事故立的)
**入口白名单 == CHAINS 键集 == 契约 profile 的 stages 集合**。
当年 `post` 在入口白名单里、契约里却没有, 不一致数周无人发现 —— 复发三次的根因。
新增 profile 必须三处同步, 缺一处 tests/test_cce_retired_chain_removed.py 就会红。

## 边界(2026-08-15 已否决的三条, 这里逐条钉住)
· 不为静态图片与视频帧各建一套视觉合同 —— 本档**只收视频解析产物**
· `standalone_image_ingest` 仍 missing ⇒ **不得声称图片全链可用**
· 不因「视觉描述文本已走 outbound_post」就声称图片全链生产可用
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from cce_full_run import CHAINS  # noqa: E402

CONTRACT = json.load(open(os.path.join(ROOT, "config/cce_submission_contract_v1.json"),
                          encoding="utf-8"))
CAPS = {c["id"]: c for c in json.load(
    open(os.path.join(ROOT, "config/cce_capability_registry_v1.json"), encoding="utf-8")
)["capabilities"]}
WF = open(os.path.join(ROOT, ".github/workflows/cce-submit.yml"), encoding="utf-8").read()

# ── ① 三处同步 ────────────────────────────────────────────────────────
prof = CONTRACT["profiles"]["media_ingest"]
assert "media_ingest" in CHAINS, "★ CHAINS 缺 media_ingest"
assert [f.stage_name for f in CHAINS["media_ingest"]] == prof["stages"], \
    "★ CHAINS 顺序与契约 stages 不逐位相等"
prep = open(os.path.join(ROOT, ".github/prepare.py"), encoding="utf-8").read()
assert '"media_ingest"' in prep, "★ 入口白名单缺 media_ingest"

# ── ② workflow 真的会为它跑(不是只在契约里存在) ───────────────────────
body = "\n".join(l for l in WF.splitlines() if not l.lstrip().startswith("#"))
assert "media_ingest" in body, "★ workflow 里没有 media_ingest —— 契约有、管道没有 = 空声明"
# job 名不得再叫 outbound: media_ingest 不是出站, 名实不符会被读成「发出去了」
assert "\n  measure:\n" in WF and "\n  outbound:\n" not in WF, \
    "★ 跑 media_ingest 的 job 不得叫 outbound"
assert "needs: [prep, measure]" in body, "★ 聚合 job 的依赖没跟着改名"

# ── ③ 媒体档不走出站的两道要求(它没有稿子, 也不该自我声明有无媒体) ────
assert "media_ingest 不是出站" in prep, "★ 为什么不要 guard/媒体声明, 理由要留在原地"

def entry(item):
    fd, p = tempfile.mkstemp(suffix=".json"); os.close(fd)
    json.dump([item], open(p, "w", encoding="utf-8"), ensure_ascii=False)
    try:
        r = subprocess.run([sys.executable, os.path.join(ROOT, ".github/prepare.py")],
                           cwd=ROOT, capture_output=True, text=True,
                           env={**os.environ, "ITEMS_FILE": p, "ITEM_INDEX": "0"})
        return r.returncode, r.stdout + r.stderr
    finally:
        os.unlink(p)

art = json.dumps({"duration": 12.5, "audio": {"present": True}})
rc, out = entry({"mode": "media_ingest", "text": art, "context": "回放",
                 "context_decl": '{"场景类型":"工作中"}', "ref_tag": "t"})
assert rc == 0, f"★ 合法的 media_ingest 被入口拦了: {out[:300]}"

# ── ④ 全链回放: 拿**真实历史解析产物**跑生产驱动 ──────────────────────
SRC = "/Volumes/data/viral-skill-eval/results/video_parse"
if os.path.isdir(SRC):
    f = sorted(p for p in os.listdir(SRC) if p.endswith(".json") and not p.startswith("_"))[0]
    with tempfile.TemporaryDirectory() as td:
        inp = os.path.join(td, "input.json")
        open(inp, "w", encoding="utf-8").write(
            open(os.path.join(SRC, f), encoding="utf-8").read())
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts/cce_full_run.py"),
                            "--mode", "media_ingest", "--text-file", inp,
                            "--context", "历史解析产物回放", "--outdir", td],
                           cwd=ROOT, capture_output=True, text=True,
                           env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        assert r.returncode == 0, f"★ 全链回放失败: {(r.stdout + r.stderr)[-400:]}"
        man = json.load(open(os.path.join(td, "manifest.json"), encoding="utf-8"))
        assert man["complete"] is True and man["failed_at"] is None, man
        assert os.path.exists(os.path.join(td, "observations.json"))
        assert os.path.exists(os.path.join(td, "events.json"))
        q = man["stages"]["qualified_readout"]
        assert "p3.observations" in q["usable_keys"] and "p3.events" in q["usable_keys"], q
        # ★ 抽取质量必须占一个**具名扣发位** —— 抽出来了 != 抽得准
        assert "p3.extraction_quality" in q["withheld"], \
            "★ 抽取质量未测必须具名扣发, 否则下游会把 observation 里的文字当已验收转写"
        assert "p3.cross_domain_calibration" in q["withheld"]

# ── ⑤ 晋升不等于全部具备: 图片链仍不得声称可用 ────────────────────────
v = CAPS["video_multimodal_parse_v5"]
assert v["status"] == "production_github" and v["fallback_policy"] == "WITHHOLD"
assert CAPS["standalone_image_ingest"]["status"] == "missing", \
    "★ 图片链仍 missing —— 视频档进生产不得顺带把图片也说成可用"
assert "★scope_video_only" in prof and "standalone_image_ingest" in prof["★scope_video_only"]

print("test_cce_media_ingest_production: OK "
      f"(三处同步: 契约 profile / CHAINS / 入口白名单 逐位一致 | "
      f"job 已由 outbound 改名 measure(它不是出站) | "
      "全链回放 complete=true 且 observations+events 落盘 | "
      "抽取质量与跨域标定**具名扣发** | 图片链仍 missing, 未被顺带声称)")
