#!/usr/bin/env python3
"""★★★ 判据准入检查 —— **在发起任何调用之前**判定「这条判据裁得动吗」。零 API。

## 为什么
2026-09-09 花 220 次跑完一个候选实验, 才发现否决判据 R3 是**多组零容差规则**,
在一次实际的纯噪声对照里**确实会 FAIL**。⇒ 钱花了, 结论是「未建立」。

网页版 GPT-6 Pro 的裁定(本仓采纳):
「这轮真正需要打破的, 不是『没有独立噪声基线就不能研究』的循环, 而是
 **『先写一个看似严格的二值规则, 花钱后才发现它裁不了, 再靠下一轮修规则』的循环**。
 **预注册必须约束分析自由度, 但它不能替代对判据本身的验证。**」

## 本工具做三件(都不需要噪声估计)
① **离散可达性**: 把连续门槛翻译成**实际整数允许区间**, 把「文字看起来有余量、
   离散后却零容差」直接显示出来。
② **最优单侧 p**: m 个独立同向观测的最好单侧 p 是 2^-m。
   两题最好 0.25、四题最好 0.0625 ⇒ **在 α=0.05 下调用前就能判定不可达**。

③ **零基线降级必备**(2026-09-15 加): 声明了零基线臂的预注册, 必须带**逐槽位零增益**降级 ——
   r4 实测: 端到端降级响应了, 而 predicate(零增益)/possession(负增益)两格的数
   照样被当成能力读出去, **四条降级一条没响**。

★ 它**不能**替代对整个决策规则操作特性的仿真检查(GPT 的 4.2), 只是最便宜的一道。
"""
from __future__ import annotations

import json
import math
import sys


def integer_band(n: int, thr: float, direction: str) -> dict:
    """连续门槛在 n 个离散单元上的**实际整数允许区间**。"""
    ks = range(n + 1)
    if direction == "<=":
        ok = [k for k in ks if k / n <= thr + 1e-12]
    else:
        ok = [k for k in ks if k / n >= thr - 1e-12]
    return {"n": n, "阈值": f"{direction}{thr}", "允许的整数计数": ok,
            "★零容差": (len(ok) == 1),
            "★实际等价于": (f"必须恰好 {ok[0]}/{n}" if len(ok) == 1
                            else f"{min(ok)}~{max(ok)} / {n}" if ok else "**无解**")}



def paired_delta_band(n: int, delta_max: float = 0.0, flip: float = None) -> dict:
    """**配对差**判据: 「候选不得比控制差」= E_cand − E_ctrl <= delta_max。

    ★★★ 2026-09-09 修: 我第一版把这种判据建模成**绝对率门槛**(rate <= 0.0),
        于是报成「必须恰好 0/n 个错误」。**那是完全不同、严得多的要求。**
        网页版 GPT 指出: 真正的条件是**净新增 <= 0** —— 控制 5/10 时候选 4/10 **可以通过**。
        ⇒ 正确说法是「**允许的净新增错误数为零**」, 不是「必须恰好 0/n」。

    ★ 这类判据**不是**「零容差」意义上的不可能; 它的问题是**误拒率**:
      在对称噪声下, 净差为正的概率约 (1 − P(平局))/2, 多个组还会叠加。
      flip 给定时(单元级翻转率)按二项近似给出**单组误拒率**与**k 组至少一组触发**的概率。
    """
    out = {"n": n, "判据": f"净新增(E_cand − E_ctrl) <= {delta_max}",
           "允许的净新增计数": f"<= {int(delta_max * n)} / {n}",
           "★不是「必须恰好 0/n 个错误」": "控制组有多少错, 候选就允许有多少错; 只约束**差**"}
    if flip is not None:
        # 每单元以 flip 概率变动, 变好/变坏各半 ⇒ 净差 > 0 的近似概率
        from math import comb
        p_up = flip / 2.0
        p_dn = flip / 2.0
        # P(净>0): 枚举变坏数 a 与变好数 b
        pr = 0.0
        for a in range(n + 1):
            for b in range(n - a + 1):
                if a > b:
                    pr += (comb(n, a) * p_up ** a * comb(n - a, b) * p_dn ** b
                           * (1 - flip) ** (n - a - b))
        out["★单组误拒率(对称噪声近似)"] = round(pr, 4)
        out["★flip"] = flip
    return out


def best_one_sided_p(m: int) -> float:
    """m 个独立同向观测能达到的**最好**单侧 p(符号检验) = 2^-m。"""
    return 2.0 ** (-m)


def reachable_at(alpha: float, m: int) -> bool:
    return best_one_sided_p(m) <= alpha


def zero_baseline_downgrade(spec: dict) -> list[str]:
    """★★★ 2026-09-15 加的**第三道**: 声明了零基线臂的预注册, 必须带**逐槽位零增益**降级。

    ## 为什么(r4 实测逼出来的)
    r4 的三臂对照里零基线是**完全不读文本的常数填充**。端到端降级 D5 响应的是
    「模型阴性放行 == 零基线」, 但**逐个格子**没人管 —— 实测:
      · predicate  模型 18/20 == 零基线 18/20  ⇒ **零增益**
      · possession 模型 14/20 <  零基线 16/20  ⇒ **负增益**
    **四条降级一条都没响**, 而那两格的数照样进了「逐槽位准确率」表。
    ⇒ 一个与「完全不读文本」持平的格子, 被当成**能力**读了出去。

    ## 这条为什么放在准入而不是补进 r4
    测量**之后**改判据 = 调结果。所以它不回溯 r4 的读数, 而是**下一轮起**对
    「凡声明零基线臂的预注册」生效 —— 制度, 不是事后补分。
    """
    arms = json.dumps(spec.get("arms", []), ensure_ascii=False)
    body = json.dumps(spec.get("downgrades", []), ensure_ascii=False)
    structured = "零基线" in arms or "zero_baseline" in arms
    # ★★★ 2026-09-15 补(280-agent 评审抓到, 两个维度独立报到): 上面那两行**只认 arms/downgrades 两个英文键**,
    #   而本仓真实的预注册全用中文键 ⇒ **这条制度立起来的当天就是空转的**, 机器检查一次都没生效过。
    #   ⇒ 兜底: 整份预注册只要提到零基线, 就要求它带零增益条款。
    #   ★ **日期门**: 只对 2026-09-15 及之后的预注册生效 —— 「不回溯 r4 的读数」是立这条时就写死的,
    #     测量后改判据 = 调结果。没有 date 的一律视为历史件, 不触发
    #     (**这个 fail-open 是故意的**, 由 test_新预注册必须带date 把住, 不许靠不写 date 绕过)。
    whole = json.dumps(spec, ensure_ascii=False)
    date = str(spec.get("date") or "")
    fallback = (date >= "2026-09-15") and ("零基线" in whole)
    if not structured and not fallback:
        return []
    hay = body if structured else whole
    if "零基线" in hay and ("零增益" in hay or "不得读成能力" in hay):
        return []
    return ["★★★ 本预注册声明了**零基线臂**, 却没有**逐槽位零增益**降级。"
            "必须写上: 「某敏感槽位准确率 ≤ 零基线 ⇒ 该槽位**零增益**, 它的数**不得读成能力**」。"
            "★ 依据: r4 实测 —— 端到端降级响应了, 而 predicate(零增益)/possession(负增益) "
            "两格的数照样被当成能力读出去, **四条降级一条没响**。"]


def check(spec: dict) -> tuple[bool, list[str], dict]:
    """spec: {"alpha":0.05, "criteria":[{"name","n","thr","direction","kind"}]}"""
    alpha = spec.get("alpha", 0.05)
    errs, info = [], {}
    for c in spec["criteria"]:
        name, n = c["name"], c["n"]
        r = {}
        if c.get("kind") == "paired_delta":
            r = paired_delta_band(n, c.get("delta_max", 0.0), c.get("flip"))
            fr = r.get("★单组误拒率(对称噪声近似)")
            if fr is not None and fr > alpha:
                errs.append(f"★★「{name}」: 配对差判据的**单组误拒率**约 {fr:.3f} > α={alpha} "
                            f"(单元级翻转率 {c['flip']}) ⇒ 多组同时要求时会进一步叠加。"
                            f"**先校准误拒率, 再决定要不要用它当否决门槛。**")
        elif c.get("kind") == "significance":
            # ★★★ 2026-09-09 修: 必须绑定**原本的声明**。
            #   网页版 GPT 指出: 若该判据原本只是「小型开发测试中是否改善」的**描述性筛选**,
            #   就**不能事后追加「必须 p<0.05」再宣布它本来不合法** ——
            #   正确做法是**限制其结论权限**, 而不是要求所有开发测试都有确认性功效。
            #   ★ 实测: 我第一版正是这么误报的(把两条点估计比较判成「不可达」)。
            claim = c.get("claim", "confirmatory")
            p = best_one_sided_p(n)
            r = {"n": n, "最优单侧p": round(p, 5), "★声称的结论性质": claim,
                 "★在α下可达": reachable_at(alpha, n)}
            if claim != "confirmatory":
                r["★裁决"] = ("**描述性筛选, 不受可达性约束** —— 但其**结论权限受限**: "
                              "只能说「观察到改善/未观察到退化」, **不得**说「已证明」。")
            elif not r["★在α下可达"]:
                errs.append(f"★★★「{name}」: 声称**确认性**结论, 但 n={n} 时最好的单侧 p 是 "
                            f"{p:.4f} > α={alpha} ⇒ **无论结果多好都不可能显著。发起前即判定不可达。**")
        else:
            r = integer_band(n, c["thr"], c.get("direction", "<="))
            if not r["允许的整数计数"]:
                errs.append(f"★★★「{name}」: 阈值 {r['阈值']} 在 n={n} 上**无解**")
            elif r["★零容差"]:
                errs.append(f"★★「{name}」: 阈值 {r['阈值']} 在 n={n} 上**离散后是零容差** "
                            f"({r['★实际等价于']}) —— 任何一次随机波动都会触发。"
                            f"**先检查它的误拒率, 再决定要不要用它当否决门槛。**")
        info[name] = r
    errs += zero_baseline_downgrade(spec)   # ★ 预注册**结构**层的第三道, 与判据级并列
    return (not errs), errs, info


def main() -> int:
    spec = json.load(open(sys.argv[1], encoding="utf-8")) if len(sys.argv) > 1 else json.load(sys.stdin)
    ok, errs, info = check(spec)
    print("=" * 62)
    print("判据准入检查(零调用) —— 发起前判定「这条判据裁得动吗」")
    print("=" * 62)
    for k, v in info.items():
        print(f"  {k}: {json.dumps(v, ensure_ascii=False)}")
    for e in errs:
        print("  ✗ " + e)
    print("CRITERION_PREFLIGHT_PASS" if ok else "CRITERION_PREFLIGHT_FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
