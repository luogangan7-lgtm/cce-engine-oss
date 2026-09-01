#!/usr/bin/env python3
"""平台适配器校验的守卫 —— §48 链路第 2 段（CONTEXT），此前零测试。

## 它守的那条边界，库里有两条明文否决撑着
- 「每个 subreddit/community/profile 新建平台 adapter」——**否决**：它们是 runtime
  surface/context，不是协议边界，会造成模块爆炸。
- 「在 platform adapter 写入受众偏好/年龄/期待/信任等主体假设」——**否决**：
  会冻结动态人群并造成测量泄漏。

所以这个模块的全部职责是：**adapter 是稳定协议，surface 是带时间戳的动态值。**
把 surface 当 adapter 用，就是那两条被否决方案的具体形态。

## 为什么必须有测试
它 64 行、8 个平台，决定一份投料的 context 合不合法。零测试意味着
「subreddit 被当成 adapter id」这类回归可以静默通过。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from cce_platform_adapter import registry, validate_platform_context  # noqa: E402

REG = registry()["adapters"]
OK_TIME = "2026-09-01T10:00:00Z"


def V(platform, adapter, surface):
    return validate_platform_context(platform, adapter, surface)


# ── ① 正向对照：合法 context 必须放行，且产出 canonical ─────────────────────
spec = REG["reddit"]
good = V("reddit",
         {"id": spec["adapter_id"], "version": spec["adapter_version"]},
         {"kind": "community", "id": "r/HearingAids", "observed_at": OK_TIME})
assert good["ok"], f"★ 合法 context 被拒 —— 永远红与永远绿是同一种失效：{good['errors']}"
assert good["canonical"]["space"]["id"] == "r/HearingAids"
assert good["canonical"]["platform"]["adapter_version"] == spec["adapter_version"]

# ── ② ★ 核心边界：subreddit 不得冒充 adapter id ─────────────────────────────
bad = V("r/HearingAids",
        {"id": "r/HearingAids", "version": "1.0.0"},
        {"kind": "community", "id": "r/HearingAids", "observed_at": OK_TIME})
assert not bad["ok"], \
    ("★ 把 subreddit 当成 platform 放行了。库里明文否决：subreddit/community/profile "
     "是 runtime surface，不是协议边界；每个建 adapter 会造成模块爆炸。")

# ── ③ adapter 版本必须逐字匹配（版本漂了就是换了协议）──────────────────────
drift = V("reddit",
          {"id": spec["adapter_id"], "version": "9.9.9"},
          {"kind": "community", "id": "r/HearingAids", "observed_at": OK_TIME})
assert not drift["ok"] and any("version" in e for e in drift["errors"]), \
    "★ adapter 版本不匹配却放行 —— 版本漂移意味着协议变了，读数不可比"

# ── ④ surface.id 必须过该平台该 kind 的模式 ────────────────────────────────
malformed = V("reddit",
              {"id": spec["adapter_id"], "version": spec["adapter_version"]},
              {"kind": "community", "id": "HearingAids", "observed_at": OK_TIME})
assert not malformed["ok"], "★ 缺 `r/` 前缀的 community id 被放行"

unsupported = V("reddit",
                {"id": spec["adapter_id"], "version": spec["adapter_version"]},
                {"kind": "nonexistent_kind", "id": "x", "observed_at": OK_TIME})
assert not unsupported["ok"] and any("unsupported" in e for e in unsupported["errors"]), \
    "★ 该平台不支持的 surface kind 被放行"

# ── ⑤ observed_at 必填且须为 ISO-8601 —— surface 是**带时间的动态值** ───────
for t in (None, "", "yesterday", "2026-13-45"):
    r = V("reddit",
          {"id": spec["adapter_id"], "version": spec["adapter_version"]},
          {"kind": "community", "id": "r/HearingAids", "observed_at": t})
    assert not r["ok"], \
        (f"★ observed_at={t!r} 被放行。surface 是动态值，没有观测时间就无法判断它是否已过期 —— "
         "那正是「冻结动态人群」那条被否决方案的入口。")

# ── ⑥ 失败时不得产出 canonical（半成品比没有更危险）────────────────────────
for r in (bad, drift, malformed, unsupported):
    assert r["canonical"] is None, "★ 校验失败却产出了 canonical —— 下游会当它是合法的"
    assert r["errors"], "★ ok=False 却没给错误原因"

print(f"test_cce_platform_adapter: OK ({len(REG)} 个平台 / 合法放行 / "
      "subreddit 不得冒充 adapter / 版本逐字匹配 / surface 模式与 kind 受限 / "
      "observed_at 必填 ISO / 失败不产 canonical)")
