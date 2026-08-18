#!/usr/bin/env python3
"""
CCE 两级流水线 · 统一入口(供任何 agent 调用)
=================================================
第 1 级(冻结仪器): exp_v4_full_validation 逆推 → 四层分布 + appraisal + chain_trace
   —— prompt 与所有既有基准(n=31/G1-G3/τλ)同一,绝不改动。
第 2 级(结分类):  config/knot_taxonomy.json 九结签名 → 结组合(带权,非 argmax)
   —— 新增 appraisal 槽(归责 attribution / 对象层 target_layer)只活在本级,不污染第 1 级。

用法(其他 agent 从这里进,不要自己拼 prompt):
  set -a; . /Volumes/data/viral-skill-eval/.env; set +a
  python3 scripts/cce_knot_classify.py --text-file /path/to/content.txt \
      [--context "平台/形态一句话"] [--k 3] [--out /path/out.json]
  echo "some text" | python3 scripts/cce_knot_classify.py --stdin

输出 JSON:
  { "input_sha", "instrument": {stage1, stage2, taxonomy_version},
    "stage1": {四层分布, tops, appraisal, chain_trace, k, within_js},
    "stage2": {"knots": [ {key,name,weight,evidence_quote,signature{...含attribution/target_layer},
                           desire_code,need_code,playbook,freshness_days_hint} ],
               "levers_present": [...], "notes": ...},
    "caveats": [...] }
纪律: 全占比(结组合带权,允许多结,禁单 argmax 断言);解析失败全量存 raw 不截断;
      结论引用须带 config 里的 status 标注(G-K1/2/3 未验)。
"""
import os, sys, json, time, hashlib, argparse, statistics
ROOT = os.environ.get("VSE_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# .env 自加载(Windows/n8n 无 shell source;显式 utf-8 防 GBK 解码失败)
def _load_env_utf8():
    p = os.path.join(ROOT, ".env")
    if not os.path.exists(p):
        return
    with open(p, encoding="utf-8", errors="replace") as _f:
        for _l in _f:
            _l = _l.strip()
            if _l and not _l.startswith("#") and "=" in _l:
                _k, _v = _l.split("=", 1)
                _k = _k.strip()
                if _k.startswith("export "):
                    _k = _k[7:].strip()
                _v = _v.strip().strip('"').strip("\'")
                os.environ.setdefault(_k, _v)
_load_env_utf8()
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from concurrent.futures import ThreadPoolExecutor
from exp_v4_full_validation import call_parse, extract_json_robust, DESIRES, NEED_KEYS, top_label, js_divergence
from exp_v4_causal_chain import EMOTIONS, ACTIONS
from exp_crossmodel_desire import call_model

TAXO_PATH = os.path.join(ROOT, "config/knot_taxonomy.json")
RAW_DIR = os.path.join(ROOT, "results/knot_classify_raw")
LAYERS = ("desire_vec", "need_vec", "emotion_vec", "action_vec")


def stage1(text, context, k):
    case = (f"平台/形态: {context}\n"
            f"以下是内容全文(仅文本, 无任何互动数据):\n\n{text}\n\n"
            f"(注: 请对『写下这段内容的这一个人』反推其心理因果链四层占比分布。这是一个个体，不是群体。)")
    # 温度梯度按 k 自适应展开(修 2026-08-08: 原写死3档,--k>3 时静默降为3)
    _base = [0.0, 0.3, 0.6, 0.9, 0.15, 0.45, 0.75]
    temps = _base[:k] if k <= len(_base) else _base + [round(0.05 * i, 2) for i in range(1, k - len(_base) + 1)]

    def one(T):
        for att in range(3):
            c, p, pv, m, ok = call_parse("M3", case, T, f"knot_s1_T{T}")
            if ok:
                return pv
            os.makedirs(RAW_DIR, exist_ok=True)
            with open(os.path.join(RAW_DIR, f"s1_fail_{int(time.time())}_{T}_{att}.txt"), "w", encoding="utf-8") as f:
                f.write(c or "")
        return None

    with ThreadPoolExecutor(max_workers=min(5, k)) as ex:
        pvs = [p for p in ex.map(one, temps) if p]
    if not pvs:
        raise RuntimeError("stage1 全部失败(raw 已存 results/knot_classify_raw/)")
    avg = {L: [sum(p[L][j] for p in pvs) / len(pvs) for j in range(len(pvs[0][L]))] for L in LAYERS}
    within = None
    if len(pvs) >= 2:
        within = {L: round(sum(js_divergence(pvs[i][L], pvs[j][L])
                               for i in range(len(pvs)) for j in range(i + 1, len(pvs)))
                           / (len(pvs) * (len(pvs) - 1) / 2), 4) for L in LAYERS}
    # 2026-08-18: 同一个返回体里此前混着两种统计口径且无任何标注 ——
    #   layers/tops = K 次采样的聚合;  appraisal/chain_trace = pvs[0] 即单次抽样。
    # 下游若把它们等同看待就是口径混用。现在显式分开: 聚合项与单抽项各自归组,
    # 单抽项保留在 `single_draw` 下并带 caveat, 顶层同名键仍在(兼容), 但加 `_provenance` 说明。
    tops = {"desire": top_label(avg["desire_vec"], DESIRES),
            "need": top_label(avg["need_vec"], NEED_KEYS),
            "emotion": top_label(avg["emotion_vec"], EMOTIONS),
            "action": top_label(avg["action_vec"], ACTIONS)}
    return {
        "k_requested": k, "k_ok": len(pvs),
        "layers": avg,
        "tops": tops,
        # ↓ 兼容保留(下游已有读法), 但出处已在 _provenance 与 single_draw 里写明
        "appraisal": pvs[0].get("appraisal"),
        "chain_trace": pvs[0].get("chain_trace", ""),
        "single_draw": {
            "appraisal": pvs[0].get("appraisal"),
            "chain_trace": pvs[0].get("chain_trace", ""),
            "from_temperature": temps[0],
            "caveat": "单次抽样(温度阶梯第一档), 不是 K 次聚合; 与 layers/tops 不同口径, 不得并列引用",
        },
        "_provenance": {"aggregated": ["layers", "tops", "within_js"],
                        "single_draw": ["appraisal", "chain_trace"],
                        "n": len(pvs)},
        "within_js": within,
    }


def stage2(text, s1, taxo):
    knots_brief = "\n".join(
        f"- {k['key']}({k['name']}|{k['family']}): 签名={json.dumps(k['signature'], ensure_ascii=False)}; "
        f"典型codes={json.dumps(k['typical_codes'], ensure_ascii=False)}; 行为={k['behavior'][:60]}"
        for k in taxo["knots"])
    levers = "、".join(taxo["levers_not_knots"].keys())
    prompt = f"""你是 CCE 结分类器。「结」= 人身上预装的动机配置(四层的具名绑定),满足: 人侧预装、有保质期(约75天)。
与「杠杆」严格区分(杠杆=内容侧制造、瞬时: {levers})。

【九结签名(冻结 v{taxo['version']})】
{knots_brief}

【补充判定槽】attribution(归责): self/other_agent/system/none。target_layer(闸门对象): consumption_goal/epistemic_trust/identity/fairness。
【阻挡结特别提示】inertia 的行为签名是缺席与替代行为——认命句("but I understand it now"式)、长期忍受、伪装,即使文本表面是致谢也要识别。
【多结】一个人可同时持多结(如 归属+惯性)。
【★强度独立打分, 不要归一】对每个结独立给 intensity ∈ [0,1]:
  0 = 该结在这段内容里完全没有迹象; 1 = 强烈且明确。
  **不同结的 intensity 互相独立, 不要求加起来等于 1** ——
  「想要很强」与「审查也很强」可以同时成立(如 reward=0.85 且 audit=0.80),
  强行让总和为 1 会逼着你在两个都真实存在的结之间人为压低一个。
  只列 intensity > 0 的结; 没有迹象的结不要列。

【第 1 级引擎读出(参考,不是真值)】
四层首位: {json.dumps(s1['tops'], ensure_ascii=False)}
appraisal: {json.dumps(s1['appraisal'], ensure_ascii=False)}

【待分类内容】
{text}

只输出 JSON:
{{"knots":[{{"key":"<九结key之一>","intensity":0.0,"evidence_quote":"<原文引句>",
  "signature":{{"congruence":"","need_status":"","coping":"","time":"","attribution":"","target_layer":""}},
  "desire_code":"","need_code":"","freshness_days_hint":0}}],
 "levers_present":["内容里出现的杠杆(若有)"],"notes":"<一句话>"}}"""
    return _stage2_aggregate(prompt, taxo)


# ─────────────────────────────────────────────────────────────────────────────
# 2026-08-18: stage2 由「1 次抽样」改为「n 次抽样 + 聚合」。
#
# 为什么必须改: 同项重跑实测(run 32096357295, 整项指纹逐字相同, 断言经反向测试)
#   · 完全相同的读数对 0/6
#   · 单结权重极差 0.65 (pain_seek 四次里 0.65 / 0.50 / 0.40 / 完全缺席)
# 即单次调用给出的是一次抽样, 不是一个测量。此前它被当读数写进台账。
#
# 为什么不是别的修法(P0-0 探针实测, probes/seed_probe.py):
#   · 加 seed        —— 两个端点都接受该参数但不实现它(同 prompt n=6 仍 6 个不同输出)
#   · 调 temperature —— temperature=0.0 本身就不产生确定性(6/6 全不同)
#   · 换端点         —— Qwen 3/6 vs MiniMax 6/6, 减半但不归零, 且需重标定全部基线
# 剩下唯一诚实的方向: 承认不确定性, 报分布而不是报点值。
#
# ★ 刻意不设权重阈值。项目已有纪律: 差距落在噪声内的层禁止排名、CCE 输出禁止 argmax、
#   不得再拍未校准阈值。故稳定性判据取一个**二元且客观**的量:
#   n 次抽样的首结是否同一个 key。它不需要任何拍出来的数字。
# ─────────────────────────────────────────────────────────────────────────────
KNOT_N = int(os.environ.get("CCE_KNOT_N", "5"))


def _stage2_draw(prompt, taxo, tag):
    """一次抽样。失败重试 3 次, 全失败返回 None(由聚合层决定是否致命)。"""
    ok_keys = {k["key"] for k in taxo["knots"]}
    for att in range(3):
        content, _ = call_model("M3", prompt, temperature=0.0)
        d = extract_json_robust(content, log_note=f"knot_s2_{tag}")
        if isinstance(d, dict) and isinstance(d.get("knots"), list) and d["knots"]:
            if not [x for x in d["knots"] if x.get("key") not in ok_keys]:
                # 兼容: 模型偶尔仍吐 weight。统一落到 intensity。
                for x in d["knots"]:
                    if "intensity" not in x:
                        x["intensity"] = x.get("weight", 0.0)
                return d
        os.makedirs(RAW_DIR, exist_ok=True)
        with open(os.path.join(RAW_DIR, f"s2_fail_{int(time.time())}_{tag}_{att}.txt"),
                  "w", encoding="utf-8") as f:
            f.write(content or "")
    return None


def _stage2_aggregate(prompt, taxo, n=None):
    n = n or KNOT_N
    with ThreadPoolExecutor(max_workers=min(5, n)) as ex:
        draws = [d for d in ex.map(lambda i: _stage2_draw(prompt, taxo, f"d{i}"), range(n)) if d]
    if not draws:
        raise RuntimeError(f"stage2 {n} 次抽样全部失败(raw 已存)")

    # 每结: 出现次数 / 强度中位数 / 极差。缺席记 0 —— 分母恒为实际成功抽样数, 不是出现次数。
    keys = {x["key"] for d in draws for x in d["knots"]}
    stability = {}
    for k in keys:
        ws = [next((x["intensity"] for x in d["knots"] if x["key"] == k), 0.0) for d in draws]
        nz = [w for w in ws if w > 0]
        stability[k] = {"occur": len(nz), "n": len(draws),
                        "median": round(statistics.median(ws), 4),
                        "min": round(min(ws), 4), "max": round(max(ws), 4),
                        "range": round(max(ws) - min(ws), 4)}

    # 首结身份稳定性: 二元, 无阈值。n 次抽样的 top-1 key 是否全部相同。
    tops = [max(d["knots"], key=lambda x: x["intensity"])["key"] for d in draws]
    top1_stable = len(set(tops)) == 1

    # knots 保持 [[key, weight]] 的既有形状(weight 改为中位数), 下游 5 个消费者不需要改。
    merged = sorted(keys, key=lambda k: -stability[k]["median"])
    out_knots = []
    for k in merged:
        if stability[k]["median"] <= 0:
            continue
        meta_k = next(m for m in taxo["knots"] if m["key"] == k)
        src = next((x for d in draws for x in d["knots"] if x["key"] == k), {})
        out_knots.append({"key": k, "intensity": stability[k]["median"],
                          # weight = 全局组成(和为1), 仅为兼容下游既有 {key: weight} 读法而保留。
                          # 真正的强度是 intensity, 它不受和为 1 的约束。
                          "weight": 0.0,   # 占位, 循环后统一回填

                          "name": meta_k["name"], "family": meta_k["family"],
                          "playbook": meta_k["playbook"], "behavior_predicted": meta_k["behavior"],
                          "evidence_quote": src.get("evidence_quote", ""),
                          "signature": src.get("signature", {}),
                          "desire_code": src.get("desire_code", ""),
                          "need_code": src.get("need_code", ""),
                          "freshness_days_hint": src.get("freshness_days_hint", 0)})
    # ── 四层结构 (重构文档 §22) ────────────────────────────────────────────
    # 此前只有单层 9-simplex: 权重和恒为 1 ⇒ compositional data ⇒
    # 一个分量升必然压低其他 ⇒ 「想要很强」与「审查也很强」不能同时表达。
    # 实测确证: 21 次观测里 20 次总和恰为 1.0。
    #
    # 第 2 层 独立强度 intensity ∈ [0,1], 各结互不约束(prompt 已明确禁止归一)。
    # 第 3 层 族内组成 composition: 在推动族/阻挡族**各自内部**归一, 两族分别和为 1。
    # 第 4 层 族质量 mass —— §22 未钉死其定义, 本实现取**族内最大强度**,
    #        理由: §22.2 举例 reward=0.88 与 audit=0.81 同时成立(个体强度接近 1),
    #        若 mass 取和则会 >1 而失去「强度」量纲; 取最大值使 mass 与 intensity 同量纲,
    #        可直接用于 §22.4 的 high/low drive × high/low brake 四象限。
    #        composition 与 mass 正交: 前者是形状, 后者是水平。
    fam_of = {m["key"]: m["family"] for m in taxo["knots"]}
    inten = {k: stability[k]["median"] for k in keys if stability[k]["median"] > 0}
    families = {}
    for fam in {"推动", "阻挡"}:
        mem = {k: v for k, v in inten.items() if fam_of.get(k) == fam}
        tot = sum(mem.values())
        families[fam] = {
            "mass": round(max(mem.values()), 4) if mem else 0.0,
            "composition": {k: round(v / tot, 4) for k, v in sorted(mem.items(), key=lambda x: -x[1])} if tot else {},
            "members_active": len(mem)}
    dm, bm = families["推动"]["mass"], families["阻挡"]["mass"]
    _tot = sum(k["intensity"] for k in out_knots) or 1.0
    for k in out_knots:
        k["weight"] = round(k["intensity"] / _tot, 4)
    return {"knots": out_knots,
            "intensity": {k: round(v, 4) for k, v in sorted(inten.items(), key=lambda x: -x[1])},
            "families": families,
            "drive_brake": {"drive_mass": dm, "brake_mass": bm,
                            "quadrant": f"{'high' if dm >= 0.5 else 'low'}_drive/"
                                        f"{'high' if bm >= 0.5 else 'low'}_brake",
                            "note": "象限切点 0.5 是量纲中点, 不是校准阈值; 仅作分类标签, 不得作判据"},
            "levers_present": sorted({l for d in draws for l in (d.get("levers_present") or [])}),
            "notes": draws[0].get("notes", ""),
            "sampling": {"n_requested": n, "n_ok": len(draws),
                         "top1_stable": top1_stable, "top1_draws": tops,
                         "max_range": round(max((v["range"] for v in stability.values()), default=0.0), 4),
                         "per_knot": stability},
            "caveat": ("单次抽样不是测量: 本结果为 n 次抽样的逐结中位数; "
                       "top1_stable=false 时首结身份本身不可复现, 不得作断言依据")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text-file")
    ap.add_argument("--stdin", action="store_true")
    ap.add_argument("--context", default="社交平台文本内容")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--out")
    a = ap.parse_args()
    if not os.environ.get("MINIMAX_API_KEY"):
        print("MINIMAX_API_KEY 未设置(set -a; . .env; set +a)", file=sys.stderr); sys.exit(1)
    text = open(a.text_file, encoding="utf-8").read() if a.text_file else (sys.stdin.read() if a.stdin else None)
    if not text or not text.strip():
        print("无输入。--text-file 或 --stdin", file=sys.stderr); sys.exit(2)
    taxo = json.load(open(TAXO_PATH, encoding="utf-8"))
    s1 = stage1(text.strip(), a.context, a.k)
    s2 = stage2(text.strip(), s1, taxo)
    out = {
        "input_sha": hashlib.sha256(text.encode()).hexdigest()[:16],
        "run_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "instrument": {"stage1": "exp_v4_full_validation(frozen, M3)",
                       "stage2": f"knot_taxonomy v{taxo['version']} (M3)",
                       "taxonomy_status": taxo["status"]},
        "stage1": s1, "stage2": s2,
        "caveats": [
            "结分类学 v1: G-K1/G-K2/G-K3 验收未跑,引用须带「未验」",
            "全占比: knots 是带权组合,禁把单个 top 当断言",
            "第1级情绪层禁单top(4模型面板判);行动层无分辨率(三重合证),两处以分布/appraisal为准",
        ],
    }
    js = json.dumps(out, ensure_ascii=False, indent=1)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(js)
        print(f"→ {a.out}", file=sys.stderr)
    print(js)


if __name__ == "__main__":
    main()
