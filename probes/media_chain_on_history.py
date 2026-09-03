#!/usr/bin/env python3
"""把**历史多模态解析产物**整批走 P3 链路。零 API 调用。

## 我错在哪(2026-09-03)
我把 276 个历史视频解析判为「域不同, 不能当能力证据」。
★ owner 2026-08-12 的裁定是: 「随便投入一篇文章/一段聊天, 能够分析动态占比」,
  并当场用**一段与助听器毫无关系的中文聊天**实证了通用性; 同时**否决了我三版
  「每个域配一套容器」的方案**。我这次是同一个错换了件衣服 —— 又拿「域」当准入容器。

## 三件事必须拆开
· **能不能读**(capability): **域无关**。本探针就是它的证据。
· **抽取质量**(ASR/OCR 在不同语言上的准确率): **语言相关**, 仍未测。
· **分辨率/阈值**(calibration): **域相关**, 2026-08-19 已定 across_domains=NOT_ESTABLISHED,
  禁止跨域搬。★ 我原来是拿这一条的约束去否了第一条。
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from cce_contract import validate_case          # noqa: E402
from cce_event_assemble import assemble          # noqa: E402
from cce_foundation_adapter import adapt         # noqa: E402

SRC = Path("/Volumes/data/viral-skill-eval/results/video_parse")
OUT = ROOT / "tests" / "data" / "media_chain_on_history.json"


def run(limit=None):
    files = sorted(SRC.glob("*.json"))
    if limit:
        files = files[:limit]
    ok = Counter()
    obs_n, ev_n, kinds, etypes, langs = [], [], Counter(), Counter(), Counter()
    failures = []
    for f in files:
        try:
            parsed = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            ok["unreadable"] += 1; failures.append((f.name, f"unreadable: {e}")); continue
        if not isinstance(parsed, dict):
            # 有些历史文件是别的形状(list) —— 如实计入 skipped, 不静默略过
            ok["not_a_parse_artifact"] += 1
            failures.append((f.name, f"顶层是 {type(parsed).__name__}, 不是解析产物"))
            continue
        tags = (parsed.get("audio") or {}).get("tags") or []
        langs[next((t for t in tags if t in ("zh", "en", "ja", "ko")), "?")] += 1
        try:
            case = adapt(parsed, f)
            ev = assemble(case)
            v = validate_case(ev)
        except Exception as e:
            ok["chain_error"] += 1
            failures.append((f.name, f"{type(e).__name__}: {str(e)[:90]}")); continue
        if not v["ok"]:
            ok["contract_fail"] += 1
            failures.append((f.name, "contract: " + "; ".join(v["errors"][:2]))); continue
        ok["pass"] += 1
        obs_n.append(len(ev.get("observations", [])))
        ev_n.append(len(ev.get("events", [])))
        kinds.update({o.get("kind") for o in ev.get("observations", [])})
        etypes.update({e.get("event_type") for e in ev.get("events", [])})
    import statistics
    return {"kind": "cce.p3.media_chain_on_history.v1",
            "★status": "CAPABILITY_DEMONSTRATED_calibration_still_scoped",
            "★what_it_shows": "P3 链路能吃真实多模态产物并产出合同合法的 observations/events —— **能力**证据",
            "★what_it_does_not_show": (
                "① 抽取质量(ASR/OCR 在英文上的准确率)未测 —— 那是语言相关的另一件事; "
                "② 分辨率/阈值仍 across_domains=NOT_ESTABLISHED, **禁止跨域搬**"),
            "source": str(SRC), "files": len(files), "result": dict(ok),
            "language_mix": dict(langs),
            "observations": {"median": statistics.median(obs_n) if obs_n else None,
                             "min": min(obs_n) if obs_n else None,
                             "max": max(obs_n) if obs_n else None,
                             "total": sum(obs_n)},
            "events": {"median": statistics.median(ev_n) if ev_n else None,
                       "min": min(ev_n) if ev_n else None, "max": max(ev_n) if ev_n else None,
                       "total": sum(ev_n)},
            "observation_kinds": dict(kinds), "event_types": dict(etypes),
            "failures": failures[:10]}


def main():
    r = run()
    OUT.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{r['files']} 个历史解析产物 → {r['result']}")
    print(f"  observations 合计 {r['observations']['total']} (中位 {r['observations']['median']})")
    print(f"  events       合计 {r['events']['total']} (中位 {r['events']['median']})")
    print(f"  观察类型: {sorted(r['observation_kinds'])}")
    print(f"  事件类型: {sorted(r['event_types'])}")
    print(f"  语言分布: {r['language_mix']}")
    if r["failures"]:
        print("  失败样例:", r["failures"][:3])
    print(f"\n★ {r['★status']}")
    print(f"→ {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
