# -*- coding: utf-8 -*-
"""两轮小批试的**跨轮汇总**。零调用, 只读两份已冻结的产物。

★★★ 为什么要有这份: 两份产物各自都**不含**下面这两个读法 ——
  ① 83% 复现了, 但**只有 12/42 过机械资格层** ⇒ 「交卷率」与「合格证书产出率」差 2.8 倍
  ② 代价下界该用哪个数 —— 这里把**能用**与**不能用**的分清楚, 不含糊过去
★ 两份源产物一个字节不动。
"""
import importlib.util, json, pathlib, sys
from math import comb

ROOT = pathlib.Path(__file__).resolve().parents[1]
R1 = ROOT / "results/real_corpus_pilot.json"
R2 = ROOT / "results/real_corpus_pilot_r2.json"
OUT = ROOT / "results/real_corpus_pilot_rollup.json"


def cp(k, n, alpha=0.05):
    def F(p): return sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))
    def G(p): return sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(0, k + 1))
    def bis(f, t):
        lo, hi = 0.0, 1.0
        for _ in range(100):
            m = (lo + hi) / 2
            if f(m) < t: lo = m
            else: hi = m
        return (lo + hi) / 2
    return (0.0 if k == 0 else bis(F, alpha / 2)), (1.0 if k == n else bis(lambda p: -G(p), -alpha / 2))


def _k(d, frag):
    ks = [x for x in d if frag in x]
    assert len(ks) == 1, "★ 片段 %r 命中 %d 个键" % (frag, len(ks))
    return d[ks[0]]


def build(d1, d2):
    A = d1["★★★ 主读数: 真实语料交卷率"]
    M = _k(d2, "主判据: 第一轮的判决复现吗")
    K = _k(d2, "稳定性: 逐条稳不稳")
    Q = _k(d2, "新增: 资格层的**机械**部分")["出口分布"]
    k1, n1 = (int(x) for x in A["交卷/有效"].split("/"))
    k2, n2 = (int(x) for x in M["第二轮"].split(" = ")[0].split("/"))
    npass = Q.get("PASS_MECHANICAL", 0)
    n_sub2 = sum(Q.values())
    lo_s, hi_s = cp(k2, n2)
    lo_p, hi_p = cp(npass, n2)
    F2 = 2 / 15

    return {
        "block": "REAL_CORPUS_PILOT_ROLLUP",
        "date": "2026-09-17",
        "★零调用": "只读两份已冻结的产物, **不发起任何调用**, 也不改它们。",
        "★源": {"第一轮": str(R1.relative_to(ROOT)), "第二轮": str(R2.relative_to(ROOT))},

        "★★★ 一、第一轮的判决复现了": {
            "第一轮": "%s = %s" % (A["交卷/有效"], A["率"]),
            "第二轮": M["第二轮"],
            "判决": M["★★★判决"],
            "★意味着": "TRANSFERS_NOT_HIGHER **可以引用**了 —— 它不再是单次读数。",
            "★逐条也稳": "kappa %s, 95%%CI %s(下界 > 0) ⇒ **%s**。"
                          % (K.get("kappa"), K.get("kappa 95%CI"), K["★★★判读"]),
            ("★★★但 kappa 只有 %s, 不是 1" % K.get("kappa")): "独立基线 pe = %s ⇒ 观察一致率 %s 里, "
                "**有相当一部分是随机撞上的**。翻转 %d 条(%d 掉出 + %d 新增)。"
                "⇒ 「哪一条会交卷」**仍有真实的不确定性**, 只是没大到淹没信号。"
                % (K.get("pe(独立基线)"), K.get("po"),
                   K["配对 2x2"]["一交二不交"] + K["配对 2x2"]["一不交二交"],
                   K["配对 2x2"]["一交二不交"], K["配对 2x2"]["一不交二交"]),
        },

        "★★★★★ 二、真正的新发现: 交卷 ≠ 合格, 差 %.1f 倍" % (k2 / npass if npass else float("inf")): {
            "交卷": "%d/%d = %.4f" % (k2, n2, k2 / n2),
            "过机械资格层": "%d/%d = %.4f" % (npass, n2, npass / n2),
            "机械出口分布": Q,
            "★★★ 主要卡点是 P2_FAIL": "%d/%d 张交卷证书**两支指到不同对象** —— "
                "模型在「新信息增量」那一支说的东西, 和在「自己已拥有」那一支说的**不是同一个物**。"
                "★ 这与 r1/r2 上看到的是**同一族故障**(对象粒度/错配), "
                "但那时只在 16 条手构模板上见过; 现在在真实语料上见到 %d 次。"
                % (Q.get("P2_FAIL", 0), n_sub2, Q.get("P2_FAIL", 0)),
            "★MALFORMED": "%d 张 —— span 或 object **非逐字**出自原文, 或 A 支缺 increment_kind。"
                          % Q.get("MALFORMED", 0),
            "★★★这对第一轮那个 83% 的修正": "第一轮报的 83%% 是**交卷率**, 读起来像「真实语料大多满足判别式」。"
                "加上资格层之后, **每 42 次调用只产出 %d 张机械合格的证书**(%.0f%%)。"
                "⇒ 83%% 那个数**没错, 但它不是「可用产出率」**。" % (npass, 100 * npass / n2),
        },

        "★★★ 三、代价下界: 哪个数能用, 哪个不能": {
            "★能用(纯下界, 只用交卷率)": "鉴别格 ≤ 交卷 ⇒ 买 24 格**至少**需 %.0f 次(用交卷率 CP95 上界 %.4f)。"
                % (24 / hi_s, hi_s),
            "★★★ 不得用 PASS_MECHANICAL 去收紧这个界": "很容易想当然地写「鉴别格 ≤ 合格证书」—— **那是错的**。"
                "鉴别格是**金标标注**上的格子; 一张被资格层拒掉的证书**照样可以被人标注**"
                "(r1/r2/r3 的 15 条 A 支标注就是这么来的, 其中多数并未过资格层)。"
                "⇒ 收紧那个界会**低估**代价。",
            "★另一个问题的答案(合格证书产出率)": "若要的是**能用的证书**而不是可标注的格子, "
                "那是 %d/%d = %.4f, CP95 [%.4f, %.4f] ⇒ 每张合格证书约需 %.1f 次调用。"
                % (npass, n2, npass / n2, lo_p, hi_p, n2 / npass if npass else float("inf")),
            "★借手构因子二的点算(**仍不是界**)": "24/(%.4f × %.4f) ≈ %.0f 次 —— "
                "因子二自己的 CI 从未传播进来。" % (hi_s, F2, 24 / (hi_s * F2)),
        },

        "★★★ 四、仍然没有回答的": [
            "**因子二**(每张证书里有几个鉴别格) —— 需要金标, 真实语料没有。两轮都事前声明过测不了。",
            "**验证器能不能拦住语义错误的证书** —— 机械出口只回答形式。"
            "这句话自 r2 起零证据, **两轮之后仍然零证据**。",
            "**为什么真实语料交卷率高** —— 长度混淆未消除, 机制未识别。",
            "**语料整体率** —— 两轮跑的都是含品牌子总体, 那是上界, 上界有多松没测。",
        ],
        "★预算": {"第一轮": d1["★实际执行数"], "第二轮": d2["★实际执行数"],
                  "两轮合计": d1["★实际执行数"] + d2["★实际执行数"],
                  "之前已用": 158, "累计": 158 + d1["★实际执行数"] + d2["★实际执行数"]},
    }


def main():
    if not (R1.exists() and R2.exists()):
        print("★ 缺产物", file=sys.stderr)
        return 1
    out = build(json.loads(R1.read_text(encoding="utf-8")),
                json.loads(R2.read_text(encoding="utf-8")))
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    two = _k(out, "真正的新发现")
    print("复现:", _k(out, "一、第一轮的判决复现了")["判决"], "· kappa",
          json.loads(R2.read_text(encoding="utf-8"))[
              [x for x in json.loads(R2.read_text(encoding="utf-8")) if "稳定性" in x][0]].get("kappa"))
    print("交卷", two["交卷"], "→ 过机械资格层", two["过机械资格层"])
    print("出口:", json.dumps(two["机械出口分布"], ensure_ascii=False))
    print("→", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
