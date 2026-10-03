# -*- coding: utf-8 -*-
"""闸: audit 写手指导串落地(2026-10-01, Core 第五条路)—— 哪一半行为变了、哪一半没变, 各自现算。零调用。

裁定: docs/decisions/PLAYBOOK_TRI_STATE_AUDIT_DECIDED_2026-10-01.md ②。登记: config/cce_core_manifest.json refactor_log
(event AUDIT_PLAYBOOK_LANDED_ROUTE_5)。旧串与新串只差 audit 一个 playbook 值 —— 本闸把两份 taxonomy 并排现算。
"""
import copy, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "probes"))
import cce_knot_classify as K            # noqa: E402
import knot_taxonomy_ablation as A       # noqa: E402

OLD = "不辩解不表演;给可验证事实+接受检验的姿态(『Ask me anything specific』)"
NEW = "不辩解不表演;给可验证事实(数字/来源/可查记录)+明确邀请对方核验或追问具体细节(『Ask me anything specific』)"
TAXO = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
MAN = json.loads((ROOT / "config/cce_core_manifest.json").read_text(encoding="utf-8"))


def _old():
    t = copy.deepcopy(TAXO)
    next(k for k in t["knots"] if k["key"] == "audit")["playbook"] = OLD
    return t


def test_landed_text_is_the_decided_text():
    pb = {k["key"]: k["playbook"] for k in TAXO["knots"]}
    assert pb["audit"] == NEW, "★ 产品串不是裁定的串"
    assert sum(p != q for p, q in zip((k["playbook"] for k in TAXO["knots"]), (k["playbook"] for k in _old()["knots"]))) == 1


def test_unchanged_half_instrument_and_gate():
    """没变的一半: 生产分类器 P(instrument_hash / s1+s2 模板)与验收闸 G 的材料, 新旧串逐字相同。"""
    kw = dict(k=3, knot_n=5, s1_pairing="round_robin_over_3_s1_draws")
    assert K.instrument_id(TAXO, **kw)["instrument_hash"] == K.instrument_id(_old(), **kw)["instrument_hash"] \
        == MAN["instrument_expected"]["instrument_hash"]
    assert K._stage2_template(TAXO) == K._stage2_template(_old())
    assert A.gate_materials(TAXO) == A.gate_materials(_old())


def test_changed_half_reaches_the_writer_and_the_dissolve_judge():
    """变了的一半: 交付给写稿方的 playbook(v3-203)与 cce_align_v2 拆除判官的规范(v3-205)现在是新串。"""
    import cce_align_v2 as V2
    assert V2.PLAYBOOK["audit"] == NEW      # dissolve_hit() 以 PLAYBOOK.get(knot) 填 DISSOLVE_PROMPT 的 {playbook}
    assert max(len(k["playbook"]) for k in TAXO["knots"]) <= 120, "★ v3-326(playbook_primary 截断 [:120] UNREACHABLE)被复活"


def test_ablation_rerun_on_the_landed_file():
    """LOAD_BEARING_L2 字段改了 ⇒ 消融在改后的文件上重跑过, 双向对照通过, playbook 判决不变。"""
    d = json.loads((ROOT / "tests/data/knot_taxonomy_ablation.json").read_text(encoding="utf-8"))
    assert d["controls_passed"] is True
    assert next(r for r in d["rows"] if r["field"] == "playbook")["verdict"] == "LOAD_BEARING_L2"


def test_route_5_registration():
    """第五条路四件: pin 已更新 · refactor_log 有完整转移且写明两半 · 可比不可合声明 · instrument_expected 现算相符(上面)。"""
    e = [x for x in MAN["refactor_log"] if x.get("event") == "AUDIT_PLAYBOOK_LANDED_ROUTE_5"]
    assert len(e) == 1
    # ★ 2026-10-03: 原写「本条 to_sha == 当前 pin」, 是位置依赖(假定本条永远是最后一次改 taxonomy) ——
    #   GK1_V2_NO_ROBUST_PASS_RESTATED(只改 status/gate_record 自述)把 pin 合法地往前推了一格就断。
    #   按登记链定位: 从本条 to_sha 出发, 每一跳都必须是 refactor_log 里的完整转移, 走得到当前 pin。
    #   后续跳没动 playbook 由 test_landed_text_is_the_decided_text 现算。
    nxt = {x["from_sha"]: x["to_sha"] for x in MAN["refactor_log"] if x.get("file") == "config/knot_taxonomy.json"}
    cur = e[0]["to_sha"]
    for _ in range(len(nxt) + 1):
        if cur == MAN["core_files"]["config/knot_taxonomy.json"]:
            break
        assert cur in nxt, "★ 从 AUDIT_PLAYBOOK_LANDED_ROUTE_5 的 to_sha 走不到当前 pin: %s 之后没有登记转移" % cur
        cur = nxt[cur]
    assert cur == MAN["core_files"]["config/knot_taxonomy.json"]
    assert e[0]["from_sha"] == "56a1c1977bf8d18c" and e[0]["instrument_hash_unchanged"] is True
    assert "★which_half_of_behavior_changed" in e[0] and "可比不可合" in e[0]["★可比不可合"]
    assert "tests/test_cce_audit_playbook_landed.py" in e[0]["behavior_evidence"]
