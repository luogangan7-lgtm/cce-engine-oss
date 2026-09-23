#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨轮请求预算闸 —— DEV-001 暴露的机制缺口的修补。

★★★ 补这个闸**不等于**恢复放行(web GPT 第八轮):
  「**允许**离线修补、评审和使用**假请求**测试限额代码; **不允许**因此恢复任何真实请求, 也不回写原授权。
   真正不能做的是: **重置已用计数 · 改大旧上限 · 回填授权日期 · 宣布『代码补好了所以可以继续』**。」

★ GPT 定的实现要求, 逐条对应本文件:
  ① 在**共同的出站路径**上执行      → wrap() 包住真正发请求的函数
  ② **计数持久化**                → _STATE 落盘 JSON, 重启不清零
  ③ **并发原子预留**              → reserve() 先占后用, fcntl 排他锁
  ④ **重试同样经过该路径**        → 包在最内层, 重试必然重新计数
  ⑤ **已发出的失败请求不能抹掉**  → 记的是「已发出」, 与是否拿到有效结果无关
"""
import fcntl, json, os, pathlib, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE = pathlib.Path(os.environ.get("CCE_BUDGET_STATE", ROOT / "results" / ".request_budget.json"))


class BudgetExceeded(RuntimeError):
    """★ 撞上限 —— **抛异常**, 不静默降级、不裁尾、不「跑完再说」。"""


def _load(fh):
    fh.seek(0)
    raw = fh.read().strip()
    return json.loads(raw) if raw else {"authorizations": {}}


def _save(fh, d):
    fh.seek(0); fh.truncate()
    json.dump(d, fh, ensure_ascii=False, indent=1); fh.flush(); os.fsync(fh.fileno())


def reserve(auth_id, limit, n=1, note=""):
    """★ **先占后用** —— 在发请求**之前**原子地扣额度。
    返回扣完后的已用数。撞上限抛 BudgetExceeded, **且不扣**。

    ★ auth_id = **授权单**的标识, 不是轮次标识 —— 跨轮共用同一个 auth_id 才拦得住跨轮超支。
    """
    STATE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE, "a+", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)                    # ③ 并发原子
        try:
            d = _load(fh)
            a = d["authorizations"].setdefault(auth_id, {"limit": limit, "used": 0, "log": []})
            if a["limit"] != limit:
                raise BudgetExceeded(
                    f"★★★ 授权 {auth_id} 的上限从 {a['limit']} 变成了 {limit} —— "
                    f"**改大旧上限是 GPT 明令禁止的四件事之一**。要改上限必须**新开一张授权单**。")
            if a["used"] + n > a["limit"]:
                raise BudgetExceeded(
                    f"★★★ 授权 {auth_id} 撞上限: 已用 {a['used']} + 本次 {n} > {a['limit']} —— "
                    f"**立即停, 不追加**。要继续需**新的授权单**, 补闸不等于恢复放行。")
            a["used"] += n
            a["log"].append({"n": n, "used_after": a["used"], "note": note})
            _save(fh, d)
            return a["used"]
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def wrap(fn, auth_id, limit, note=""):
    """① 包住**真正发请求**的函数。④ 重试走同一条路 ⇒ 必然重新计数。
    ⑤ 记的是「**已发出**」—— 先 reserve 再调用, 调用抛异常也**不退还**。"""
    def wrapped(*a, **kw):
        reserve(auth_id, limit, 1, note)
        return fn(*a, **kw)
    return wrapped


def status(auth_id=None):
    if not STATE.exists():
        return {"authorizations": {}}
    d = json.loads(STATE.read_text(encoding="utf-8") or '{"authorizations":{}}')
    return d["authorizations"].get(auth_id, None) if auth_id else d


def _mp_worker(path, q):
    """★ 必须是模块级函数 —— spawn 启动方式要求可 pickle。"""
    global STATE
    STATE = pathlib.Path(path)
    ok = 0
    for _ in range(20):
        try:
            reserve("C", 10, 1, "mp"); ok += 1
        except BudgetExceeded:
            pass
    q.put(ok)


# ────────────────────────── 离线自检(假请求, 零真实调用) ──────────────────────────
def selftest():
    """★ GPT 要求的三条离线验证 + 两条我加的。**全用假请求**, 一次真实调用都不发。"""
    import multiprocessing as mp, tempfile, shutil
    tmp = pathlib.Path(tempfile.mkdtemp())
    global STATE
    keep, STATE = STATE, tmp / "b.json"
    out = {}
    try:
        calls = {"n": 0}
        fake = wrap(lambda: calls.__setitem__("n", calls["n"] + 1), "T", 3, "fake")

        fake(); fake(); fake()
        out["①到达上限前放行"] = (calls["n"] == 3)

        # ★ GPT 要求1: 到达上限后的**重试**被拦
        try:
            fake(); out["②到达上限后被拦"] = False
        except BudgetExceeded:
            out["②到达上限后被拦"] = True
        out["★被拦时未产生调用"] = (calls["n"] == 3)

        # ★ GPT 要求2: **重启不会清零**
        STATE_before = json.loads(STATE.read_text(encoding="utf-8"))
        out["③重启不清零"] = (STATE_before["authorizations"]["T"]["used"] == 3)

        # ★ GPT 要求3: 多进程并发不各算各的
        q = mp.Queue()
        ps = [mp.Process(target=_mp_worker, args=(str(STATE), q)) for _ in range(4)]
        [p.start() for p in ps]; granted = sum(q.get() for _ in ps); [p.join() for p in ps]
        out["④并发总放行数不超上限"] = (granted == 10)
        out["★并发实际放行"] = granted

        # ★ 我加的: **失败的请求也计数**(不因无有效结果而抹掉)
        boom = wrap(lambda: (_ for _ in ()).throw(RuntimeError("api down")), "F", 2, "fail")
        for _ in range(2):
            try: boom()
            except RuntimeError: pass
        out["⑤失败请求仍计数"] = (status("F")["used"] == 2)

        # ★ 我加的: **改大旧上限**要被拒
        try:
            reserve("T", 999, 1, "sneak"); out["⑥改大旧上限被拒"] = False
        except BudgetExceeded as e:
            out["⑥改大旧上限被拒"] = "改大旧上限" in str(e)
    finally:
        STATE = keep
        shutil.rmtree(tmp, ignore_errors=True)
    return out


if __name__ == "__main__":
    r = selftest()
    print(json.dumps({
        "block": "REQUEST_BUDGET_SELFTEST",
        "★zero_api": "**全部用假请求**, 一次真实调用都不发。",
        "★★★补这个闸不等于恢复放行": "GPT 第八轮: 允许离线修补+假请求测试; **不允许**恢复真实请求或回写原授权。"
                          "禁止的四件事: **重置已用计数 · 改大旧上限 · 回填授权日期 · 宣布代码补好了所以可以继续**。",
        "结果": r, "全过": all(v is True for k, v in r.items() if not k.startswith("★并发实际")),
        "★仍需 owner 的": "**新的轮次授权** —— 本闸只保证下次不会静默超支, **不产生任何放行资格**。",
    }, ensure_ascii=False, indent=1))
