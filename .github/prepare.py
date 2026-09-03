#!/usr/bin/env python3
"""投料 + 契约校验(与 Windows runner 同一套规范)。校验不过直接失败, 不进链路。"""
import os, sys

# 两种投料源: 环境变量(单条) 或 items.json + 索引(批量)
if os.environ.get("ITEMS_FILE"):
    import json as _j
    _items = _j.load(open(os.environ["ITEMS_FILE"], encoding="utf-8"))
    _it = _items[int(os.environ.get("ITEM_INDEX", "0"))]
    mode = (_it.get("mode") or "").strip()
    text = _it.get("text") or ""
    context = (_it.get("context") or "").strip()
    audience = (_it.get("audience") or "").strip()
    cdecl = (_it.get("context_decl") or "").strip()
    ref = (_it.get("ref_tag") or "").strip()
    refpost = (_it.get("ref_post") or "").strip()
    reader_text = _it.get("reader_text") or ""
    guard_profile = (_it.get("guard_profile") or "").strip()
    media_decl = _it.get("media_declaration")
    submission_meta = _it.get("_meta") or {}
else:
    mode = (os.environ.get("MODE") or "").strip()
    text = os.environ.get("TEXT") or ""
    context = (os.environ.get("CONTEXT") or "").strip()
    audience = (os.environ.get("AUDIENCE") or "").strip()
    cdecl = (os.environ.get("CONTEXT_DECL") or "").strip()
    ref = (os.environ.get("REF_TAG") or "").strip()
    refpost = (os.environ.get("REF_POST") or "").strip()
    reader_text = os.environ.get("READER_TEXT") or ""
    guard_profile = (os.environ.get("GUARD_PROFILE") or "").strip()
    media_decl = os.environ.get("MEDIA_DECLARATION")
    submission_meta = {}

errs = []
# 2026-09-01: 摘掉 "post"。旧九环节链(s0-s8)已于 2026-08-13 退役, 契约里从来没有
# post 这一档 —— 但入口一直允许它, 于是「拿退役组件当现行标准」复发了三次
# (08-13 旧 s0-s8 当尺子 / 08-14 s8 写进判注 / 08-14 帖15 九条 run 全跑旧链)。
# 靠 manifest.chain 断言在下游判红只是兜底; 入口直接拒绝才让复发结构上不可能。
if mode not in ("reply", "response", "outbound_post"):
    errs.append(f"mode 必须是 reply|response|outbound_post, 收到 {mode!r} "
                f"(post = 已退役的旧九环节链, 2026-09-01 从入口移除)")
if not text.strip():
    errs.append("text 不能为空")
if not context:
    errs.append("context 不能为空")
CTX_KEYS = None
if cdecl:
    try:
        import json as _j
        _d = _j.loads(cdecl)
        if not isinstance(_d, dict) or not _d:
            errs.append("context_decl 必须是非空 JSON 对象")
        else:
            _t = _j.load(open("config/context_taxonomy.json", encoding="utf-8"))
            CTX_KEYS = {f["key"]: f["values"] for f in _t["facets"]}
            for k, v in _d.items():
                if k not in CTX_KEYS:
                    errs.append(f"context_decl 面名不在分类学里: {k!r} (合法: {list(CTX_KEYS)})")
                elif v not in CTX_KEYS[k]:
                    errs.append(f"context_decl 取值不合法: {k}={v!r} (合法: {CTX_KEYS[k]})")
    except Exception as e:
        errs.append(f"context_decl 不是合法 JSON: {e}")

if mode in ("reply", "outbound_post") and not guard_profile:
    errs.append("出站模式必填 guard_profile")

# ── 媒体声明: 出站必填 ────────────────────────────────────────────────
# 2026-09-03 实测: 本文件此前**零媒体感知**, 只收 text。带图的帖子里那张图从不进系统,
# 而 manifest 照样 complete=true —— 那句「完整测量」覆盖的其实只是作品的一部分。
# 这是「静默缺席」不是「能力不足」: 媒体内容测不了可以接受, 存在被吞掉不行。
# 形状同 guard_profile —— **入口拒绝才让复发结构上不可能**(旧 post 档就是这么根治的)。
if mode in ("reply", "outbound_post"):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
    try:
        from cce_media_declaration import check as _media_check
        import json as _mj
        _d = None
        if media_decl:
            _d = media_decl if isinstance(media_decl, dict) else _mj.loads(media_decl)
        _ok, _me = _media_check(text, _d, envelope=_it if os.environ.get("ITEMS_FILE") else None)
        if not _ok:
            errs.extend(f"media_declaration: {m}" for m in _me)
    except ImportError as _e:
        errs.append(f"媒体声明闸不可用({_e}) —— **不降级放行**: 闸缺席就是缺席, 不是通过")
    except ValueError as _e:
        errs.append(f"media_declaration 不是合法 JSON: {_e}")
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
    open("run/ref_tag", "w", encoding="utf-8").write(ref)      # 仅元数据, 不进链路
if refpost:
    open("run/ref.txt", "w", encoding="utf-8").write(refpost)  # s8 的上一篇正文
if cdecl:
    open("run/context_decl.json", "w", encoding="utf-8").write(cdecl)
    print(f"::notice::情境声明已落盘: {cdecl}")
if reader_text:
    open("run/reader.txt", "w", encoding="utf-8").write(reader_text)
if guard_profile:
    open("run/guard_profile", "w", encoding="utf-8").write(guard_profile)
if submission_meta:
    open("run/submission_meta.json", "w", encoding="utf-8").write(
        _j.dumps(submission_meta, ensure_ascii=False, indent=2))
print(f"投料校验通过: mode={mode} text={len(text.split())}词 audience={len(audience.split())}词 ref_tag={ref} ref_post={len(refpost.split())}词 guard_profile={guard_profile}")
