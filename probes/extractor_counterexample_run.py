#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抽取器构造反例筛查 —— 判据见 tests/data/extractor_counterexample_prereg.json(测量前冻结)。

问题: 给定**已定标签** display, 抽取器会不会交出「形式合规、语义错误」的证书?
做法: 16 条构造文本(4 正 / 12 阴), 每条**只调一次**, 结果直接送进现有资格层。
★ key 仅从 /Volumes/data/viral-skill-eval/.env 进程内加载, 不回显 · 不复制 · 不写仓 · 不写记忆。
★ 硬上限 16 · 零重试 · 失败也计数, 不补抽。
"""
import json, os, pathlib, random, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

PREREG = json.loads((ROOT / "tests/data/extractor_counterexample_prereg.json").read_text(encoding="utf-8"))
TPL = json.loads((ROOT / "tests/data/extractor_counterexample_templates.json").read_text(encoding="utf-8"))
CAP = PREREG["执行"]["★请求硬上限"]
OUT = ROOT / "results" / "extractor_counterexample.json"

CONJ_P = "输出新信息增量"
CONJ_Q = "谈论对象是自己已拥有或已经历的"

PROMPT = """你在核验一条**已经定好的**标注。标签是 `display`。

`display` 的判别式(逐字):
%s

文本:
\"\"\"%s\"\"\"

请判断:这段文本**是否真的**满足该判别式。如果满足,请为**每一个必要条件**各引用一段**逐字出现在上面文本里的**原文片段作为支撑。

只输出 JSON,不要别的:
{
  "supported": true 或 false,
  "increment": {"span": "支撑「输出新信息增量」的逐字片段", "kind": "具体型号|数据|使用细节|纠错|结构化经验", "about": "**这一段**是在讲哪个对象"},
  "owned_or_experienced": {"span": "支撑「自己已拥有或已经历」的逐字片段", "about": "**这一段**是在讲哪个对象"},
  "why_not": "supported 为 false 时,一句话说明差在哪;否则填 null"
}
supported 为 false 时,increment 与 owned_or_experienced 都填 null。
片段必须**逐字**出自上面的文本。不要改写、不要合并不相邻的词。
两个 about 各自照**那一段实际在讲的**对象填,**不要**为了凑成一致而填同一个。"""


def _load_key():
    p = pathlib.Path("/Volumes/data/viral-skill-eval/.env")
    if not p.exists():
        raise SystemExit("★ 找不到订阅凭据文件 —— **未发起任何调用**")
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:]
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    if not os.environ.get("MINIMAX_API_KEY"):
        raise SystemExit("★ 凭据文件里没有 MINIMAX_API_KEY —— **未发起任何调用**")


def _parse(raw):
    """抠出第一个 JSON 对象。抠不出 ⇒ 记为格式失败, **不重试**。"""
    s = raw.find("{")
    if s < 0:
        return None
    depth = 0
    for i in range(s, len(raw)):
        if raw[i] == "{":
            depth += 1
        elif raw[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(raw[s:i + 1])
                except Exception:
                    return None
    return None


def _judge(t, obj):
    """把模型交出的证书送进**现有资格层**。Z=1 ⟺ 通过整套机械验证器。"""
    import cce_label_qualification as LQ
    if not obj or not obj.get("supported"):
        return 0, "模型自己判**不支持**", None
    inc = obj.get("increment") or {}
    own = obj.get("owned_or_experienced") or {}
    # ★★★ 两支的 about **各自照模型填的取**, 绝不合并。
    #   2026-09-14 零调用自检抓到: 早先只收一个 object 字段再贴到两支上,
    #   P2(同一对象)那一支就**结构上不可能失败** —— 期望与实际同源, N2。
    try:
        ev = [
            LQ.EvidenceSpan(inc.get("span") or "", CONJ_P, t["text"],
                            about=inc.get("about"), increment_kind=inc.get("kind")),
            LQ.EvidenceSpan(own.get("span") or "", CONJ_Q, t["text"],
                            about=own.get("about")),
        ]
    except Exception as e:
        return 0, "证书构造即被拒: %s" % str(e).split("\n")[0][:120], None
    q = LQ.qualify("display", t["text"], evidence=ev,
                   required_conjuncts=[CONJ_P, CONJ_Q])
    z = 1 if q["state"] == LQ.CITED_UNVERIFIED else 0
    return z, q["why"][:200], q["state"]


def main():
    assert PREREG["★★★status"].startswith("**READY**"), "★ 预注册未就绪, 不得发起"
    _load_key()
    from exp_crossmodel_desire import call_model
    import cce_knot_classify as CK

    disc = TPL[[k for k in TPL if k.startswith("★合同原文")][0]]
    items = list(TPL["templates"])
    random.Random(20260914).shuffle(items)          # 顺序固定种子打乱

    rows, n = [], 0
    t0 = time.time()
    for t in items:
        if n >= CAP:
            print("★★★ 撞硬上限 %d —— 停" % CAP)
            break
        n += 1
        raw, meta = call_model(CK.MEASUREMENT_MODEL,
                               PROMPT % (disc, t["text"]),
                               temperature=0.0, max_retries=1)
        err = meta.get("error")
        obj = _parse(raw) if raw and raw.strip() else None
        if err or obj is None:
            z, why, st = 0, "调用或格式失败(**计入预算, 不补抽**): %s" % (err or "无法解析 JSON"), None
            ok = False
        else:
            z, why, st = _judge(t, obj)
            ok = True
        rows.append({"id": t["id"], "arm": t["arm"], "结构": t["结构"],
                     "预期": t["推导"]["预期"], "Z": z, "资格层": st,
                     "why": why, "调用成功": ok,
                     "模型原样": obj if ok else (raw or "")[:200]})
        print("  %-7s %-10s Z=%d  %s" % (t["id"], t["arm"], z, why[:70]))
        if z and t["arm"] != "正证据对照":
            print("  ★★★ 错误升格见证: %s —— 按冻结的停止规则可以停" % t["id"])

    neg = [r for r in rows if r["arm"] != "正证据对照"]
    negz = [r for r in neg if r["Z"]]
    pos = [r for r in rows if r["arm"] == "正证据对照"]
    posz = [r for r in pos if r["Z"]]
    if negz:
        verdict = "COUNTEREXAMPLE_FOUND"
    elif not posz:
        verdict = "DEGENERATE_ON_CONTROLS"
    else:
        verdict = "NO_COUNTEREXAMPLE_IN_THIS_SUITE"
    res = {"block": "EXTRACTOR_COUNTEREXAMPLE_RESULT",
           "prereg": "tests/data/extractor_counterexample_prereg.json",
           "model": CK.MEASUREMENT_MODEL,
           "★实际执行数": n, "★硬上限": CAP, "★重试": 0,
           "调用或格式失败": sum(1 for r in rows if not r["调用成功"]),
           "p_challenge": "%d/%d" % (len(negz), len(neg)),
           "正证据成功": "%d/%d" % (len(posz), len(pos)),
           "★★★verdict": verdict,
           "★这个数不是什么": PREREG["★★★主判据(测量前冻结)"]["★这个数是什么不是什么"],
           "elapsed_s": round(time.time() - t0, 1), "rows": rows}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n判决 %s · 阴性错误升格 %s · 正证据成功 %s · 执行 %d/%d · 失败 %d"
          % (verdict, res["p_challenge"], res["正证据成功"], n, CAP, res["调用或格式失败"]))
    print("→", OUT)


if __name__ == "__main__":
    # ★★★ r1 的预算(16 次)**已用尽**, 判决 DEGENERATE_ON_CONTROLS, 读数已落盘。
    #   本文件保留为**历史执行器**(r2/r3 的回放自检要读它产出的数据), 但**入口封死**:
    #   2026-09-14 实测教训 —— 仓里每多一份**可运行的分叉执行器**, 就多一份**旧闸守不到**的代码
    #   (配对变异实测: 同一变异打 r2 文件被抓, 打分叉文件 96 道全绿)。
    raise SystemExit("★★★ r1 的预算已用尽, 本执行器**已被否决再运行**; 重复测量请用 probes/extractor_counterexample_run_r2.py + CCE_EXTRACTOR_OUT。")
