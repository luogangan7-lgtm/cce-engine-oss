#!/usr/bin/env python3
"""P3 Multimodal 的第一件实事: 让**媒体的存在**不能静默消失。

## 实测出来的问题(2026-09-03)
`.github/prepare.py` 只收 text —— **零媒体感知**。
一条带图的帖子进来, 那张图从不进入系统, 而 manifest 照样判 `complete=true`。
于是「完整测量」这句话覆盖的其实只是这件作品的一部分, 没有任何东西会红。

这正是本项目最在意的那类失败: **不是测错, 是缺席被当成不存在**。

## 本模块不做什么
不做 OCR、不做语音、不做 diarization/prosody —— 那些要模型和真素材,
`scripts/cce_video_parse.py` 已把它们如实标成 `missing_no_capability`。
**能力缺席与声明缺席是两件事**: 前者可以接受, 后者不行。

## 做什么
① 检出输入里的媒体引用; ② 强制一份显式声明; ③ 让读数带上「测了哪些模态」。
`complete=true` 从此只能是「声明过的模态都测了」, 不再能被读成「整件作品都测了」。

## 假阳性是硬约束
一个在普通句子上乱响的检测器比没有更坏(它会训练所有人忽略它)。
所以只认**可定位的引用**(markdown 图片语法 / 带媒体扩展名的 URL / 已知媒体host),
不认「文中提到 image 这个词」。反向用例见 tests/test_cce_media_declaration.py。
"""
from __future__ import annotations

import re

# 只认带扩展名的, 不猜
IMAGE_EXT = r"png|jpe?g|gif|webp|bmp|tiff?|heic|avif"
VIDEO_EXT = r"mp4|mov|webm|mkv|avi|m4v"
AUDIO_EXT = r"mp3|wav|m4a|aac|flac|ogg|opus"

_URL = r"https?://[^\s<>\)\]\"']+"
_EXT_URL = re.compile(rf"({_URL})\.({IMAGE_EXT}|{VIDEO_EXT}|{AUDIO_EXT})\b", re.I)
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\(\s*(" + _URL + r")\s*\)")
# 已知媒体宿主: 这些域名下的链接就是媒体, 即使 URL 不带扩展名
_MEDIA_HOST = re.compile(
    r"https?://(?:[\w.-]+\.)?"
    r"(i\.redd\.it|v\.redd\.it|i\.imgur\.com|imgur\.com|youtu\.be|youtube\.com/watch"
    r"|vimeo\.com|soundcloud\.com|open\.spotify\.com)/[^\s<>\)\]\"']+", re.I)

_EXT_KIND = [(re.compile(rf"\.({IMAGE_EXT})$", re.I), "image"),
             (re.compile(rf"\.({VIDEO_EXT})$", re.I), "video"),
             (re.compile(rf"\.({AUDIO_EXT})$", re.I), "audio")]
_HOST_KIND = {"i.redd.it": "image", "i.imgur.com": "image", "imgur.com": "image",
              "v.redd.it": "video", "youtu.be": "video", "youtube.com/watch": "video",
              "vimeo.com": "video", "soundcloud.com": "audio", "open.spotify.com": "audio"}

# 代码块里的链接是**被讨论的文本**, 不是本作品的媒体
_FENCE = re.compile(r"```.*?```|~~~.*?~~~", re.S)
_INLINE_CODE = re.compile(r"`[^`\n]+`")


class MediaDeclarationError(ValueError):
    """声明与检出不符。★ 绝不降级为 warning —— 警告会被忽略, 这正是要防的。"""


def _strip_code(text: str) -> str:
    return _INLINE_CODE.sub(" ", _FENCE.sub(" ", text))


def _kind(url: str) -> str:
    for pat, k in _EXT_KIND:
        if pat.search(url.split("?")[0]):
            return k
    for host, k in _HOST_KIND.items():
        if host in url.lower():
            return k
    return "unknown"


def detect(text: str, envelope: dict | None = None) -> list[dict]:
    """检出可定位的媒体引用。★ 只认引用, 不认「提到了 image 这个词」。"""
    body = _strip_code(text or "")
    found: dict[str, dict] = {}

    def add(url, how):
        url = url.rstrip(".,;:!?")
        found.setdefault(url, {"ref": url, "kind": _kind(url), "found_by": how})

    for m in _MD_IMAGE.finditer(body):
        add(m.group(1), "markdown_image")
    for m in _EXT_URL.finditer(body):
        add(m.group(0), "url_extension")
    for m in _MEDIA_HOST.finditer(body):
        add(m.group(0), "known_media_host")
    for key in ("media", "attachments", "images", "video", "audio"):
        for item in (envelope or {}).get(key) or []:
            ref = item if isinstance(item, str) else (item.get("ref") or item.get("url") or "")
            if ref:
                add(ref, f"envelope.{key}")
    return sorted(found.values(), key=lambda d: d["ref"])


VALID_STATES = {"measured", "not_measured_no_capability", "not_measured_out_of_scope"}


def check(text: str, declaration: dict | None, envelope: dict | None = None) -> tuple[bool, list[str]]:
    """媒体声明闸。

    声明形状: {"media_present": bool, "items": [{"ref":..., "state": <VALID_STATES>, "why":...}]}
    """
    errs: list[str] = []
    found = detect(text, envelope)
    if declaration is None:
        errs.append("缺 media_declaration —— 「没声明」不等于「没有媒体」, "
                    "必须显式写 media_present=false 才算断言过")
        return False, errs

    present = bool(declaration.get("media_present"))
    items = declaration.get("items") or []
    if found and not present:
        errs.append(f"检出 {len(found)} 处媒体引用 {[f['ref'][:48] for f in found[:3]]} "
                    "却声明 media_present=false —— 声明与输入不符")
    if present and not items:
        errs.append("声明 media_present=true 却没有 items —— 「有媒体」必须逐项落地")

    declared = {i.get("ref") for i in items}
    for f in found:
        if f["ref"] not in declared:
            errs.append(f"检出的媒体 {f['ref'][:60]} 未出现在声明 items 里 —— 漏一项即漏一段作品")
    for i in items:
        st = i.get("state")
        if st not in VALID_STATES:
            errs.append(f"items 里 {str(i.get('ref'))[:40]} 的 state={st!r} 不在 {sorted(VALID_STATES)}")
        elif st != "measured" and not i.get("why"):
            errs.append(f"{str(i.get('ref'))[:40]} 标 {st} 却没写 why —— "
                        "「没测」必须说清为什么, 否则等于静默跳过")
    return (not errs), errs


def modalities(text: str, declaration: dict | None, envelope: dict | None = None) -> dict:
    """给 manifest 用: complete=true 只能是「声明过的模态都测了」, 不是「整件作品都测了」。"""
    found = detect(text, envelope)
    kinds = sorted({f["kind"] for f in found})
    measured = sorted({i.get("ref") for i in (declaration or {}).get("items") or []
                       if i.get("state") == "measured"})
    return {"modalities_present": (["text"] + kinds) if kinds else ["text"],
            "modalities_measured": ["text"] + sorted(
                {_kind(r) for r in measured}) if measured else ["text"],
            "media_refs_found": len(found),
            "media_refs_measured": len(measured),
            "★complete_scope": ("complete=true 覆盖的是 modalities_measured, **不是** modalities_present。"
                                "两者不等时, 这条读数只覆盖了作品的一部分。")}


if __name__ == "__main__":
    import json
    import sys
    txt = sys.stdin.read()
    print(json.dumps({"detected": detect(txt), "modalities": modalities(txt, None)},
                     ensure_ascii=False, indent=1))
