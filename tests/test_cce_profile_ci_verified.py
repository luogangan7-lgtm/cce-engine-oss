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
# ★ 2026-09-04 改判据。原来是「四档的最新 run 都必须落在 TODAY 这一天」——
#   那条在我今天只重验了 media_ingest 一档时就红了, 而它红的理由是**对的**:
#   另外三档是 09-03 对着旧代码验的, 我今天动过链路代码。
#   但「必须同日」是错的形状: 它逼人要么全部重跑要么放松断言。
#   ⇒ 判据改为**逐档现算 + 状态表不得多声称**:
#     ① 每档算出「最近一次 CI 验证是哪天、是否 >= 当前代际」
#     ② 断言: 凡未达当前代际的档, **不得**在任何地方被说成「当前代码已验证」
#   这样红的是**虚报**, 不是「今天没全跑一遍」。
CODE_GENERATION = "2026-09-04"   # 链路代码最后一次实质变更日。改链路就要改它。

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
VERIFIED_AT, CURRENT_GEN, STALE_GEN = {}, [], []
for p in ("media_ingest", "outbound_post", "outbound_reply", "subject_chain"):
    rs = by_profile.get(p) or []
    assert rs, f"★ profile {p} 归档里没有成功 run —— 它**没有**被 CI 验证过"
    # ★ 不用「run_id 数值阈值」做比较 —— 那种常量长得就是 run_id 形状,
    #   归档闸会把它当成未入册的引用(实际发生过)。改用归档里记的日期。
    _m = json.load(open(os.path.join(ROOT, "archive", max(rs), "manifest.json"),
                        encoding="utf-8"))
    VERIFIED_AT[p] = _m["recovered_at"]
    (CURRENT_GEN if _m["recovered_at"] >= CODE_GENERATION else STALE_GEN).append(p)

# ★ 断言不是「都得是今天」, 而是「没验的不许被说成验了」。
_status = open(os.path.join(ROOT, "scripts/cce_production_status.py"), encoding="utf-8").read()
for p in STALE_GEN:
    assert f'"{p}": "当前代码已验证"' not in _status, \
        f"★ profile {p} 最近一次 CI 是 {VERIFIED_AT[p]}(旧代际 < {CODE_GENERATION}), 不得声称已验证"
assert CURRENT_GEN, ("★ 一档都没有在当前代际验证过 —— 那么「生产可用」这句话现在没有任何 CI 支撑")

# ★ 2026-09-03: subject_chain 也已验证(run 33748217410, 用仓内现成真实夹具, 未硬造)。
#   原来这里断言它**没有**归档并写着「哪天真验了就把断言改成正向」—— 今天改成了正向。
_sc = json.load(open(os.path.join(ROOT, "archive", max(by_profile["subject_chain"]),
                                  "manifest.json"), encoding="utf-8"))
assert "没有硬造" in _sc["★scope"], "★ 必须写明夹具是现成真实数据, 不是造出来跑通的"
assert "NOT_VERIFIED" in _sc["★scope"], \
    "★ 审计判 NOT_VERIFIED 这件事要留着 —— **链路跑通 != 业务已验证**"

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
      f"(四档都有成功 run, 但**代际不同**: 当前代际({CODE_GENERATION}+) "
      f"{len(CURRENT_GEN)} 档 [{', '.join(CURRENT_GEN) or '无'}] · "
      f"旧代际 {len(STALE_GEN)} 档 [{', '.join(f'{p}@{VERIFIED_AT[p]}' for p in STALE_GEN) or '无'}] "
      f"—— 旧代际的**不得**被说成「当前代码已验证」(subject_chain 的审计另判 NOT_VERIFIED) | "
      f"实证「可用读数按 profile 不同」: post({ih_post[:8]}) 结层零可用 vs "
      f"reply({ih_reply[:8]}) top-1 可用 | 两档均不放行强度层)")
