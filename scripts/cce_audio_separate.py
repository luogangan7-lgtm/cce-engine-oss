#!/usr/bin/env python3
"""音频源分离(demucs htdemucs) —— 把混音拆成 vocals / drums / bass / other。

## 它为什么在这里
韵律指标(f0 / 能量 / 语速代理)算在**混音**上会被 BGM 污染。分离出人声轨再算, 理论上更干净。
★ 但「更干净」是**待测断言**, 不是前提 —— 见 probes/prosody_on_separated_vs_mixed.py 的实测。

## 它产出什么、**不**产出什么
· 产出: 四源的**能量占比**(0–1, 和为 1) + 人声轨波形
· ★ **不**产出: 「有几个人说话」「谁在说」—— 那是说话人分离(diarization), 是另一件事,
  且需要 pyannote(受限模型 + HF token), 本项目没有 ⇒ 记 not_available, 不拿能量占比冒充。
· ★ **不**把 vocals 占比读成「语音内容占比」。分离有伪影: 唱歌会进 vocals,
  说话背景的人声也会。能量占比是**声学量**, 不是语义判断。

## 代价与上限
htdemucs 在 CPU 上约 0.27x 实时(实测)。默认只分析前 `MAX_SECONDS` 秒并**如实标注**截断,
不假装分析了全长。模型约 300MB, 首次运行会下载 ⇒ CI 不装它, 该能力标为**本机验证**。
"""
from __future__ import annotations

import warnings

MAX_SECONDS = 60          # 分析窗上限。改它会改变 energy_share 的含义, 属于判据变更。
MODEL = "htdemucs"
SOURCES = ("drums", "bass", "other", "vocals")

# 结构闸: 源分离**不得**产出说话人/身份/情绪类字段。
FORBIDDEN = ("speaker", "diarization", "num_speakers", "identity", "emotion",
             "说话人", "身份", "情绪")


def available() -> bool:
    try:
        import demucs, torch, soundfile, librosa      # noqa: F401
        return True
    except Exception:
        return False


def separate(path: str, *, max_seconds: int = MAX_SECONDS) -> dict:
    """返回 {status, energy_share, vocals(np.ndarray|None), sr, analysed_seconds, truncated}。

    ★ 三态: ok / not_available(依赖缺席或模型取不到) / failed(这一条跑挂了)。
    """
    out = {"status": "not_available", "model": MODEL, "energy_share": None,
           "vocals": None, "sr": None, "analysed_seconds": None,
           "truncated": None, "error": None}
    if not available():
        out["error"] = "demucs/torch/soundfile/librosa 未装"
        return out
    try:
        import warnings as _w
        _w.filterwarnings("ignore")
        import numpy as np, soundfile as sf, torch, librosa
        from demucs.pretrained import get_model
        from demucs.apply import apply_model

        model = get_model(MODEL); model.eval()
        x, sr = sf.read(path, dtype="float32")
        if x.ndim > 1:
            x = x.mean(axis=1)
        full = len(x) / float(sr)
        keep = int(min(full, max_seconds) * sr)
        x = x[:keep]
        y = librosa.resample(x, orig_sr=sr, target_sr=model.samplerate) \
            if sr != model.samplerate else x
        wav = torch.tensor(np.stack([y, y]))[None]
        with torch.no_grad():
            est = apply_model(model, wav, split=True, overlap=0.1, progress=False)[0]
        energy = {n: float((est[i] ** 2).mean()) for i, n in enumerate(model.sources)}
        total = sum(energy.values())
        if total <= 0:
            out.update(status="failed", error="全源能量为 0 —— 输入可能是静音")
            return out
        vi = list(model.sources).index("vocals")
        out.update(status="ok",
                   energy_share={k: round(v / total, 4) for k, v in energy.items()},
                   vocals=est[vi].mean(axis=0).numpy(), sr=model.samplerate,
                   analysed_seconds=round(len(x) / float(sr), 2),
                   truncated=(full > max_seconds), full_seconds=round(full, 2))
        _guard(out)
        return out
    except Exception as e:                                    # noqa: BLE001
        out.update(status="failed", error=f"{type(e).__name__}: {str(e)[:160]}")
        return out


def _guard(out: dict) -> None:
    """结构上挡住「用能量占比冒充说话人/情绪判断」。字段名出现即抛, 不靠注释约束。"""
    keys = {k.lower() for k in out} | {k.lower() for k in (out.get("energy_share") or {})}
    for bad in FORBIDDEN:
        if any(bad in k for k in keys):
            raise RuntimeError(f"★ 源分离产出里出现被禁字段 {bad!r} —— "
                               "能量占比是声学量, 不得读成说话人或情绪判断")


if __name__ == "__main__":
    import json, sys
    r = separate(sys.argv[1])
    r.pop("vocals", None)
    print(json.dumps(r, ensure_ascii=False))
