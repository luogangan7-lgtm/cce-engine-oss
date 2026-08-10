#!/usr/bin/env python3
"""两日实验台账 —— 汇总所有 GitHub 运行产物, 列出结论与相互矛盾之处。"""
import json, glob, os, collections
B = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def load(pat):
    f = glob.glob(f"{B}/{pat}", recursive=True)
    return json.load(open(f[0], encoding="utf-8")) if f else None

E = []
def add(**kw): E.append(kw)

d = load("acc7/**/gates_result.json")
if d:
    g1, g2 = d["G_K1v2_分布一致性"], d["G_K2v2_成本档预测"]
    add(id="A1", 名称="九结验收 G-K1/G-K2", run="31306754953", n=d["sample_n"],
        指标={"top2": g1["mean_top2_hit"], "JS": g1["mean_JS"], "κ": g1["mean_top1_kappa"],
             "G-K2精确": g2["exact_acc"], "G-K2基线": g2["baseline_majority"],
             "spearman": g2["spearman_score_vs_observed"]},
        结论="overall_pass=True(首次)", 判据="top2>=.8 且 JS<=.25", 性质="正")

d = load("oos2/**/oos_result.json")
if d:
    add(id="A2", 名称="OOS 样本外(自家帖)", run="31308460433", n=d["n_rows"],
        指标={"全部ρ": d["全部"]["spearman"], "样本外ρ": d["样本外(未进验收语料)"]["spearman"],
             "样本外p": d["样本外(未进验收语料)"]["p"], "样本外n": d["样本外(未进验收语料)"]["n"]},
        结论="样本外不显著(n=20 欠功效)", 判据="ρ>=.3 且 p<.05", 性质="未定")

d = load("ev1/**/external_validity.json")
if d:
    add(id="B1", 名称="外部效度·他人帖成对", run="31315790209", n=d["n_parsed"],
        指标={"命中": d["accuracy"], "CI": d["ci95"]}, 结论="70.8% 显著高于50%",
        判据="95%CI下界>0.5", 性质="正", 备注="只调裸M3, 未走九结链路")

for f, rid, nm in [("sub1/**/simulation.json", "31314971609", "主体模拟·预测会不会动")]:
    d = load(f)
    if d: add(id="C1", 名称=nm, run=rid, n=d["n"],
              指标={"命中": d["accuracy"], "基线": d["majority_baseline"], "增益": d["lift"],
                   "只看帖": 0.75}, 结论="无增益, 且只看帖(75%)碾压", 判据="命中>基线", 性质="负")

d = load("oc1/**/order_calibration.json")
if d:
    add(id="D1", 名称="五层顺序组合校准", run="31321746836", n=d["n"],
        指标={o["链序"][:22]: o["改善"] for o in d["链序对比"]},
        结论="六排列小数点后四位相同, 测不出(链式合成退化)", 判据="改善最大者胜", 性质="废")

d = load("cs1/**/context_sensitivity.json")
if d:
    add(id="D2", 名称="情境敏感度·九面", run="31322272555", n=d["n_calls"],
        指标={r["面"]: r["平均位移"] for r in d["逐面"]},
        结论="需求层几乎不动(.06-.13) vs 情绪/行动大动(.36-.78)", 判据="逐面JS位移", 性质="正")

d = load("sh1/**/splithalf.json")
if d:
    add(id="D3", 名称="折半信度·聚合读出", run="31322941186", n=d["n_people"],
        指标={k: v["比值"] for k, v in d["逐层"].items()},
        结论="欲望.711/需求.776 是主体属性; 情绪.899/行动1.084 不是", 判据="组内显著<组间", 性质="正")

for f, rid, nm, ka, kb in [
        ("ta1/**/twoarm.json", "31322998893", "双臂v1·九结", "A臂_裸M3", "B臂_带九结"),
        ("ts1/**/twoarm_stable.json", "31353314992", "双臂v2·欲望+需求", "A臂_裸M3", "B臂_欲望需求"),
        ("T1/**/t1_prior.json", "31354746469", "双臂v3·外部先验", "A臂", "B臂_带先验")]:
    d = load(f)
    if d: add(id=f"E{len(E)}", 名称=nm, run=rid, n=d[ka]["n"],
              指标={"A": d[ka]["acc"], "B": d[kb]["acc"], "增量": d["增量"],
                   "McNemar_p": (d.get("配对比较") or d.get("配对"))["McNemar_p"]},
              结论="无增量", 判据="B臂CI下界>A臂点估", 性质="负")

d = load("T3/**/t3_profile.json")
if d: add(id="E4", 名称="画像→预测未来行为", run="31354754280", n=d["n_people"],
          指标={"画像精确": d["画像法"]["精确"], "画像召回": d["画像法"]["召回"],
               "基线精确": d["查表基线"]["精确"], "基线召回": d["查表基线"]["召回"]},
          结论="判负(精确大幅落后), 但F1略高", 判据="精确与召回均须超基线", 性质="负")

d = load("T2/**/t2_rewrite.json")
if d: add(id="F1", 名称="生成侧·CCE诊断指导改写", run="31360516549", n=d["主判_B胜A"]["n"],
          指标={"A胜原": d["A臂_裸改写_胜原版"]["胜率"], "B胜原": d["B臂_CCE诊断改写_胜原版"]["胜率"],
               "B胜A": d["主判_B胜A"]["胜率"], "B胜A_CI": d["主判_B胜A"]["ci95"]},
          结论="主判成立 91.4%", 判据="B胜A的CI下界>0.5", 性质="正")

d = load("T2C/**/t2_control.json")
if d:
    R = d["rows_c1"]; ok = [r for r in R if 0.7 <= r["wp"]/r["w0"] <= 1.3]
    clean = sum(r["空转胜原"] for r in ok)/len(ok)
    add(id="F2", 名称="生成侧对照 C1/C2", run="31362019408", n=len(R),
        指标={"C1原始": d["C1_空转胜原版"]["率"], "C1清洗后": round(clean, 3),
             "C1崩坏条数": len(R)-len(ok), "C2真帖校准": d["C2_会话内真帖校准"]["率"]},
        结论="裁判正常(C2 75%); LLM文本轻微偏好57.6%, 只污染'胜原版'不污染主判",
        判据="C1>=.75作废", 性质="正")

json.dump({"生成时间": "2026-08-10", "运行总数": 60, "成功": 42, "失败": 11, "取消": 7,
           "实验": E}, open(f"{B}/ledger/experiments.json", "w"), ensure_ascii=False, indent=1)
print(f"{'ID':4s} {'实验':26s} {'n':>5s} {'性质':4s} 结论")
for e in E:
    print(f"{e['id']:4s} {e['名称'][:26]:26s} {str(e['n']):>5s} {e['性质']:4s} {e['结论'][:46]}")
print(f"\n共 {len(E)} 个实验入册 → ledger/experiments.json")
c = collections.Counter(e["性质"] for e in E)
print(f"性质分布: {dict(c)}")
