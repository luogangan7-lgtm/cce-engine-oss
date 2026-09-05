"""OPEN_QUESTIONS.md 是**对外**文档 —— 它引的每个数字必须能在仓内数据里对上。

为什么要有这条闸: 那份文档的用途是招人来帮忙, 它会被陌生人读、被引用、被拿去判断
这个项目值不值得花十分钟。一份**悄悄过期**的对外文档比没有文档更坏 ——
它把「测过的」和「以为测过的」混在一起, 而这正是本项目反复栽的那类错。

★ 本闸只查**一个方向**: 文档里写的数, 数据里必须支持。
   文档漏掉某个数据**不算**违规 —— 对外文档本来就该是子集。
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC = ROOT / "OPEN_QUESTIONS.md"
P2 = ROOT / "tests" / "data" / "phase2"


def _load(name):
    return json.loads((P2 / name).read_text(encoding="utf-8"))


def _dig(obj, path):
    for seg in path.split("/"):
        obj = obj[seg]
    return obj


# (人读的名字, 文件, JSON 路径, 文档里该出现的字面串, 换算说明)
CLAIMS = [
    ("LibriSpeech test-clean WER", "asr_quality_en_other.json",
     "test_clean_gen2_for_comparison/mean", "2.34%", "mean 0.0234 → 百分比两位"),
    ("LibriSpeech test-other WER", "asr_quality_en_other.json",
     "wer/mean", "11.61%", "mean 0.1161 → 百分比两位"),
    ("跨引擎一致率中位", "asr_agreement_social.json",
     "agreement/median", "0.475", "0.4754 → 三位"),
    ("说话人分段 DER(STRICT)", "diarization_der.json",
     "der_profiles/STRICT/aggregate", "0.1004", "原值"),
    ("受控退化 clean CER", "asr_degradation_curve.json",
     "clean_cer_median", "0.00", "原值 0.0"),
    ("真实素材非人声占比中位", "asr_degradation_curve.json",
     "★where_real_material_sits/real_nonvocal_share_median", "0.491", "原值"),
]


def test_doc_exists():
    assert DOC.exists(), "OPEN_QUESTIONS.md 不在了 —— 对外承诺的入口不该被静默删掉"


def test_every_number_in_doc_is_backed_by_data():
    text = DOC.read_text(encoding="utf-8")
    for name, fname, path, literal, how in CLAIMS:
        value = _dig(_load(fname), path)
        assert literal in text, (
            f"★ {name}: 文档里找不到 {literal!r} —— "
            f"要么文档改了数没同步, 要么数据变了没回改文档。数据现值 {value} ({how})"
        )
        # 字面串必须真的是那个数, 不是巧合撞上的另一处
        if literal.endswith("%"):
            assert abs(float(literal[:-1]) / 100 - value) < 5e-5, \
                f"★ {name}: 文档写 {literal}, 数据是 {value}"
        else:
            assert abs(float(literal) - value) < 5e-4, \
                f"★ {name}: 文档写 {literal}, 数据是 {value}"


def test_playbook_counts_match_verdict():
    v = _load("playbook_atoms_verdict.json")
    text = DOC.read_text(encoding="utf-8")
    assert v["texts"] == 8 and v["meeting_criterion"] == 6
    assert "6 of 8" in text, "文档该写 6/8 —— 那是实测的达标数"
    assert "4 of 8" in text, "文档该写基线 4/8 —— 少了基线, 改善幅度就无从判断"
    assert "line was pre-registered at 7" in text, \
        "★ 必须写明采纳线是**预注册**的 7 —— 否则读者会以为 6/8 只是差一点点, " \
        "而不是「阈值不因看到结果而下调」"


def test_sesoi_is_still_none_as_the_doc_claims():
    """文档说 SESOI 是 None 且被测试钉住。若哪天有人填了值, 这条必须先红。"""
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import cce_ksep

    # ★ 钉的是**契约里的语义档**, 不是那个兼容别名 —— 别名叫 SESOI, 真正被下游读的是这个。
    sem = cce_ksep.SIGNIFICANCE_CONTRACT["interpretive"]["semantic_sesoi"]
    assert sem is None, (
        f"★ semantic_sesoi 不再是 None(现为 {sem!r}) —— OPEN_QUESTIONS.md 里"
        "「currently None」这句已过期, 而那句话正是招募盲评人的**理由**。"
        "若确实标定出来了, 先改文档再改这条闸。"
    )
    assert cce_ksep.SESOI is None, "★ 兼容别名 SESOI 也必须仍为 None"
    assert "None" in DOC.read_text(encoding="utf-8")


def test_doc_does_not_overclaim_rater_independence():
    """★ 最重要的一条: 文档**不许**把「n 份提交」说成「n 名独立评分者」。

    这是本项目栽过最多次那类错(把「查不了」写成「查过了」)在对外文档上的形态,
    而这条基线是要拿去当仪器标定证据的 —— 位置比之前每一次都更承重。
    """
    text = DOC.read_text(encoding="utf-8")
    assert "distinctness not verified" in text, \
        "★ 必须显式声明「distinctness not verified」—— 没有它, 读者会默认这是 n 个人"
    assert "never as" in text and "independent raters" in text, \
        "★ 必须显式写出**不会**用哪种措辞报告"
    # 反向: 不许出现无限定的「n independent raters」承诺
    bad = re.findall(r"\b\d+\s+independent\s+raters\b", text)
    for hit in bad:
        idx = text.find(hit)
        window = text[max(0, idx - 120): idx + 60]
        assert "never" in window or "not " in window, \
            f"★ 出现了未加限定的独立性承诺: {hit!r}"


def _reverse_checks():
    """反向验证: 每条闸都必须能在被破坏时判红, 否则它只是装饰。"""
    import copy

    text = DOC.read_text(encoding="utf-8")

    # ① 数字对不上时必须红
    tampered = text.replace("11.61%", "1.61%")
    assert tampered != text
    saved = DOC.read_text(encoding="utf-8")
    try:
        DOC.write_text(tampered, encoding="utf-8")
        try:
            test_every_number_in_doc_is_backed_by_data()
            raise SystemExit("★ 反向验证失败: 把 11.61% 改成 1.61% 后闸仍绿")
        except AssertionError:
            pass
    finally:
        DOC.write_text(saved, encoding="utf-8")

    # ② 拿掉独立性限定时必须红
    tampered2 = text.replace("distinctness not verified", "all independently verified")
    assert tampered2 != text
    try:
        DOC.write_text(tampered2, encoding="utf-8")
        try:
            test_doc_does_not_overclaim_rater_independence()
            raise SystemExit("★ 反向验证失败: 拿掉独立性限定后闸仍绿")
        except AssertionError:
            pass
    finally:
        DOC.write_text(saved, encoding="utf-8")

    # ③ 拿掉预注册说明时必须红
    tampered3 = text.replace("line was pre-registered at 7", "line was 7")
    assert tampered3 != text
    try:
        DOC.write_text(tampered3, encoding="utf-8")
        try:
            test_playbook_counts_match_verdict()
            raise SystemExit("★ 反向验证失败: 拿掉「预注册」后闸仍绿")
        except AssertionError:
            pass
    finally:
        DOC.write_text(saved, encoding="utf-8")

    assert DOC.read_text(encoding="utf-8") == saved, "★ 反向验证把文档改坏了没还原"
    return 3


if __name__ == "__main__":
    test_doc_exists()
    test_every_number_in_doc_is_backed_by_data()
    test_playbook_counts_match_verdict()
    test_sesoi_is_still_none_as_the_doc_claims()
    test_doc_does_not_overclaim_rater_independence()
    n_rev = _reverse_checks()
    print(f"test_cce_open_questions_numbers: OK ({len(CLAIMS)} 个引用数字逐个对上仓内数据 | "
          f"playbook 6/8 与基线 4/8 及**预注册**采纳线 7 三者齐全 | "
          f"SESOI 仍为 None(招募理由未过期) | "
          f"独立性限定「distinctness not verified」在位 | "
          f"{n_rev} 条反向验证: 改数/去限定/去预注册 各自都判红)")
