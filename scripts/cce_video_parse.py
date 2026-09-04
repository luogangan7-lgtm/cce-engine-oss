#!/usr/bin/env python3
"""
CCE 视频多模态解析管线 v5 —— 带六道完整性 gate + 可观察音频能力台账
============================================================
相对旧 Video Knowledge Parse v3(逐镜脚本/创作视角)的升级:
  输出 = 带时间戳的全层事件流(供四层逆推), 完整性有 gate 有分数, 视觉走双模型校准。
六道完整性 gate:
  G1 分层清单: 画面/语音/声音事件/画面文字/音乐/节奏 每层强制填或显式标"缺"(禁静默丢层——旧版无音轨直接跳过=反例)
  G2 时间轴平铺: 事件覆盖全时长, >3s 无事件区间报警
  G3 双通道对账: ASR 内容 vs 画面事件 蕴含互检(抽样)
  G4 多模型并集: M3+Qwen 独立解析关键帧, 单侧检出=补漏候选, 分歧率=校准信号
  G5 重建探针: 随机时刻问答, parse-only 回答 vs 实际帧(人工/模型抽检)
  G6 校准口径: 可观测层 only(动作/场景/文字/表观情绪 apparent), 禁内心断言
用法: source .env && python3 scripts/cce_video_parse.py <video.mp4> [--frames-only|--audio-only]
产出: results/video_parse/<name>.json (事件流+完整性记分卡)
"""
import os, sys, json, subprocess, base64, time, argparse
import numpy as np

ROOT = os.environ.get("VSE_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
OUT_DIR = os.path.join(ROOT, "results/video_parse")
CACHE = os.path.join(ROOT, "assets/audio_cache")

# 固定长 system 前缀(≥1024 token 触发上下文缓存稳定命中; ts 不进 prompt 保前缀稳定→批量帧从第2帧命中)
VISION_SYS = ("你是专业的短视频画面逐帧解析器, 服务于认知因果引擎的多模态证据抽取。"
    "核心纪律: 严格只报告画面中真实可见的客观事实, 绝对禁止推断人物的内心想法、真实情绪动机、性格特质或意图目的——"
    "这些属于下游因果引擎的贝叶斯逆推范畴, 不是画面解析器的职责。你只提供可观测证据(apparent/perceived口径), 不做心理终判。"
    "对给定的单帧图像, 你必须系统性地识别并按固定JSON schema输出以下七个字段, 不得遗漏任何一项, 不得虚构不存在的元素, 不得脑补前后文情节: "
    "字段一 scene: 用一句话客观描述画面的场景环境(室内/室外、地点类型、背景要素)。"
    "字段二 persons: 描述画面中出现的人物, 包括其外观特征(性别年龄段、发型、着装颜色款式)与表观姿态表情(面向、站坐姿势、手势、面部表情的外在形态), 严格apparent口径不做内心判断; 无人物则留空。"
    "字段三 actions: 描述画面中正在发生的具体动作与行为(人物动作、物体运动、交互事件)。"
    "字段四 on_screen_text: 逐字转录画面内出现的所有文字元素, 包括标题字幕、贴纸弹幕、水印logo、产品标签、手写艺术字、片头片尾credits等, 无论中英文或艺术字体都要尽力识别转录; 没有任何文字则留空字符串。"
    "字段五 objects: 列出画面中的关键物体、道具、产品与陈设。"
    "字段六 shot_type: 判断镜头景别(大特写/特写/近景/中景/中远景/远景/大远景/产品特写/俯拍/仰拍等)。"
    "字段七 camera: 判断运镜方式(固定机位/推近/拉远/左右摇/上下移/跟随/环绕/手持晃动/变焦), 无法判断则标注未知。"
    "所有描述必须基于该帧真实可见内容。只输出符合上述schema的单个JSON对象, 键名严格用英文, 不要输出任何解释文字、前言、markdown代码块包裹或多余内容。")
VISION_USER = "解析这一帧画面, 按schema输出JSON。"

def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)

def fld(r, key):
    """模型字段容错取值: M3偶尔把 on_screen_text/camera 等返回成 list 或数字, 统一压成 str"""
    v = r.get(key)
    if isinstance(v, list): v = ' '.join(str(x) for x in v if x)
    return (v if isinstance(v, str) else ('' if v is None else str(v))).strip()

def ffprobe_duration(path):
    return float(run(['ffprobe','-v','quiet','-show_entries','format=duration','-of','csv=p=0',path]).stdout.strip())

def subsample_uniform(ts_list, max_frames):
    """帧预算: **全时长均匀采样(保首尾)**, 绝不头部截断。
    2026-07-29: 长视频(实测种子含 985s 动漫解说)按 1fps 会产 ~985 次 VLM 调用, 成本不可控。
    但预算必须以"保时间轴覆盖"的方式落, 与 cce_bundle_render._pick_frames 同一策略 ——
    `[:40]` 式头部截断正是 2026-07-28 审计打掉的那类故障, 不许在这里换个地方复活。"""
    n = len(ts_list)
    if not max_frames or n <= max_frames:
        return list(range(n)), None
    k = max(2, int(max_frames))
    idx = sorted({round(i * (n - 1) / (k - 1)) for i in range(k)})
    span = float(ts_list[idx[-1]]) - float(ts_list[idx[0]])
    full = (float(ts_list[-1]) - float(ts_list[0])) or 1.0
    return idx, {'field': 'visual.frame_stream', 'policy': 'uniform_sample_keep_endpoints',
                 'stage': 'extract_frames', 'kept': len(idx), 'total': n,
                 'coverage_ratio': round(len(idx) / n, 3),
                 'time_span_coverage': round(span / full, 3), 'max_frames': int(max_frames)}


def extract_frames(video, name, max_span=3.0, max_seconds=None, max_frames=None):
    """混合抽帧(调研CVPR'25 Apollo/AKS/Scene-Policies定案): 均匀2fps打底(UGC短视频)
    + 场景切换边界帧必采 + >max_span兜底。均匀fps最稳不漏短暂动作, 场景帧保边界。
    max_frames: VLM 预算上限, 超出改**全时长均匀采样**(保首尾), 并如实登记 frame_budget。"""
    fdir = os.path.join(CACHE, f"frames_{name}")
    os.makedirs(fdir, exist_ok=True)
    dur = ffprobe_duration(video)
    if max_seconds: dur = min(dur, float(max_seconds))  # 前窗解析(长视频钩子窗口)
    # 场景切换检测(边界帧)
    r = run(['ffmpeg','-i',video,'-vf',"select='gt(scene,0.3)',showinfo",'-vsync','vfr','-f','null','-'])
    sc_ts = [float(m) for m in __import__('re').findall(r'pts_time:([\d.]+)', r.stderr)]
    # 均匀 2fps 打底(短视频)/1fps(长视频>3min) —— fps采样优于固定帧数(Apollo CVPR'25)
    fps = 2.0 if dur <= 180 else 1.0
    grid = list(np.arange(0.5, dur, 1.0 / fps))
    all_ts = sorted(set(round(t,1) for t in (sc_ts + grid) if t < dur))
    # 相邻去重(<0.8s 合并)
    ts_final = []
    for t in all_ts:
        if not ts_final or t - ts_final[-1] >= 0.8:
            ts_final.append(t)
    keep, budget = subsample_uniform(ts_final, max_frames)
    if budget:
        ts_final = [ts_final[i] for i in keep]
        print(f"  帧预算: {budget['total']}→{budget['kept']} 帧(全时长均匀采样, "
              f"时间覆盖{budget['time_span_coverage']:.0%})")
    frames = []
    for t in ts_final:
        fp = os.path.join(fdir, f"f{t:07.1f}.jpg")
        if not os.path.exists(fp):
            run(['ffmpeg','-y','-ss',str(t),'-i',video,'-frames:v','1','-q:v','3',fp])
        if os.path.exists(fp):
            frames.append((t, fp))
    # G2 采样覆盖检查
    gaps = [round(b-a,1) for (a,_),(b,_) in zip(frames, frames[1:]) if b-a > max_span+0.5]
    # 场景切点必须落盘(2026-07-28 审计: 原来 sc_ts 只用来选帧, 用完即丢 →
    # 剪辑节奏被记为 missing_no_capability, 而它本可零成本派生)
    return dur, frames, gaps, sorted(set(round(t, 2) for t in sc_ts if t < dur)), budget

def edit_rhythm(scene_cut_ts, dur):
    """由已算出的场景切点零成本派生剪辑节奏(镜头数/平均镜头时长/切换率/时长方差)。"""
    if not dur or dur <= 0:
        return None
    cuts = [t for t in (scene_cut_ts or []) if 0 < t < dur]
    bounds = [0.0] + cuts + [float(dur)]
    lens = [round(b - a, 3) for a, b in zip(bounds, bounds[1:]) if b > a]
    if not lens:
        return None
    mean = sum(lens) / len(lens)
    var = sum((x - mean) ** 2 for x in lens) / len(lens)
    return {'n_shots': len(lens), 'avg_shot_len_s': round(mean, 3),
            'cut_rate_per_min': round(len(cuts) * 60.0 / dur, 3),
            'shot_len_var': round(var, 3),
            'detector': "ffmpeg select='gt(scene,0.3)'"}

def _audio_capabilities(present, tags=None, wav=None):
    """Capability ledger, not a claim that missing source separation is silence.

    The former v4 output mixed a full-track ASR result and a BGM tag into a
    single ``audio`` object.  Consumers could easily mistake that for stems,
    diarization, or prosody.  V5 keeps v4's compatibility fields but makes the
    distinction machine-readable.
    """
    tags = set(tags or [])
    unavailable = {'status': 'missing_no_capability'}
    return {
        'original_mix': {'status': 'present' if present else 'missing_parse_failed'},
        'source_layers': {
            'speech': {'status': 'detected_full_track' if present else 'missing_parse_failed'},
            'bgm': {'status': 'detected_not_separated' if 'BGM' in tags else 'missing_no_capability'},
            'sfx': dict(unavailable), 'ambient': dict(unavailable), 'noise': dict(unavailable),
        },
        'speech_timeline': {'status': 'missing_no_capability'},
        # ★ 2026-09-04: speaker_turns 由 missing_no_capability 转为**真做**。
        #   原来登记的理由是「pyannote 是受限模型, 需 HF token」—— **两处错**:
        #   ① pyannote.audio 是 MIT 开源**包**, 受限的是**权重**, 装包无需 token;
        #   ② 3D-Speaker 默认路径 include_overlap=False **根本不碰** pyannote 权重。
        #   实测 VoxConverse dev n=20: DER STRICT 0.1004 / LEGACY 0.0338, CPU RTF 0.133。
        #   ★ 结构性代价如实标: 不检测重叠语音; speaker_N 是**局部标签不是身份**。
        **_speaker_turns(wav),
        # ★ 2026-09-03: 韵律与混音由 missing_no_capability 转为**真做**。
        #   科学边界(2026-07-22 调研)焊在 cce_audio_prosody 里:
        #   韵律→唤醒度是已重复验证的通道; **效价仅靠声学弱, 人格/特质是伪科学** ⇒ 都不产出。
        #   这里只给**声学量本身**, 不给情绪分值 —— 韵律是 Observation 不是推断。
        **_prosody_mix(wav),
        **_source_separation(wav),
    }


# ★ 「转写近乎空白」的界。**这是工程预算, 不是标定过的阈值** ——
#   出处标 ENGINEERING_BUDGET(与本项目 qualification margin 同一套约定)。
#   为什么用**字/秒**而不是绝对字数: 3 秒视频的 9 个字是正常的, 178 秒视频的 1 个字不是。
#   实测分布(n=275): 中位 0.926 字/秒, 十分位 0.128, 四分位 0.248/5.023 —— 跨度 20 倍。
#   取 0.15 是**十分位附近**的保守位置; 它只决定「要不要去查人声占比」,
#   **真正的判定由 vocals_share 做** —— 那一步是类别判断, 不受这个界的噪声影响。
#   ★ 原始量(chars / chars_per_sec / vocals_share)一律随状态带出, 下游可自行重判。
TRANSCRIPT_MIN_CHARS_PER_SEC = 0.15
TRANSCRIPT_RATE_PROVENANCE = "ENGINEERING_BUDGET"


def _speech_status(audio, duration=None):
    """语音层四态。★ 「本就没口播」与「ASR 失败」**必须分开** —— 压成一个 true 会静默低估。

    · present               转写非空(>= TRANSCRIPT_MIN_CHARS 字)
    · missing_no_capability 无音轨
    · absent_verified       转写近乎空白**且**人声能量占比低 ⇒ 素材本就无口播, 空是**对的**
    · missing_parse_failed  转写近乎空白**而**人声能量占比高 ⇒ **ASR 失败**
    · not_available         转写近乎空白, 但**查不了**人声占比(无 wav / demucs 缺席) ⇒ 不知道
    ★ 最后一档不许写成 absent_verified —— 「查不了」不等于「查过没有」。
    """
    if not isinstance(audio, dict) or not audio.get('present'):
        return {'status': 'missing_no_capability', 'why': '无音轨'}
    tr = str(audio.get('transcript') or '').strip()
    dur = float(duration or 0) or None
    rate = (len(tr) / dur) if dur else None
    base = {'chars': len(tr), 'duration_s': round(dur, 2) if dur else None,
            'chars_per_sec': round(rate, 4) if rate is not None else None,
            '★rate_gate': TRANSCRIPT_MIN_CHARS_PER_SEC,
            '★rate_gate_provenance': TRANSCRIPT_RATE_PROVENANCE}
    if rate is None:
        return {'status': 'not_available', **base,
                'why': '无时长 ⇒ 无法按字/秒判断转写是否近乎空白'}
    if rate >= TRANSCRIPT_MIN_CHARS_PER_SEC:
        return {'status': 'present', **base}
    share = audio.get('★vocals_share')          # 由调用方在有 wav 时填
    if share is None:
        return {'status': 'not_available', **base,
                'why': ('转写近乎空白, 但**未查**人声能量占比 ⇒ 分不清「本就没口播」与「ASR 失败」。'
                        '★ 不得记 absent_verified —— 查不了不等于查过没有。')}
    if share < 0.5:
        return {'status': 'absent_verified', **base, 'vocals_share': round(share, 4),
                'why': '人声能量占比低 ⇒ 素材本就无口播, 空转写是**正确的**'}
    return {'status': 'missing_parse_failed', **base, 'vocals_share': round(share, 4),
            'why': ('人声能量占比高却近乎空白 ⇒ **ASR 失败**。'
                    '实测该情形在历史产物的短转写里占 >= 22.5%(下界)。')}


def _speaker_turns(wav):
    """说话人分段。★ 依赖缺席记 missing_parse_failed(这次没跑成), **不是** missing_no_capability
    (那是「压根没这能力」)—— 能力已具备, 两者不许混。"""
    if not wav or not os.path.exists(wav):
        return {'speaker_turns': {'status': 'missing_parse_failed'}}
    try:
        import cce_audio_diarize as DZ
        r = DZ.diarize(wav)
        if r['status'] != 'ok':
            return {'speaker_turns': {'status': 'missing_parse_failed',
                                      'inner_status': r['status'], 'error': r.get('error')}}
        return {'speaker_turns': {
            'status': 'present', 'inner_status': 'ok',
            'implementation': r['implementation'], 'n_speakers': r['n_speakers'],
            'segments': r['segments'],
            '★overlap_not_detected': r['★overlap_not_detected'],
            '★labels_are_local': r['★labels_are_local']}}
    except Exception as e:
        return {'speaker_turns': {'status': 'missing_parse_failed',
                                  'error': f"{type(e).__name__}: {str(e)[:100]}"}}


def _source_separation(wav):
    """源分离能量占比。★ 只给声学量, 不给语义判断(结构闸在 cce_audio_separate 里)。"""
    if not wav or not os.path.exists(wav):
        return {'source_separation': {'status': 'missing_parse_failed'}}
    try:
        import cce_audio_separate as SEP
        r = SEP.separate(wav)
        if r['status'] != 'ok':
            return {'source_separation': {'status': 'missing_parse_failed',
                                          'inner_status': r['status'], 'error': r.get('error')}}
        return {'source_separation': {
            'status': 'present', 'inner_status': 'ok', 'model': r['model'],
            'energy_share': r['energy_share'], 'analysed_seconds': r['analysed_seconds'],
            'truncated': r['truncated'],
            '★energy_share_is_acoustic': '能量占比是**声学量**, 不得读成说话人数或语义内容占比'}}
    except Exception as e:
        return {'source_separation': {'status': 'missing_parse_failed',
                                      'error': f"{type(e).__name__}: {str(e)[:100]}"}}


def _prosody_mix(wav):
    if not wav or not os.path.exists(wav):
        return {'prosody_timeline': {'status': 'missing_parse_failed'},
                'mix_metrics': {'status': 'missing_parse_failed'}}
    try:
        import cce_audio_prosody as AP
        r = AP.analyse(wav)
        pr, mx = r['prosody'], r['mix_metrics']
        # ★ 台账用 present/missing_*, 与其余条目同一套词; 内层自己的 status 另存,
        #   否则 **pr 会把台账的状态词覆盖成 'ok', 两套词混在一个字段里。
        def _wrap(d):
            st = 'present' if d.get('status') == 'ok' else (
                'empty_verified' if d.get('status') == 'empty' else 'missing_parse_failed')
            return {**{k: v for k, v in d.items() if k != 'status'},
                    'status': st, 'inner_status': d.get('status')}
        return {'prosody_timeline': _wrap(pr), 'mix_metrics': _wrap(mx)}
    except Exception as e:
        # ★ 依赖缺席即如实标缺, **不降级为 missing_no_capability**(那是「压根没这能力」,
        #   与「这次没跑成」是两回事)
        return {'prosody_timeline': {'status': 'missing_parse_failed',
                                     'error': f"{type(e).__name__}: {str(e)[:100]}"},
                'mix_metrics': {'status': 'missing_parse_failed',
                                'error': f"{type(e).__name__}: {str(e)[:100]}"}}


def parse_audio(video, name):
    """SenseVoice 全轨通过: ASR+情绪标签+声音事件(G1 声音层)。

    全轨标签不是 source separation；具体能力见 ``audio.capabilities``。
    """
    wav = os.path.join(CACHE, f"{name}.wav")
    if not os.path.exists(wav):
        r = run(['ffmpeg','-y','-i',video,'-ar','16000','-ac','1',wav])
        if not os.path.exists(wav) or os.path.getsize(wav) < 1000:
            return {'present': False, 'reason': '无音轨或抽取失败(显式标注, 禁静默跳过)',
                    'capabilities': _audio_capabilities(False, wav=wav)}
    from funasr import AutoModel
    m = AutoModel(model="iic/SenseVoiceSmall", trust_remote_code=False, disable_update=True)
    res = m.generate(input=wav, language="auto", use_itn=True)
    raw = res[0].get('text','')
    import re
    tags = re.findall(r'<\|([A-Za-z_]+)\|>', raw)
    text = re.sub(r'<\|[^|]*\|>', '', raw).strip()
    return {'present': True, 'transcript': text, 'tags': tags,
            'emotion_tags': [t for t in tags if t.upper() in ('HAPPY','SAD','ANGRY','NEUTRAL','FEARFUL','DISGUSTED','SURPRISED','EMO_UNKNOWN')],
            'event_tags': [t for t in tags if t in ('Speech','Music','Laughter','Applause','Cry','BGM','Cough','Sneeze','Breath')],
            'capabilities': _audio_capabilities(True, tags, wav=wav)}

_OCR = None
OCR_CONF_MIN = 0.5
# 逐帧 OCR 允许吞掉(并记 warning)的异常。RapidOCR 的自定义异常直接继承 Exception,
# 必须点名捕获 —— 但绝不退回裸 `except Exception`, 那正是 2026-07-28 事故的成因。
_OCR_ERRORS = (OSError, ValueError, TypeError, IndexError, KeyError, AttributeError)

def _ocr_engine_errors():
    errs = []
    try:
        from rapidocr_onnxruntime import utils as _u
    except ImportError:
        return ()
    for n in ('LoadImageError', 'ONNXRuntimeError', 'UnidentifiedImageError'):
        e = getattr(_u, n, None)
        if isinstance(e, type) and issubclass(e, Exception):
            errs.append(e)
    return tuple(errs)

def _conf_f(v):
    """置信度 → float。RapidOCR 1.2.x 返回 str('0.83...'), 其他版本返回 float/np.floating。
    取不到返回 None(调用方按'置信度未知'处理, 不得静默丢文字)。"""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None

def _norm_box(b):
    """把 RapidOCR 的四点框统一成 [x, y, w, h] 像素整数; 认不出就返回 None。

    ★ 2026-09-03 修一个 2026-08-15 就登记的 P0: 原来这里**把 box 丢了**,
      于是「结论不能回指图像区域」—— 视觉证据只剩一串文字, 没法说它在画面哪儿。
      区域语义按 v4 扩展标准映射 W3C Media Fragments 的 xywh(pixel)。
    """
    try:
        pts = [(float(x), float(y)) for x, y in b]
    except Exception:
        return None
    if len(pts) < 2:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    if x1 <= x0 or y1 <= y0:
        return None
    return [int(round(x0)), int(round(y0)), int(round(x1 - x0)), int(round(y1 - y0))]


def _ocr_rows(res):
    """统一不同 RapidOCR 版本的返回结构 → [(text, conf|None, box|None), ...]。
    ★ box 是 [x,y,w,h] 像素(W3C Media Fragments xywh); 取不到记 None, **不静默丢**。
    1.x: list[[box, text, score]](score 常为 str) · 变体: list[[box, (text, score)]] ·
    2.x: RapidOCROutput 对象(.txts/.scores)。结构不认识就返回空, 由调用方记为 parse 失败。"""
    if res is None:
        return []
    txts = getattr(res, 'txts', None)
    if txts is not None:
        scores = getattr(res, 'scores', None) or [None] * len(txts)
        boxes = getattr(res, 'boxes', None) or [None] * len(txts)
        return [(str(t), _conf_f(sc), _norm_box(b) if b is not None else None)
                for t, sc, b in zip(txts, scores, boxes)]
    rows = []
    for r in res:
        if not isinstance(r, (list, tuple)):
            continue
        box = _norm_box(r[0]) if len(r) >= 2 and isinstance(r[0], (list, tuple)) else None
        if len(r) >= 3:
            t, c = r[1], r[2]
        elif len(r) == 2 and isinstance(r[1], (list, tuple)) and len(r[1]) >= 2:
            t, c = r[1][0], r[1][1]
        elif len(r) == 2:
            t, c = r[1], None
        else:
            continue
        if isinstance(t, (list, tuple)):
            t = ' '.join(str(x) for x in t if x)
        rows.append((str(t), _conf_f(c), box))
    return rows

def ocr_frames(frames):
    """本地 RapidOCR = 画面文字层【权威通道】(VLM 顺带看不可靠)。
    返回 (texts, confs, regions, meta): texts {ts:[文字]} · confs {ts:[置信度]}
    · regions {ts:[[x,y,w,h]|None]} (★ 2026-09-03 新增, 修「结论回指不到图像区域」的 P0)
    · meta=通道存活账本。

    2026-07-28 事故复盘(必须留在这里): 原实现写 `r[2] > 0.5`, 而本机 RapidOCR 的置信度是
    **str**, 比较抛 TypeError, 又被裸 `except Exception: out[ts]=[]` 无声吞掉 → 90/90 产物
    OCR 全空, 却因记分卡把 OCR 与 VLM 做 OR 而照报 on_screen_text=true。三条纪律因此固化:
      ① 置信度按类型容错解析(str/float/np 都吃, 取不到就记账而非丢字);
      ② 只吞【预期】异常并逐条 print warning + 落 meta.errors, 禁止再静默吞任何异常;
      ③ 通道存活(channel_ok/channel_status)显式落盘, 让"跑通但内容确实没字"(empty_verified)
         与"跑挂了"(parse_failed)在产物里可区分 —— 这正是 schema 要堵的洞。"""
    global _OCR
    texts, confs, regions = {}, {}, {}
    meta = {'engine': 'rapidocr_onnxruntime', 'conf_min': OCR_CONF_MIN,
            'frames_attempted': len(frames), 'frames_failed': 0, 'frames_with_text': 0,
            'conf_unparsed': 0, 'errors': [], 'init_error': None,
            'channel_ok': None, 'channel_status': 'no_frames'}
    if not frames:
        return texts, confs, regions, meta   # 无帧可跑 != 通道坏
    if _OCR is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _OCR = RapidOCR()
        except (ImportError, OSError, RuntimeError) as e:
            meta.update(channel_ok=False, channel_status='dead',
                        init_error=f"{type(e).__name__}: {e}")
            print(f"  ⚠️ OCR 引擎初始化失败 → 画面文字权威通道 DEAD: {meta['init_error']}")
            for ts, _ in frames:
                texts[f"{ts:.1f}"], confs[f"{ts:.1f}"] = [], []
            return texts, confs, regions, meta
    expected = _OCR_ERRORS + _ocr_engine_errors()
    for ts, fp in frames:
        k = f"{ts:.1f}"
        try:
            res, _ = _OCR(fp)
            rows = _ocr_rows(res)
        except expected as e:
            meta['frames_failed'] += 1
            if len(meta['errors']) < 10:
                meta['errors'].append({'ts': k, 'error': f"{type(e).__name__}: {e}"})
            print(f"  ⚠️ OCR 帧 {k} 失败: {type(e).__name__}: {e}")
            texts[k], confs[k] = [], []
            continue
        kt, kc, kb = [], [], []
        for t, c, box in rows:
            t = (t or '').strip()
            if not t:
                continue
            if c is None:
                meta['conf_unparsed'] += 1     # 置信度取不到 → 保留文字并记账, 不静默丢
            elif c <= OCR_CONF_MIN:
                continue
            kt.append(t); kc.append(c)
            # ★ box 取不到记 None 并记账 —— 与置信度同样纪律: 缺席可见, 不静默丢
            if box is None:
                meta['box_unparsed'] = meta.get('box_unparsed', 0) + 1
            kb.append(box)
        texts[k], confs[k] = kt, kc
        regions[k] = kb
        if kt:
            meta['frames_with_text'] += 1
    if meta['frames_failed'] == 0:
        meta.update(channel_ok=True, channel_status='ok')
    elif meta['frames_failed'] >= len(frames):
        meta.update(channel_ok=False, channel_status='dead')
    else:
        meta.update(channel_ok=False, channel_status='partial')
    return texts, confs, regions, meta

def text_channel_report(ocr, ocr_meta, visual):
    """画面文字层【分通道】判定 —— main() 与 backfill 共用同一份逻辑, 防漂移。

    2026-07-28 修复前是 `on_screen_text = (OCR有) OR (VLM有)`, VLM 把权威通道的死亡完全
    遮住(OCR 0/90 却 81/90 报 true)。现在状态**只由权威通道(OCR)决定**, VLM 仅补充标注,
    且 empty_verified(跑通且确无文字) 与 missing_parse_failed(跑挂了) 严格分开。"""
    ocr_hit = sum(1 for v in (ocr or {}).values() if v)
    vlm_hit = sum(1 for v in (visual or {}).values()
                  if any(fld(r, 'on_screen_text') not in ('', '无')
                         for r in v.values() if isinstance(r, dict)))
    ch = (ocr_meta or {}).get('channel_status')
    if ch == 'no_frames' or ch is None:
        status = 'missing_not_attempted'
    elif not (ocr_meta or {}).get('channel_ok'):
        status = 'missing_parse_failed'
    elif ocr_hit > 0:
        status = 'present'
    elif vlm_hit > 0:
        status = 'degraded'          # OCR 跑通零命中 + VLM 见字 → 疑漏检(英文/艺术字), 不算已填
    else:
        status = 'empty_verified'    # 权威通道跑通且确认内容本身没有屏幕文字
    return {
        'on_screen_text': status in ('present', 'empty_verified'),  # bool 只由权威通道决定
        'on_screen_text_status': status,
        'authoritative_text_channel': 'OCR',
        'ocr_channel_ok': (ocr_meta or {}).get('channel_ok'),
        'ocr_channel_status': ch,
        'ocr_frames_with_text': ocr_hit,
        'vlm_text_channel_ok': (vlm_hit > 0) if visual else None,
        'vlm_frames_with_text': vlm_hit,
        # 修正: 既无 OCR 命中又无 visual 时旧代码报 'OCR_only'(误导), 现如实报 'none'
        'text_source': ('OCR+VLM' if ocr_hit and visual else
                        ('VLM_only' if visual else ('OCR_only' if ocr_hit else 'none'))),
    }

def b64_frame(fp):
    return "data:image/jpeg;base64," + base64.b64encode(open(fp,'rb').read()).decode()

_CACHE_HITS = {'M3': [], 'Qwen3.8': []}
def vision_call(model_key, ts, fp):
    """稳定长system前缀+cache_control → 上下文缓存(M3自带/Qwen订阅端点原生, 批量帧从第2帧命中)"""
    import requests
    if model_key == 'M3':
        url, key, mdl = "https://api.minimaxi.com/v1/text/chatcompletion_v2", os.environ['MINIMAX_API_KEY'], "MiniMax-M3"
        sys_content = VISION_SYS   # M3 自带缓存
    else:
        url, key, mdl = os.environ['ALIYUN_API_BASE'].rstrip('/')+'/chat/completions', os.environ['ALIYUN_API_KEY'], "qwen3.8-max-preview"
        sys_content = [{"type":"text","text":VISION_SYS,"cache_control":{"type":"ephemeral"}}]  # 显式缓存
    msg = [{"role":"system","content":sys_content},
           {"role":"user","content":[{"type":"text","text":VISION_USER},
                                      {"type":"image_url","image_url":{"url":b64_frame(fp)}}]}]
    for _ in range(3):
        try:
            r = requests.post(url, headers={'Authorization': f'Bearer {key}', 'Content-Type':'application/json'},
                              json={"model": mdl, "messages": msg, "max_tokens": 2000, "temperature": 0.0}, timeout=120)
            d = r.json()
            if d.get('input_sensitive'): return {'error': 'SENSITIVE'}
            cached = ((d.get('usage') or {}).get('prompt_tokens_details') or {}).get('cached_tokens', 0)
            _CACHE_HITS[model_key].append(cached)
            try:                                  # 实测账本(预算硬约束, 不靠上一轮外推)
                import vd_token_ledger as _tl
                _tl.add('vision_frame', model_key, d.get('usage'))
            except Exception:
                pass
            ch = (d.get('choices') or [{}])
            c = (ch[0].get('message') or {}).get('content','') if ch else ''
            s, e = c.find('{'), c.rfind('}')
            if s >= 0: return json.loads(c[s:e+1])
        except Exception:
            time.sleep(3)
    return {'error': 'FAILED'}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('video'); ap.add_argument('--skip-vision', action='store_true')
    ap.add_argument('--models', default='M3,Qwen3.8')
    ap.add_argument('--max-seconds', type=float, default=None, help='前窗解析上限(长视频钩子窗口)')
    ap.add_argument('--max-frames', type=int, default=None, help='VLM帧预算(超出改全时长均匀采样, 如实登记)')
    a = ap.parse_args()
    name = os.path.splitext(os.path.basename(a.video))[0]
    os.makedirs(OUT_DIR, exist_ok=True); os.makedirs(CACHE, exist_ok=True)
    t0 = time.time()
    dur, frames, gaps, scene_cut_ts, frame_budget = extract_frames(
        a.video, name, max_seconds=a.max_seconds, max_frames=a.max_frames)
    print(f"[{name}] 时长{dur:.1f}s | 关键帧{len(frames)}张(场景切换+{3.0}s网格兜底) | 采样空隙>3.5s: {gaps or '无'}"
          f" | 场景切点{len(scene_cut_ts)}处")
    audio = parse_audio(a.video, name)
    print(f"  声音层: {'有' if audio.get('present') else '⚠️ ' + audio.get('reason','缺')}"
          + (f" | 转写{len(audio.get('transcript',''))}字 | 情绪{audio.get('emotion_tags')} | 事件{audio.get('event_tags')}" if audio.get('present') else ""))
    # 画面文字层: OCR ∪ VLM 并集(case3实证RapidOCR中文默认模型对英文/艺术字/片头字幕系统性漏检,
    # VLM反而读对——故不让任一单方当权威, 并集补漏, 分歧标注)
    ocr, ocr_conf, ocr_regions, ocr_meta = ocr_frames(frames)
    ocr_hit = ocr_meta['frames_with_text']
    print(f"  画面文字层(OCR权威通道): {ocr_hit}/{len(frames)}帧有文字 | 通道={ocr_meta['channel_status']}"
          f" 失败帧={ocr_meta['frames_failed']}")
    visual = {}
    if not a.skip_vision:
        models = a.models.split(',')
        from concurrent.futures import ThreadPoolExecutor
        def do(args):
            mk, (ts, fp) = args
            return (mk, ts, vision_call(mk, ts, fp))
        tasks = [(mk, f) for mk in models for f in frames]
        # Qwen 首帧串行预热: 显式缓存"首次写入次次命中", 并发首批会全 miss 烧额度 → 先串行写入前缀
        if 'Qwen3.8' in models and frames:
            mk0, ts0, res0 = do(('Qwen3.8', frames[0]))
            visual.setdefault(f"{ts0:.1f}", {})[mk0] = res0
            tasks = [t for t in tasks if not (t[0] == 'Qwen3.8' and t[1] == frames[0])]
        with ThreadPoolExecutor(max_workers=6) as ex:
            for mk, ts, res in ex.map(do, tasks):
                visual.setdefault(f"{ts:.1f}", {})[mk] = res
        okc = sum(1 for v in visual.values() for r in v.values() if 'error' not in r)
        print(f"  画面层: {len(frames)}帧×{len(models)}模型, 成功{okc}/{len(tasks)}")
        # G4 分歧探针: 每帧双模型的 on_screen_text 与 actions 是否互见
        div = []
        for tsk, mres in visual.items():
            if len(mres) == 2 and all('error' not in r for r in mres.values()):
                r1, r2 = list(mres.values())
                t1, t2 = fld(r1, 'on_screen_text'), fld(r2, 'on_screen_text')
                if bool(t1) != bool(t2): div.append((tsk, 'text单侧检出'))
        print(f"  G4 单侧检出候选: {len(div)} 处")
    # 完整性记分卡 —— CHR/COR 双率量化(调研NOAH/ARGUS: 从过/不过升级为可追踪数字)
    n_frames = len(frames); n_models = len(a.models.split(',')) if not a.skip_vision else 0
    n_slots = n_frames * n_models
    n_ok = sum(1 for v in visual.values() for r in v.values() if isinstance(r, dict) and 'error' not in r)
    # COR(漏报率代理): 单侧检出候选 / 帧数 —— 一侧漏报的比例; CHR 需GT暂留位
    cor = round(len(div) / n_frames, 3) if visual and n_frames else None
    scorecard = {
        # ★ 2026-09-04 实测 ASR_SILENT_FAILURE_IN_HISTORICAL_ARTIFACTS_GEN1(n=40, 预注册):
        #   `speech` 原本 = audio.present, 即「音轨在不在」。但历史产物里 **138/275 转写不足 20 字**,
        #   其中至少 **22.5%** 人声能量占比 >= 0.5(即确有口播), 却照样标 speech=true ——
        #   **两种完全不同的情况被压成同一个 true**:
        #     ① 素材本就无口播(纯音乐/音效) ⇒ 空转写是**正确的**
        #     ② ASR 失败(人声高却近乎空白) ⇒ 空转写是**错的**
        #   下游看到 speech=true 会以为语音层完备, 于是**静默低估**语音内容。
        #   ⇒ 拆成四态, 与本项目其余状态词同一套语义。`speech` 保留为兼容别名。
        'G1_layers': {'visual': bool(visual) or a.skip_vision,
                      'speech': audio.get('present', False),   # 兼容别名: 只表示**音轨在不在**
                      'speech_status': _speech_status(audio, dur),
                      'audio_events': bool(audio.get('event_tags')) if audio.get('present') else None,
                      **text_channel_report(ocr, ocr_meta, visual),
                      'camera_filled': any(fld(r, 'camera') for v in visual.values() for r in v.values() if isinstance(r, dict)) if visual else None,
                      'explicit_absent': [] if audio.get('present') else ['audio']},
        'G2_coverage': {'duration_s': dur, 'frames': n_frames, 'fps': 2.0 if dur <= 180 else 1.0,
                        'gaps_over_3.5s': gaps, 'tiled': not gaps,
                        'scene_cut_ts': scene_cut_ts, 'n_scene_cuts': len(scene_cut_ts),
                        'frame_budget': frame_budget},
        'rates': {'vision_success': round(n_ok / n_slots, 3) if n_slots else None,
                  'COR_omission_proxy': cor,
                  # 双通道分歧(非幻觉判定): VLM检出但OCR空(多为OCR漏检英文/艺术字) / OCR检出但VLM漏
                  'text_VLM_only': sum(1 for tsk, mres in (visual or {}).items()
                      for r in mres.values() if isinstance(r, dict) and fld(r, 'on_screen_text') not in ('','无') and not ocr.get(tsk)),
                  'text_OCR_only': sum(1 for tsk, txts in ocr.items() if txts and tsk in (visual or {})
                      and not any(fld(r, 'on_screen_text') not in ('','无') for r in visual[tsk].values() if isinstance(r, dict)))},
        'ocr_frames_with_text': ocr_hit,
        'ocr_meta': ocr_meta,
        'cache_hits': {'M3': [h for h in _CACHE_HITS['M3'] if h], 'Qwen3.8': [h for h in _CACHE_HITS['Qwen3.8'] if h]} if visual else None,
        'G4_divergence_candidates': len(div) if visual else None,
        'elapsed_s': round(time.time() - t0, 1)}
    out = {'parser_version': '5.0.0', 'video': a.video, 'name': name, 'duration': dur,
           'audio': audio, 'ocr': ocr, 'ocr_conf': ocr_conf,
           # ★ 2026-09-03 新增: 区域作为**新字段**加, 不动 ocr 的形状 ——
           #   276 份历史产物与 foundation_adapter 都按老形状读, 破了就是把历史废掉。
           'ocr_regions': ocr_regions, 'ocr_meta': ocr_meta,
           'frames': [{'ts': t, 'path': p} for t, p in frames],
           'visual': visual,
           # 剪辑节奏: 由已算出的场景切点零成本派生(此前 sc_ts 用完即丢)
           'cinematography': {'shot_boundaries': scene_cut_ts,
                              'edit_rhythm': edit_rhythm(scene_cut_ts, dur)},
           'completeness': scorecard}
    fp_out = os.path.join(OUT_DIR, f"{name}.json")
    json.dump(out, open(fp_out, 'w'), ensure_ascii=False, indent=1)
    print(f"  完整性记分卡: {json.dumps(scorecard['G1_layers'], ensure_ascii=False)}")
    print(f"saved -> {fp_out} ({scorecard['elapsed_s']}s)")

if __name__ == '__main__':
    main()
