# -*- coding: utf-8 -*-
"""预注册: 减少抽样次数 K(s1 温度档数) / n(s2 抽样数) 以缩短 knot_classify 墙钟。零调用, 只写 tests/data/sampling_reduction_prereg.json。

★ 为什么先预注册: 改 K 或 n 都改 sampling_policy ⇒ 改 instrument_hash ⇒ **换仪器**(库里 2026-08-19 已定: K 是温度阶梯不是 iid 重复)。
  换仪器 = 新一代 + 该仪器自己的 K1 判定(cce_k1_status 对未登记仪器拒发)。这不是调参, 是重标定, 所以判决线必须**先于数据**冻结。
★ 结构事实(2026-09-23 读码得到, 不是猜的): s1 的 K 个 draw 与 s2 的 n 个 draw 各自已是 ThreadPoolExecutor(min(5, ·)) 并发,
  K≤5 且 n=5 ⇒ **各自只有一个并发波**。knot_classify 墙钟 ≈ max(K 个 s1 延迟) + max(n 个 s2 延迟)。
  ⇒ 减 K/n **不减波数**, 只减「N 个并发调用里最慢那个」的尾部。收益 = E[max of N] − E[max of N'], 由单次调用延迟分布决定, **先量它, 再决定值不值得换仪器**。
"""
import hashlib, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]; OUT = ROOT / "tests/data/sampling_reduction_prereg.json"

PREREG = {
 "block": "SAMPLING_REDUCTION_PREREG", "date": "2026-09-23", "★★★status": "**STEP1_READY** (第一步零仪器变更; 第二步是否启动由第一步数据按下面冻结的规则决定)",
 "★问题": "把 s1 的 K(现 reply/response=3, outbound_post=5) 或 s2 的 n(现 KNOT_N=5) 减小, 能省多少墙钟? 代价是什么? 值不值得为此换一代仪器?",
 "★当前仪器(冻结, 由闸现算比对)": {"s1_k": {"reply": 3, "response": 3, "outbound_post": 5}, "s1_temps": [0.0, 0.3, 0.6, 0.9, 0.15, 0.45, 0.75], "s2_n": 5, "concurrency": "min(5, K) 与 min(5, n)", "instrument_hash(k=3,n=5)": "d4cce4c745f3f991"},
 "★★★结构事实": {"波数": "K≤5、n=5 ⇒ s1 一波 + s2 一波, 减 K/n 不减波数", "墙钟模型": "T ≈ max_{i≤K} L1_i + max_{j≤n} L2_j (+ 重试)", "推论": "收益上限 = 尾部序统计量之差, 不是线性 (K−K')/K"},
 "★★★第一步(零仪器变更, 先做)": {
  "探针": "probes/draw_latency_probe.py", "产物": "results/draw_latency.json",
  "做什么": "同一段合成文本, 用**生产的 s1/s2 prompt 构造器**(_stage1_case + call_parse / _build_stage2_prompt + call_model)各发 10 次调用, 按生产同样的 5 路并发分两波发, 记录每次调用的延迟与成功。",
  "预算硬上限": {"MiniMax 调用": 20, "撞上即停": True},
  "算什么": "对每个候选 (K', n') 用 bootstrap(B=4000, 由延迟样本有放回抽 K'/n' 个取 max)估 E[T(K',n')], 与 E[T(3,5)] 相减得**期望节省秒**与**节省比**。",
  "★★★判决线(先于数据冻结)": {
   "启动第二步的条件(两条同时)": ["期望节省 ≥ 10 s / 每次 knot_classify", "节省比 ≥ 15%"],
   "否则": "STOP: 结论写「时间在单次调用延迟, 不在抽样次数; K/n 减少不值得换仪器」, **不进第二步, 不花标定预算**。",
   "★为什么是 10 s / 15%": "reply 链一条 ≈ 60–95 s(重叠后); 低于 10 s 的收益在单次延迟波动(实测同文本两次差 34 s)里根本看不见, 而换一代仪器的固定代价是 K1 40 次调用 + 全部标定作废。"
  },
  "★统计告知": "n=10/10 的延迟样本, bootstrap 区间会宽; 判决用**点估计**, 但产物必须带 90% 区间, 且区间跨越 10 s 门时标 INCONCLUSIVE(仍按点估计走, 但结论句必须带这个标)。"
 },
 "★★★候选方案(先列全, 禁止事后加)": {
  "A": {"s1_k": 3, "s2_n": 3, "改的是": "只 s2", "★代价": "top1_mode_share 分辨率 1/5→1/3; K1 判定要在新仪器上重做"},
  "B": {"s1_k": 2, "s2_n": 5, "改的是": "只 s1: 温度档 [0.0, 0.3], 丢 0.6 档", "★代价": "任一 draw 弃权/失败 ⇒ k_valid<2 ⇒ WITHHOLD(现 3 档可容 1 次); within_js 只剩 1 对; 且丢的是最高温档, 读数分布会变"},
  "C": {"s1_k": 2, "s2_n": 3, "改的是": "两者", "★代价": "A+B 之和"},
  "★禁止": {"K=1 或 n=1": "库里 2026-08-18 已否决「单次抽样不是测量」(0/6 相同、pain_seek 极差 0.65), 不列为候选。", "改并发上限而不改 K/n": "不属本预注册(那是限流面, 另测)。", "outbound_post 的 K=5→3": "它有自己的 K1_V2_K5 标定, 换了要重做; 本轮只在 reply/response 的 k=3 仪器上比。"}
 },
 "★★★第二步(只有第一步触发才做; 现在就冻结)": {
  "路线": "how_to_change_core 第一条路: 新一代 instrument_generation + INSTRUMENT_LINEAGE 写明「上一代标定**不能**搬」+ 该仪器自己的 K1。",
  "K1 判定": {"材料": "与 K1-v2 逐字相同的 5 条冻结文本, 每条 n=8 rep (40 次调用/候选)", "判据": "probes/k1_gate.judge 五项(n≥8 · 出现率一致 ≥7/8 · 逐对容差 A(0.10)≥0.95 · top-1 ≥7/8), 与 gen6 同判据 ⇒ 差异只能归因仪器", "★放行规则": "与现行相同: 只放行 top-1 达标的读数面; 任何一面比 gen6 退步(如 top-1 由 5/5 文本达标降到 <5) ⇒ 该候选 REJECT"},
  "资格层代价(候选 B/C)": {"材料": "real_corpus_pilot 冻结 42 条指针(不落原文), 新旧仪器各跑 s1(不跑 s2)", "看什么": "WITHHOLD(insufficient_replicates) 条数: 新 − 旧", "★判决线": "新增 WITHHOLD ≤ 2 条(≤ 5%)才可接受; 由 McNemar 精确检验报 p, 但判决用条数不用 p", "预算": "42 × (3 + 2) = 210 次 s1 调用(不含 s2)"},
  "★★★合起来的止损": "每个候选最多 40 + 210 = 250 次调用; 三个候选全做 = 750; **先做第一步筛掉不值得的候选, 预期只做 1 个**。",
  "★结论模板": "「候选 X: 期望节省 __ s (__%), K1 top-1 __/5, 新增 WITHHOLD __/42 ⇒ ADOPT / REJECT」; ADOPT 后旧代读数与新代**可比不可合**。"
 },
 "★★★可证伪": {"H1(值得)": "第一步给出 ≥10 s 且 ≥15% 的候选", "H0(不值得)": "所有候选 < 10 s 或 < 15% ⇒ 本预注册以 STOP 关闭, 结论「再快只能换更快的生成模型」", "★作者预期": "H0 —— 因为都是单波, 减 N 只砍尾部; 写在这里是为了让结果不能事后包装。"},
 "★不得据此说": ["第一步产物不得叫「优化结果」—— 它是延迟分布测量。", "第二步没做之前不得改 KNOT_N / k 的任何默认值。", "不得用第一步的合成文本延迟外推到 outbound_post 的 K=5 仪器(prompt 长度不同)。"]
}


def main():
    OUT.write_text(json.dumps(PREREG, ensure_ascii=False, indent=1), encoding="utf-8")
    print("→", OUT, hashlib.sha256(OUT.read_bytes()).hexdigest()[:16]); return 0


if __name__ == "__main__": raise SystemExit(main())
