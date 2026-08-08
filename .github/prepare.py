#!/usr/bin/env python3
"""投料 + 契约校验(与 Windows runner 同一套规范)。校验不过直接失败, 不进链路。"""
import os, sys

AUDIENCE_SPEC = {"min_words": 80, "min_utterances": 3}

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
        d = "corpus/reddit_hearingaids_utterances.txt"
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
