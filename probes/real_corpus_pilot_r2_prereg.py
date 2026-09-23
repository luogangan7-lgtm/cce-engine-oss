# -*- coding: utf-8 -*-
"""真实语料小批试**第二轮(重测)**的预注册生成器。零调用。

★★★ 为什么要有第二轮:
  第一轮的 **34/41 = 0.829**(Fisher p=0.000344 ⇒ TRANSFERS_NOT_HIGHER) 是**单次读数**。
  本仓已登记的硬教训: 「**单次运行读数不可信**」—— 同一执行器/提示词/温度重复测量,
  r3 实测 15 个比对点翻了 6 条。而我已经拿那个单次数下了判决并登记进 manifest。
  ⇒ **按本仓自己的规矩, 它在重测之前不该当结论用。**

★★★ 这一轮同时还一笔债:
  第一轮为守隐私**没存 object 字段** ⇒ 资格层事后无法重算, 而「验证器会拦住形式合规、
  语义错误的证书」自 r2 起就是零证据。本轮新增 object 的 **sha16**(不落原文) ⇒
  资格层的**机械部分**可算。

★ 第一轮的产物**一个字节不动**: 它已冻结、sha 已登记、闸已验。本轮另立文件。
★ 隐私: 仍然只登记指针与结构化事实, 不写一个字语料原文、模型 span、模型自由文本。
"""
import hashlib, importlib.util, json, pathlib, sys
from math import comb, sqrt

ROOT = pathlib.Path(__file__).resolve().parents[1]
R1_PRE = ROOT / "tests/data/real_corpus_pilot_prereg.json"
R1_RES = ROOT / "results/real_corpus_pilot.json"
OUT = ROOT / "tests/data/real_corpus_pilot_r2_prereg.json"
ALPHA = 0.05


def _g1():
    """第一轮的预注册生成器 —— fisher_p / clopper_pearson / submitted 全部复用, 不重写。"""
    s = importlib.util.spec_from_file_location("_g1", ROOT / "probes/real_corpus_pilot_prereg.py")
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def _k(d, frag):
    ks = [x for x in d if frag in x]
    assert len(ks) == 1, "★ 片段 %r 命中 %d 个键" % (frag, len(ks))
    return d[ks[0]]


def kappa_ci(a, b, c, d, z=1.96):
    """Cohen's kappa 与其正态近似 95% 区间。配对 2x2: a 都交卷 / b,c 翻转 / d 都不交卷。

    ★★★ 为什么必须用 kappa 而不是裸的一致率:
      交卷率本来就高(~0.83) ⇒ **纯随机独立下逐条一致率就已经有 ~0.72**。
      「一致率 81%」听着高, 其实几乎等于掷骰子。kappa 正是「扣掉随机一致之后还剩多少」。
    """
    n = a + b + c + d
    if n == 0:
        return None
    po = (a + d) / n
    p1, q1 = (a + b) / n, (a + c) / n
    pe = p1 * q1 + (1 - p1) * (1 - q1)
    if pe >= 1:
        return {"po": po, "pe": pe, "kappa": None,
                "★为什么算不出": "独立基线 pe=1(某一轮全交卷或全不交卷) ⇒ kappa 无定义。"}
    k = (po - pe) / (1 - pe)
    se = sqrt(po * (1 - po) / (n * (1 - pe) ** 2)) if n else 0.0
    return {"po": round(po, 4), "pe(独立基线)": round(pe, 4), "kappa": round(k, 4),
            "kappa 95%CI": [round(k - z * se, 4), round(k + z * se, 4)]}


def mcnemar_exact(b, c):
    """精确 McNemar(二项检验): 只看**翻转方向不对称**, 不看两轮都一样的那些。"""
    n = b + c
    if n == 0:
        return 1.0
    lo = min(b, c)
    p = 2 * sum(comb(n, i) * 0.5 ** n for i in range(0, lo + 1))
    return min(1.0, p)


def main():
    g1 = _g1()
    assert R1_RES.exists(), "★ 第一轮产物不在, 无法立第二轮"
    pre1 = json.loads(R1_PRE.read_text(encoding="utf-8"))
    res1 = json.loads(R1_RES.read_text(encoding="utf-8"))
    R1 = res1["★★★ 主读数: 真实语料交卷率"]
    J1 = _k(pre1, "主判据(投料前定死)")
    table = _k(J1, "拒绝域按实际 n_ok 查表")
    min_n = _k(J1, "最低可判 n_ok(= **下尾可达**")
    items = _k(pre1, "冻结输入集")["items"]
    N = len(items)
    k1, n1 = (int(x) for x in R1["交卷/有效"].split("/"))

    # ★★★ 主判据的事前功效: 第二轮 k 是否仍落在**第一轮冻结的**拒绝域
    hi_k = table[str(N)]["k ≥"]
    conf = {("q=%.2f" % q):
            round(sum(comb(N, k) * q ** k * (1 - q) ** (N - k) for k in range(hi_k, N + 1)), 3)
            for q in (0.83, 0.75, 0.70, 0.65, 0.60, 0.55, 0.50, 0.40)}

    # ★★★ kappa 的事前可达性: 翻转几条之内才判得出「比随机稳」
    reach = {}
    for flip in (0, 2, 4, 6, 8, 12):
        b = c = flip // 2
        a = round(N * (k1 / n1)) - b
        d = N - a - b - c
        if d < 0 or a < 0:
            continue
        r = kappa_ci(a, b, c, d)
        reach["翻转 %d 条(一致 %d/%d)" % (flip, a + d, N)] = {
            "kappa": r.get("kappa"), "95%CI": r.get("kappa 95%CI"),
            "独立基线 pe": r.get("pe(独立基线)"),
            "判得出比随机稳吗": bool(r.get("kappa 95%CI") and r["kappa 95%CI"][0] > 0)}
    max_flip = max(int(x.split("翻转 ")[1].split(" 条")[0])
                   for x, v in reach.items() if v["判得出比随机稳吗"])

    pre = {
        "block": "REAL_CORPUS_PILOT_R2_PREREG",
        "date": "2026-09-17",
        "★★★status": "**READY**",
        "★零调用": "本文件由零调用探针生成; 投料由 probes/real_corpus_pilot_r2_run.py 单独执行。",

        "★★★★★ 为什么要跑第二轮": {
            "第一轮的读数": "%s = %s, Fisher p=%s ⇒ **%s**"
                            % (R1["交卷/有效"], R1["率"], R1["Fisher 两侧 p"], R1["★★★判决"]),
            "★★★但它是单次读数": "本仓已登记的硬教训: 「**单次运行读数不可信**」—— "
                "同一执行器/提示词/温度重复测量, r3 实测 15 个比对点**翻了 6 条**; "
                "seed 探针又实测该端点 **temp=0 并不确定**(6 次 5 种输出)。",
            "★我已经拿它下了判决": "TRANSFERS_NOT_HIGHER 已写进 manifest refactor_log。"
                "**按本仓自己的规矩, 它在重测之前不该当结论用** ⇒ 这一轮就是去补那一步。",
            "★顺带还一笔债": "第一轮为守隐私没存 object ⇒ 资格层事后无法重算。"
                "本轮新增 object 的 **sha16**(不落原文), 于是资格层的**机械部分**可算。",
        },

        "★★★ 与第一轮**完全相同**的部分(钉 sha, 执行器调用前重验)": {
            "输入集": "逐条继承第一轮的 42 条, **不重新选**",
            "第一轮预注册 sha256": hashlib.sha256(R1_PRE.read_bytes()).hexdigest(),
            "第一轮产物 sha256": hashlib.sha256(R1_RES.read_bytes()).hexdigest(),
            "PROMPT sha256": _k(pre1, "冻结提示词与判别式")["PROMPT sha256"],
            "判别式 sha256": _k(pre1, "冻结提示词与判别式")["判别式 sha256"],
            "模型臂": _k(pre1, "冻结模型臂")["MEASUREMENT_MODEL"],
            "temperature": 0.0, "max_retries": 1,
            "★为什么必须逐字相同": "重测的全部意义就是**只让时间变**。改任何一项, 差异就归因不了。",
            "items": items,
        },

        "★★★ 主判据(投料前定死): 第一轮的判决复现吗": {
            "★判法": "第二轮的交卷数 k2, 按**第一轮冻结的拒绝域表**中 n_ok=k2 的分母那一行去查 —— "
                     "**不新立判据, 不重新推导**。",
            "第一轮拒绝域表(继承, 不重算)": table,
            "第一轮最低可判 n_ok": min_n,
            "判 CONFIRMED": "第二轮 k2 仍落在该 n_ok 对应拒绝域的**同一侧**(上尾) "
                            "⇒ TRANSFERS_NOT_HIGHER **复现**, 第一轮的读数可以引用。",
            "判 NOT_CONFIRMED": "第二轮 k2 **不在**拒绝域, 或落在**另一侧** "
                                "⇒ 第一轮的判决**不得作为单次定论引用**(r2→r3 就是这个下场)。",
            "判 INSUFFICIENT_DATA": "第二轮有效 n_ok < %d(第一轮冻结的门槛)。" % min_n,
            "★事前功效(第二轮复现 CONFIRMED 的概率)": conf,
            "★★★功效的老实话": "q 要掉到 **~0.60 以下**这条判据才会开始失败 "
                "⇒ 它测的是「**会不会大跌**」, **测不出小波动**。"
                "小波动交给下面的 kappa。",
        },

        "★★★ 稳定性读数(事前定死判法): 逐条稳不稳": {
            "★★★为什么不能看裸的一致率": "交卷率本来就高(第一轮 %.3f) ⇒ "
                "**纯随机独立下逐条一致率就已经有 ~%.3f**。"
                "「一致率 81%%」听着高, 其实几乎等于掷骰子。"
                % (k1 / n1, (k1 / n1) ** 2 + (1 - k1 / n1) ** 2),
            "★判法": "Cohen's kappa(扣掉随机一致之后还剩多少) + 正态近似 95%CI。",
            "判 STABLER_THAN_CHANCE": "kappa 的 95%CI **下界 > 0**。",
            "判 CANNOT_SHOW_BETTER_THAN_CHANCE": "下界 ≤ 0 ⇒ **这批数据分不出它比随机稳**。"
                "★ 那本身就是结论: 它会说明 83%% 这个数**在逐条层面是噪声**, 即便边际复现。",
            "★事前可达性": reach,
            "★★★ 事前就知道的上限": "翻转**超过 %d 条**就判不出「比随机稳」了。"
                "⇒ 本判据**不是**「一致率高不高」, 而是「**高到能与随机分开吗**」。" % max_flip,
            "★边际是否移动": "另报**精确 McNemar**(只看翻转方向的不对称) —— "
                "它与 kappa 回答不同的问题: kappa 问逐条稳不稳, McNemar 问**总量有没有系统性漂移**。",
        },

        "★★★ 新增读数: 资格层的**机械**部分": {
            "★为什么现在能算了": "本轮存 object 的 sha16(规范化后) ⇒ 两支是否同对象可判。",
            "★规范化复用": "probes/extractor_counterexample_run_r2.py 的 normalize_about() —— "
                           "冻结规则(去尾部括注 / 去前导冠词 / 去首尾标点), **不重写、不加别名归并**。",
            "机械出口": {
                "MALFORMED": "任一 span 或 object **非逐字**出自原文, 或 A 支缺 increment_kind。",
                "P2_FAIL": "A 支与 B 支的 object 规范化后**不相等**。",
                "PASS_MECHANICAL": "以上都过。",
            },
            "★★★ 这**不是**「验证器守得住」的证据": "机械出口只回答**形式**。"
                "「形式合规、语义错误的证书会不会被拦」需要**金标**, 真实语料没有 ⇒ "
                "**那句话本轮仍然零证据**。",
            "★GRANULARITY 与 DISTINCT 分不开": "r2 用**模板档案声明**的对象集合去分辨"
                "「仪器伪影」与「真·不同对象」。真实语料没有档案 ⇒ 本轮只报 P2_FAIL, 不拆。",
        },

        "★★★ 不得做的事": [
            "不得看过结果再改任何判据。",
            "不得改第一轮的任何产物 —— 它已冻结、sha 已登记, 本轮只**读**它。",
            "不得把 kappa 的「分不出」读成「稳」。",
            "不得把资格层的**机械**出口读成「验证器守得住」—— 那需要金标。",
            "不得与 r3 的 60%% 直接比: 那是**多值判决**, 本轮是**二值交卷**, 天然更容易一致。",
            "撞硬上限 %d 立即停。" % N,
        ],
        "预算": {"本轮上限": N, "之前已用": 200, "上限达成时合计": 200 + N,
                 "★计费": "订阅制(非按量), 但仍逐次登记。"},
    }
    OUT.write_text(json.dumps(pre, ensure_ascii=False, indent=1), encoding="utf-8")
    print("第一轮: %s = %s ⇒ %s" % (R1["交卷/有效"], R1["率"], R1["★★★判决"]))
    print("主判据: 第二轮 k2 是否仍 ≥ %d(继承第一轮冻结表)" % hi_k)
    print("事前功效:", json.dumps(conf, ensure_ascii=False))
    print("kappa 可达上限: 翻转 ≤ %d 条" % max_flip)
    print("→", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
