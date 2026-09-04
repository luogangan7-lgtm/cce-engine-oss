#!/usr/bin/env python3
"""闸: 公开仓不得含媒体二进制。

## 为什么需要这条闸 —— 边界闸有个结构性盲区
`/Volumes/data/cce-identified-vault/check_boundary.py` 守的是「识别层的真实身份不许进公开仓」,
做法是逐文件 `read_text(encoding="utf-8", errors="ignore")` 做字面匹配。

**它是文本闸。** 一张 PNG 里的人脸、一张截图上渲染的用户名 handle、EXIF 里的作者字段 ——
读成文本全是乱码, 匹配不上, 于是闸**报绿**。
⇒ 「边界闸 PASS」这句话对媒体二进制**不成立**, 而我差点据此把真实素材提交进公开仓。

## 所以闸设在这里
公开仓一张媒体二进制都不放。CI 要图片就**现场合成**(scripts/cce_synth_image.py),
真实素材的回放只在本机做(probes/image_chain_real_material.py)。
这不是「暂时没有图片」, 是**结构上不放** —— 有了这条闸, 边界闸的盲区就够不着公开仓。

## 反向自检
黑名单检查必须自带「它防的是什么」的证据, 否则失效时无声(本项目 2026-09-03 记过四次同类)。
下面第 ② 段现场造一个真 PNG, 断言它会被判出。
"""
import os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif",
             ".mp4", ".mov", ".avi", ".mkv", ".webm",
             ".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"}
SKIP = {".git", "node_modules", "__pycache__", ".venv", "dist", "build", "archive"}


def scan(root: str) -> list[str]:
    hits = []
    for dp, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for f in files:
            if os.path.splitext(f)[1].lower() in MEDIA_EXT:
                hits.append(os.path.relpath(os.path.join(dp, f), root))
    return sorted(hits)


# ── ① 工作树 ──────────────────────────────────────────────────────────
tree = scan(ROOT)
assert not tree, ("★ 公开仓出现媒体二进制, 而边界闸看不见它们的内容:\n  "
                  + "\n  ".join(tree))

# ── ② 反向: 真 PNG 必须被判出(否则这条闸失效时无声) ───────────────────
with tempfile.TemporaryDirectory() as td:
    os.makedirs(os.path.join(td, "sub"))
    # 最小合法 PNG(1x1), 不依赖 Pillow —— 闸不该有媒体依赖
    open(os.path.join(td, "sub", "planted.png"), "wb").write(bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
        "1f15c4890000000a49444154789c6300010000050001"
        "0d0a2db40000000049454e44ae426082"))
    caught = scan(td)
    assert caught == ["sub/planted.png"], f"★ 埋进去的 PNG 没被判出: {caught}"

# ── ③ 索引也不许把媒体登记成公开仓资产 ────────────────────────────────
git_tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
if git_tracked.returncode == 0:
    tracked = [p for p in git_tracked.stdout.split("\n")
               if os.path.splitext(p)[1].lower() in MEDIA_EXT]
    assert not tracked, f"★ git 已跟踪媒体二进制: {tracked[:5]}"
    _P = f"git 已跟踪 {len(git_tracked.stdout.strip().splitlines())} 个文件, 零媒体二进制"
else:
    _P = "非 git 环境: 只扫了工作树"

print("test_cce_gate_no_binary_media: OK (公开仓零媒体二进制 | "
      f"{_P} | 反向: 埋一个真 PNG 会被判出)"
      "\n  ★ 这条闸补的是 check_boundary 的结构盲区: 它 read_text 逐文件扫身份字面量, "
      "PNG 像素里的人脸/屏幕上的 handle 它**看不见**, 会报假绿")
