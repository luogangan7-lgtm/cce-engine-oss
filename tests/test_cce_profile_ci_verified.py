#!/usr/bin/env python3
"""各 profile 的 CI 验证状态 —— 由**归档的真实 run** 算出来, 不是我说的。

## 为什么要有它
2026-09-03 owner 问「生产端没问题了吗」。当时我只验过 1/4 个 profile,
却差点笼统答「没问题」。而 §44.9 立过硬规则:
**禁用裸的「完整/全链路」字样, 必须给逐项清单(组件 + 跑/没跑 + 文件路径)。**
⇒ 把「哪个 profile 验过」变成从 archive/ 现算的事实。

## 顺带钉住一条由生产实跑证实的结论
**可用读数按 profile 不同**: outbound_post(k=5)是仪器 0e9ca1d4e7a2f180,
K1 标定不在其上 ⇒ 结层零可用; reply(k=3)是 565470cf26c16d01(=K1 那台) ⇒ top-1 可用。
"""
import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODAY = "2026-09-03"

by_profile = {}
for f in glob.glob(os.path.join(ROOT, "archive", "*", "*normalized.json")):
    rid = os.path.basename(os.path.dirname(f))
    try:
        d = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    by_profile.setdefault(d.get("profile"), []).append(rid)

CONTRACT = json.load(open(os.path.join(ROOT, "config/cce_submission_contract_v1.json"),
                          encoding="utf-8"))
# 今天(当前代码)验过的三档
for p in ("media_ingest", "outbound_post", "outbound_reply"):
    rs = by_profile.get(p) or []
    assert rs, f"★ profile {p} 归档里没有成功 run —— 它**没有**被 CI 验证过"
    # ★ 不用「run_id 数值阈值」做比较 —— 那种常量长得就是 run_id 形状,
    #   归档闸会把它当成未入册的引用(实际发生过)。改用归档里记的日期。
    _m = json.load(open(os.path.join(ROOT, "archive", max(rs), "manifest.json"),
                        encoding="utf-8"))
    assert _m["recovered_at"] == TODAY, \
        f"★ profile {p} 最近的 run 是 {_m['recovered_at']} 落的 —— 当前代码未验证"

# ★ subject_chain 仍未验证, 必须如实标着, 不许悄悄当验过
assert not by_profile.get("subject_chain"), \
    "★ subject_chain 有归档了 —— 那就把本断言改成正向, 别让它继续说「未验」"

# ── ★ 由真实产物钉住「可用读数按 profile 不同」 ───────────────────────
def usable_of(rid):
    f = glob.glob(os.path.join(ROOT, "archive", rid, "*item*manifest.json"))
    m = json.load(open(f[0], encoding="utf-8"))
    q = m["stages"]["qualified_readout"]
    return q["instrument_hash"], set(q["usable_keys"])

ih_post, u_post = usable_of("33745544418")     # outbound_post, k=5
ih_reply, u_reply = usable_of("33746399209")   # outbound_reply, k=3
assert ih_post != ih_reply, "★ 两档若成了同一台仪器, 本节结论要重写"
assert ih_reply == "565470cf26c16d01", f"★ reply 应跑 K1 那台仪器, 实测 {ih_reply}"
assert not any(k.startswith("s2.distribution") for k in u_post), \
    f"★ outbound_post 的结层竟有可用读数 {u_post} —— K1 标定不在那台仪器上"
assert "s2.distribution.top1" in u_reply, \
    f"★ reply 档的 top-1 应可用(K1 8/8), 实测 usable={u_reply}"
# 两档都不得放行强度层
for u in (u_post, u_reply):
    assert not any("intensity" in k or "weight" in k for k in u), u

print("test_cce_profile_ci_verified: OK "
      f"(已 CI 验证: media_ingest · outbound_post · outbound_reply; "
      f"**subject_chain 仍未验证** | "
      f"实证「可用读数按 profile 不同」: post({ih_post[:8]}) 结层零可用 vs "
      f"reply({ih_reply[:8]}) top-1 可用 | 两档均不放行强度层)")
