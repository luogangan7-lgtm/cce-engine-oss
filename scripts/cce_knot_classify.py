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
import os, sys, json, time, math, hashlib, argparse, statistics
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


# ★ 2026-08-18 [2/4] 补一个真洞: 此前 `prompt_sha256` **只哈希了 `_stage2_template`** ——
#   stage1 的 prompt 根本没进仪器指纹。改那句「请对这一个人反推…这是一个个体」
#   **不会改变 instrument_hash** ⇒ **静默换仪器**, 正是 instrument_id 当初要防的事。
#   现在 s1 与 s2 各出一份模板哈希, 两边都忘不掉。
def _stage1_template(context="<CONTEXT>", text="<TEXT>"):
    """stage1 prompt 里**不随内容变化**的部分, 变量位用哨兵占位, 用于取仪器哈希。"""
    return _stage1_case(text, context)


def _stage1_case(text, context):
    return (f"平台/形态: {context}\n"
            f"以下是内容全文(仅文本, 无任何互动数据):\n\n{text}\n\n"
            f"(注: 若这段内容确实是某一个人写下的自我表达，请对『写下这段内容的这一个人』"
            f"反推其心理因果链四层占比分布——这是一个个体，不是群体。\n"
            f"若它**不是个人表达**（例如纯数据表、条款样板、说明书、操作步骤、代码、目录、"
            f"日志），请在 JSON 顶层返回 \"no_inferable_subject\": true 并说明理由，"
            f"**不要为它构造一个人**。四层分布此时留空或省略即可。)")


def stage1(text, context, k):
    case = _stage1_case(text, context)
    # 温度梯度按 k 自适应展开(修 2026-08-08: 原写死3档,--k>3 时静默降为3)
    _base = _S1_BASE_TEMPS
    temps = _base[:k] if k <= len(_base) else _base + [round(0.05 * i, 2) for i in range(1, k - len(_base) + 1)]

    def one(T):
        for att in range(3):
            c, p, pv, m, ok = call_parse("M3", case, T, f"knot_s1_T{T}")
            # ★ 弃权信号必须**显式**。绝不能拿「全零向量」当弃权 ——
            #   top_label(全零) 会返回第一个标签(实测: 拥有欲), 即一个自信的假读数。
            if isinstance(p, dict) and p.get("no_inferable_subject") is True:
                return {"_abstained": True, "_reason": str(p.get("reason", ""))[:200]}
            if ok:
                pv["_abstained"] = False
                return pv
            os.makedirs(RAW_DIR, exist_ok=True)
            with open(os.path.join(RAW_DIR, f"s1_fail_{int(time.time())}_{T}_{att}.txt"), "w", encoding="utf-8") as f:
                f.write(c or "")
        return None

    with ThreadPoolExecutor(max_workers=min(5, k)) as ex:
        # 2026-08-18: 此前只留 pvs, 丢掉了「哪一档温度成功了」——
        # 于是 from_temperature 恒写 temps[0], 首档失败时记的是错的出处。
        # 一个专门记出处的字段记错出处, 比没有这个字段更坏。
        paired = [(T, p) for T, p in zip(temps, ex.map(one, temps)) if p]
    pvs_all = [p for _, p in paired]
    if not pvs_all:
        raise RuntimeError("stage1 全部失败(raw 已存 results/knot_classify_raw/)")
    # 弃权与失败必须分开: 失败是管线坏了, 弃权是仪器声明「这里读不出人」。
    n_abstain = sum(1 for p in pvs_all if p.get("_abstained"))
    pvs = [p for p in pvs_all if not p.get("_abstained")]
    if not pvs:
        # ★ 2026-08-19 修三处(同一个 bug 的第二现场):
        #   ① k_ok 曾是 len(pvs_all) —— 把**弃权的 draw 也算成成功**。上一轮只修了非弃权分支。
        #   ② 缺 k_attempted/k_valid/k_abstained/measurement_status, 下游用新键会静默兜底。
        #   ③ draws 曾是 [] —— 逐 draw 弃权率无从计算, 通道自检失效(实际害我作废了一整轮 156 调用)。
        return {"k_requested": k, "k_attempted": len(pvs_all), "k_valid": 0,
                "k_abstained": n_abstain, "k_ok": 0,
                "measurement_status": "abstain",
                "n_abstain": n_abstain, "abstained": True,
                "abstain_reason": next((p.get("_reason") for p in pvs_all if p.get("_reason")),
                                       "全部 draw 声明无可推断主体"),
                "layers": {}, "tops": {},
                "draws": [{"from_temperature": T, "abstained": True,
                           "reason": pv.get("_reason", ""), "tops": {},
                           "desire_vec": None, "need_vec": None,
                           "emotion_vec": None, "action_vec": None, "appraisal": None}
                          for T, pv in paired],
                "within_js": None,
                "caveat": ("stage1 全体弃权: 这不是「四层分布都是 0」, "
                           "而是仪器声明本次输入不构成个人表达, 不产出心理读数。")}
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
    # ★ 全零守卫: top_label 对全零向量会返回**第一个标签**(实测 拥有欲) —— 一个自信的假读数。
    #   共享的 top_label 被别处也在用, 不动它; 在本处加守卫。
    def _top(vec, keys):
        return top_label(vec, keys) if vec and sum(vec) > 0 else None

    tops = {"desire": _top(avg["desire_vec"], DESIRES),
            "need": _top(avg["need_vec"], NEED_KEYS),
            "emotion": _top(avg["emotion_vec"], EMOTIONS),
            "action": _top(avg["action_vec"], ACTIONS)}
    # 2026-08-18: 额外暴露**逐 draw** 的 tops/appraisal。
    # 用途见 _stage2_aggregate 的 s1 配对: 此前 s2 的 n 次抽样共享同一份 pvs[0] 的 appraisal,
    # 于是一个 rep 内所有 s2 抽样吃同一份抖过的 prompt ——
    # **s2 的聚合器在数学上碰不到 rep 间方差**, 无论 n 多大。
    # 把 k 份 s1 draw 分发给 n 份 s2 draw, s1 的方差才进得了 s2 的聚合。
    # ★ 2026-08-18 draw ledger: 此前每个 draw 只留 tops(**顶层标签**)与 appraisal,
    #   四层完整向量在算完 top 之后就被丢掉。后果(外部源码审计指出, 已核实):
    #   事后无法重算不同聚合、无法重算 within_js、无法做维度级 bootstrap。
    #   ★ API 调用比 JSON 存储贵得多 —— 事后发现 raw draw 没留是不可逆损失。
    per_draw = [({"from_temperature": T, "abstained": True,
                  "reason": pv.get("_reason", ""),
                  "desire_vec": None, "need_vec": None,
                  "emotion_vec": None, "action_vec": None,
                  "tops": {}, "appraisal": None}
                 if pv.get("_abstained") else
                 {"from_temperature": T, "abstained": False,
                  "desire_vec": pv["desire_vec"], "need_vec": pv["need_vec"],
                  "emotion_vec": pv["emotion_vec"], "action_vec": pv["action_vec"],
                  "tops": {"desire": _top(pv["desire_vec"], DESIRES),
                           "need": _top(pv["need_vec"], NEED_KEYS),
                           "emotion": _top(pv["emotion_vec"], EMOTIONS),
                           "action": _top(pv["action_vec"], ACTIONS)},
                  "appraisal": pv.get("appraisal")})
                for T, pv in paired]
    return {
        # ★ 2026-08-19: k_ok 曾把**弃权的 draw 也算成成功**(len(pvs_all)) ——
        #   于是 2/3 弃权时它报 k_ok=3, 下游以为拿到了三档。外部评审指出后实测确认。
        #   现在三个计数各归各: attempted / valid / abstained, k_ok 只等于 valid。
        "k_requested": k, "k_attempted": len(pvs_all), "k_valid": len(pvs),
        "k_abstained": n_abstain, "k_ok": len(pvs),
        "n_abstain": n_abstain, "abstained": False,
        # k_valid<2 时组内散布无从计算 ⇒ 这是**合法的测量不足**, 不是管线故障。
        "measurement_status": ("insufficient_replicates" if len(pvs) < 2 else "qualified"),
        "layers": avg,
        "tops": tops,
        "draws": per_draw,
        # ↓ 兼容保留(下游已有读法), 但出处已在 _provenance 与 single_draw 里写明
        "appraisal": pvs[0].get("appraisal"),
        "chain_trace": pvs[0].get("chain_trace", ""),
        "single_draw": {
            "appraisal": pvs[0].get("appraisal"),
            "chain_trace": pvs[0].get("chain_trace", ""),
            "from_temperature": paired[0][0] if paired else None,
            "caveat": "单次抽样(温度阶梯第一档), 不是 K 次聚合; 与 layers/tops 不同口径, 不得并列引用",
        },
        "_provenance": {"aggregated": ["layers", "tops", "within_js"],
                        "single_draw": ["appraisal", "chain_trace"],
                        "n": len(pvs)},
        "within_js": within,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Measurement System · Instrument Definition (2026-08-18)
#
# 存在理由: 2026-08-18 的一组 A/B 作废, 根因是**prompt 与采样数一起变了而无人察觉** ——
# 当时没有「仪器」这个一等概念, 两臂看起来只差一个环境变量。
# 仪器版本化之后, 那种混淆在**构造上**不可能发生: 两臂 instrument_hash 不同, 跑之前就能拦。
#
# 覆盖六项(缺一项都可能让两次读数不可比):
#   ontology_version  九结分类学版本
#   prompt_sha256     ★ 由**模板文本本身**导出 —— 改一个字哈希就变, 忘不掉
#   model / endpoint  模型与端点(服务端微调 = 换仪器, 见既有「仪器漂移」纪律)
#   sampling_policy   s1 的 k 与温度阶梯 / s2 的 n
#
# ★ 2026-08-19 重划: aggregation_policy 从 instrument_hash 里**移出**, 归入
#   qualification_policy_hash。判据 = 「改它之后已采集的 raw draw 还能不能用」——
#   support_rule / intensity_stat / abstention / k_valid 都能从 draw ledger 重算,
#   不该让仪器标定作废(重标定要真投料, 代价不对等)。
# ─────────────────────────────────────────────────────────────────────────────
def _stage2_template(taxo):
    """把 prompt 里**不随内容变化**的部分单独构造出来, 用于取仪器哈希。

    关键: 变量位用固定哨兵占位。这样哈希只反映「仪器」, 不反映「被测对象」。
    """
    return _build_stage2_prompt(taxo, "<TEXT>", {"tops": "<TOPS>", "appraisal": "<APPRAISAL>"})


# ★ 仪器换代桥接。2026-08-18 [2/4] 把 s1 prompt 与 abstention 纳入指纹后, 哈希必然改变。
#   **物理仪器没变**(prompt 原文、模型、端点、采样策略全同), 变的是「身份定义更完整了」。
#   为了让当日六个 run 仍能与后续对账, 把换代关系钉在这里, 并由测试守住:
#   旧哈希 57ec6cf478d3875e 对应的 s1 prompt sha 就是下面这个;
#   若将来 s1 prompt 被改动, 该 sha 变化 ⇒ 桥接断开 ⇒ 当日数据**不再**可与新数据比较。
# ★ 仪器谱系。每一代都记清楚「哪些数据是它产的」与「上一代的标定还能不能用」。
INSTRUMENT_LINEAGE = [
    {"gen": 1, "hash": "57ec6cf478d3875e", "s1_prompt_sha256": "d73764202b732e98",
     "s2_prompt_sha256": "b8d0f60d66d10f12",
     "runs": ["32130867661", "32141330271", "32143780680",
              "32143785964", "32147076464", "32150369795"],
     "note": "2026-08-18 当日全部六次实测。指纹未覆盖 s1 prompt 与 abstention 策略。"},
    {"gen": 2, "hash": "287d07a0ef1ea78e", "s1_prompt_sha256": "d73764202b732e98",
     "s2_prompt_sha256": "b8d0f60d66d10f12", "runs": [],
     "note": ("[2/4] 把 s1 prompt 与 abstention 策略纳入指纹。**物理仪器与 gen1 相同**"
              "(prompt 原文/模型/端点/采样策略全同), 只是身份定义更完整 ⇒ "
              "gen1 的数据与标定对 gen2 **仍然适用**。")},
    {"gen": 3, "hash": "ea70b373d5bef630",
     "s1_prompt_sha256": "eadcdcdac46a5180", "s2_prompt_sha256": "b8d0f60d66d10f12",
     "runs": ["32223866100", "32224198135", "32227550589(VOID)", "32231676330"],
     "note": ("stage1 prompt 改为**允许模型声明无可推断主体**(no_inferable_subject)。"
              "★ 这是**物理仪器变了** —— 被测对象收到的指令不同, 读数分布可能整体移动。"
              "⇒ **gen1/gen2 的标定对 gen3 不适用**, 必须重新标定。"
              "hash 留 None: 它由代码现算, 写死会与实现漂移。")},
    {"gen": 4, "hash": None,
     "s1_prompt_sha256": "eadcdcdac46a5180", "s2_prompt_sha256": "b8d0f60d66d10f12",
     "runs": [],
     "note": ("把 aggregation_policy 从 instrument_hash 移出, 归入 qualification_policy_hash。"
              "★ **物理仪器与 gen3 完全相同**(prompt/model/endpoint/采样策略全同), "
              "只是标识符重新划界 —— 与 gen1→gen2 同性质 ⇒ **gen3 的标定对 gen4 仍适用**。"
              "判据: 改它之后已采集的 raw draw 还能不能用。hash 留 None(由代码现算)。")},
]
# 兼容别名(旧引用仍可用)
LEGACY_INSTRUMENT_20260818 = INSTRUMENT_LINEAGE[0]


def _spec_field(spec, path):
    cur = spec
    for part in path.split("."):
        cur = (cur or {}).get(part)
    return cur


def calibration_transfers(calibration, taxo, k=3, knot_n=None, s1_pairing=None):
    """某个标定能不能搬到当前仪器上。

    ⚠️ 2026-08-19 外部评审纠正: 初版拿「s1/s2 prompt 相同」当**通用迁移律**, **太松**。
       prompt 一字未改, 但 s2 的 n 从 5 改到 10、median 改成 mean、support 规则改了、
       s1 配对改了、端点换了 —— 读数分布与噪声底都会变, 标定同样失效。
       正确做法: **每个标定自己声明它依赖仪器定义的哪些部分**, 只比那些。
       比「整个 instrument_hash 必须相同」更精细, 比「prompt 相同就搬」更安全。

    calibration: 需含 `depends_on`(仪器 spec 里的字段路径列表) 与 `snapshot`(当时的取值)。
    """
    dep = calibration.get("depends_on")
    snap = calibration.get("snapshot")
    if not dep or not snap:
        return {"transfers": False, "reason": "标定未声明 depends_on/snapshot ⇒ 无法判定, 一律不搬"}
    cur = instrument_id(taxo, k=k, knot_n=knot_n, s1_pairing=s1_pairing)["spec"]
    changed = [d for d in dep if _spec_field(cur, d) != snap.get(d)]
    return {"transfers": not changed,
            "changed": changed,
            "reason": ("所依赖的仪器字段全部未变 ⇒ 标定可搬" if not changed else
                       f"★ 依赖字段已变 {changed} ⇒ 标定**不可搬**, 必须重标定"),
            "checked": dep}


def instrument_id(taxo, k=None, knot_n=None, s1_pairing=None):
    """当前仪器的完整定义 + 哈希。任何跨读数比较之前必须先比它。"""
    from exp_crossmodel_desire import MODELS
    m = MODELS["M3"]
    spec = {
        "ontology_version": taxo.get("version"),
        # 拆成两份: 此前只有 s2, 改 s1 prompt 不换指纹(静默换仪器)。两边都要覆盖。
        "s1_prompt_sha256": hashlib.sha256(_stage1_template().encode("utf-8")).hexdigest()[:16],
        "s2_prompt_sha256": hashlib.sha256(_stage2_template(taxo).encode("utf-8")).hexdigest()[:16],
        "model": m["model"],
        "endpoint": m["base"],
        "sampling_policy": {"s1_k": k, "s1_temps": _S1_BASE_TEMPS, "s2_n": knot_n or KNOT_N,
                            "s1_pairing": s1_pairing or "unspecified"},
        "aggregation_policy": {"support_rule": SUPPORT_RULE,
                               "intensity_stat": "median_of_nonzero",
                               "composition": "within_family_then_global_weight",
                               # 空 knots 从「解析失败」改为「合法弃权」—— 行为变了就是换仪器
                               "abstention": ABSTENTION_POLICY},
    }
    # ★★ 2026-08-19: 拆成两个哈希。判据不是「prompt vs schema」, 而是**可操作的一条**:
    #     改了它之后, **已采集的原始 draw 还能不能用**?
    #       不能用(必须重新投料) → instrument      —— 它决定 draw 本身
    #       能用(可从 draw ledger 重算) → qualification policy —— 它只决定怎么解读 draw
    #   为什么要拆: 此前 support_rule / intensity_stat / abstention / k_valid 这些
    #   **可重算**的策略也进了 instrument_hash, 于是每修一次资格协议就白白作废一次仪器标定
    #   (而重标定要真投料)。外部评审指出后, 按上述判据重划。
    #   ⚠️ spec 仍原样保留全部字段(不改形状), 以免 calibration 的 depends_on 路径失效。
    _INSTRUMENT_FIELDS = ("ontology_version", "s1_prompt_sha256", "s2_prompt_sha256",
                          "model", "endpoint", "sampling_policy")
    _POLICY_FIELDS = ("aggregation_policy", "qualification_policy")
    spec["qualification_policy"] = {
        "k_valid_min": 2,            # <2 ⇒ WITHHOLD(within_js 数学上需要 >=2 个有效 draw)
        "insufficient_replicates": "WITHHOLD",
        "abstain_semantics": ABSTENTION_POLICY,
        "statuses": ["qualified", "abstain", "insufficient_replicates"],
    }
    ih = hashlib.sha256(json.dumps({k: spec[k] for k in _INSTRUMENT_FIELDS},
                                   ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    qh = hashlib.sha256(json.dumps({k: spec[k] for k in _POLICY_FIELDS},
                                   ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    return {"instrument_hash": ih, "qualification_policy_hash": qh, "spec": spec,
            "hash_scope": {"instrument": list(_INSTRUMENT_FIELDS),
                           "qualification_policy": list(_POLICY_FIELDS),
                           "criterion": "改它之后已采集的 raw draw 还能不能用"}}


def assert_same_instrument(readouts, what="跨读数比较"):
    """★ 不同仪器的读数不可比。这是那次 A/B 作废的直接教训, 写成可执行的拦截。"""
    hs = {r.get("instrument", {}).get("instrument_hash") for r in readouts}
    # 缺失先判 —— 它比「不同」更具体, 且此前放在后面会被前一分支吞掉,
    # 报出「涉及 2 个不同仪器 [只列了1个]」这种自相矛盾的诊断。
    # 一个诊断信息自己报错数量, 比没有诊断更坏。
    if None in hs:
        n_missing = sum(1 for r in readouts
                        if not r.get("instrument", {}).get("instrument_hash"))
        raise RuntimeError(
            f"{what}被拒绝: {n_missing}/{len(readouts)} 个读数不带 instrument_hash, "
            "无从判断是否同一把尺子。没有仪器标识的读数不参与任何比较。")
    if len(hs) > 1:
        raise RuntimeError(
            f"{what}被拒绝: 涉及 {len(hs)} 个不同仪器 {sorted(hs)}。"
            "换了仪器就是换了尺子, 读数不可直接比较 —— "
            "2026-08-18 的一组 A/B 正是因为 prompt 与采样数一起变了而作废。")
    return hs.pop()


def _build_stage2_prompt(taxo, text, s1):
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
    return prompt


def stage2(text, s1, taxo):
    # 每份 s1 draw 各生成一份 prompt, s2 的 n 次抽样轮转使用。
    # 此前是 s1 聚合后的 tops + pvs[0] 的 appraisal 拼成**一份**固定 prompt。
    #
    # ⚠️ 2026-08-18 当晚 probes/pairing_calibration.py (R=6 x 2臂, s1_pairing 作因子)
    # 实测: **本次改动没有改善任何可测的东西。** 核心结口径下两臂的
    # 实际 rep 间变动**都是 0.33**, 一点没动; 校准比 NEW 1.61 / OLD 1.33, 两臂皆过报。
    # 原先写在这里的机理("s2 所有抽样共享同一份 s1 噪声, 聚合再多次也削不掉")
    # **有反证**: 若 s1 真是大头, 解冻它应当改变 rep 间变动, 而它没有。
    #
    # 代码保留是因为零新增成本、且"不冻结一个已知噪声源"在原则上更干净。
    # **但它的地位是结构性选择, 不是经过验证的改进** —— 不要拿它当已证结论往下推。
    s1_draws = s1.get("draws") or []
    # ★ s1 已弃权 ⇒ 不必再发 s2 调用(既省钱又避免为不存在的主体构造九结)
    if s1.get("abstained"):
        return {"knots": [], "measurement_status": "abstain",
                "abstain_reason": "stage1 弃权: " + str(s1.get("abstain_reason", "")),
                "draw_ledger": [], "intensity": {}, "families": {},
                "levers_present": [], "notes": "", "n_abstain": 0,
                "s1_pairing": "n/a(s1_abstained)",
                "instrument": instrument_id(taxo, k=s1.get("k_requested"), knot_n=KNOT_N,
                                            s1_pairing="n/a(s1_abstained)"),
                "sampling": {"n_requested": 0, "n_ok": 0, "top1_mode": None,
                             "top1_mode_share": 0.0, "top1_unanimous": False,
                             "top1_stable": False, "top1_draws": [], "max_range": 0.0,
                             "per_knot": {}},
                "caveat": "stage1 声明无可推断主体 ⇒ 本次不产出九结, 且未发起 s2 调用。"}
    if s1_draws:
        prompts = [_build_stage2_prompt(taxo, text,
                                        {"tops": d["tops"], "appraisal": d["appraisal"]})
                   for d in s1_draws]
        pairing = f"round_robin_over_{len(s1_draws)}_s1_draws"
    else:   # 兼容: 老调用方没有 draws 字段
        prompts = _build_stage2_prompt(taxo, text, s1)
        pairing = "single_s1_aggregate(legacy)"
    out = _stage2_aggregate(prompts, taxo)
    out["instrument"] = instrument_id(taxo, k=s1.get("k_requested"), knot_n=KNOT_N, s1_pairing=pairing)
    out["s1_pairing"] = pairing
    return out


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
# ★ 稳定性判据取二元且客观的量: n 次抽样的首结是否同一个 key。它不需要拍数字。
#
# ⚠️ 2026-08-18 二次更正: 本处初稿写「刻意不设权重阈值」——**那句是假的**。
#   聚合里 `median(ws) > 0`(缺席记 0)等价于一个未写下来的硬阈值 `occur > n/2`,
#   它藏在中位数算术里, 没写成常量, 也就没法被质疑或校准。
#   对抗评审逐条指出后已改为显式常量 SUPPORT_RULE, 见下。
#   教训: **声称「没有阈值」之前, 先找一遍藏在算术里的那个。**
# ─────────────────────────────────────────────────────────────────────────────
# 九结全集。draw ledger 要「缺席显式记 0」就必须有全集, 不能只列出现过的。
KNOTS_ALL = ("pain_seek", "injustice", "belong", "reward", "display",
             "itch", "suspend", "inertia", "audit")

# 弃权策略。此前 `{"knots": []}` 被当成解析失败去重试 —— 模型就算想说「读不出」也说不出口。
# 现在它是**合法弃权**。注意: 这不代表 stage1 的 prompt 允许模型弃权(那句话仍要求"反推"),
# 那是另一次改动, 且会再换一次仪器 —— 见 ABSTENTION_S1_NOTE。
ABSTENTION_POLICY = "empty_knots_is_abstain_v1"
ABSTENTION_S1_NOTE = (
    "stage1 prompt 仍要求『对写下这段内容的这一个人反推』, 未授权模型判断『有没有主体』。"
    "本次只打通 stage2 与 ingest 两处通道; 改 s1 prompt 会再换一次仪器并使当日标定失效, "
    "属独立决策。")

KNOT_N = int(os.environ.get("CCE_KNOT_N", "5"))

# 少数派抽样不进输出。此前这条规则藏在 `median(缺席记0) > 0` 里, 从未被写下来。
# 现在写成常量, 是为了让它**可以被质疑与校准** —— 而不是为了给它辩护。
# 奇数 n 上与旧行为完全等价; 偶数 n 上顺带修掉「occur=n/2 报真值一半」的 bug。
SUPPORT_RULE = "occur * 2 > n"   # 严格多数
#
# ★ 2026-08-18 三次更正 —— 本规则**不再当过滤器用, 只当注记**。
#   实测(run 32130867661, 3 文本 × R=4): 3/3 文本各有一个结在这条线上翻转,
#   重跑之间结集完全相同的比例只有 0.50/0.50/0.33。P1a 判 FAIL。
#
#   根因不是 n 太小, 是**在一个连续量上切一刀**: 让输出布尔不稳的 p 区间宽度
#   n=5→0.507, n=20→0.277 —— 4 倍成本只压掉一半, O(1/√n)。
#
#   但更要紧的是另一半实测: occur/n 的 rep 间抖动 **过散参数 1.20, X²/df=1.23, p=0.159**
#   ⇒ **无法拒绝「抖动全部来自 n=5 抽样」**。仪器没有额外漂移。
#   所以问题从来不是仪器不稳, 是**把一个 ±0.22 的测量洗成了一个干净的布尔**。
#
#   修法: knots 发布**全部被观测到的结**, 每条自带 occur/n 与 Wilson 95% 区间;
#   本规则只留在 support_majority 字段里, 供需要布尔的下游自行决定。
#   weight 仍只在过闸结上归一 ⇒ 下游 {key: weight} 逐值不变。
#
#   ⚠️ 我此前把「量化步长 ±0.2(一个计数)」说成了可复现性 —— 那是两回事。
#      实测 rep 间极差最大 0.60(3 个计数), 与二项预期一致。

# s1 温度阶梯。提为常量供 instrument_id 引用 —— 改它就是换仪器。
_S1_BASE_TEMPS = [0.0, 0.3, 0.6, 0.9, 0.15, 0.45, 0.75]


def _has_support(st_k):
    return st_k["occur"] * 2 > st_k["n"]


def _wilson(occur, n, z=1.96):
    """occur/n 的 Wilson 95% 区间。

    不用 sqrt(p(1-p)/n): 它在 occur=0 或 occur=n 时给 se=0,
    等于宣称「5 次全中 ⇒ 完全确定」。Wilson 在边界不塌 ——
    实测 5/5 给 [0.566, 1.0], 即**全票通过的结, 真值也可能低到 0.57**。
    这正是布尔闸藏起来的那部分。
    """
    if n <= 0:
        return [0.0, 1.0]
    p = occur / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def _stage2_draw(prompt, taxo, tag):
    """一次抽样。失败重试 3 次, 全失败返回 None(由聚合层决定是否致命)。"""
    ok_keys = {k["key"] for k in taxo["knots"]}
    for att in range(3):
        content, _ = call_model("M3", prompt, temperature=0.0)
        d = extract_json_robust(content, log_note=f"knot_s2_{tag}")
        # ★ 去掉 `and d["knots"]`: 空列表此前被当成解析失败去重试 ——
        #   模型就算想说「这里读不出人」也说不出口。现在它是合法弃权。
        if isinstance(d, dict) and isinstance(d.get("knots"), list):
            if not [x for x in d["knots"] if x.get("key") not in ok_keys]:
                # 兼容: 模型偶尔仍吐 weight。统一落到 intensity。
                # ★ 记录垫片是否触发 —— 若模型吐的是和为 1 的 weight(旧 schema),
                #   那些 draw 与自由 intensity 的 draw **量纲不同**(max~0.4 vs ~0.9),
                #   却一起进逐坐标中位数。静默量纲混合, 不落盘就永远看不见。
                d["_weight_shim_fired"] = any("intensity" not in x for x in d["knots"])
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
    """prompt 可以是**一个字符串**, 也可以是**一列字符串**(每份对应一个 s1 draw)。

    2026-08-18: 传列表时逐 draw 轮转 —— 这是「仪器边界必须包含 s1」的落地。
    传单串时行为与改动前完全一致(兼容, 且用于离线测试)。
    """
    n = n or KNOT_N
    prompts = prompt if isinstance(prompt, (list, tuple)) else [prompt]
    with ThreadPoolExecutor(max_workers=min(5, n)) as ex:
        draws = [d for d in ex.map(
            lambda i: _stage2_draw(prompts[i % len(prompts)], taxo, f"d{i}"), range(n)) if d]
    if not draws:
        raise RuntimeError(f"stage2 {n} 次抽样全部失败(raw 已存)")

    # 每结: 出现次数 / 强度中位数 / 极差。缺席记 0 —— 分母恒为实际成功抽样数, 不是出现次数。
    keys = {x["key"] for d in draws for x in d["knots"]}
    stability = {}
    for k in keys:
        ws = [next((x["intensity"] for x in d["knots"] if x["key"] == k), 0.0) for d in draws]
        nz = [w for w in ws if w > 0]
        # 强度与出现率是两维, 不塌成一个数。
        # 此前 median(ws)(缺席记 0) 把两者乘在了一起, 后果实测:
        #   · occur=3/5 时报值系统性低估约 25%(蒙特卡洛 20 万次: 真 0.500 → 报 0.374)
        #   · 偶数 n 上 occur=n/2 报**真值的一半**(n=4/6/8 实测 0.40 → 0.20)
        #   · 且 median>0 本身就是一个藏在算术里的未校准阈值
        stability[k] = {"occur": len(nz), "n": len(draws),
                        "support": round(len(nz) / len(draws), 4),
                        "intensity": round(statistics.median(nz), 4) if nz else 0.0,
                        # median 保留为兼容别名, 语义已改为「出现时的强度中位数」
                        "median": round(statistics.median(nz), 4) if nz else 0.0,
                        "min": round(min(nz), 4) if nz else 0.0,
                        "max": round(max(nz), 4) if nz else 0.0,
                        "range": round(max(nz) - min(nz), 4) if nz else 0.0}

    # 首结身份的抽样一致性。
    #
    # ⚠️ 2026-08-18 更正: 此前这个字段叫 top1_stable, 判据是 len(set(tops))==1。
    #   那个名字与判据都有问题:
    #   · **n=1 时 len(set)==1 恒成立** ⇒ 扣发闸在单抽下永不触发
    #   · P(全体一致) ≈ p^n, 随 n 单调下降是**构造性**的 ——
    #     把默认 n 从 1 提到 5, 等于凭算术收紧了闸, 与被测现象是否变化无关。
    #     闸的严格度成了旋钮, 不是测量。
    #   · 「stable」这个词把样本的性质说成了世界的性质。
    #
    # 改法: 主量报**众数占比**(跨 n 可比), 二元字段改名为 top1_unanimous ——
    #   「一致」是样本的事实, 「稳定」是对世界的断言, 二者不该共用一个名字。
    from collections import Counter as _C
    # 弃权的 draw 没有 top1 —— 它不投票, 但**必须计入分母**, 否则弃权会抬高众数占比。
    tops = [max(d["knots"], key=lambda x: x["intensity"])["key"] for d in draws if d["knots"]]
    n_abstain = sum(1 for d in draws if not d["knots"])
    if not tops:
        return {"knots": [], "measurement_status": "abstain",
                "abstain_reason": f"{n_abstain}/{len(draws)} 次抽样均未读出任何结",
                "draw_ledger": [{"draw_id": i, "abstained": True,
                                 "knot_vector": {k: 0.0 for k in KNOTS_ALL}}
                                for i in range(len(draws))],
                "intensity": {}, "families": {}, "levers_present": [], "notes": "",
                "sampling": {"n_requested": n, "n_ok": len(draws), "n_abstain": n_abstain,
                             "top1_mode": None, "top1_mode_share": 0.0,
                             "top1_unanimous": False, "top1_stable": False,
                             "top1_draws": [], "max_range": 0.0, "per_knot": {}},
                "caveat": "全体弃权: 这不是「没有信号强度」, 是仪器声明本次不产出心理读数。"}
    _mode = _C(tops).most_common(1)[0]
    # ★ 分母用 len(draws) 而不是 len(tops): 弃权若不计入分母, 弃权越多众数占比越高
    mode_share = round(_mode[1] / len(draws), 4)
    top1_unanimous = len(set(tops)) == 1
    top1_stable = top1_unanimous   # 兼容别名, 语义同 unanimous; 新代码请用 mode_share

    # knots 保持 [[key, weight]] 的既有形状(weight 改为中位数), 下游 5 个消费者不需要改。
    merged = sorted(keys, key=lambda k: -stability[k]["intensity"])
    out_knots = []
    for k in merged:
        # ★ 不再 `continue` 掉少数派 —— 那是把测到的东西丢掉。
        #   全部发布, 用 support_majority 注记它是否过闸。
        meta_k = next(m for m in taxo["knots"] if m["key"] == k)
        src = next((x for d in draws for x in d["knots"] if x["key"] == k), {})
        out_knots.append({"key": k, "intensity": stability[k]["intensity"],
                          "support": stability[k]["support"],
                          "occur": stability[k]["occur"], "n": stability[k]["n"],
                          "support_ci95": _wilson(stability[k]["occur"], stability[k]["n"]),
                          "support_majority": _has_support(stability[k]),
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
    inten = {k: stability[k]["intensity"] for k in keys if _has_support(stability[k])}
    families = {}
    for fam in {"推动", "阻挡"}:
        mem = {k: v for k, v in inten.items() if fam_of.get(k) == fam}
        tot = sum(mem.values())
        families[fam] = {
            "mass": round(max(mem.values()), 4) if mem else 0.0,
            "composition": {k: round(v / tot, 4) for k, v in sorted(mem.items(), key=lambda x: -x[1])} if tot else {},
            "members_active": len(mem)}
    dm, bm = families["推动"]["mass"], families["阻挡"]["mass"]
    # weight 仍**只在过闸结上**归一, 未过闸者恒 0.0 ——
    # 下游 5 个消费者读的是 {key: weight}, 这样它们逐值不变(已验: hooks_for 取 top2 不受
    # 零权重影响; cce_align_v2.score 的 w*c / w*hit 项对 w=0 恒为 0)。
    # 想用全部证据的消费者请读 support / support_ci95, 不要读 weight。
    _tot = sum(k["intensity"] for k in out_knots if k["support_majority"]) or 1.0
    for k in out_knots:
        k["weight"] = round(k["intensity"] / _tot, 4) if k["support_majority"] else 0.0
    # ★ draw ledger: 完整 9 维向量, **缺席显式记 0** —— 只存 top1 或只存最终 intensity
    #   都会永久失去 co-occurrence / latent structure / 替代阈值 / 替代聚合 的重研究能力。
    draw_ledger = [{"draw_id": i,
                    "knot_vector": {k: next((float(x["intensity"]) for x in d["knots"]
                                             if x["key"] == k), 0.0) for k in KNOTS_ALL},
                    "weight_shim_fired": bool(d.get("_weight_shim_fired")),
                    "abstained": not d["knots"],
                    "top1": (max(d["knots"], key=lambda x: x["intensity"])["key"]
                             if d["knots"] else None)}
                   for i, d in enumerate(draws)]
    return {"knots": out_knots,
            "measurement_status": "qualified" if out_knots else "abstain",
            "n_abstain": n_abstain,
            "draw_ledger": draw_ledger,
            "intensity": {k: round(v, 4) for k, v in sorted(inten.items(), key=lambda x: -x[1])},
            "families": families,
            "drive_brake": {"drive_mass": dm, "brake_mass": bm,
                            "quadrant": f"{'high' if dm >= 0.5 else 'low'}_drive/"
                                        f"{'high' if bm >= 0.5 else 'low'}_brake",
                            "note": "象限切点 0.5 是量纲中点, 不是校准阈值; 仅作分类标签, 不得作判据"},
            "levers_present": sorted({l for d in draws for l in (d.get("levers_present") or [])}),
            "notes": draws[0].get("notes", ""),
            "sampling": {"n_requested": n, "n_ok": len(draws),
                         "top1_mode": _mode[0], "top1_mode_share": mode_share,
                         "top1_unanimous": top1_unanimous,
                         "top1_stable": top1_stable, "top1_draws": tops,
                         "caveat_unanimous": ("top1_unanimous 在 n=1 时恒真, 且 P≈p^n 随 n 单调下降 —— "
                                              "跨不同 n 比较必须用 top1_mode_share, 不能用 unanimous"),
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
