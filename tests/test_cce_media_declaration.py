#!/usr/bin/env python3
"""P3 媒体声明闸的测试。

★ 两个方向同等重要:
  · 漏检 = 一段作品静默消失(本闸要防的)
  · 误报 = 检测器在普通句子上乱响, 结果所有人都学会忽略它 —— 比没有更坏
所以负例和正例一样是硬断言。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from cce_media_declaration import detect, check, modalities  # noqa: E402

# ── 正例: 这些必须检出 ────────────────────────────────────────────────
POS = [
    ("markdown", "看这个 ![before](https://example.com/a.png) 对比", "image"),
    ("扩展名 URL", "图在 https://cdn.site.com/x/y.JPEG 这里", "image"),
    ("视频扩展名", "录了段 https://s.io/clip.mp4", "video"),
    ("音频扩展名", "https://s.io/take1.m4a 是原始录音", "audio"),
    ("reddit 图床", "https://i.redd.it/abc123 见图", "image"),
    ("youtube", "https://youtu.be/dQw4w9WgXcQ 讲得清楚", "video"),
]
for name, txt, kind in POS:
    d = detect(txt)
    assert len(d) == 1, f"★ 漏检/多检 [{name}]: {d}"
    assert d[0]["kind"] == kind, f"[{name}] 类型判错: {d[0]}"

# ── 负例: 这些一个都不许响 ────────────────────────────────────────────
NEG = [
    ("只是提到 image 这个词", "The image of the brand matters more than the audio quality."),
    ("普通链接", "文档在 https://docs.example.com/guide 里"),
    ("代码块里的链接", "```\nfetch('https://example.com/a.png')\n```"),
    ("行内代码", "用 `https://example.com/a.png` 当占位符"),
    ("中文谈论图片", "我拍了照片但没上传, 视频也还没剪。"),
    ("像扩展名但不是 URL", "文件名是 report.png, 我发你邮箱"),
]
for name, txt in NEG:
    d = detect(txt)
    assert d == [], f"★ 误报 [{name}]: {d} —— 乱响的检测器比没有更坏"

# ── 闸: 缺声明 -> 红("没声明" != "没有媒体") ──────────────────────────
ok, e = check("纯文本一段", None)
assert not ok and any("没声明" in x for x in e)

# ── 闸: 有媒体却声明 false -> 红 ──────────────────────────────────────
ok, e = check("![x](https://s.io/a.png)", {"media_present": False})
assert not ok and any("声明与输入不符" in x for x in e)

# ── 闸: 声明 true 但漏了其中一项 -> 红 ────────────────────────────────
ok, e = check("![x](https://s.io/a.png) ![y](https://s.io/b.png)",
              {"media_present": True,
               "items": [{"ref": "https://s.io/a.png", "state": "not_measured_no_capability",
                          "why": "无 OCR 能力"}]})
assert not ok and any("未出现在声明 items 里" in x for x in e)

# ── 闸: 标「没测」却不写为什么 -> 红 ──────────────────────────────────
ok, e = check("![x](https://s.io/a.png)",
              {"media_present": True,
               "items": [{"ref": "https://s.io/a.png", "state": "not_measured_no_capability"}]})
assert not ok and any("没写 why" in x for x in e)

# ── 闸: state 不在枚举 -> 红 ──────────────────────────────────────────
ok, e = check("![x](https://s.io/a.png)",
              {"media_present": True,
               "items": [{"ref": "https://s.io/a.png", "state": "skipped", "why": "懒"}]})
assert not ok and any("不在" in x for x in e)

# ── 正向: 如实声明「有图但没能力测」-> 绿 ─────────────────────────────
ok, e = check("![x](https://s.io/a.png)",
              {"media_present": True,
               "items": [{"ref": "https://s.io/a.png", "state": "not_measured_no_capability",
                          "why": "OCR 仅在 cce_video_parse 组件层, 未进生产路径"}]})
assert ok, e
ok, e = check("纯文本", {"media_present": False})
assert ok, e

# ── ★ complete 的口径: 有图没测时, 两个模态列表必须不等 ───────────────
m = modalities("![x](https://s.io/a.png)",
               {"media_present": True,
                "items": [{"ref": "https://s.io/a.png",
                           "state": "not_measured_no_capability", "why": "无能力"}]})
assert m["modalities_present"] == ["text", "image"], m
assert m["modalities_measured"] == ["text"], m
assert m["modalities_present"] != m["modalities_measured"], \
    "★ 有图未测时两者必须不等 —— 相等就等于把「测了文字」说成「测了整件作品」"
assert "不是" in m["★complete_scope"]

print(f"test_cce_media_declaration: OK ({len(POS)} 正例检出 · {len(NEG)} 负例零误报 | "
      "缺声明/声明不符/漏项/没写why/非法state —— 各自见红 | "
      "有图未测时 present != measured)")
