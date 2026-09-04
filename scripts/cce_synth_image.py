#!/usr/bin/env python3
"""确定性合成图片 —— 给 CI 用的图片链素材。

## 为什么不把真实素材提交到公开仓
边界闸 `check_boundary.py` 是**文本闸**: 它 `read_text(errors="ignore")` 逐文件扫身份字面量。
PNG/JPG 的像素里有人脸、有屏幕上的 handle —— **它结构上看不见**, 会给出假绿。
⇒ 公开仓不放任何媒体二进制(由 tests/test_cce_gate_no_binary_media.py 钉住),
  CI 用的图片一律**现场合成**。真实素材的回放只在本机做, 见 probes/image_chain_real_material.py。

## 它能证明什么、不能证明什么
· 能: 图片链在**任何机器上**都能从像素跑到读数(全链回放)
· 能: OCR 对**干净渲染文字**的下限检查(读得出 = 引擎确实在工作)
· ★ **不能**: 当作真实素材的 OCR 准确率。合成图无压缩、无花字、无遮挡、无低对比,
  拿它的命中率去代表真实世界 = 用最容易的样本冒充分布。抽取质量仍记**未测**。
"""
from __future__ import annotations
import os, sys

# 固定文案: 短、无歧义、不含真实身份。改动它会改动下限检查的判据, 属于判据变更。
SYNTH_LINES = ("HEARING TEST", "2026 REPORT")


def synth(path: str, *, lines=SYNTH_LINES, size=(480, 240)) -> dict:
    """写一张确定性图片, 返回其 ground truth。缺 Pillow 直接抛 —— 不静默降级。"""
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new("RGB", size, (255, 255, 255))
    d = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 44)
    except Exception:
        font = ImageFont.load_default(44) if hasattr(ImageFont, "load_default") else ImageFont.load_default()
    for i, t in enumerate(lines):
        d.text((24, 40 + i * 80), t, fill=(0, 0, 0), font=font)
    im.save(path, "PNG", optimize=False)          # 不压缩 ⇒ 同输入同字节
    return {"path": path, "ground_truth": list(lines), "size": list(size)}


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "synth.png"
    print(synth(out))
