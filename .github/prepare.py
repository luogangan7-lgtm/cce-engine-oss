#!/usr/bin/env python3
"""投料 + 契约校验(与 Windows runner 同一套规范)。校验不过直接失败, 不进链路。"""
import os, sys

# 门槛由实测定, 不拍脑袋: 9条/193词 虽满足旧门槛(80词/3条)却导致受众读数 3 倍摆动,
# 即「合规不等于够稳」。先提到 1000词/30条, 待稳定性实测后再定终值。
AUDIENCE_SPEC = {"min_words": 1000, "min_utterances": 30}

# 两种投料源: 环境变量(单条) 或 items.json + 索引(批量)
if os.environ.get("ITEMS_FILE"):
    import json as _j
    _items = _j.load(open(os.environ["ITEMS_FILE"], encoding="utf-8"))
    _it = _items[int(os.environ.get("ITEM_INDEX", "0"))]
    mode = (_it.get("mode") or "").strip()
    text = _it.get("text") or ""
    context = (_it.get("context") or "").strip()
    audience = (_it.get("audience") or "").strip()
    ref = (_it.get("ref_tag") or "").strip()
else:
    mode = (os.environ.get("MODE") or "").strip()
    text = os.environ.get("TEXT") or ""
    context = (os.environ.get("CONTEXT") or "").strip()
    audience = (os.environ.get("AUDIENCE") or "").strip()
    ref = (os.environ.get("REF_TAG") or "").strip()

errs = []
if mode not in ("reply", "post"):
    errs.append(f"mode 必须是 reply|post, 收到 {mode!r}")
if not text.strip():
    errs.append("text 不能为空")
if not context:
    errs.append("context 不能为空")

if mode == "post":
    if not ref:
        errs.append("post 模式必填 ref_tag")
    if not audience:
        # 2026-08-09: 旧默认语料仅 9 条/193 词, 实测同一份语料四次运行读出的受众主结
        # pain_seek 在 0.20~0.60 之间摆动(3倍), s6 的参照系不稳到无法支撑二值门。
        # 换为 104 条真人评论快照(8406词, 43倍)。
        d = "corpus/reddit_hearingaids_audience_v2.txt"
        if os.path.exists(d):
            audience = open(d, encoding="utf-8").read().strip()
            print(f"::notice::audience 未提供, 回退仓库默认语料 {d}")
        else:
            errs.append("post 模式必填 audience")
    lines = [l for l in audience.splitlines() if len(l.strip()) > 10]
    words = len(audience.split())
    if words < AUDIENCE_SPEC["min_words"] or len(lines) < AUDIENCE_SPEC["min_utterances"]:
        errs.append(
            f"audience 不符合语料规范(疑似人群画像描述而非受众原话): "
            f"实得 {words}词/{len(lines)}条, 要求 ≥{AUDIENCE_SPEC['min_words']}词/"
            f"≥{AUDIENCE_SPEC['min_utterances']}条。s5受众逆推吃的是目标读者原话。")

if errs:
    for e in errs:
        print(f"::error::{e}")
    sys.exit(1)

os.makedirs("run", exist_ok=True)
open("run/mode", "w", encoding="utf-8").write(mode)
open("run/context", "w", encoding="utf-8").write(context)
open("run/input.txt", "w", encoding="utf-8").write(text)
if audience:
    open("run/audience.txt", "w", encoding="utf-8").write(audience)
if ref:
    open("run/ref.txt", "w", encoding="utf-8").write(ref)
print(f"投料校验通过: mode={mode} text={len(text.split())}词 audience={len(audience.split())}词 ref={ref}")
