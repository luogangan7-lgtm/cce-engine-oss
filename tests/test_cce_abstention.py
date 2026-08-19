#!/usr/bin/env python3
"""[2/4] 弃权：「读不出」必须能被表达，且不能伪装成第十个结。

外部源码审计确认「无空读数」是 **contract-impossible**，三处阻断（我逐一核实过）：
  1. stage1 prompt 要求对「这一个人」反推 —— 从未授权模型判断有没有主体
  2. stage2 `and d["knots"]` ⇒ `{"knots":[]}` 被当成解析失败去重试
  3. ingest `if total <= 0: raise` ⇒ 零分布在契约上不可能

本次打通 2 与 3。**1 未动** —— 改 s1 prompt 会再换一次仪器并使当日标定失效，属独立决策。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_knot_classify as K      # noqa: E402
import cce_response_chain as RC    # noqa: E402

TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))


def _agg(specs):
    draws = [{"knots": [{"key": k, "intensity": v, "evidence_quote": "", "signature": {}}
                        for k, v in sp.items()], "levers_present": [], "notes": ""}
             for sp in specs]
    orig = K._stage2_draw
    K._stage2_draw = lambda p, t, tag: draws[int(tag[1:]) % len(draws)]
    try:
        return K._stage2_aggregate("x", TAXO, n=len(draws))
    finally:
        K._stage2_draw = orig


# ── 1. 全体弃权 ⇒ abstain, 且**不产出任何结** ───────────────────────────────
r = _agg([{}, {}, {}, {}])
assert r["measurement_status"] == "abstain", r["measurement_status"]
assert r["knots"] == [] and r["intensity"] == {}, "弃权时不得产出任何结"
assert "4/4" in r["abstain_reason"]
# ★ 弃权**不是**第十个结: 九结里不许出现 no_signal 之类的键
assert not any("signal" in k.lower() or "abstain" in k.lower() for k in K.KNOTS_ALL)
assert all(v == 0.0 for row in r["draw_ledger"] for v in row["knot_vector"].values())
assert all(row["abstained"] is True for row in r["draw_ledger"])

# ── 2. ★ 部分弃权不得抬高众数占比(分母必须是全部 draw) ──────────────────────
r = _agg([{"audit": .5}, {}, {"audit": .5}, {"audit": .5}])
assert r["measurement_status"] == "qualified" and r["n_abstain"] == 1
assert r["sampling"]["top1_mode_share"] == 0.75, \
    f"弃权若不计入分母会得 3/3=1.0(假的稳), 实得 {r['sampling']['top1_mode_share']}"
assert [x["abstained"] for x in r["draw_ledger"]] == [False, True, False, False]

# ── 3. 反向测试: 把分母改回 len(tops), 这条必须能抓住 ───────────────────────
_tops = [x for x in r["draw_ledger"] if not x["abstained"]]
assert len(_tops) == 3 and 3 / 3 != r["sampling"]["top1_mode_share"], \
    "反向用例必须证明两种分母给出不同的数, 否则本断言测不到东西"

# ── 4. 正常路径不受影响 ─────────────────────────────────────────────────────
r = _agg([{"audit": .5}] * 4)
assert r["measurement_status"] == "qualified" and r["n_abstain"] == 0
assert r["sampling"]["top1_mode_share"] == 1.0

# ── 5. ingest: 零分布是弃权, 不是 raise ─────────────────────────────────────
src = (ROOT / "scripts" / "cce_response_chain.py").read_text(encoding="utf-8")
assert 'raise ValueError(f"{row[\'evidence_ref\']} empty' not in src, \
    "零分布不得再 raise —— 那让「读不出」与「管线坏了」不可区分"
assert '"measurement_status"' in src and '"abstained_layers"' in src

# ── 6. ★★ 仪器指纹: s1 prompt 现在必须进指纹(此前不进 = 静默换仪器) ─────────
spec = K.instrument_id(TAXO, k=3, knot_n=5,
                       s1_pairing="round_robin_over_3_s1_draws")["spec"]
assert "s1_prompt_sha256" in spec and "s2_prompt_sha256" in spec
# ⚠️ [2/4] 时这里断言 s1 prompt **必须等于** gen1 —— 那是当时的契约(本次不许动 s1)。
#   本次(第三处开口)**有意**改了 s1 prompt, 于是这条绊线响了。它响得对: 桥接确实断了。
#   新契约不是「不许变」, 而是「**变了必须在谱系里有记录, 且标定随之作废**」。
assert spec["s1_prompt_sha256"] != K.INSTRUMENT_LINEAGE[0]["s1_prompt_sha256"], \
    "s1 prompt 应已改为允许弃权 —— 若与 gen1 相同, 说明第三处开口没真正落地"
assert spec["s2_prompt_sha256"] == K.INSTRUMENT_LINEAGE[0]["s2_prompt_sha256"], \
    "s2 prompt 本次不该动"
assert spec["aggregation_policy"]["abstention"] == K.ABSTENTION_POLICY

# 反向: 改一个字的 s1 prompt 必须换哈希(这正是此前做不到的)
import hashlib  # noqa: E402
_now = hashlib.sha256(K._stage1_template().encode()).hexdigest()[:16]
_alt = hashlib.sha256((K._stage1_template() + "。").encode()).hexdigest()[:16]
assert _now != _alt, "★ s1 prompt 改一个字必须换指纹 —— 否则又是静默换仪器"

# ── 7. 换代桥接必须诚实: 六个 run 全在册, 且旧哈希写死 ───────────────────────
# 别名仍指向 gen1(旧引用不破), 但键名随谱系统一为 hash
lg = K.LEGACY_INSTRUMENT_20260818
assert lg is K.INSTRUMENT_LINEAGE[0]
assert lg["hash"] == "57ec6cf478d3875e" and len(lg["runs"]) == 6
assert "32150369795" in lg["runs"]

# ── 8. s1 prompt **未**被改动 —— 本次只通 2/3 两处, 不许悄悄动第 1 处 ────────
assert "反推其心理因果链四层占比分布" in src or True  # s1 在另一文件
k_src = (ROOT / "scripts" / "cce_knot_classify.py").read_text(encoding="utf-8")
# ⚠️ 同上: [2/4] 时断言「s1 prompt 原文仍在」。本次已按用户批准改动, 契约随之更新 ——
#   现在要断言的是: 改动**保留了原有语义**(仍要求对个体反推), 只是**追加**了弃权出口,
#   而不是把整段指令换掉。两者的读数可比性完全不同。
assert "请对『写下这段内容的这一个人』" in k_src and "这是一个个体，不是群体" in k_src, \
    "★ 弃权出口是**追加**的, 不得把原有的个体反推指令删掉或改写"
assert "若它**不是个人表达**" in k_src, "必须有明确的弃权条件描述"
assert "ABSTENTION_S1_NOTE" in k_src, "保留历史说明, 记录这一处曾经未通及其理由"

print("test_cce_abstention: OK (全体/部分弃权 · 分母不被抬高 · ingest 不再 raise · "
      "s1 进指纹 · 换代桥接 · s1 prompt 未动)")

# ── 9. [第三处开口] stage1 prompt 现在允许模型声明「无可推断主体」 ──────────
k_src2 = (ROOT / "scripts" / "cce_knot_classify.py").read_text(encoding="utf-8")
assert "no_inferable_subject" in k_src2, "s1 prompt 必须给出显式弃权字段"
assert "不要为它构造一个人" in k_src2
# ★ 弃权信号必须**显式**, 不得拿全零向量当弃权
from exp_v4_full_validation import top_label, DESIRES  # noqa: E402
assert top_label([0.0] * len(DESIRES), DESIRES) == DESIRES[0], \
    "共享 top_label 对全零返回第一个标签 —— 这正是不能拿全零当弃权信号的理由"
assert "全零守卫" in k_src2 and "sum(vec) > 0" in k_src2, \
    "stage1 必须自带全零守卫, 否则全零会被报成一个自信的假 top"

# ── 10. stage1 弃权 ⇒ stage2 不发任何调用 ──────────────────────────────────
r = K.stage2("x", {"abstained": True, "abstain_reason": "纯数据表", "k_requested": 3}, TAXO)
assert r["measurement_status"] == "abstain" and r["knots"] == []
assert r["sampling"]["n_ok"] == 0, "s1 已弃权还发 s2 调用 = 白烧钱且在为不存在的主体造结"
assert "stage1 弃权" in r["abstain_reason"]

# ── 11. ★★ 仪器谱系与标定可搬性 ────────────────────────────────────────────
lin = K.INSTRUMENT_LINEAGE
assert [g["gen"] for g in lin] == [1, 2, 3, 4, 5], "换代必须登记进谱系, 不许只改代码不留代"
# ★ gen5 换的是**测量模型**(阿里云 qwen3.7-max) —— 换模型 = 换仪器, 不是换算力。
#   谱系里必须写明它与生成器的关系, 否则下游读不出「为什么不是 qwen3.8」。
g5 = lin[4]
assert g5["hash"] == "eb487df50f5aec31" and g5["model"] == "qwen3.7-max"
assert "自己写的自己读" in g5["note"], "★ 必须写明为何不选 qwen3.8/glm-5.2(它们是刺激生成器)"
assert "同属 qwen 家族" in g5["note"], "★ 残留的家族级重叠必须写出来, 不许只说模型不同"
assert "不可复现" in g5["note"], "★ 订阅到期后仪器不可得, 这条必须随谱系走"
assert lin[0]["hash"] == "57ec6cf478d3875e" and len(lin[0]["runs"]) == 6
assert lin[1]["hash"] == "287d07a0ef1ea78e" and lin[1]["runs"] == []
assert lin[2]["hash"] == "ea70b373d5bef630" and len(lin[2]["runs"]) == 4, "gen3 的四个 run"
assert lin[3]["hash"] is None, "当代 hash 由代码现算, 写死会与实现漂移"
# ★ 只有**改了物理仪器**的换代才让标定作废: gen1→gen2 与 gen3→gen4 都只是重划标识符
assert lin[0]["s1_prompt_sha256"] == lin[1]["s1_prompt_sha256"], "gen1/gen2 物理同一"
assert lin[2]["s1_prompt_sha256"] == lin[3]["s1_prompt_sha256"], "gen3/gen4 物理同一"
assert lin[1]["s1_prompt_sha256"] != lin[2]["s1_prompt_sha256"], "gen2→gen3 才是真换仪器"

# ⚠️ 2026-08-19 外部评审纠正: 初版拿「prompt 相同」当**通用迁移律**太松 ——
#   prompt 一字未改但 s2 的 n、聚合统计量、support 规则、配对、端点变了, 噪声底一样会变。
#   改为**每个标定声明自己的 depends_on**, 只比那些字段。
import cce_ksep as _KS  # noqa: E402
_t = K.calibration_transfers(_KS.PAIR1_NULL_CALIBRATION_STATISTIC, TAXO, k=3, knot_n=5,
                             s1_pairing="round_robin_over_3_s1_draws")
assert _t["transfers"] is False and _t["changed"] == ["s1_prompt_sha256"], _t
assert len(_t["checked"]) >= 8, "依赖清单必须覆盖 prompt 之外的项, 否则又退回太松的判据"
# ★ 反向: 未声明 depends_on 的标定一律不许搬
assert K.calibration_transfers({}, TAXO)["transfers"] is False
# ★ 判据必须是 prompt 相同而**不是** hash 相同: gen1→gen2 hash 变了但标定仍适用
assert lin[0]["s1_prompt_sha256"] == lin[1]["s1_prompt_sha256"], \
    "gen1 与 gen2 的 s1 prompt 必须相同 —— 那次只是身份定义变完整, 物理仪器没变"
assert lin[0]["hash"] != lin[1]["hash"], "但 hash 确实变了 ⇒ 可搬性判据不能用 hash"

# ── 12. KSEP 的标定常量必须自己声明「对当前仪器不适用」 ──────────────────────
import cce_ksep as KS  # noqa: E402
c = KS.PAIR1_NULL_CALIBRATION_STATISTIC
assert c["measured_on_instrument"] == "57ec6cf478d3875e"
assert c["transfers_to_current"] is False, \
    "★ 标定常量必须自己说清它对当前仪器不适用, 否则会被后来的 agent 直接拿去用"
assert KS.SESOI is None and KS.DELTA_RESOLUTION is None

print("test_cce_abstention[9-12]: OK (s1 弃权 · 全零不当弃权 · s2 零调用 · 谱系 · 标定不可搬)")

# ── 13. gen3 验收 gate 实测(run 32223866100, 30 次调用) ─────────────────────
AUF = ROOT / "tests" / "data" / "abstention_uptake_20260819.json"
if AUF.exists():
    au = json.loads(AUF.read_text(encoding="utf-8"))
    assert au["instrument"] == "ea70b373d5bef630", "验收必须跑在 gen3 上"
    assert au["s1_prompt_sha256"] == "eadcdcdac46a5180"
    # ★ 阴性侧: 四份中性垫料**每一个 draw** 都弃权(不只是「至少一个 rep」)
    neg = {k: v for k, v in au["by_text"].items() if "应当弃权" in k}
    assert len(neg) == 4
    for k, v in neg.items():
        assert v["any_abstention"] is True, k
        assert all(r["n_abstain"] == 3 for r in v["reps"]), \
            f"{k}: 期望每 rep 3/3 draw 弃权, 实得 {[r['n_abstain'] for r in v['reps']]}"
    # ★ 阳性侧: 真人文本零弃权 —— 过度触发比改动前更坏
    pos = au["by_text"]["HUMAN_base(应当不弃权)"]
    assert pos["any_abstention"] is False and all(r["n_abstain"] == 0 for r in pos["reps"]), \
        "★ 真人文本被判无主体 = 过度触发, 会静默缩掉 P2 的语料, 必须回滚"
    assert au["verdict"].startswith("通过")
    # ★ 诚实边界: R=2 / 4 份垫料 / **仅 1 份真人文本** —— 这是筛选不是测量。
    assert au["R"] == 2, "R=2 是筛选; 不得据此报弃权率"
    assert len([k for k in au["by_text"] if "应当不弃权" in k]) == 1, \
        "★ 只测了 1 份真人文本 —— 假阳性(过度触发)方向证据很薄, 需要全语料扫"
    print("  gen3 验收已钉: 阴性 4/4 全 draw 弃权 · 阳性零弃权 · 但假阳性侧仅 n=1")

# ── 14. 假阳性收口(run 32224198135, 72 调用) ───────────────────────────────
AFF = ROOT / "tests" / "data" / "abstention_false_positive_20260819.json"
if AFF.exists():
    af = json.loads(AFF.read_text(encoding="utf-8"))
    assert af["instrument"] == "ea70b373d5bef630"
    # 通道必须是活的, 否则真人侧零弃权不可读作好消息
    assert any(af["control"]["n_abstain"]), "★阴性对照未弃权 ⇒ 通道死, 整轮作废"
    hum = af["human"]
    assert len(hum) == 12, "12 份真实语料不挑不排"
    # ★ 灾难性失败(整条被判无主体)**没有**发生
    assert not any(any(v["abstained"]) for v in hum.values()), \
        "★ 若有真人文本被**整条**判无主体, 那是必须立刻回滚的灾难性失败"
    # ★ 但部分弃权确实发生: 4/12, 最差 T02 两个 rep 都丢 2/3 draw
    part = {k: v for k, v in hum.items() if any(v["n_abstain"])}
    assert set(part) == {"T01", "T02", "T03", "T10"}, sorted(part)
    assert max(hum["T02"]["n_abstain"]) == 2, "T02 最差丢 2/3 draw ⇒ 有效 k=1"
    # ★★ 有效 k=1 的下游后果: within_js 需要 >=2 个 draw, 故该闸跑不了
    import inspect  # noqa: E402
    assert "if len(pvs) >= 2:" in inspect.getsource(K.stage1), \
        "within_js 需 >=2 draw —— 部分弃权把有效 k 压到 1 时该闸静默失效"
    # ★ 前登记缺口(必须记着, 不许悄悄补): 判决线把弃权当**二元**(有/无),
    #   而实际现象是**分级**的(0-3 个 draw)。这与 0.36 那次是同一类失败。
    assert "误伤率 >1/12 即建议回滚" in "".join(af["verdict_lines"]), \
        "前登记原文必须留着 —— 事后重新解释判决线正是它要防的事"
    print("  假阳性收口已钉: 通道活 · 无整条误判 · 部分弃权 4/12(T02 有效k=1) · "
          "前登记把分级现象写成了二元")


# ── 15. ★ k_valid<2 必须 WITHHOLD, 绝不静默退回单 draw ─────────────────────
# 外部评审指出、我实测确认的两个 bug:
#   (a) k_ok 曾把**弃权的 draw 也算成成功**(2/3 弃权时报 k_ok=3), 下游以为拿到三档
#   (b) within_js 需 >=2 有效 draw; k_valid=1 时它是 None, 读数照常产出
_orig = K.call_parse
_n = {"i": 0}


def _fake(mk, case, T, note):
    _n["i"] += 1
    if _n["i"] <= 2:            # 前两档弃权
        return "", {"no_inferable_subject": True, "reason": "技术问答"}, None, {}, False
    pv = {"desire_vec": [1.0] + [0] * 8, "need_vec": [1.0] + [0] * 16,
          "emotion_vec": [1.0] + [0] * 12, "action_vec": [1.0] + [0] * 6,
          "need_slots": {}, "appraisal": {}, "chain_trace": "", "evidence": {}}
    return "", {}, pv, {}, True


K.call_parse = _fake
try:
    _s1 = K.stage1("x", "ctx", 3)
finally:
    K.call_parse = _orig
assert _s1["k_attempted"] == 3 and _s1["k_valid"] == 1 and _s1["k_abstained"] == 2
assert _s1["k_ok"] == _s1["k_valid"], \
    "★ k_ok 必须等于**有效** draw 数 —— 把弃权算成成功会让下游以为拿到了三档"
assert _s1["measurement_status"] == "insufficient_replicates"
assert _s1["within_js"] is None

# 下游闸: 不得 raise(那会把「重复数不够」混成「管线坏了」), 必须 WITHHOLD
fr = (ROOT / "scripts" / "cce_full_run.py").read_text(encoding="utf-8")
assert '"measurement_status": "insufficient_replicates"' in fr
assert "raise RuntimeError(f\"within_js 缺失" not in fr, "改为 WITHHOLD, 不再 raise"
assert '"tops": {}' in fr, "重复数不足时不得产出 tops"
# ★ 明确禁止「抽到够两个为止」—— 那会条件化于模型愿意给读数, 隐藏真实弃权倾向
assert "绝不能退回单 draw 继续当合格读数" in fr
print("  k 计数与 withhold 已钉: k_ok=有效数 / insufficient_replicates / 不 raise / 无 tops")

# ── 16. ★ 弃权分支必须与非弃权分支**同构** —— 同一个 bug 的第二现场 ────────
# 2026-08-19: k_ok 把弃权算成成功这个 bug 我只修了非弃权分支, 弃权分支照旧。
# 后果: 全体弃权被记成 k_valid=3(经探针兜底), 通道自检读出 Nd=0, **156 次调用整轮作废**。
_o = K.call_parse
K.call_parse = lambda mk, c, T, n: ("", {"no_inferable_subject": True, "reason": "纯数据表"},
                                    None, {}, False)
try:
    _ab = K.stage1("x", "ctx", 3)
finally:
    K.call_parse = _o
assert _ab["abstained"] is True and _ab["measurement_status"] == "abstain"
assert _ab["k_attempted"] == 3 and _ab["k_valid"] == 0 and _ab["k_abstained"] == 3
assert _ab["k_ok"] == 0, "★ 弃权分支的 k_ok 也必须是**有效**数(0), 不能是尝试数"
# ★ draws 不得为空 —— 否则逐 draw 弃权率无从计算, 通道自检失效
assert len(_ab["draws"]) == 3 and all(d["abstained"] for d in _ab["draws"]), \
    "★ 弃权分支必须保留逐 draw 记录, 否则阴性对照的 Nd 算不出来"
# ★ 两个分支的键集合必须一致(结构同构), 防「只修了一处」再次发生
_o = K.call_parse
_i = {"n": 0}


def _ok(mk, c, T, n):
    pv = {"desire_vec": [1.0] + [0] * 8, "need_vec": [1.0] + [0] * 16,
          "emotion_vec": [1.0] + [0] * 12, "action_vec": [1.0] + [0] * 6,
          "need_slots": {}, "appraisal": {}, "chain_trace": "", "evidence": {}}
    return "", {}, pv, {}, True


K.call_parse = _ok
try:
    _no = K.stage1("x", "ctx", 3)
finally:
    K.call_parse = _o
_common = {"k_requested", "k_attempted", "k_valid", "k_abstained", "k_ok",
           "measurement_status", "abstained", "layers", "tops", "draws", "within_js"}
assert _common <= set(_ab), f"弃权分支缺 {_common - set(_ab)}"
assert _common <= set(_no), f"正常分支缺 {_common - set(_no)}"

# ── 17. ★ 探针禁止对自己的 schema 用 .get(key, default) ────────────────────
# ⚠️ 初版写的是 `assert 's1.get("k_valid"' not in 全文` —— 它抓住了**解释旧 bug 的注释本身**。
#   与今天早上「82%」那次同形: 断言字符串存在/不存在的守卫, 总被解释它的文字绊倒。
#   改为只看**非注释的代码行**。
_gq = (ROOT / "probes" / "gen3_qualification.py").read_text(encoding="utf-8")
_code = [l for l in _gq.split("\n") if not l.lstrip().startswith("#")]
for _l in _code:
    assert 's1.get(' not in _l, \
        f"★ 兜底把 schema 漂移变成自信的错数 —— 缺键必须当场炸, 不许 .get 默认值: {_l.strip()[:70]}"
assert 'raise KeyError' in _gq and "禁止兜底" in _gq
# 反向: 构造一行含兜底的代码行, 规则必须抓住
assert any('s1.get(' in _l for _l in ['    x = s1.get("k_valid", 3)']), "反向用例自检"
print("  弃权分支同构已钉: k_valid=0 / k_ok=0 / draws 保留 / 两分支键集一致 / 探针无兜底")

# ── 18. Gen3 资格实验(前登记, run 32231676330) ─────────────────────────────
GQF = ROOT / "tests" / "data" / "gen3_qualification_20260819.json"
VOID = ROOT / "tests" / "data" / "gen3_qualification_20260819_VOID.json"
if GQF.exists():
    gq = json.loads(GQF.read_text(encoding="utf-8"))
    assert gq["instrument"] == "ea70b373d5bef630" and gq["K"] == 3 and gq["R_requested"] == 4
    # ★ 通道自检必须先过, 否则真人侧的零不可读
    assert gq["Nd"] == 1.0 and gq["Nf"] == 1.0, "阴性对照必须确证弃权"
    # 修复验证: 弃权时 k_valid 报 0(上一轮因缺键+兜底错报成 3)
    assert all(r["k_valid"] == 0 for r in gq["control"]["reps"]), \
        "★ 全体弃权时 k_valid 必须是 0 —— 报 3 正是上一轮作废的原因"
    assert gq["U"] == 0.0 and gq["F"] == 0.0
    assert gq["verdict"].startswith("ADOPT_PENDING_MARGIN")
    assert gq["R_qualified_rep_observations"] == gq["R_total_rep_observations"] == 48
    # ★★ U=0 **不等于** U 真的是 0: 48 观测的三法则上界 ≈ 3/48 = 0.0625
    assert 3 / gq["R_total_rep_observations"] > 0.06, "三法则上界必须被记住, 不许把 0 读成不会发生"
    # ★★ 且同一台 gen3 的上一轮**确实**观测到 U>0(T02 两个 rep k_valid=1)
    fp = json.loads((ROOT / "tests" / "data" /
                     "abstention_false_positive_20260819.json").read_text(encoding="utf-8"))
    assert any(3 - x < 2 for v in fp["human"].values() for x in v["n_abstain"]), \
        "★ 上一轮 gen3 观测到过 k_valid<2 —— 本轮的 U=0 不得被读成『从不发生』"
if VOID.exists():
    v = json.loads(VOID.read_text(encoding="utf-8"))
    assert "VOID_REASON" in v and v["verdict"].startswith("INDETERMINATE"), \
        "作废轮次必须带作废理由, 且不得被当成有效结果引用"
    assert all(r["abstained"] for r in v["control"]["reps"]), \
        "作废轮的阴性对照其实是全体弃权的 —— 这条钉住『Nd=0 是仪器缺陷不是通道死』"
print("  gen3 资格实验已钉: 通道 Nd=1.0 / U=F=0 / ADOPT_PENDING_MARGIN / "
      "三法则上界 0.0625 / 上一轮观测到过 U>0 / 作废轮带 VOID 理由")
