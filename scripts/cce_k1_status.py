#!/usr/bin/env python3
"""K1 判定的**单一真相源** —— 哪一层读数允许进入下游。

## 为什么需要它
2026-09-02 发现系统内部自相矛盾:
  · 出站闸(cce_strategy_gate)按 K1 判定**硬拦** [[knot_intensity:]] 的引用
  · 而 cce_full_run.usable_readouts 把 s2.distribution 里的 intensity
    **无条件**放进 usable —— usable 的定义是「允许进入下游/Population Field」
    「只有 usable 里的东西允许被引用」
同一份读数, 一条路上被拦、另一条路上宣布可引用。

它靠的是一句散文 caveat:「必须带 n 与不确定性一起引用」。
而本项目已确立: **散文式 caveat 在这个项目已被证伪**
(13 条 Notion 读数都标了「不可单独使用」, 照样被当读数引用)。
所以改成由判定驱动的**路由**, 不是再加一句话。

## 分层, 不是一刀切
K1 的判定本身是分层的: top-1 一致 8/8 达标, 逐对容差一致 A(0.1) 不达标。
所以 top-1 层可用、强度层不可用 —— 这正是铁律 24 要求分离的两件事。

## 缺判定 != 判定通过
找不到判定文件时一律扣发。这条规则与出站闸一致。

## ★ 标定不可跨仪器搬 —— 缺仪器标识 != 仪器相同
K1 判定是在**某一台**仪器上做的(产物里记着 instrument_hash)。
gen2→gen3 已确立: prompt 变了 ⇒ 标定不可搬, 必须重标定。
所以路由必须比对本次运行的仪器与判定所属仪器:
  · 不同  -> 两层都扣发(这台仪器没有 K1 判定, 不是「判定通过」)
  · 缺失  -> 同样扣发。**缺指纹 != 指纹相同** —— 与 K1 闸自己那条教训同源
            (8 份 manifest 全缺 text_sha256 时 {None} 长度也是 1, 曾打印「指纹唯一 ✅」)。
"""
from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
K1_VERDICT = os.path.join(ROOT, "tests", "data", "phase2", "k1_reliability_verdict.json")
# v2 多文本判定(5 文本 × n=8)。intensity 与 weight 同批判, 决策规则在预注册里冻结。
K1_V2_VERDICT = os.path.join(ROOT, "tests", "data", "phase2", "k1_v2_multitext_verdict.json")

# 判据名 -> 它管的是哪一层
INTENSITY_CRITERION = "逐对容差一致"
TOP1_CRITERION = "top-1 一致"


def _load(path=None):
    # ★ 路径在**调用时**解析, 不用默认参数绑定 —— 默认参数在 def 时就固定了,
    #   测试改不动它, 于是「换一份判定验证闸会跟着变」这类反向测试根本跑不了。
    path = path or K1_VERDICT
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _criterion(v, needle):
    for c in v.get("checks", []):
        if needle in c["name"]:
            return c
    return None


def layer_status(path=None, instrument_hash=None):
    """返回 {层: {"usable": bool, "reason": str}}。

    instrument_hash: **本次运行**的仪器。必须传 —— 缺它一律扣发。
    """
    path = path or K1_VERDICT
    v = _load(path)
    if v is None:
        miss = {"usable": False,
                "reason": "缺 K1 判定 —— **缺判定不等于判定通过**, 一律扣发"}
        return {"intensity": dict(miss), "top1": dict(miss)}

    # ★ 标定不可跨仪器搬
    verdict_inst = v.get("instrument_hash")
    if not instrument_hash:
        miss = {"usable": False,
                "reason": ("本次运行未提供 instrument_hash —— **缺仪器标识不等于仪器相同**, "
                           f"无从判断 K1 判定(在 {verdict_inst} 上做的)是否适用, 一律扣发")}
        return {"intensity": dict(miss), "top1": dict(miss)}
    if instrument_hash != verdict_inst:
        miss = {"usable": False,
                "reason": (f"K1 判定是在仪器 {verdict_inst} 上做的, 本次是 {instrument_hash} —— "
                           "**标定不可跨仪器搬**(gen2→gen3 已确立), 这台仪器没有 K1 判定, "
                           "不是「判定通过」")}
        return {"intensity": dict(miss), "top1": dict(miss)}

    out = {}
    for layer, needle in (("intensity", INTENSITY_CRITERION), ("top1", TOP1_CRITERION)):
        c = _criterion(v, needle)
        if c is None:
            out[layer] = {"usable": False,
                          "reason": f"K1 判定里找不到「{needle}」这一项 —— 判据变了却没更新路由"}
        elif c["pass"]:
            out[layer] = {"usable": True,
                          "reason": f"K1「{c['name']}」达标: {c['value']}"}
        else:
            out[layer] = {"usable": False,
                          "reason": f"K1「{c['name']}」不达标: {c['value']} "
                                    f"(判定 {v.get('verdict')}, 见 {os.path.relpath(path, ROOT)})"}
    return out


# 结层可用读数形式的**白名单**。默认拒发 —— 加进来必须有预注册判定, 不是探索性观察。
# 2026-09-03 探索性实测(probes/k1_readout_forms.py, 零调用, 5 文本 × 28 对):
#     cardinal 0.712 / band3 0.726 / rank_rho 0.856 / top2_set 0.814 / **top1 1.000**
# ★ 粗档几乎救不回来(0.712 -> 0.726) —— 这是最显然的一条逃生路, 已实测堵死。
#   连 top-2 集合都只有 0.814(最差文本 0.536)。可复现的信号**恰好只有 top-1**。
KNOT_READOUT_ALLOWLIST = {"top1"}
KNOT_READOUT_EXCLUDED = {
    "intensity": "K1 预注册判定 0/5 文本(v1 同文本上复现)",
    "weight": "K1-v2 预注册判定 0/5 文本",
    "band3": "探索性 0.726(最差 0.661) —— 粗档不是逃生路, 别再花钱试",
    "rank_rho": "探索性 0.856(最差 0.732) —— 比基数好但离 0.95 仍远",
    "top2_set": "探索性 0.814(最差 0.536) —— 一出 top-1 就崩",
}


def knot_readout_usable(form: str, instrument_hash=None):
    """结层的**任何**读数形式都走这里。白名单之外一律拒发。

    ★ 默认拒发的方向性: 关门不需要预注册(安全方向), 开门需要 ——
      要把某个 form 加进白名单, 必须有在**新一批文本**上的预注册判定,
      不能拿 probes/k1_readout_forms.py 那份探索性数据当依据(它是看完 v2 结果之后才做的)。
    """
    if form in KNOT_READOUT_ALLOWLIST:
        if form == "top1":
            return top1_usable(instrument_hash=instrument_hash)
        return True, f"{form} 在白名单内"
    why = KNOT_READOUT_EXCLUDED.get(form, "不在白名单内 —— 缺预注册判定不等于可用")
    return False, f"结层读数形式 {form!r} 不可用: {why}"


def playbook_hit_usable(path=None, instrument_hash=None):
    """top-1 的 playbook_hit 是否可用 —— 由预注册判定决定。

    ★ 2026-09-03 判定 UNRELIABLE(4/8 文本达标)。失败的形状是关键:
      稳在地板(中位 0.0)或天花板(1.0)时极差为 0, **中间地带极差 0.3–0.7** ——
      它只在答案明显时稳, 而阈值判决恰恰住在中间。**在需要它的地方它不可靠。**
      非退化闸过了 ⇒ 不是「什么都没测」, 是「测到了但不稳」。
    """
    path = path or os.path.join(ROOT, "tests", "data", "phase2", "playbook_hit_verdict.json")
    if not os.path.exists(path):
        return False, "无 playbook_hit 判定 —— 缺判定不等于可用"
    v = json.load(open(path, encoding="utf-8"))
    if not instrument_hash:
        return False, "本次运行未提供 instrument_hash —— 缺仪器标识不等于仪器相同"
    if instrument_hash != v.get("instrument_hash"):
        return False, (f"判定在仪器 {v.get('instrument_hash')} 上做的, 本次是 {instrument_hash}"
                       " —— 标定不可跨仪器搬")
    if v.get("decision") == "USABLE":
        return True, f"playbook_hit 达标 {v['meeting_criterion']}/{v['texts']} 文本且非退化"
    return False, (f"playbook_hit 判定 {v['decision']}: 仅 {v['meeting_criterion']}/{v['texts']} "
                   "文本达标; 且它只在答案明显时稳, **中间地带不稳** —— 阈值判决正住在中间。")


def playbook_mode_usable(path=None, instrument_hash=None):
    """playbook 的**众数占比**形式是否可用 —— 由预注册判定决定。

    ★ 2026-09-03 判定 INCONCLUSIVE(达标 6/8, 需 7/8)。
      改读数形式(标量 → 分布摘要)确实把达标从 4/8 提到 6/8, 非退化也变好,
      **但没到预注册的线**。差一个也是差 —— 不得采纳, 更不得事后下调阈值或合并两轮凑数。
    """
    path = path or os.path.join(ROOT, "tests", "data", "phase2", "playbook_mode_verdict.json")
    if not os.path.exists(path):
        return False, "无 playbook_mode 判定 —— 缺判定不等于可用"
    v = json.load(open(path, encoding="utf-8"))
    if not instrument_hash:
        return False, "本次运行未提供 instrument_hash —— 缺仪器标识不等于仪器相同"
    if instrument_hash != v.get("instrument_hash"):
        return False, f"判定在仪器 {v.get('instrument_hash')} 上做的, 本次是 {instrument_hash}"
    if v.get("decision") == "USABLE":
        return True, f"达标 {v['meeting_criterion']}/{v['texts']} 且非退化"
    return False, (f"playbook_mode 判定 {v['decision']}: 达标 {v['meeting_criterion']}/{v['texts']}"
                   f"(需 {v['required']})。改形式有改善(旧判据 4/8 → 新判据 6/8)但**未到线**; "
                   "对齐线保持关闭。")


def weight_usable(path=None, instrument_hash=None):
    """weight 层是否可用 —— 由 v2 多文本判定决定, 不由单文本观察决定。

    ★ 为什么必须有这个函数: 上一轮派生层探针在**单个文本**上观察到
      weight(0.9111–1.0) 比 intensity(0.7333–1.0) 稳, 很容易被读成「换成 weight 就行」。
      v2 按预注册判据在 5 个文本上判: **weight 也是 0/5**。
      不把这个结论接进路由, 下一个人还会照那句单文本观察去换层。
    """
    path = path or K1_V2_VERDICT
    if not os.path.exists(path):
        return False, "无 v2 多文本判定 —— 缺判定不等于可用"
    v = json.load(open(path, encoding="utf-8"))
    if instrument_hash and instrument_hash != v.get("instrument_hash"):
        return False, (f"v2 判定在仪器 {v.get('instrument_hash')} 上做的, 本次是 {instrument_hash} "
                       "—— 标定不可跨仪器搬")
    if not instrument_hash:
        return False, "本次运行未提供 instrument_hash —— 缺仪器标识不等于仪器相同"
    L = (v.get("layers") or {}).get("weight") or {}
    passed, of = L.get("passed_texts"), L.get("of")
    if passed is None:
        return False, "v2 判定里没有 weight 层 —— 判据变了却没更新路由"
    need = (of or 0) - 1
    if passed >= need and (L.get("degeneracy") or {}).get("passes"):
        return True, f"weight 过 {passed}/{of} 文本且非退化"
    return False, (f"weight 过 {passed}/{of} 文本(需 >= {need}) —— 判定 {v.get('decision')}。"
                   "★ 上轮单文本上 weight 看着比 intensity 稳, 那是单文本观察, "
                   "过不了预注册判据。")


def intensity_usable(path=None, instrument_hash=None):
    s = layer_status(path, instrument_hash)["intensity"]
    return s["usable"], s["reason"]


def top1_usable(path=None, instrument_hash=None):
    s = layer_status(path, instrument_hash)["top1"]
    return s["usable"], s["reason"]


if __name__ == "__main__":
    import sys
    _v = _load() or {}
    st = layer_status(instrument_hash=_v.get("instrument_hash"))
    print(f"(按判定自带的仪器 {_v.get('instrument_hash')} 演示; 生产必须传本次运行的仪器)")
    for k, v in st.items():
        print(f"{'✓' if v['usable'] else '✗'} {k:<10} {v['reason']}")
    sys.exit(0)
