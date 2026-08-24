#!/usr/bin/env python3
"""Phase 2 多 base 标定面板 —— 采集（分析另开脚本，本文件不出判决）。

## 前登记（跑前写死）
仪器: gen4 MiniMax-M3 565470cf26c16d01。**不换仪器** —— 换模型 = 换仪器 = gen5。
设计: 24 base × 7 臂(L0/L0b/A1/A2/A3/B1/B2) × R=4，每 rep = k3 stage1 + 5 stage2 = 8 调用。
context 字符串对**所有臂逐字相同** —— 否则 context 成为混杂因子。

三个 primary output，**不许压成一个 PASS**:
  ① resolution profile   T(L0,L0b) 跨 base 的分布
  ② invariance profile   T(B1) / T(B2) 的分布
  ③ perturbation profile T(A1) / T(A2) / T(A3) 的分布
再报 P[A1<A2<A3] 与 P[Ax > same-null]。

★ 禁止: 用本批数据现算一个 delta_resolution, 再拿它给**同一批** A 臂发合格证。
  「一次买两样可以; 拿其中一样给另一样现场发毕业证不可以。」

★ 两套分析集合(见 panel_manifest.analysis_sets): primary 只用盲验 FOLLOWS,
  sensitivity 用全部机器验收通过。任一 headline 判决两套不一致 ⇒ 该判决记 INDETERMINATE。

★ 停止规则: 24 个预定 base 全部 attempt 后停止。不许按 T/p/单调性提前停,
  不许替换「结果不好」的 base。coverage gate: ladder 完备 >= 20/24。

★ 限流熔断: M3 的限流形态是 **HTTP 200 + 空 content**(或 body 内 2062), 不是标准 429。
  空 body 已归 INFRA_FAILED(不进弃权/解析失败, 故不污染 U/F)。但若近窗口 INFRA 率飙高,
  继续跑只会把 5312 次调用烧成一堆 INFRA_FAILED ⇒ 主动熔断, 等冷却(历史约 3h)后续跑。
"""
import json, os, random, sys, threading, time
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_knot_classify as K   # noqa: E402

# ★ 同一套采集逻辑复用到 Phase 2B: 只切数据目录, 规则一字不改(改了两批就不可比)
P = ROOT / "tests" / "data" / os.environ.get("CCE_PHASE_DIR", "phase2")
CKPT = P / "panel_checkpoint.jsonl"
R = int(os.environ.get("P2_R", "4"))
KK = int(os.environ.get("P2_K", "3"))
WORKERS = int(os.environ.get("P2_WORKERS", "9"))   # 实测稳态 9 workers ≈ 50 calls/min
CTX = "reddit hearing discussion: 多 base 标定面板"  # ★ 所有臂逐字相同
TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))

SHUFFLE_SEED = 20260820           # 冻结: 任务顺序可复现且与臂身份无关
MAX_CALLS_PER_MIN = 45            # 实测稳态 ~50; 首轮跑到 73/min 撞限流, 留余量
INFRA_WINDOW, INFRA_TRIP = 40, 0.35    # 近 40 次里 INFRA 超半 ⇒ 熔断
_lock = threading.Lock()
_recent = deque(maxlen=INFRA_WINDOW)
_tripped = threading.Event()


def _rep(text):
    """一个 rep。与 Phase 1 同一套取数逻辑, 禁止兜底缺键。"""
    s1 = K.stage1(text, CTX, KK)
    for n in ("k_valid", "abstained", "measurement_status", "operational"):
        if n not in s1:
            raise KeyError(f"stage1 缺 {n} —— 禁止兜底")
    op = s1["operational"]
    if s1["abstained"] or s1["k_valid"] < 2:
        return {"qualified": False, "k_valid": s1["k_valid"],
                "abstained": s1["abstained"], "op": op, "knots": None}
    s2 = K.stage2(text, s1, TAXO)
    return {"qualified": True, "k_valid": s1["k_valid"], "abstained": False,
            "op": op, "knots": {x["key"]: x["intensity"] for x in s2["knots"]}}


def _done():
    if not CKPT.exists():
        return set()
    return {(r["base_id"], r["arm"], r["rep"]) for r in
            (json.loads(l) for l in CKPT.read_text(encoding="utf-8").splitlines() if l.strip())}


def main():
    man = json.loads((P / "panel_manifest.json").read_text(encoding="utf-8"))
    inst = K.instrument_id(TAXO, k=KK, knot_n=5, s1_pairing=f"round_robin_over_{KK}_s1_draws")
    assert inst["instrument_hash"] == man["measurement_instrument"]["instrument_hash"] \
        == "565470cf26c16d01", \
        f"★ 仪器不符: 现 {inst['instrument_hash']} vs 清单 {man['measurement_instrument']['instrument_hash']}"
    print(__doc__.split("## 前登记")[1].split("\n\n")[0])
    print(f"仪器 {inst['instrument_hash']}  资格协议 {inst['qualification_policy_hash']}")

    done = _done()
    tasks = [(a, i) for a in man["arms"] for i in range(R)
             if (a["base_id"], a["arm"], i) not in done]
    # ★★ 顺序必须与**被比较的因子(臂)**无关, 否则任何随时间衰减的故障
    #   (限流/服务降级/配额耗尽)会直接**做成**一个看起来很漂亮的臂间效应。
    #   2026-08-20 实测: 首轮未打散 ⇒ L0 4% vs B1 65%, 打散后 10-24% 各臂齐平
    #   ⇒ 那个"生成文本更难读"的戏剧性发现完全是顺序造成的假象。
    #
    # ★ 但**完全打散**又踩了第二个坑: 294 reps 摊在 166 个臂上, 只有 3 个臂凑够 R=4
    #   ⇒ 中断后一个 base 都分析不了。
    # ⇒ 正解: **按 base 分块随机** —— base 的顺序随机, base 内 7 臂连续跑完。
    #   臂间对比仍受时间保护(同一 base 的臂几乎同时跑, 衰减对各臂等同作用),
    #   而中断时已完成的 base 是**完整可分析**的。两个性质同时拿到。
    rng = random.Random(SHUFFLE_SEED)
    by_base = {}
    for t in tasks:
        by_base.setdefault(t[0]["base_id"], []).append(t)
    order = sorted(by_base)
    rng.shuffle(order)
    tasks = []
    for b in order:
        blk = by_base[b]
        rng.shuffle(blk)          # base 内也打散, 避免臂在块内固定次序
        tasks += blk
    print(f"臂 {len(man['arms'])} × R={R} = {len(man['arms'])*R} reps; "
          f"已完成 {len(done)}, 待办 {len(tasks)} ⇒ {len(tasks)*(KK+5)} 次调用")
    if os.environ.get("P2_DRYRUN"):
        print("[DRYRUN] 不发调用。")
        return
    n, t0 = len(tasks), time.time()
    cnt = Counter()

    _pace = {"next": time.time()}
    _min_gap = 60.0 / (MAX_CALLS_PER_MIN / (KK + 5))   # 每 rep 的最小间隔

    def run(t):
        arm, i = t
        if _tripped.is_set():
            return
        with _lock:                                   # 全局节流, 防止再撞限流
            now = time.time()
            wait = max(0.0, _pace["next"] - now)
            _pace["next"] = max(now, _pace["next"]) + _min_gap
        if wait:
            time.sleep(wait)
        try:
            r = _rep(arm["text"])
        except Exception as e:
            # ★ 绝不伪造 k_valid=0 —— 那会把 stage2 的**基础设施失败**误记成
            #   「stage1 重复不足」, 与项目既有教训同类(静默失败被算成仪器行为)。
            msg = f"{type(e).__name__}: {e}"
            stage = ("stage2" if "stage2" in msg else
                     "stage1" if "stage1" in msg else "unknown")
            r = {"qualified": False, "k_valid": None, "abstained": None,
                 "stage_failed": stage, "infra_suspected": "全部失败" in msg,
                 "op": {"error": msg[:160]}, "knots": None}
        rec = {"base_id": arm["base_id"], "arm": arm["arm"], "rep": i,
               "length_stratum": arm["length_stratum"],
               "generator_family": arm["generator_family"],
               "blind_rule_check": arm["blind_rule_check"],
               "in_primary": arm["in_primary"], **r}
        with _lock:
            with CKPT.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            cnt["done"] += 1
            cnt["qualified" if r["qualified"] else "unqualified"] += 1
            # ★ 熔断必须覆盖 stage2: stage1 有 attempt ledger, **stage2 没有** ——
            #   首轮 213 次 stage2 空返回对熔断器全程隐形, 熔断从未触发。
            infra = ((r.get("op") or {}).get("n_infra_failed", 0)
                     or r.get("infra_suspected"))
            _recent.append(1 if infra else 0)
            if len(_recent) == INFRA_WINDOW and sum(_recent) / INFRA_WINDOW > INFRA_TRIP:
                _tripped.set()
                print(f"\n★ 熔断: 近 {INFRA_WINDOW} 个 rep 中 {sum(_recent)} 个有 INFRA 失败 "
                      f"⇒ 疑似限流/配额耗尽。已落盘, 恢复后重跑本脚本自动续(按 base 分块, 已完成的 base 完整)。", flush=True)
            if cnt["done"] % 20 == 0 or cnt["done"] == n:
                el = time.time() - t0
                print(f"  [{cnt['done']}/{n}] qualified={cnt['qualified']} "
                      f"unqualified={cnt['unqualified']}  "
                      f"{cnt['done']*(KK+5)/el*60:.0f} calls/min  "
                      f"剩余约 {(n-cnt['done'])*el/max(cnt['done'],1)/60:.0f} min", flush=True)

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        list(ex.map(run, tasks))

    allrec = [json.loads(l) for l in CKPT.read_text(encoding="utf-8").splitlines() if l.strip()]
    out = P / "panel_raw.json"
    out.write_text(json.dumps({"instrument": inst["instrument_hash"],
                               "qualification_policy": inst["qualification_policy_hash"],
                               "R": R, "K": KK, "context": CTX,
                               "tripped": _tripped.is_set(),
                               "n_reps": len(allrec), "records": allrec},
                              ensure_ascii=False), encoding="utf-8")
    q = sum(1 for r in allrec if r["qualified"])
    print(f"\n落盘 {len(allrec)} reps (qualified {q}) → {out.relative_to(ROOT)}"
          + ("  ★ 本轮被熔断, 未跑完" if _tripped.is_set() else ""))


if __name__ == "__main__":
    main()
