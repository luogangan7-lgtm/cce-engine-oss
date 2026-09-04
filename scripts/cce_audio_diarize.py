#!/usr/bin/env python3
"""说话人分离(3D-Speaker, **无 token 路径**) —— 谁在什么时候说话。

## 为什么是这条路径
`pyannote/speaker-diarization-3.1` 是 HF **受限模型**。但两件事我原来搞混了:
① `pyannote.audio` 是 **MIT 开源包**, 受限的是**权重** —— 装包无需 token
② 3D-Speaker 的默认路径 `include_overlap=False` **根本不碰** pyannote 权重
   (源码: `if include_overlap and hf_access_token is None: raise`), 走 ModelScope CAM++ 权重
⇒ 无账号、无 token、无点击条款、无许可限制 —— **四项分别成立**(不是一个笼统的「开放」)。

## 实测(2026-09-04, VoxConverse dev n=20, 判据 profile 冻结)
· DER STRICT(collar=0, 计重叠) **0.1004** · LEGACY(collar=0.25, 不计重叠) **0.0338**
· 官方报 0.1175 但**未注明 profile** ⇒ 只作量级参考, 不作验收线
· CPU RTF 中位 **0.133**(本机铸值; 官方无同口径数字)
· ★ 说话人**数**预测正确 **14/20** —— **DER 低不等于人数对**, 两者是不同读数

## 它**不**产出什么
· **不检测重叠语音**(include_overlap=False 的结构性代价, 如实标注)
· **不做说话人身份识别** —— 只给 speaker_0/1/2 这样的**局部标签**, 跨录音不可比,
  更不得与任何真实身份关联(识别层的事由边界闸管)
"""
from __future__ import annotations

import os
import sys

TOOL = "/Volumes/data/cce-eval-corpora/tools/3D-Speaker"
# 结构闸: 产出里不得出现身份类字段。局部标签 != 身份。
FORBIDDEN = ("identity", "name", "person_id", "real_name", "身份", "姓名", "真名")


def available() -> bool:
    if not os.path.isdir(TOOL):
        return False
    try:
        import modelscope, torch, soundfile  # noqa: F401
        return True
    except Exception:
        return False


def diarize(path: str, *, speaker_num: int | None = None) -> dict:
    """返回 {status, segments:[{start,end,speaker}], n_speakers, ...}。

    ★ 三态: ok / not_available(依赖或工具缺席) / failed(这一条跑挂了)。
    ★ **绝不**开 include_overlap —— 那会要求 HF 受限模型的 token。
    """
    out = {"status": "not_available", "implementation": "3D-Speaker CAM++",
           "include_overlap": False, "segments": None, "n_speakers": None, "error": None,
           "★overlap_not_detected": "include_overlap=False ⇒ **结构上不检测重叠语音**",
           "★labels_are_local": "speaker_N 是**本录音内的局部标签**, 跨录音不可比, 且与任何真实身份无关"}
    if not available():
        out["error"] = f"3D-Speaker 工具或依赖缺席({TOOL})"
        return out
    try:
        import warnings; warnings.filterwarnings("ignore")
        if TOOL not in sys.path:
            sys.path.insert(0, TOOL)
        from speakerlab.bin.infer_diarization import Diarization3Dspeaker
        pipe = Diarization3Dspeaker(device="cpu", include_overlap=False,
                                    hf_access_token=None, speaker_num=speaker_num)
        segs = pipe(path)
        rows = [{"start": round(float(s), 3), "end": round(float(e), 3),
                 "speaker": f"speaker_{int(k)}"} for s, e, k in segs]
        out.update(status="ok", segments=rows,
                   n_speakers=len({r["speaker"] for r in rows}))
        _guard(out)
        return out
    except Exception as e:                                        # noqa: BLE001
        out.update(status="failed", error=f"{type(e).__name__}: {str(e)[:160]}")
        return out


def _guard(out: dict) -> None:
    """结构上挡住「把局部标签写成身份」。字段名出现即抛, 不靠注释约束。"""
    import json as _j
    blob = _j.dumps(out, ensure_ascii=False).lower()
    for bad in FORBIDDEN:
        if f'"{bad}"' in blob:
            raise RuntimeError(f"★ 说话人分离产出里出现被禁字段 {bad!r} —— "
                               "speaker_N 是局部标签, 不是身份; 身份的事由识别层与边界闸管")


if __name__ == "__main__":
    import json
    r = diarize(sys.argv[1])
    r["segments"] = (r["segments"] or [])[:5]
    print(json.dumps(r, ensure_ascii=False, indent=1))
