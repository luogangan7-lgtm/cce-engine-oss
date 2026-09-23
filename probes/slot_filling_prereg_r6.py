# -*- coding: utf-8 -*-
"""r6 预注册生成器: r5 的协议**原样**, 只把 contract_pairs 换成 v4(表层配平后)。零调用。

★★★ 这一轮问什么: r5 的负结果(B 臂鉴别格 4/24 < 门 11, D6 触发)是在 v3 上得到的, 而 v3 与真人语料
  表层偏离 14 点。**在表层配平后的 v4 上, 这个负结果复现吗?**
★ p0 与 base_net 都从 v4 items 上**现搜**(冻结族 + 单 token 取更高), 门与功效事前算死。
★ 与 r5 的读数**不得直接比**: item 集不同 + r3 实测重测一致率 60%。
"""
import hashlib, importlib.util, json, pathlib, sys
from math import comb

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "tests/data/slot_filling_prereg_r6.json"
PAIRS = ROOT / "tests/data/semantic_minimal_pairs.json"
ANN = ROOT / "tests/data/claim_frame_annotations.json"
R5_PRE = ROOT / "tests/data/slot_filling_prereg_r5.json"
ALPHA = 0.05


def _load(rel, name):
    s = importlib.util.spec_from_file_location(name, ROOT / rel)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m


def _sha16(o):
    return hashlib.sha256(json.dumps(o, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def bge(k, n, p):
    return sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))


def joint_power(gate, base_net, q, n_d=24, n_b=42):
    """①k≥gate ∧ ②(k − 多数类错数) > base_net, 逐格命中率 q, 精确卷积(不是蒙特卡洛)。"""
    pd = [comb(n_d, k) * q ** k * (1 - q) ** (n_d - k) for k in range(n_d + 1)]
    pb = [comb(n_b, j) * q ** j * (1 - q) ** (n_b - j) for j in range(n_b + 1)]
    return sum(pd[k] * pb[j] for k in range(n_d + 1) for j in range(n_b + 1)
               if k >= gate and (k - (n_b - j)) > base_net)


def shallow_null(v4, d, ann):
    """零假设: 模型 = v4 items 上最强的浅层规则。冻结族与单 token 两个口径都搜, 取更严的。"""
    bs = _load("probes/best_shallow_rule_search.py", "bs")
    v4c = _load("probes/contract_pairs_v4_check.py", "v4c")
    rows = v4c.cells(v4, d, ann, ann["★默认槽位"])
    fam, nd, nb = bs.search_family(rows, "RESTATES_IDENTIFIER")
    tok, _, _ = bs.search(rows, "RESTATES_IDENTIFIER")
    f, t = fam[0], tok[0]
    fh, th = int(f["命中鉴别格"].split("/")[0]), int(t["命中鉴别格"].split("/")[0])
    return {"鉴别格数": nd, "多数类格数": nb,
            "冻结族最佳": {"规则": f["规则"], "命中": f["命中鉴别格"], "误伤": f["误伤多数类格"], "净增益": f["净增益"]},
            "单token最佳": {"token": t["token"], "命中": t["命中鉴别格"], "误伤": t["误伤多数类格"], "净增益": t["净增益"]},
            "p0": max(fh, th) / nd, "base_net": max(f["净增益"], t["净增益"]),
            "★取更严的": "p0 取两口径里**更高的命中率**(r5 同); base_net 取**更高的净增益**"
                         "(r5 只用了冻结族的 1, 本轮更严 —— 单 token 'sound' 净 3 就在那里, 不能装看不见)。"}


def main():
    d = json.loads(PAIRS.read_text(encoding="utf-8")); ann = json.loads(ANN.read_text(encoding="utf-8"))
    r5 = json.loads(R5_PRE.read_text(encoding="utf-8"))
    r5exe = _load("probes/slot_filling_run_r5.py", "r5exe")
    v4 = d["contract_pairs_v4"]
    n_items = (len(d["pairs"]) + len(v4)) * 2
    null = shallow_null(v4, d, ann)
    n, p0, base_net = null["鉴别格数"], null["p0"], null["base_net"]
    gate = min(k for k in range(n + 1) if bge(k, n, p0) < ALPHA)
    qs = (0.40, 0.50, 0.60, 0.65, 0.70, 0.75, 0.80, 0.90)
    power1 = {"q=%.2f" % q: "%.3f" % bge(gate, n, q) for q in qs}
    powerJ = {"q=%.2f" % q: "%.3f" % joint_power(gate, base_net, q) for q in qs}
    q80 = min(q for q in qs if joint_power(gate, base_net, q) >= 0.8)

    # 判据准入(库内硬规则)
    sys.path.insert(0, str(ROOT / "scripts")); import cce_criterion_preflight as CP
    spec = {"date": "2026-09-23", "alpha": ALPHA,
            "arms": ["① 金标", "② 零基线(完全不读文本的常数填充)", "③ 浅层线索臂", "④ 最佳浅层规则(冻结族)", "⑥ 模型 B 臂"],
            "downgrades": [x for x in r5["★★★降级条件(测量前冻结)"]],
            "criteria": [
                {"name": "主判据 二项检验 n=24", "n": n, "kind": "significance", "claim": "confirmatory"},
                {"name": "D1 调用失败过半", "n": n_items, "thr": 0.5, "direction": ">="},
                {"name": "D3 对照全部不通过(退化检测)", "n": n_items // 2, "thr": 0.0, "direction": "<="},
                {"name": "D4 端到端可用不足半数", "n": n_items, "thr": 0.5, "direction": "<="}]}
    ok, errs, info = CP.check(spec)

    pre = {
        "block": "SLOT_FILLING_PREREG_R6", "date": "2026-09-23", "★★★status": "**READY**",
        "★★★这一轮问什么": "r5 的负结果(B 臂鉴别格 4/24 < 门 11, D6 触发)是在 **v3** 上得到的, 而 v3 的 A 支与真人语料"
            "表层偏离 14 点(读数不得外推)。**在表层配平后的 v4(偏离 1.8 点)上, 这个负结果复现吗?**",
        "★★★怎么读两种结局": {
            "未达成": "负结果在**外部效度更好**的对照集上复现 ⇒ 「附件 A 这条合同条款目前没有可靠的自动判定方法」这句话**站得更稳**。",
            "达成": "**不得**读成「v3 的表层伪影拖累了模型」—— item 集不同 + 重测噪声 60%; 只能说「在 v4 上超过了浅层规则」, "
                    "要归因得同轮配对跑 v3, 那是另一张预算。"},
        "★协议与 r5 逐字相同的部分": "提示词(sha 由闸现算比对) · 只跑 B 臂 · 打分/tally/judge 代码(执行器 **import r5 模块**, 一行不改) · "
                                   "六臂对照 · 降级 D1–D6 · 硬上限 = items 数 · 每条尝试 1 次 · 交错发起。",
        "★★★items(测量前冻结)": {"来源": "pairs(10 对, 冻结未动) + contract_pairs_v4(24 对, 2026-09-23 表层配平) = 34 对 × 2 版 = %d 条" % n_items,
                               "★为什么 pairs 那 10 对必须在": r5["★★★items(测量前冻结)"]["★★★为什么不能砍掉 pairs 那 10 对"],
                               "★span 与 supports 不让模型选": "从冻结文件取。"},
        "★★★金标哈希(测量前冻结)": {"tests/data/claim_frame_annotations.json": hashlib.sha256(ANN.read_bytes()).hexdigest()[:8],
                                 "tests/data/semantic_minimal_pairs.json::contract_pairs_v4": _sha16(v4),
                                 "tests/data/semantic_minimal_pairs.json::pairs": _sha16(d["pairs"]),
                                 "★v4 自己的体检": "results/contract_pairs_v4_check.json(表层偏离 1.8 · 冻结族净增益 1 · 单 token 净增益 3 · 判据层与 v3 逐对相同)"},
        "★★★两臂提示词哈希(测量前冻结)": r5exe.prompt_sha(),
        "★★★两臂的唯一差异": r5["★★★两臂的唯一差异"],
        "★★★六臂必须一起报(四条零调用 + 两条模型)": r5["★★★六臂必须一起报(四条零调用 + 两条模型)"],
        "★★★主判据(测量前冻结_confirmatory)": {
            "定义": "B 臂在 **predicate 鉴别格**(金标 = RESTATES_IDENTIFIER)上的答对数。",
            "零假设": "模型等同于 **v4 items 上最强的浅层规则**。",
            "★零假设从哪来(现搜, 不是抄 r5)": null,
            "★冻结的 n": n, "★冻结的 p0": round(p0, 4), "★冻结的门": gate,
            "★事前算好的门": "P(X≥%d | n=%d, p0=%.3f) = **%.4f** < %.2f ⇒ 门 = ≥%d/%d" % (gate, n, p0, bge(gate, n, p0), ALPHA, gate, n),
            "★冻结的最佳浅层规则净增益": base_net,
            "★三个前置条件": "① 鉴别格 ≥ **%d/%d**; ② **净增益 > %d**; ③ 端到端可用过半。" % (gate, n, base_net),
            "★★★power(单条①, 测量前算)": power1,
            "★★★power(联合①∧②, 精确卷积不是蒙特卡洛)": powerJ,
            "★★★power 是联合的不是单条": "结论要求 ①∧②。联合功效 q≥%.2f 时 ≥0.8。★ 低于此的「未达成」**不等于模型不行**。"
                                        "★ 门比 r5 低(%d vs 11)是因为 v4 上浅层规则更弱(p0 %.3f vs 0.250) —— 不是放水, 是零假设变弱了。" % (q80, gate, p0),
            "★★★这不证明什么": "即使达成, 也只说明在这 %d 个**手构**鉴别格上优于两个口径内的浅层规则。族外规则不在空间内 ⇒ p0 仍是下界。" % n,
        },
        "★★★降级条件(测量前冻结)": r5["★★★降级条件(测量前冻结)"],
        "★★★判据准入结果(零调用预检_库内硬规则)": {"工具": "scripts/cce_criterion_preflight.py", "通过": ok, "警告": errs, "明细": info,
            "★与 r5 相同的那条警告": "D3「对照全部不通过」离散后是零容差 —— r5 也带着它投料, 它是**退化检测**不是否决门槛。"},
        "★★★不得据此说": [
            "不得与 r5 的 4/24 直接比 —— item 集不同, 且 r3 实测同一仪器重测一致率 60%。",
            "不得说「模型能不能在自然语料上做这件事」—— 分母仍是手构最小对照, 只是表层配平了。",
            "不得据「达成」说 v3 的表层伪影拖累了模型 —— 归因需同轮配对 v3。",
            "不得把 D6 的「零增益」读成模型摆烂 —— 同批其他槽位的读数会一起报出。"],
        "★★★已知局限(测量前写下)": ["n=1 每条零重试, 每个数都是单次读数。", "只跑 B 臂, 不提供 B−A。",
            "B 臂提示词比无判据版更长, 「给了判据内容」与「提示词更长」仍混在一起(r5 同)。",
            "③ 手写浅层臂的 RULES 是评审 agent 在 **v3 文本**上写的, 在 v4 上可能不命中 —— 它的数只作陪跑。"],
        "★★★预算": {"总数": "**%d 次**(%d 条 × 只跑 B 臂)" % (n_items, n_items), "硬上限": n_items, "尝试次数": 1,
                   "★失败也计数": "计入预算, 不进分母, 单列。", "★停止规则": "撞硬上限即停; 提示词哈希与预注册不符即拒发; v4 哈希不符即拒发。",
                   "已用": "**242**", "本轮后合计": "**%d**" % (242 + n_items)},
    }
    OUT.write_text(json.dumps(pre, ensure_ascii=False, indent=1), encoding="utf-8")
    print("items %d · p0 %.4f(族 %s / 单token %s) · 门 ≥%d/%d · base_net %d · 联合功效 q≥%.2f≥0.8 · 准入 %s(警告 %d)"
          % (n_items, p0, null["冻结族最佳"]["命中"], null["单token最佳"]["命中"], gate, n, base_net, q80, ok, len(errs)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
