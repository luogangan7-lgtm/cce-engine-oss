#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""accuracy/run_gates.py 的五种失效定向测试 + 变异检定。

★ 五种失效来自 web GPT 第九轮:
  ① 缺必需规则却通过 ② **空必需集合空过** ③ 解析失败或未知被转成成功
  ④ 没有可裁定条目仍汇总成完整通过 ⑤ 本应通过的合法基线被一律拒绝

★★★ 变异检定要防的假成功(GPT 原话):
  「删掉某个保护后, 测试因为**语法错误或导入失败**而变红, **不算**证明检测到了那个保护的缺失。
    应让变异版**确实走到目标路径**, 并因**预期行为差异**被测试拒绝。」
  ⇒ 每个变异臂都记录 `reached_target`, 未到达目标路径的一律判**变异无效**, 不计为检出。

★ ⑤ 的存在理由: **一个永远拒绝的闸, 同样可以通过全部负例。**
"""
import json, pathlib, sys, traceback

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "probes"))
from accuracy_offline_harness import load, NetworkTripwire  # noqa: E402

OK_JSON = '{"knots":[{"key":"suspend","weight":0.7},{"key":"itch","weight":0.3}]}'


def _five_qualified():
    return [{"model": m, "hits": 5, "of": 5} for m in
            ("A", "B", "C", "D", "E")]


# ── ① 缺必需规则却通过 ────────────────────────────────────────────────
def t1_missing_required_rule():
    """DIST_TMPL 需要 decision_tree/negative_examples。历史上 qualify() 漏填 ⇒ KeyError,
    **一次都没跑通过**。定向检查: 少一个必需键必须**抛错**, 不许静默产出。"""
    m = load(responses=lambda md, p: OK_JSON)
    reached, behaviour = False, None
    try:
        m.DIST_TMPL.format(unit=m.UNIT_LABEL, brief=m.KNOT_BRIEF, body="x")  # 故意少两个键
        reached, behaviour = True, "**静默通过** —— 缺必需规则却产出了 prompt"
    except KeyError as e:
        reached, behaviour = True, f"KeyError({e}) —— 缺键当场抛错 ✅"
    full = m.DIST_TMPL.format(unit=m.UNIT_LABEL, decision_tree=m.DECISION_TREE,
                              negative_examples=m.NEGATIVE_EXAMPLES, brief=m.KNOT_BRIEF, body="x")
    return {"到达目标路径": reached, "缺键时": behaviour,
            "★必需规则确实在完整 prompt 里": (m.DECISION_TREE[:12] in full
                                  and m.NEGATIVE_EXAMPLES[:12] in full),
            "判": "PASS" if "KeyError" in (behaviour or "") else "**FAIL**"}


# ── ② 空必需集合空过 ─────────────────────────────────────────────────
def t2_empty_set_vacuous_pass():
    """`of == 0`(考试根本没跑)必须单列 NOT_EXAMINED 并**扣发整轮**,
    不许归入 UNRESOLVED 后放行(那是 v1 fail-open 换壳)。"""
    m = load()
    st, _ = m.qualification_state(0, 0)
    empty_panel = m.admit_annotators([])
    one_ne = m.admit_annotators([{"model": "A", "hits": 5, "of": 5},
                                 {"model": "B", "hits": 0, "of": 0}])
    return {"到达目标路径": True,
            "of=0 的状态": st,
            "★空面板 admit": empty_panel["admit"], "★空面板 status": empty_panel["status"],
            "★混入一名未考者": one_ne["status"],
            "判": "PASS" if (st == "NOT_EXAMINED"
                            and empty_panel["admit"] is None
                            and one_ne["status"] == "QUALIFICATION_NOT_RUN") else "**FAIL**"}


# ── ③ 解析失败被转成成功 ──────────────────────────────────────────────
def t3_parse_failure_as_success():
    """annot_dist 拿到垃圾/空/权重全零时必须返回 None, **不许**编一个分布出来。"""
    cases = {"垃圾文本": "not json at all",
             "空串": "",
             "knots 为空列表": '{"knots":[]}',
             "权重全零": '{"knots":[{"key":"suspend","weight":0}]}',
             "未知结名": '{"knots":[{"key":"NOT_A_KNOT","weight":1}]}'}
    out, bad = {}, []
    for name, resp in cases.items():
        m = load(responses=lambda md, p, _r=resp: _r)
        _id, dist = m.annot_dist(("MiniMax-M3", {"id": "x", "b": "t"}))
        out[name] = dist
        if dist is not None:
            bad.append(name)
    m2 = load(responses=lambda md, p: OK_JSON)
    _id, good = m2.annot_dist(("MiniMax-M3", {"id": "x", "b": "t"}))
    return {"到达目标路径": True, "逐例": out, "★合法输入仍能产出": good,
            "判": "PASS" if (not bad and good) else f"**FAIL** —— 这些被转成了成功: {bad}"}


# ── ④ 没有可裁定条目仍汇总成完整通过 ────────────────────────────────────
def t4_no_adjudicable_still_passes():
    """两两一致性需要 >=2 名。少于此**数学上无定义** —— 不得回退到全员。"""
    m = load()
    r0 = m.admit_annotators([])
    r1 = m.admit_annotators([{"model": "A", "hits": 5, "of": 5}])
    # 全员 DISQUALIFIED
    rall = m.admit_annotators([{"model": x, "hits": 0, "of": 40} for x in ("A", "B", "C")])
    return {"到达目标路径": True,
            "零名": r0["status"], "一名": r1["status"], "全员不合格": rall["status"],
            "★没有一个回退到全员": all(r["admit"] is None for r in (r0, r1, rall)),
            "判": "PASS" if all(r["admit"] is None for r in (r0, r1, rall)) else "**FAIL**"}


# ── ⑤ 合法基线不得被一律拒绝 ──────────────────────────────────────────
def t5_legitimate_baseline_not_rejected():
    """★ 一个永远拒绝的闸, 同样可以通过全部负例 ⇒ 必须有这一条。"""
    m = load()
    ok = m.admit_annotators(_five_qualified())
    # UNRESOLVED 必须**留在** primary, 不得当成 FAIL
    mixed = m.admit_annotators([{"model": "A", "hits": 5, "of": 5},
                                {"model": "B", "hits": 3, "of": 5},
                                {"model": "C", "hits": 4, "of": 5}])
    return {"到达目标路径": True,
            "五名全合格": {"status": ok["status"], "admit": ok["admit"]},
            "混合(含 UNRESOLVED)": {"status": mixed["status"], "admit": mixed["admit"]},
            "★UNRESOLVED 留在 primary": bool(mixed["admit"]) and len(mixed["admit"]) == 3,
            "判": "PASS" if (ok["status"] == "OK" and len(ok["admit"]) == 5
                            and mixed["status"] == "OK" and len(mixed["admit"]) == 3) else "**FAIL**"}


# ── 变异检定 ────────────────────────────────────────────────────────
MUTANTS = [
 {"id": "M1_of0_归入UNRESOLVED", "目标": "②",
  "find": '    if not of:\n        return "NOT_EXAMINED", (0.0, 1.0)\n',
  "repl": '    if not of:\n        return "UNRESOLVED", (0.0, 1.0)\n',
  "probe": lambda m: m.admit_annotators([{"model": "A", "hits": 5, "of": 5},
                                         {"model": "B", "hits": 0, "of": 0}]),
  "reached": lambda r: r["★states"]["B"]["state"] in ("NOT_EXAMINED", "UNRESOLVED"),
  "caught": lambda r: r["status"] != "QUALIFICATION_NOT_RUN"},

 {"id": "M2_不足两名时回退全员", "目标": "④",
  "find": '    if len(admitted) < 2:\n',
  "repl": '    if False:\n',
  "probe": lambda m: m.admit_annotators([{"model": "A", "hits": 5, "of": 5}]),
  "reached": lambda r: "★states" in r and "A" in r["★states"],
  "caught": lambda r: r["admit"] is not None},

 {"id": "M3_解析失败编一个分布", "目标": "③",
  "find": '    return item["id"], None\n',
  "repl": '    return item["id"], {"suspend": 1.0}\n',
  "probe": lambda m: m.annot_dist(("MiniMax-M3", {"id": "x", "b": "t"})),
  "reached": lambda r: r[0] == "x",
  "caught": lambda r: r[1] is not None},

 {"id": "M4_UNRESOLVED当成FAIL剔除", "目标": "⑤",
  "find": '    admitted = [m for m, v in states.items() if v["state"] != "DISQUALIFIED"]\n',
  "repl": '    admitted = [m for m, v in states.items() if v["state"] == "QUALIFIED"]\n',
  "probe": lambda m: m.admit_annotators([{"model": "A", "hits": 5, "of": 5},
                                         {"model": "B", "hits": 3, "of": 5},
                                         {"model": "C", "hits": 4, "of": 5}]),
  "reached": lambda r: "★states" in r,
  "caught": lambda r: r["admit"] is None or len(r["admit"]) != 3},
]


def run_mutants():
    rows = []
    for mu in MUTANTS:
        row = {"id": mu["id"], "针对失效": mu["目标"]}
        def mutator(src, _f=mu["find"], _r=mu["repl"]):
            if _f not in src:
                raise AssertionError(f"★ 变异锚点不在源码里: {_f!r} —— 变异**无效**, 不计为检出")
            return src.replace(_f, _r, 1)
        try:
            m = load(source_mutator=mutator,
                     responses=lambda md, p: "not json" if mu["id"].startswith("M3") else OK_JSON)
            row["源码确实被改动"] = m._OFFLINE_MUTATED
            r = mu["probe"](m)
            row["变异版确实走到目标路径"] = bool(mu["reached"](r))
            row["被检出"] = bool(mu["caught"](r))
            row["★判"] = ("PASS(检出)" if (row["变异版确实走到目标路径"] and row["被检出"])
                         else ("**变异无效 —— 没走到目标路径, 不计为检出**"
                               if not row["变异版确实走到目标路径"] else "**FAIL(漏检)**"))
        except Exception as e:
            # ★★★ 因语法错/导入失败而红 —— **不算检出**
            row["源码确实被改动"] = row.get("源码确实被改动", None)
            row["★判"] = f"**变异无效 —— 变异版自身抛错({type(e).__name__}), 按 GPT 规则不计为检出**"
            row["异常"] = f"{type(e).__name__}: {e}"[:200]
            row["traceback尾"] = traceback.format_exc()[-300:]
        rows.append(row)
    return rows


def build():
    five = {"①缺必需规则却通过": t1_missing_required_rule(),
            "②空必需集合空过": t2_empty_set_vacuous_pass(),
            "③解析失败被转成成功": t3_parse_failure_as_success(),
            "④无可裁定条目仍完整通过": t4_no_adjudicable_still_passes(),
            "⑤合法基线被一律拒绝": t5_legitimate_baseline_not_rejected()}
    mut = run_mutants()
    m = load()
    return {
      "block": "ACCURACY_DIRECTED_TESTS",
      "★zero_api": "**全程零真实调用** —— socket 绊线在位且**未被触发**。",
      "★绊线作用域(不夸大)": m._OFFLINE_TRIPWIRE.scope,
      "★替换边界": "只替换**传输结果**; 构造/解析/断言/汇总**逐字未改**",
      "★★★据此能支持的结论": "**对这份闸实现的离线软件验证**。"
                   "**不能**证明真实模型的语义判断准确率或重复稳定性。",
      "五种失效": five,
      "★五种全过": all(v["判"] == "PASS" for v in five.values()),
      "变异检定": mut,
      "★变异全被检出": all(r["★判"].startswith("PASS") for r in mut),
      "★★不许": "把刚撤销的八条 display 断言**重新偷偷当作金标塞回来** —— 本文件**一条都没用**。",
      "★仍未验证的": ["真实 provider 的语义判断准确率", "真实 provider 的重复稳定性",
                 "G-K2 成本档链路(CCE_SKIP_GK2=1)", "main() 的端到端编排"],
    }


if __name__ == "__main__":
    r = build()
    print(json.dumps(r, ensure_ascii=False, indent=1))
