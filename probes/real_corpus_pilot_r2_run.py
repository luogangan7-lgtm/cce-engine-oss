# -*- coding: utf-8 -*-
"""真实语料小批试**第二轮(重测)** · 执行器。**会发起真实模型调用。**

★★★ 判据全部来自冻结的 tests/data/real_corpus_pilot_r2_prereg.json, 本文件**不定义任何判据**,
    而且主判据的拒绝域是**继承第一轮那张冻结表**, 不重新推导。
★ 第一轮的执行器与产物**一个字节不动** —— preflight / load_lines / classify_kind 全部 import 复用。
★ 隐私: object 只存**规范化后的 sha16**, 不落一个字原文。
"""
import argparse, hashlib, importlib.util, json, pathlib, sys, time

ROOT = pathlib.Path(__file__).resolve().parents[1]
PRE = ROOT / "tests/data/real_corpus_pilot_r2_prereg.json"
R1_PRE = ROOT / "tests/data/real_corpus_pilot_prereg.json"
R1_RES = ROOT / "results/real_corpus_pilot.json"
OUT = ROOT / "results/real_corpus_pilot_r2.json"
PARTIAL = ROOT / "results/real_corpus_pilot_r2_partial.jsonl"


def _load(path, name):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def _p1():
    return _load(ROOT / "probes/real_corpus_pilot_run.py", "_pilot1")


def _g2():
    return _load(ROOT / "probes/real_corpus_pilot_r2_prereg.py", "_g2")


def _r2mod():
    return _load(ROOT / "probes/extractor_counterexample_run_r2.py", "_r2")


def _k(d, frag):
    ks = [x for x in d if frag in x]
    assert len(ks) == 1, "★ 片段 %r 在预注册里命中 %d 个键" % (frag, len(ks))
    return d[ks[0]]


def preflight2(pre, p1, m):
    """★★★ 第一次调用之前: 第一轮的**全部**冻结件重验一遍。不符就停, 一次 HTTP 都不发。"""
    same = _k(pre, "与第一轮**完全相同**的部分")
    for rel, want in (("tests/data/real_corpus_pilot_prereg.json", same["第一轮预注册 sha256"]),
                      ("results/real_corpus_pilot.json", same["第一轮产物 sha256"])):
        got = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
        assert got == want, (
            "★★★ %s 与第二轮预注册记的不符 ⇒ 第一轮被改过, 重测失去意义 —— **未发起任何调用**" % rel)
    assert hashlib.sha256(m.PROMPT.encode()).hexdigest() == same["PROMPT sha256"], (
        "★★★ 提示词变了 —— 重测的意义就是只让时间变。**未发起任何调用**")
    assert hashlib.sha256(m.DISC.encode()).hexdigest() == same["判别式 sha256"], (
        "★★★ 判别式变了 —— **未发起任何调用**")
    assert same["max_retries"] == 1 and same["temperature"] == 0.0
    # ★ 第一轮 preflight 里的模型臂 / 底数产物 / 语料 sha 全部复用它跑一遍
    env = p1.preflight(json.loads(R1_PRE.read_text(encoding="utf-8")), m)
    return env


def obj_facts(ev, line, m):
    """★★★ 隐私: object 只回**规范化后的 sha16** 与几个布尔, 绝不带回文本。"""
    o = ev.get("object")
    if not isinstance(o, str) or not o.strip():
        return {"有 object": False, "object 逐字": False, "sha16": None}
    return {"有 object": True,
            "object 逐字": o in line,
            "sha16": hashlib.sha256(m.normalize_about(o).encode()).hexdigest()[:16]}


def qualify_mechanical(row):
    """资格层的**机械**部分。★ 它只回答形式; 语义对不对需要金标, 真实语料没有。"""
    if not row["调用成功"] or row["交卷"] is not True:
        return None
    if not all(row["span_逐字"]):
        return "MALFORMED"
    if not all(o["有 object"] and o["object 逐字"] for o in row["objects"]):
        return "MALFORMED"
    if row["A_支"] >= 1 and not row["kinds"]:
        return "MALFORMED"
    a = {o["sha16"] for o, s in zip(row["objects"], row["supports"]) if s == "A"}
    b = {o["sha16"] for o, s in zip(row["objects"], row["supports"]) if s == "B"}
    if not a or not b or a != b:
        return "P2_FAIL"
    return "PASS_MECHANICAL"


def build_result(pre, rows, n_exec, elapsed, model, env=None):
    """★ 计算与产物构造全在这里 —— 闸现算整份逐键比对。"""
    g2 = _g2()
    from collections import Counter

    same = _k(pre, "与第一轮**完全相同**的部分")
    J = _k(pre, "主判据(投料前定死)")
    table = _k(J, "第一轮拒绝域表(继承, 不重算)")
    min_n = _k(J, "第一轮最低可判 n_ok")

    ok = [r for r in rows if r["调用成功"]]
    n_ok = len(ok)
    k2 = sum(1 for r in ok if r["交卷"] is True)

    reg = table.get(str(n_ok))
    if n_ok < min_n or reg is None:
        verdict, side = "INSUFFICIENT_DATA", None
    elif reg["k ≥"] is not None and k2 >= reg["k ≥"]:
        verdict, side = "CONFIRMED", "上尾"
    elif k2 <= reg["k ≤"]:
        verdict, side = "NOT_CONFIRMED", "下尾(**方向翻了**)"
    else:
        verdict, side = "NOT_CONFIRMED", "不在拒绝域"

    # ── 配对: 与第一轮逐条比 ────────────────────────────────────────
    r1 = json.loads(R1_RES.read_text(encoding="utf-8"))
    m1 = {r["ptr"]: r for r in r1["rows"]}
    a = b = c = d = 0
    paired, only_one_valid = [], 0
    for r in rows:
        o = m1.get(r["ptr"])
        if o is None or not (r["调用成功"] and o["调用成功"]):
            only_one_valid += 1 if (o is not None) else 0
            continue
        x, y = o["交卷"] is True, r["交卷"] is True
        paired.append((r["ptr"], x, y))
        if x and y: a += 1
        elif x and not y: b += 1
        elif (not x) and y: c += 1
        else: d += 1
    kap = g2.kappa_ci(a, b, c, d)
    mc = g2.mcnemar_exact(b, c)
    stable = ("STABLER_THAN_CHANCE"
              if kap and kap.get("kappa 95%CI") and kap["kappa 95%CI"][0] > 0
              else "CANNOT_SHOW_BETTER_THAN_CHANCE")

    qual = Counter(q for q in (qualify_mechanical(r) for r in rows) if q)

    return {
        "block": "REAL_CORPUS_PILOT_R2_RESULT",
        "date": "2026-09-17",
        "prereg": str(PRE.relative_to(ROOT)),
        "prereg_sha256": hashlib.sha256(PRE.read_bytes()).hexdigest(),
        "★第一轮产物 sha256(投料前重验过)": same["第一轮产物 sha256"],
        "model": model,
        "★实际执行数": n_exec,
        "★重试": "max_retries=1(**不是 0**)",
        "调用或格式失败": n_exec - n_ok,
        "★失败构成": _err_tally(rows),
        "★★★ 运行时环境(有效值, 非源码值)": env,

        "★★★ 主判据: 第一轮的判决复现吗": {
            "第一轮": "%s = %s ⇒ %s" % (r1["★★★ 主读数: 真实语料交卷率"]["交卷/有效"],
                                       r1["★★★ 主读数: 真实语料交卷率"]["率"],
                                       r1["★★★ 主读数: 真实语料交卷率"]["★★★判决"]),
            "第二轮": "%d/%d = %s" % (k2, n_ok, round(k2 / n_ok, 4) if n_ok else None),
            "★继承的拒绝域(第一轮冻结表, 未重算)": reg,
            "落在": side,
            "★★★判决": verdict,
        },
        "★★★ 判决怎么读": (
            {"CONFIRMED":
                "TRANSFERS_NOT_HIGHER **复现** ⇒ 第一轮那个读数可以引用。"
                "★ 但这只说明**边际**稳, 逐条稳不稳看下面的 kappa。",
             "NOT_CONFIRMED":
                "第一轮的判决**没有复现** ⇒ 它**不得作为单次定论引用**。"
                "★ r2→r3 就是这个下场, 本仓已登记过一次。",
             "INSUFFICIENT_DATA":
                "第二轮有效调用只有 %d 次, 低于第一轮冻结的门槛 %s ⇒ **什么都没测到**。"
                % (n_ok, min_n)}[verdict]),

        "★★★ 稳定性: 逐条稳不稳(kappa)": {
            "配对 2x2": {"两轮都交卷": a, "一交二不交": b, "一不交二交": c, "两轮都不交": d},
            "可配对条数": len(paired),
            **(kap or {}),
            "★★★判读": stable,
            "★★★怎么读": (
                "kappa 的 95%%CI 下界 > 0 ⇒ **逐条一致显著好于随机**。"
                if stable == "STABLER_THAN_CHANCE" else
                "kappa 的 95%%CI 下界 ≤ 0 ⇒ **这批数据分不出它比随机稳**。"
                "★★★ 那不是「稳」—— 它说明**即便边际复现, 逐条层面仍可能是噪声**: "
                "哪些段落交卷像是随机的。"),
            "★为什么不看裸的一致率": "交卷率高 ⇒ 纯随机独立下一致率就已经有 pe 那么高。"
                "kappa 正是扣掉它之后剩下的。",
            "★边际是否漂移(精确 McNemar)": {
                "翻转": "%d 条 一→二 掉出, %d 条 一→二 新增" % (b, c),
                "p": round(mc, 6),
                "★怎么读": "它只看翻转方向的**不对称**, 与 kappa 回答不同的问题。",
            },
        },

        "★★★ 新增: 资格层的**机械**部分": {
            "出口分布": dict(sorted(qual.items())),
            "★★★这不是「验证器守得住」的证据": "机械出口只回答**形式**。"
                "「形式合规、语义错误的证书会不会被拦」需要**金标**, 真实语料没有 "
                "⇒ **那句话本轮仍然零证据**(自 r2 起)。",
            "★P2_FAIL 没有再拆": "r2 用模板档案声明去分辨「仪器伪影」与「真·不同对象」, "
                "真实语料没有档案 ⇒ 不拆。",
        },

        "★★★ 本轮不回答什么": [
            "**不回答**验证器能不能拦住语义错误的证书 —— 需要金标。",
            "**不回答**因子二(鉴别格产出率) —— 同样需要金标, 第一轮已事前声明测不了。",
            "**不回答**为什么真实语料交卷率高 —— 长度混淆未消除, 机制未识别。",
            "**不得**与 r3 的 60% 直接比: 那是多值判决, 本轮是二值交卷, 天然更容易一致。",
        ],
        "★隐私": "产物里只有指针与结构化事实, **无一字语料原文、无一字模型 span、"
                 "无一字模型 object 文本(只存规范化后的 sha16)、无一字模型自由文本**。",
        "耗时秒": round(elapsed, 1),
        "rows": rows,
    }


def _err_tally(rows):
    t = {}
    for r in rows:
        if not r["调用成功"]:
            t[r["err_类型"]] = t.get(r["err_类型"], 0) + 1
    return dict(sorted(t.items()))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="dry-run 专用")
    args = ap.parse_args(argv)

    p1, m, g1 = _p1(), _r2mod(), None
    g1 = _load(ROOT / "probes/real_corpus_pilot_prereg.py", "_g1")
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    assert pre["★★★status"].startswith("**READY**"), "★ 预注册未就绪"
    env = preflight2(pre, p1, m)

    pairs = p1.load_lines(json.loads(R1_PRE.read_text(encoding="utf-8")))
    same = _k(pre, "与第一轮**完全相同**的部分")
    assert len(pairs) == len(same["items"]), "★ 输入集条数与第二轮预注册不符"
    cap = args.limit if (args.limit is not None and args.dry_run) else len(pairs)
    assert args.limit is None or args.dry_run, "★★★ --limit 只许配 --dry-run 使用"
    enum = _k(json.loads(R1_PRE.read_text(encoding="utf-8")), "increment_kind 枚举")["枚举"]

    if args.dry_run:
        model_name = "DRY_RUN"
        def call(_a, _b, temperature=0.0, max_retries=1):
            assert max_retries == 1
            return ('{"supported": true, "evidence":['
                    '{"span":"x","supports":"A","object":"o","increment_kind":"使用细节"},'
                    '{"span":"y","supports":"B","object":"o","increment_kind":null}],'
                    '"why_not":null}'), {"finish_reason": "stop"}
    else:
        m._load_key()
        sys.path.insert(0, str(ROOT / "scripts"))
        from exp_crossmodel_desire import call_model as call
        import cce_knot_classify as CK
        model_name = CK.MEASUREMENT_MODEL

    done = {}
    if not args.dry_run and PARTIAL.exists():
        for ln in PARTIAL.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                r = json.loads(ln)
                done[r["ptr"]] = r
        print("★ 续跑: 已有 %d 行, 跳过(上限按**累计**算)" % len(done))

    rows, n, t0 = list(done.values()), len(done), time.time()
    for it, line in pairs:
        ptr = "%s:%d" % (it["file"], it["line_index"])
        if ptr in done:
            continue
        if n >= cap:
            print("★★★ 撞硬上限 %d —— 停" % cap)
            break
        n += 1
        raw, meta = call(model_name, m.PROMPT % (m.DISC, line), temperature=0.0, max_retries=1)
        err = (meta or {}).get("error")
        obj = m._parse(raw) if raw and raw.strip() else None
        base = {"ptr": ptr, "sha256": it["sha256"], "n_chars": it["n_chars"]}
        if err or obj is None:
            et = ("SENSITIVE_BLOCKED" if (meta or {}).get("sensitive")
                  else ("CALL_ERROR" if err else "UNPARSEABLE"))
            row = dict(base, **{"调用成功": False, "交卷": None, "err_类型": et,
                                "finish_reason": (meta or {}).get("finish_reason")})
        else:
            ev = obj.get("evidence") or []
            ev = [e for e in ev if isinstance(e, dict)] if isinstance(ev, list) else []
            row = dict(base, **{
                "调用成功": True,
                "交卷": g1.submitted(obj),
                "n_evidence": len(ev),
                "A_支": sum(1 for e in ev if e.get("supports") == "A"),
                "B_支": sum(1 for e in ev if e.get("supports") == "B"),
                "supports": [e.get("supports") for e in ev],
                "kinds": [p1.classify_kind(e.get("increment_kind"), enum) for e in ev
                          if e.get("supports") == "A" and e.get("increment_kind") is not None],
                "objects": [obj_facts(e, line, m) for e in ev],
                "span_逐字": [bool(isinstance(e.get("span"), str) and e["span"] in line) for e in ev],
                "why_not_字数": len(obj.get("why_not") or "") if isinstance(obj.get("why_not"), str) else 0,
                "finish_reason": (meta or {}).get("finish_reason"),
            })
        rows.append(row)
        if not args.dry_run:
            with PARTIAL.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print("  %-52s 交卷=%-5s" % (row["ptr"], row.get("交卷")))

    res = build_result(pre, rows, n, time.time() - t0, model_name, env)
    M = res["★★★ 主判据: 第一轮的判决复现吗"]
    if args.dry_run:
        print("\n[dry-run] main() 真跑完(n=%d), 未写盘。判决 = %s" % (n, M["★★★判决"]))
        return 0
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    K = res["★★★ 稳定性: 逐条稳不稳(kappa)"]
    print("\n第一轮 %s" % M["第一轮"])
    print("第二轮 %s · 继承拒绝域 %r ⇒ **%s**" % (M["第二轮"], M["★继承的拒绝域(第一轮冻结表, 未重算)"], M["★★★判决"]))
    print("配对 %r · kappa %s %s ⇒ %s" % (K["配对 2x2"], K.get("kappa"), K.get("kappa 95%CI"), K["★★★判读"]))
    print("资格层机械出口:", json.dumps(res["★★★ 新增: 资格层的**机械**部分"]["出口分布"], ensure_ascii=False))
    print("→", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
