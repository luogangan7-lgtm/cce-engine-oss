#!/usr/bin/env python3
"""arm B —— 把分类学材料换成**生产 s2 的那一份**, 其余逐字不动。

预注册: tests/data/gate_vs_production_fieldset_prereg.json (条目校验和 958738e11d211ae5)

## 唯一变量
| | arm A(已有) | arm B(本轮) |
|---|---|---|
| signature | ✅ | ✅ |
| behavior | [:70] | [:60] |
| family / typical_codes / levers | ❌ | ✅ |
| 决策树 / 负例 / 5 条锚例 | ✅ | ❌ |
| 任务措辞·输出 schema·条目·模型·温度·截断 | ——— **两臂逐字相同** ——— |

## ★ 现网不动
本探针在旁路做模板手术, **不写回任何配置**。
"""
import json
import os
import pathlib
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parent.parent
VAULT = pathlib.Path("/Volumes/data/cce-identified-vault")
sys.path.insert(0, str(ROOT / "accuracy"))
sys.path.insert(0, str(ROOT / "scripts"))
import run_gates as RG  # noqa: E402

PRE = json.loads((ROOT / "tests/data/gate_vs_production_fieldset_prereg.json").read_text(encoding="utf-8"))
OUT = VAULT / "cce_runs" / "fieldset_arm_b"
_lock = threading.Lock()

# ── 模板手术: 砍掉 决策树/负例/锚例 三块, 其余逐字保留 ────────────────────
_CUT_FROM = "\n\n{decision_tree}"
_CUT_TO = "\n给你一条{unit}。"
assert RG.DIST_TMPL.count(_CUT_FROM) == 1, "★ 切点1 不唯一 —— 模板变了, 停"
assert RG.DIST_TMPL.count(_CUT_TO) == 1, "★ 切点2 不唯一 —— 模板变了, 停"
_i, _j = RG.DIST_TMPL.index(_CUT_FROM), RG.DIST_TMPL.index(_CUT_TO)
assert _i < _j
TMPL_B = RG.DIST_TMPL[:_i] + "\n" + RG.DIST_TMPL[_j:]
for gone in ("{decision_tree}", "{negative_examples}", "【锚例·display】"):
    assert gone not in TMPL_B, f"★ {gone} 没被切掉"
for kept in ("{brief}", "{unit}", "{body}", "只输出JSON", "带权分布"):
    assert kept in TMPL_B, f"★ {kept} 被误删 —— 任务形态必须两臂相同"

# ── 生产字段集的 brief —— 逐字照抄 _build_stage2_prompt 的构造 ────────────
TAXO = RG.TAXO
BRIEF_B = "\n".join(
    f"- {k['key']}({k['name']}|{k['family']}): 签名={json.dumps(k['signature'], ensure_ascii=False)}; "
    f"典型codes={json.dumps(k['typical_codes'], ensure_ascii=False)}; 行为={k['behavior'][:60]}"
    for k in TAXO["knots"])
BRIEF_B += ("\n与「杠杆」严格区分(杠杆=内容侧制造、瞬时: "
            + "、".join(TAXO["levers_not_knots"].keys()) + ")。")


def parse(txt):
    """★ 2026-09-08 修: 原来假设 `knots` 的元素都是 dict。

    实测有模型回了字面 `...`(省略号), 被 JSON 修复成 Python `Ellipsis`
    ⇒ `k.get` 抛 AttributeError ⇒ **整个 arm B 在 339/405 处崩掉**。
    ★ 一次解析失败本该只丢一条读数, 却因为异常没被隔离而丢掉了整轮的剩余部分。
      ⇒ 除了认元素类型, 还把每条的解析包进 try, **一条坏数据不许掀翻整轮**。
    """
    try:
        d = RG.extract_json_robust(txt, log_note="armB")
        if isinstance(d, dict) and isinstance(d.get("knots"), list) and d["knots"]:
            v = {}
            for k in d["knots"]:
                if not isinstance(k, dict):      # ★ `...` / 字符串 / null 都在这里被挡掉
                    continue
                key = k.get("key")
                if key in RG.KNOTS:
                    try:
                        v[key] = float(k.get("weight", 0))
                    except (TypeError, ValueError):
                        continue
            t = sum(v.values())
            if t > 0:
                return {k: w / t for k, w in v.items()}
    except Exception:
        pass          # ★ 解析失败 = 这一条没读到, 不是整轮失败
    return None


def main():
    a = json.loads((VAULT / "cce_runs/run_a_repeat/raw_annotations.json").read_text(encoding="utf-8"))
    ids = a["sample_ids"]
    import hashlib
    assert hashlib.sha256("|".join(ids).encode()).hexdigest()[:16] == \
        PRE["design"]["items"]["checksum"], "★ 条目集合与预注册校验和不符 —— 停"
    by_id = {x["id"]: x for x in RG.CORPUS}
    items = [by_id[i] for i in ids if i in by_id]
    assert len(items) == len(ids), f"★ 语料里少了 {len(ids)-len(items)} 条"

    OUT.mkdir(parents=True, exist_ok=True)
    RG.stamp_params(OUT)   # ★ 记下进 prompt 的环境参数, 否则事后无法核实可比性
    ck = OUT / "raw.json"
    rows = json.loads(ck.read_text(encoding="utf-8")) if ck.exists() else []
    have = {(r["id"], r["model"]) for r in rows}
    models = list(a["annotators"])
    jobs = [(it, m) for it in items for m in models if (it["id"], m) not in have]
    cap = PRE["★cost_ceiling"]["新增调用上限"]
    assert len(rows) + len(jobs) <= cap, f"★ 超过预注册上限 {cap} —— 停"
    print(f"arm B · {len(items)} 条 × {len(models)} 标注者 · 待跑 {len(jobs)} (上限 {cap})", flush=True)
    print("★ 只换分类学字段集合; 任务形态/条目/模型/温度/截断**逐字同 arm A**", flush=True)

    def one(job):
        it, m = job
        p = TMPL_B.format(unit=RG.UNIT_LABEL, brief=BRIEF_B, body=it["b"][:RG.BODY_CHARS])
        txt = ""
        try:
            txt = RG.call(m, p) or ""
            dist = parse(txt)
        except Exception:            # ★ 网络/解析任何异常都只丢这一条
            dist = None
        r = {"id": it["id"], "model": m, "dist": dist,
             "top1": max(dist, key=dist.get) if dist else None,
             # ★★ 2026-09-09: 落盘**模型原始响应**。没有它就无法区分「模型没答」与「解析器坏了」,
             #   也走不了「用同一确定性修复重新解析已有响应」这条最干净的重试路(那条不算重新抽样)。
             #   ⇒ 「聚合是判决要的, 逐条是复核要的」再深一层: **逐条 parsed 是复核要的, raw 是重解析要的。**
             "raw": txt[:4000]}
        with _lock:                       # ★ 逐条落盘 —— 崩了不丢已花的钱
            rows.append(r)
            ck.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
            if len(rows) % 40 == 0:
                print(f"  {len(rows)}/{len(items)*len(models)}", flush=True)
        return r

    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(one, jobs))
    print(f"\n★ 完成 {len(rows)} · 解析成功 {sum(1 for r in rows if r['top1'])}")
    (OUT / "prompt_arm_b_sample.txt").write_text(
        TMPL_B.format(unit=RG.UNIT_LABEL, brief=BRIEF_B, body="<BODY>"), encoding="utf-8")
    print("✏️ 已存 arm B 的完整 prompt 样张(供复核两臂唯一差异)")


if __name__ == "__main__":
    main()
