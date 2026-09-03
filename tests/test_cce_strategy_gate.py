#!/usr/bin/env python3
"""生成物闸的守卫 —— §44 Phase 7 的验收 gate。

## §44.9 事先写好的判据
> **7 Strategy** | 生成物必须过现有三闸（outbound_guard / style_check / check_boundary），
> **且不得引用未达标层的读数** | 反向：喂一条引用了 K1 未达标读数的生成物，必须被拦

前半句是接三个已有的闸。**后半句是这一段真正新增的**：它此前无法执行，因为「未达标」
没有可查询的定义 —— 哪条机制算达标只以散文形态躺在架构文档的 33 个小节里。
P6 的机制登记表把它变成可查的：`status != ESTABLISHED` 就不许被引用。

## 为什么 REJECTED 要单独报
引用一条**已被自己否决**的结论对外发声，是最坏的一种 —— 那不是「证据不够」，
是「我们自己已经知道它是错的」。所以它的报错要带 reject_reason 与取代者。
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from cce_strategy_gate import check_citations, gate  # noqa: E402

T = ROOT / "tests" / "data" / "strategy_gate"


def run(name):
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "cce_strategy_gate.py"),
                        str(T / f"{name}.txt")], capture_output=True, text=True)
    return r.returncode, r.stdout


# ── ① §44.9 的反向测试，逐字执行 ────────────────────────────────────────────
rc, out = run("cites_unestablished")
assert rc != 0, "★ 引用未达标读数的生成物被放行 —— §44.9 的反向测试原文正是这一条"
assert "未达标机制" in out and "status=TESTED" in out, \
    f"★ 拦下了但没说清为什么。报错必须指名机制与它的 status：\n{out}"

# ── ② 引用已被否决的结论：最坏的一种，必须带理由与取代者 ────────────────────
rc, out = run("cites_rejected")
assert rc != 0, "★ 引用已被否决的机制被放行"
assert "已被否决" in out and "取代" in out, \
    ("★ 拦下了但没给 reject_reason / superseded_by。"
     "引用已否决结论时，作者最需要知道的是「那该引哪条」。")

# ── ③ 引用未登记的机制 ─────────────────────────────────────────────────────
assert run("cites_unknown")[0] != 0, "★ 引用登记表里不存在的机制被放行"

# ── ④ 正向对照：引用已确立的机制且其余合规 ──────────────────────────────────
# ★ 2026-09-03 CI 实跑暴露的结构性事实：**三闸之一 check_boundary 故意只在本地**
#   (它持有识别层, 绝不能进 CI)。于是在 CI 上「可发布」这个判决**结构上无法验证** ——
#   闸会如实判 UNAVAILABLE → 三闸缺一 → 不得判为可发布。这是闸对的行为, 不是 bug。
#   ⇒ 本条按环境分档断言, 各自断言**该环境下正确的那个结果**;
#     绝不因为在 CI 上过不了就把它改成「取不到就跳过」——
#     那是本项目记过的「环境降级下断言静默变成恒真」。
_CB = os.path.exists("/Volumes/data/cce-identified-vault/check_boundary.py")
rc, out = run("cites_established")
if _CB:
    assert rc == 0, \
        (f"★ 合规生成物被误拦 —— 永远红与永远绿是同一种失效。输出：\n{out}")
    _PATH = "本地(三闸齐全): 已验证**可发布**这条路"
else:
    assert rc != 0 and "check_boundary 不可用" in out, \
        ("★ 缺 check_boundary 时必须拒判可发布 —— 缺席不得默认放行。"
         f"输出：\n{out}")
    _PATH = "CI(无识别层保险库): 只验证了**拒判**这条路; 「可发布」判决在此结构上不可验证"

# ── ⑤ 另两闸必须各自独立生效（不能只有引用闸在干活）────────────────────────
rc, out = run("violates_compliance")
assert rc != 0 and '"outbound_guard": "FAIL"' in out, \
    f"★ 疗效宣称/凭证幻觉未被合规闸拦下：\n{out}"
assert '"citations": "PASS"' in out, "★ 该样本不引用任何机制，引用闸不该报错"

rc, out = run("violates_style")
assert rc != 0 and '"style_check": "FAIL"' in out, \
    f"★ 大纲标签句未被文风闸拦下：\n{out}"

# ── ⑥ 三闸缺一不得判为可发布 ───────────────────────────────────────────────
rep, _ = gate(T / "cites_established.txt")
assert rep["check_boundary"] != "PASS", \
    ("★ check_boundary 是全库扫描型、由发布流程单独跑，本闸不得替它判 PASS。"
     "缺席时必须如实标 UNAVAILABLE/AVAILABLE_NOT_RUN，而不是默认放行。")
# 2026-09-01: 加入 knot_readout_claims —— K1 首次真实判定(FAIL)后, §44.9 P7 那条
# 「不得引用未达标层的读数」终于可执行: 强度层引用被拦, 首结层放行(见 test_cce_k1_verdict)。
assert set(rep) == {"citations", "knot_readout_claims",
                    "outbound_guard", "style_check", "check_boundary"}, \
    f"★ 报告分项与 §44.9 的三闸+引用不一致：{sorted(rep)}"

# ── ⑦ 引用检查是纯函数，可脱离文件直接测 ───────────────────────────────────
assert not check_citations("no citations here"), "★ 无引用的文本不该报错"
assert check_citations("see [[mech:length_threshold_1500]]"), "★ 已否决机制未被抓到"

print("test_cce_strategy_gate: OK (未达标/已否决/未登记 三种引用全拦 · 合规样本放行 · "
      "合规闸与文风闸各自独立生效 · check_boundary 缺席不冒充 PASS)")
print(f"  ★ 本次覆盖: {_PATH}")
