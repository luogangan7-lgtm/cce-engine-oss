#!/usr/bin/env python3
"""s6 对齐算子 v2 — 分布级 + 分族判定(共鸣/拆除)

替代 v1 的三处缺陷:
  v1: top_aud = argmax(受众结); covered = top_aud in 稿件结集合
      ①裸argmax丢分布(违反全占比原则) ②集合成员判定丢权重 ③推动/阻挡族同尺(阻挡族恒不可满足)

v2: 对齐分 = Σ(推动族受众结) w_a × 稿件该结权重          [共鸣]
           + Σ(阻挡族受众结) w_a × 拆除动作命中度(0..1)   [拆除]
    命中度由 playbook 检测器给出(模型判定, 三次表决)。

作为库使用: score(aud_knots, post_knots, text) -> dict
命令行自测: cce_align_v2.py --selftest
"""
import json, os, re, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAXO = json.load(open(os.path.join(ROOT, "config/knot_taxonomy.json"), encoding="utf-8"))
FAMILY = {k["key"]: k.get("family", "推动") for k in TAXO["knots"]}
PLAYBOOK = {k["key"]: k.get("playbook", "") for k in TAXO["knots"]}
DISCR = {k["key"]: k.get("hard_discriminant", "") for k in TAXO["knots"]}


def _load_env():
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line.startswith("export "):
                line = line[7:]
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_env()
BASE = "https://api.minimaxi.com/v1/text/chatcompletion_v2"


def _call(prompt, model="MiniMax-Text-01", temperature=0.0):
    key = os.environ.get("MINIMAX_API_KEY", "")
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}],
               "max_tokens": 700, "temperature": temperature}
    for _ in range(3):
        try:
            req = urllib.request.Request(BASE, json.dumps(payload).encode(),
                                         headers={"Authorization": f"Bearer {key}",
                                                  "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.loads(r.read())
            if (d.get("base_resp") or {}).get("status_code") == 0:
                return d["choices"][0]["message"].get("content") or ""
        except Exception:
            pass
    return ""


DISSOLVE_PROMPT = """你判定一段内容是否执行了针对某个"阻挡结"的拆除动作。

【阻挡结】{knot}
判据(受众处于该状态的表现): {discr}
拆除动作规范(playbook): {playbook}

【待判内容】
{text}

只判内容**是否实际执行了**该拆除动作,不判内容好坏,不判是否提到该话题。
执行=内容里有可指认的句子在做 playbook 描述的事; 只是谈论相关话题不算执行。

只输出JSON: {{"hit": 0到1的小数, "evidence": "支撑判定的逐字子串,无则空"}}
hit 标尺: 0=完全没做; 0.3=沾边但不到位; 0.6=做了但不完整; 1.0=完整执行 playbook"""


def _extract_json(s):
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j < 0:
        return None
    try:
        return json.loads(s[i:j + 1])
    except Exception:
        return None


def dissolve_hit(knot, text, votes=3):
    """阻挡结拆除动作命中度: 三次表决取中位数"""
    p = DISSOLVE_PROMPT.format(knot=knot, discr=DISCR.get(knot, ""),
                               playbook=PLAYBOOK.get(knot, ""), text=text)
    temps = [0.0, 0.3, 0.6][:votes]
    with ThreadPoolExecutor(max_workers=votes) as ex:
        outs = list(ex.map(lambda t: _call(p, temperature=t), temps))
    hits, evs = [], []
    for o in outs:
        d = _extract_json(o)
        if isinstance(d, dict) and isinstance(d.get("hit"), (int, float)):
            hits.append(max(0.0, min(1.0, float(d["hit"]))))
            if d.get("evidence"):
                evs.append(str(d["evidence"])[:80])
    if not hits:
        return 0.0, "检测失败"
    hits.sort()
    return hits[len(hits) // 2], (evs[0] if evs else "")


def score(aud_knots, post_knots, text, theta=None, detect=True):
    """aud_knots/post_knots: {knot: weight} 或 [[knot,weight],...]"""
    if isinstance(aud_knots, list):
        aud_knots = dict(aud_knots)
    if isinstance(post_knots, list):
        post_knots = dict(post_knots)
    resonance, dissolution, detail = 0.0, 0.0, []
    for k, w in aud_knots.items():
        fam = FAMILY.get(k, "推动")
        if fam == "推动":
            c = float(post_knots.get(k, 0.0))
            resonance += w * c
            detail.append({"knot": k, "family": fam, "aud_w": w, "mode": "共鸣",
                           "response": round(c, 3), "contrib": round(w * c, 4)})
        else:
            hit, ev = dissolve_hit(k, text) if detect else (0.0, "未检测")
            dissolution += w * hit
            detail.append({"knot": k, "family": fam, "aud_w": w, "mode": "拆除",
                           "response": round(hit, 3), "contrib": round(w * hit, 4),
                           "evidence": ev})
    total = resonance + dissolution
    out = {"alignment_score": round(total, 4),
           "resonance": round(resonance, 4),
           "dissolution": round(dissolution, 4),
           "detail": detail}
    if theta is not None:
        out["theta"] = theta
        out["pass"] = total >= theta
    return out


if __name__ == "__main__":
    CASES = [
        ("长文案piece1(旧闸:通过)", {"reward": .60, "display": .25, "itch": .15},
         {"pain_seek": .65, "belong": .20, "reward": .15},
         "Can't hear the person across the table at a restaurant? Don't blame your hearing aid yet. "
         "You might just be sitting in the wrong seat. Here's why. Many hearing aid microphones face "
         "forward. They boost what's in front and turn down what's behind. So here's tip one. Keep the "
         "loudest stuff behind you. Tip two is distance. Tip three starts when you book the table. "
         "Remember the order. Seat first, then settings. Try it tonight and tell me in the comments."),
        ("微片v1(旧闸:失败)", {"display": .65, "reward": .35}, {"reward": 1.0},
         "Can't hear the person across the table? Don't blame your hearing aid. You might just be "
         "sitting in the wrong seat. Put the loudest stuff behind you."),
        ("微片v3(旧闸:失败)", {"inertia": .45, "audit": .2, "reward": .2, "itch": .15},
         {"display": 1.0},
         "Here's what no one explains about hearing aids. The mic faces forward, so whatever sits "
         "behind you gets turned down. Most people blame the device. It's usually the seat."),
        ("微片v4(旧闸:失败)", {"inertia": .4, "reward": .3, "itch": .2, "display": .1},
         {"reward": .65, "display": .35},
         "No one explains this about hearing aids. The mic faces forward, so noise behind you gets "
         "turned down. Most people blame the device. You don't have to change a single setting. "
         "Just take the seat with the noise behind you."),
    ]
    print(f"{'样本':26s} {'总分':>6s} {'共鸣':>6s} {'拆除':>6s}   阻挡结命中")
    for name, aud, post, text in CASES:
        r = score(aud, post, text)
        blk = "; ".join(f"{d['knot']}={d['response']}" for d in r["detail"] if d["family"] == "阻挡") or "—"
        print(f"{name:26s} {r['alignment_score']:6.3f} {r['resonance']:6.3f} {r['dissolution']:6.3f}   {blk}")
