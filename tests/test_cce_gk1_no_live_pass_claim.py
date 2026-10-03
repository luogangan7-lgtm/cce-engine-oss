#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闸: 现行状态字段里不许再出现无保留的 G-K1「通过 / 达标 / PASS / ✅」。零 API。

★ 由来(2026-10-03 owner「2和3都做吧」③): v2 时期(2026-09-07 资格考生效后重跑、2026-09-09 闸协议 v2
  启用验收)的那句「通过」在现行状态里改述为「未建立稳健通过证据」。依据由本闸**现读核对**, 不信手抄:
  · tests/data/gk1_fail_diagnosis_2026-10-03.json —— 同一闸协议 v2 两次运行一过一不过, 配对差区间含 0,
    条目聚类自助上界两次都越 0.25
  · tests/data/gk1_v3_result.json —— v3(R=4, 交叉自助单侧 95%)推理型四人 UNRESOLVED、含 Text-01 五人 FAIL
  · tests/data/webgpt_consultation_2026-10-03_gk1.json —— 记录口径本身
  历史数字、changelog、预注册与结果文件**不改** —— 它们是当时的记录, 由下面的白名单**逐个显式**放行。

## 三道断言
① LIVE(现行状态字段, 逐个列出): 带改述口径、无无保留主张、引用的每个数与证据文件逐值相等。
② 全仓(git ls-files): 无保留主张只许出现在 HISTORICAL_FILES / GUARD_TESTS / HISTORICAL_JSON_KEYS 里;
   白名单不许腐烂 —— 列了却已无命中就红(删掉它), 不留「以防万一」的豁免。
③ 变异: 每一处改述改回旧句 ⇒ ①红; 往非白名单文件注入旧句 ⇒ ②红。恒绿的闸不是闸。

## 「无保留」的判据(只查结构, 不猜措辞)
先剥掉改述口径本身与被「」括住的引文(引用/被撤回的原句), 再找 G-K1 之后同一句 16 字内的
通过/达标/PASS/✅(前一字是 未/不/非 的除外); 英文另查其后 40 字内的 pass/passed。
"""
import json
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
GK = "G-K" + "1"          # 本文件自己不含字面主张 —— 它不在白名单里, 也被全仓扫描
PHRASE = "未建立稳健通过证据"
EN_PHRASE = "no robust pass evidence"
DIAG = "tests/data/gk1_fail_diagnosis_2026-10-03.json"
V3 = "tests/data/gk1_v3_result.json"
WEB = "tests/data/webgpt_consultation_2026-10-03_gk1.json"

_QUOTE = re.compile(r"「[^「」]*」")
_CN = re.compile(GK + r"[^。;；\n「」]{0,16}?(?<![未不非])(?:通过|达标|PASS|✅)")
_EN = re.compile(GK + r"[^.;\n\"'\[\]「」]{0,40}?\bpass(?:ed|es)?\b", re.I)   # 引号/方括号截断: 代码里的 gk1["pass"] 不是散文主张


def bare_claims(text):
    s = text.replace(PHRASE, "").replace("未建立通过证据", "")
    s = re.sub(re.escape(EN_PHRASE), "", s, flags=re.I)
    for _ in range(3):                       # 嵌套引文由内向外剥
        s = _QUOTE.sub("", s)
    return [" ".join(s[max(0, m.start() - 12):m.end() + 12].split()) for r in (_CN, _EN) for m in r.finditer(s)]


def _j(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def evidence():
    """改述所依据的数, 全部从证据文件现读; 同时核对改述的**前提**仍然成立。"""
    d, v = _j(DIAG), _j(V3)
    cp, h, b = d["②comparability_run_params(A, B)"], d["③headline"], d["⑨item_cluster_bootstrap"]
    assert cp["gate_protocol_hash"][0] == cp["gate_protocol_hash"][1], "★ 两次运行不是同一闸协议 —— 改述前提不成立"
    thr = h["threshold"]
    assert h["A_mean_JS"] <= thr < h["B_mean_JS"], "★ 两次运行不再一过一不过 —— 改述前提要重审"
    lo, hi = b["paired_diff_B_minus_A_CI95"]
    assert lo < 0 < hi, "★ 配对差区间不再含 0 —— 改述前提要重审"
    assert b["A_CI95"][1] > thr and b["B_CI95"][1] > thr, "★ 条目聚类自助上界不再两次越线 —— 改述前提要重审"
    p4, p5 = v["P4_primary"]["verdict"], v["P5_comparison_only"]["verdict"]
    assert p4 != "PASS" and p5 != "PASS", "★ v3 出现了 PASS —— 改述要重审, 不是本闸放宽"
    assert (GK + " v2 " + PHRASE) in _j(WEB)["answer_page_text"], "★ 记录口径的出处里找不到这句"
    return {"A": str(h["A_mean_JS"]), "B": str(h["B_mean_JS"]), "lo": str(lo), "hi": str(hi),
            "Aup": str(b["A_CI95"][1]), "Bup": str(b["B_CI95"][1]), "hash": cp["gate_protocol_hash"][0],
            "P4": p4, "P5": p5, "diag": DIAG, "v3": V3, "web": WEB}


def _readme_status():
    t = (ROOT / "README.md").read_text(encoding="utf-8")
    return t.split("## Status", 1)[1].split("\n## ", 1)[0]


def _open_items_text():
    import cce_open_items as OI
    return "\n".join(r["项"] + " " + r["证据"] for r in OI.items())


# 现行状态字段: (取值函数, 必须引用的证据键)。★ 显式列出; 新增现行状态位置就加一行。
ALL = ("A", "B", "lo", "hi", "Aup", "Bup", "hash", "P4", "P5", "diag", "v3", "web")
LIVE = {
    "config/knot_taxonomy.json:status": (lambda: _j("config/knot_taxonomy.json")["status"], ALL),
    "config/knot_taxonomy.json:annotation_protocol.gate_record":
        (lambda: _j("config/knot_taxonomy.json")["annotation_protocol"]["gate_record"], ("A", "B", "diag", "v3", "web")),
    "config/cce_core_manifest.json:gate_protocol_expected.★status":
        (lambda: _j("config/cce_core_manifest.json")["gate_protocol_expected"]["★status"], ALL),
    "scripts/cce_knot_classify.py:CANDIDATE_CAVEAT":
        (lambda: __import__("cce_knot_classify").CANDIDATE_CAVEAT, ("A", "B", "P4", "diag")),
    "scripts/cce_open_items.py:items()": (_open_items_text, ALL),
    "README.md:## Status": (_readme_status, ("A", "B", "P4", "diag", "v3")),
}

# 历史记录类文件: 无保留的旧说法在这里是**当时的记录**, 不改。逐个显式列出, 不用通配。
HISTORICAL_FILES = {
    "ledger/contradictions.json": "2026-08-09~10 两日实验台账",
    "probes/gate_vs_production_prompt_gap.py": "产出 2026-09-08 结果文件的探针, 结论串随产物落盘",
    "tests/data/ablation_v3/空白_漏报的分类学字段.json": "消融留档: 当时 taxonomy.status 的逐臂快照",
    "tests/data/cross_family_reference_81.json": "结果文件",
    "tests/data/gate_protocol_v2_acceptance_prereg.json": "预注册",
    "tests/data/gate_protocol_v2_acceptance_result.json": "结果文件(2026-09-09 启用验收)",
    "tests/data/gate_vs_production_fieldset_prereg.json": "预注册",
    "tests/data/gate_vs_production_fieldset_result.json": "结果文件",
    "tests/data/gate_vs_production_prompt_gap.json": "结果文件",
    "tests/data/gk1_margin_analysis.json": "结果文件",
    "tests/data/gpt_review_three_options.json": "外部评审留档",
    "tests/data/nine_knot_acceptance_rerun_prereg.json": "预注册",
    "tests/data/repeatability_and_external_validity_prereg.json": "预注册",
    "tests/data/webgpt_ruling_2026-09-09.json": "外部裁决留档",
}
# 守卫测试: 为了测「旧说法回来就红」或在 docstring 里复述历史, 必须引用旧说法。同样逐个列出。
GUARD_TESTS = {
    "tests/test_cce_cross_family_reference.py", "tests/test_cce_fieldset_arm_b.py",
    "tests/test_cce_gate_v2_acceptance.py", "tests/test_cce_gk1_margin.py",
    "tests/test_cce_gk3_not_a_tautology.py", "tests/test_cce_knot_caveat.py",
    "tests/test_cce_qualification_premise_revised.py", "tests/test_cce_repeatability.py",
}
# 原始运行产物: archive/<run_id>/ 下是当时那次运行的输出(载荷里带着当时的 taxonomy_status 与 caveat)。
#   放行条件不是通配 archive/, 而是 run_id **登记在 config/cce_archive_index.json 的 runs 里** —— 未登记的目录照扫。
ARCHIVE_INDEX = "config/cce_archive_index.json"
# 混合文件(现行字段与历史记录同在一份 JSON): 按顶层键放行历史记录键, 其余键照扫。
HISTORICAL_JSON_KEYS = {
    "config/knot_taxonomy.json": {"changelog_1_2_0"},
    "config/cce_core_manifest.json": {"refactor_log"},
}


def _tracked():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [p for p in out.split("\0") if p]


def scan(read=lambda rel: (ROOT / rel).read_text(encoding="utf-8")):
    """返回 {(文件, 顶层键或 None): [命中]}; 白名单外的命中才算违规。"""
    hits = {}
    for rel in _tracked():
        try:
            text = read(rel)
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        if rel in HISTORICAL_JSON_KEYS:
            for k, v in json.loads(text).items():
                c = bare_claims(json.dumps(v, ensure_ascii=False))
                if c:
                    hits[(rel, k)] = c
            continue
        c = bare_claims(text)
        if c:
            hits[(rel, None)] = c
    return hits


def _archived(rel, _runs=[]):
    if not _runs:
        _runs.append(set(_j(ARCHIVE_INDEX)["runs"]))
    p = rel.split("/")
    return len(p) >= 3 and p[0] == "archive" and p[1] in _runs[0]


def _violations(hits):
    return {k: v for k, v in hits.items()
            if not (k[0] in HISTORICAL_FILES or k[0] in GUARD_TESTS or _archived(k[0])
                    or k[1] in HISTORICAL_JSON_KEYS.get(k[0], ()))}


def _problems(name, text, ev):
    out = []
    if PHRASE not in text:
        out.append("没有改述口径「%s」" % PHRASE)
    bad = bare_claims(text)
    if bad:
        out.append("无保留的通过主张 %s" % bad)
    missing = [(k, ev[k]) for k in LIVE[name][1] if ev[k] not in text]
    if missing:
        out.append("引用的依据与证据文件对不上(缺 %s)" % missing)
    return out


def test_live_fields_carry_the_restatement_and_no_bare_claim():
    ev = evidence()
    for name, (get, _) in LIVE.items():
        p = _problems(name, get(), ev)
        assert not p, "★★★ %s: %s" % (name, "; ".join(p))


def test_repo_wide_bare_claims_only_in_explicit_history():
    bad = _violations(scan())
    assert not bad, "★★★ 白名单外出现无保留的通过主张:\n  " + "\n  ".join(
        "%s%s: %s" % (f, (" [%s]" % k) if k else "", c[:2]) for (f, k), c in sorted(bad.items()))


def test_whitelist_does_not_rot():
    hits = scan()
    hit_files = {f for f, _ in hits}
    stale = sorted(f for f in list(HISTORICAL_FILES) + sorted(GUARD_TESTS) if f not in hit_files)
    assert not stale, "★ 白名单里这些文件已无命中 —— 删掉, 不留豁免: %s" % stale
    stale_keys = sorted((f, k) for f, ks in HISTORICAL_JSON_KEYS.items() for k in ks if (f, k) not in hits)
    assert not stale_keys, "★ 白名单里这些 JSON 键已无命中 —— 删掉: %s" % stale_keys


# ── ③ 变异: 改回旧句必须红 ─────────────────────────────────────────────────────
# (现行字段名, 改述后的片段, 改述前的旧句) —— 旧句来自 2026-10-03 之前各字段的原文
MUTATIONS = [
    ("config/knot_taxonomy.json:status", "**%s %s**" % (GK, PHRASE), "**%s 的两项指标达标**" % GK),
    ("config/knot_taxonomy.json:annotation_protocol.gate_record", "%s: **%s**" % (GK, PHRASE),
     "%s ✅ 2026-09-07 重跑通过" % GK),
    ("config/cce_core_manifest.json:gate_protocol_expected.★status", "**%s v2 %s**" % (GK, PHRASE), "%s 两项均达标" % GK),
    ("scripts/cce_knot_classify.py:CANDIDATE_CAVEAT", "**%s %s**" % (GK, PHRASE), "%s 两项指标达标" % GK),
    ("scripts/cce_open_items.py:items()", "%s 判据一字未改, 两项点估计过线" % GK, "%s 判据一字未改且两项达标" % GK),
    ("README.md:## Status", "%s\n(inter-annotator agreement) has **%s**" % (GK, EN_PHRASE),
     "%s (inter-annotator agreement) passed" % GK),
]


def test_reverting_any_restatement_turns_red():
    ev, caught = evidence(), 0
    for name, new, old in MUTATIONS:
        live = LIVE[name][0]()
        assert new in live, "★ 变异锚点不在 %s 里 —— 改了措辞就同步更新本表" % name
        mutated = live.replace(new, old)
        assert bare_claims(mutated), "★★★ %s 改回旧句「%s」后检测器仍绿 —— 闸是空的" % (name, old)
        assert _problems(name, mutated, ev), "★★★ %s 改回旧句后 LIVE 判据仍绿" % name
        caught += 1
    # README 的旧文不是「通过」而是「未跑」 —— 整段换回旧文, 也必须红(缺改述口径)
    old_readme = ("Research code. The knot taxonomy's acceptance gates (G-K1/G-K2/G-K3) have not\n"
                  "been run; any conclusion drawn from stage-2 output should carry that caveat.\n")
    assert _problems("README.md:## Status", old_readme, ev), "★★★ README 换回旧文后仍绿"
    caught += 1
    # 全仓扫描的变异: 往一个非白名单文件(scripts/cce_open_items.py)注入旧句
    target = "scripts/cce_open_items.py"
    real = lambda rel: (ROOT / rel).read_text(encoding="utf-8")
    poisoned = lambda rel: real(rel) + ("\n# %s 两项均达标\n" % GK if rel == target else "")
    assert target in {f for f, _ in _violations(scan(poisoned))}, "★★★ 注入旧句后全仓扫描仍绿"
    assert target not in {f for f, _ in _violations(scan())}
    assert caught + 1 == N_MUTATIONS


N_MUTATIONS = len(MUTATIONS) + 2      # 逐字段改回旧句 + README 整段换回旧文 + 全仓注入


def test_quoted_and_negated_mentions_are_not_claims():
    """会误报的闸不上 —— 引文、否定、改述口径本身都不是主张。"""
    for ok in ("「%s 通过」不蕴含「九个结分得开」" % GK, "%s 作为已知未达标的验收闸" % GK,
               "%s v2 %s" % (GK, PHRASE), "%s v3 未建立通过证据" % GK, "%s has %s" % (GK, EN_PHRASE),
               "生产分类器 %s 不达标" % GK):
        assert not bare_claims(ok), ok


if __name__ == "__main__":
    test_live_fields_carry_the_restatement_and_no_bare_claim()
    test_repo_wide_bare_claims_only_in_explicit_history()
    test_whitelist_does_not_rot()
    test_reverting_any_restatement_turns_red()
    test_quoted_and_negated_mentions_are_not_claims()
    print("test_cce_gk1_no_live_pass_claim: OK (%d 个现行状态字段带「%s」且数字与证据文件逐值相等 · "
          "全仓无保留主张只在 %d 个历史文件 + %d 个守卫测试 + 已登记归档 run + %d 个历史 JSON 键里 · 变异 %d/%d 判红)"
          % (len(LIVE), PHRASE, len(HISTORICAL_FILES), len(GUARD_TESTS),
             sum(map(len, HISTORICAL_JSON_KEYS.values())), N_MUTATIONS, N_MUTATIONS))
