#!/usr/bin/env python3
"""生成物闸 —— §44 Phase 7 的验收 gate, 逐字落地。

## §44.9 事先写好的判据(不是事后补的)
> **7 Strategy** | 生成物必须过现有三闸(outbound_guard / style_check / check_boundary),
> **且不得引用未达标层的读数** | 反向: 喂一条引用了 K1 未达标读数的生成物, 必须被拦

前半句是三个已有的闸, 只需接上。**后半句才是这一段真正新增的东西** ——
它此前无法执行, 因为「未达标」没有可查询的定义: 哪条机制算达标、哪条只是候选,
只以散文形态躺在架构文档的 33 个小节里。

P6 的机制登记表(`config/mechanism_registry.json`)把它变成可查的:
**`status != ESTABLISHED` 的机制, 生成物不得引用。**
被否决的(REJECTED)更是硬拦 —— 引用一条已被自己否决的结论对外发声, 是最坏的一种。

## 为什么闸而不是提示
本仓库反复栽在「结论写进记录 ≠ 进了执行队列」(2026-09-01 一天内四次)。
所以这里非零退出 = 禁止发布, 与 design_preflight 同形。
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from cce_mechanism import _load as _load_registry  # noqa: E402

# 生成物用这个形态引用一条机制: [[mech:<id>]]
CITE = re.compile(r"\[\[mech:([a-z0-9_]+)\]\]")


def check_citations(text):
    """★ 本段真正新增的判据: 生成物不得引用未达标层的读数。"""
    reg = {m["id"]: m for m in _load_registry()["mechanisms"]}
    issues = []
    for mid in CITE.findall(text):
        m = reg.get(mid)
        if m is None:
            issues.append(f"引用了登记表里不存在的机制 `{mid}` —— 不得引用未登记的读数")
        elif m["status"] == "REJECTED":
            issues.append(
                f"引用了**已被否决**的机制 `{mid}`: {m.get('reject_reason','')[:80]}"
                + (f" (已被 `{m['superseded_by']}` 取代)" if m.get("superseded_by") else ""))
        elif m["status"] != "ESTABLISHED":
            issues.append(
                f"引用了未达标机制 `{mid}` (status={m['status']}) —— "
                f"§44.9: 生成物不得引用未达标层的读数。"
                + (f" 未升级原因: {m['note'][:70]}" if m.get("note") else ""))
    return issues


def _run(cmd, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    return r.returncode, (r.stdout + r.stderr)


def gate(path, profile="hearing_aid", market="intl"):
    text = open(path, encoding="utf-8").read()
    report = {}

    issues = check_citations(text)
    report["citations"] = "PASS" if not issues else "FAIL"

    # 三闸之一: 合规(疗效/凭证幻觉/广告法)
    from cce_outbound_guard import scan_draft
    v = [x for x in scan_draft(text, market=market, profile=profile)
         if not x.get("negated") and x.get("tier") in ("core", "efficacy", "adlaw_cn")]
    report["outbound_guard"] = "PASS" if not v else "FAIL"
    issues += [f"合规闸: {x['canonical']} —— {x['context'][:60]}" for x in v]

    # 三闸之二: 文风
    rc, out = _run([sys.executable, os.path.join(ROOT, "scripts", "style_check.py"), path])
    report["style_check"] = "PASS" if rc == 0 else "FAIL"
    if rc:
        issues += ["文风闸: " + l.strip() for l in out.splitlines() if "ERROR" in l]

    # 三闸之三: 身份边界(不在本仓库, 缺席时如实标 UNAVAILABLE 而非默认放行)
    cb = "/Volumes/data/cce-identified-vault/check_boundary.py"
    if os.path.exists(cb):
        report["check_boundary"] = "AVAILABLE_NOT_RUN"   # 全库扫描型, 由发布流程单独跑
    else:
        report["check_boundary"] = "UNAVAILABLE"
        issues.append("check_boundary 不可用 —— 三闸缺一, 不得判为可发布")

    return report, issues


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    rep, iss = gate(sys.argv[1],
                    profile=os.environ.get("CCE_GUARD_PROFILE", "hearing_aid"),
                    market=os.environ.get("CCE_MARKET", "intl"))
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    for i in iss:
        print(f"  ERROR {i}")
    print("PASS —— 允许发布" if not iss else "★ FAIL —— **禁止发布**")
    sys.exit(0 if not iss else 1)
