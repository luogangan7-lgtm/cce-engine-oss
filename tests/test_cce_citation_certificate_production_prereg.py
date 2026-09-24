# -*- coding: utf-8 -*-
"""闸: 引用证书协议进生产的预注册(tests/data/citation_certificate_production_prereg.json)。零调用。
守: 协议 sha 与 r2 模块现算一致 · P2 为 v2 · 试点材料由 archive/冻结集现算一致且只有指针 · 上限 = 2×n · 判决线/预测/禁止项在 · 生产**未接线**、开关不存在。"""
import hashlib, importlib.util, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
_s = importlib.util.spec_from_file_location("_ccp", ROOT / "probes/citation_certificate_production_prereg.py"); gen = importlib.util.module_from_spec(_s); _s.loader.exec_module(gen)
P = json.loads((ROOT / "tests/data/citation_certificate_production_prereg.json").read_text(encoding="utf-8"))


def test_protocol_pinned_to_r2_module_and_p2_v2():
    fresh = gen.build(); proto = P["★★★协议(逐字沿用 r2, 由闸现算比对)"]
    assert proto == fresh["★★★协议(逐字沿用 r2, 由闸现算比对)"]
    import cce_label_qualification as LQ; assert proto["P2 绑定"] == LQ.P2_BINDING == "witness_intersection"
    assert "UPGRADED" in proto["结局分类法"] and "MALFORMED" in proto["结局分类法"]


def test_pilot_material_recomputes_and_is_pointer_only():
    mat = P["★★★试点材料(指针+sha, 冻结)"]; A = mat["A · 归档里 s2 top-1=display 且原文可找回"]; B = mat["B · real_corpus_pilot 冻结 42 条(top-1 未知)"]
    assert A["items"] == gen.stratum_a() and B["items"] == gen.stratum_b() and B["n"] == 42
    for it in A["items"]: assert set(it) == {"input_sha", "text_source", "item_index", "n_chars", "readouts"} and (ROOT / it["text_source"]).exists() and all((ROOT / r).exists() for r in it["readouts"])
    for it in B["items"]: assert set(it) == {"file", "line_index", "sha256", "n_chars"}
    s = json.dumps(mat, ensure_ascii=False); assert "hearing aid" not in s.lower() and " the " not in s   # 没有原文
    assert P["★预算硬上限"]["证书调用"] == 2 * (A["n_texts"] + B["n"]) and P["★预算硬上限"]["撞上即停"] is True


def test_rules_frozen_and_production_not_wired():
    rules = P["★★★决策规则(测量前冻结)"]
    for k in ("ADOPT_SHADOW", "NEEDS_N3", "STOP", "COST_BLOCK", "★预测(先写)"): assert k in rules
    assert "60%" in rules["ADOPT_SHADOW"] and "10%" in rules["ADOPT_SHADOW"] and "45 s" in rules["ADOPT_SHADOW"]
    assert "citable_as_confirmed **恒 False**" in P["★★★影子段 s2b 的形状(接线时照此, 现在不接)"]["★不变量"]
    assert "未执行" in P["★★★status"] and "生产未接线" in P["★★★status"]
    src = (ROOT / "scripts/cce_full_run.py").read_text(encoding="utf-8")
    assert "CCE_CITATION_CERT" not in src and "s2b" not in src, "★ 预注册未执行/未判 ADOPT 前不许接线"
    assert any("MIS-4" in x for x in P["★★★不得据此说"])
