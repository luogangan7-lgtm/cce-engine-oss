#!/usr/bin/env python3
"""生产 suspend 缺陷的判决 —— 判据在看到读数之前写完。零 API。

★ 阳性对照**先行**: 真悬置 <2/4 ⇒ 整轮 NOT_INTERPRETABLE, 不报主结论。
★ 分析单位是**题**(上一轮伪重复的教训)。
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = pathlib.Path("/Volumes/data/cce-identified-vault/cce_runs/production_suspend_defect/raw.json")
PRE = json.loads((ROOT / "tests/data/production_suspend_defect_prereg.json").read_text(encoding="utf-8"))
FAIL = ["已决定_延后执行", "历史悬置_现已决定"]
TRUE = ["★真悬置_必须仍判"]


def main():
    rows = json.loads(RAW.read_text(encoding="utf-8"))
    got = {r["id"]: r for r in rows if r.get("top1") or r.get("abstained")}

    def cnt(cells):
        s = [r for r in got.values() if r["cell"] in cells]
        return sum(1 for r in s if r["top1"] == "suspend"), len(s), \
            sum(1 for r in s if r.get("abstained"))

    tk, tn, tab = cnt(TRUE)
    fk, fn, fab = cnt(FAIL)
    res = {
        "block": "PRODUCTION_SUSPEND_DEFECT_RESULT",
        "★prereg": "tests/data/production_suspend_defect_prereg.json",
        "★★口径": "**stage1+stage2 两段, 不是完整 CCE 链路**; 读数只取 top-1",
        "n_items_with_reading": len(got),
        "★★★阳性对照(先行)": {
            "真悬置 top1=suspend": f"{tk}/{tn}", "弃权": tab,
            "判据": ">=2/4",
            "verdict": "PASS —— 生产确实会产 suspend, 主结论可解释"
            if tk >= 2 else "★★★NOT_INTERPRETABLE —— 生产在**该判 suspend 的题上也不判**, "
                            "低命中率无法区分「没缺陷」与「从不说 suspend」。**扣发主结论。**",
        },
        "主判据P1_失败方向": {
            "题级 top1=suspend": f"{fk}/{fn}", "弃权": fab,
            "★闸的 V0 同题参照": "3/8(题级多数判) —— **并列, 不等价**: 两台仪器",
        },
        "★逐题": [{"id": r["id"], "cell": r["cell"], "top1": r["top1"],
                   "abstained": r.get("abstained"), "k_assert": r.get("★k_assert")}
                  for r in sorted(got.values(), key=lambda x: (x["cell"], x["id"]))],
        "★数量硬断言": {
            "k 被静默降级的题": [r["id"] for r in got.values()
                                if r.get("★k_assert") and r["★k_assert"] != "OK"],
        },
    }
    if tk < 2:
        res["★★★verdict"] = res["★★★阳性对照(先行)"]["verdict"]
    elif fn == 0:
        res["★★★verdict"] = "★ 失败方向无有效读数 —— 扣发"
    elif fk >= 3:
        res["★★★verdict"] = ("**HAS_DEFECT** —— 生产也有同一缺陷 ⇒ **route 6 不够**, "
                             "必须另立生产修复候选与原生验收。**不能用修好的闸替没变的生产宣告修复成功。**")
    elif fk <= 1:
        res["★★★verdict"] = ("**NO_DEFECT** —— 生产没有这个缺陷 ⇒ route 6 足够, "
                             "但结论必须写明「本修法只改闸」")
    else:
        res["★★★verdict"] = ("**UNRESOLVED**(2/8) —— 8 题在任何阈值下都分不清 p=0.2 与 p=0.5, "
                             "**不做二值判决**")
    res["★my_bet"] = {
        "赌的是": PRE["★★my_directional_bet_declared_in_advance"]["赌"][:40] + "…(HAS_DEFECT)",
        "信心": "中",
        "★结果": ("**赌对**" if fk >= 3 else "**赌错**" if fk <= 1 else "未定(UNRESOLVED)"),
    }
    res["★★限度"] = PRE["★★★what_this_still_cannot_say"]
    (ROOT / "tests/data/production_suspend_defect_result.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k not in ("★逐题", "★★限度")},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
