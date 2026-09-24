"""suspend 修法的确证 V0 vs V1 —— 判决必须**现算**, 且必须吃缺失敏感性。零 API。

## 结果(全部由本闸从原始读数现算, 不引用产物里的数字)
| | MiniMax 五员 | GLM 跨家族 |
|---|---|---|
| **C1** 失败方向上有效 | 45.0% → **12.5%**, 下尾 p=0.0013 ✅ | 37.5% → 0%, p=0.15(n 太小) |
| **C2** 不许压掉真悬置 | 0.95 → **1.00** ✅ | 1.00 → 1.00 ✅ |
| **C3** 对抗组能分开 | 1.0 vs 0.2, p=0.00036 ✅ | 1.0 vs 0.0, n=2 无检定力 |

## ★★★ 本闸真正防的四件事
① **判决必须现算** —— 产物里的数字不许被引用成事实。
② **C2 是修法可能失败的方向**(修法压掉真悬置)。它没失败, 但断言必须留着。
③ **作者偏倚声明不许被删** —— 题是我出的, 而我知道修法是什么。
④ **★★ 差别性缺失必须被吃进总判** —— 首轮 4 条解析失败**全在 V1 臂**,
   而判据分母变小会**机械地帮 V1**。预注册没预见这个失败模式, 敏感性块是**事后加的**,
   只能让判决**更严**, 不放宽任何一条。

## ★ 这条修法**修不到生产分类器**
生产 s2 prompt **不含** negative_examples(实测: 改它 instrument_hash 一字不变)。
⇒ 本轮只证明「闸的标注者不再把执行延后判成 suspend」。**这句缺了就是夸大。**
"""
import json
import pathlib
from math import comb

ROOT = pathlib.Path(__file__).resolve().parent.parent
# ★ 原始读数与题目在**识别层保险库**(仓外) —— CI 上不存在。
#   本闸必须在缺席时**降级但仍有断言**, 不许静默跳过。见 test_cce_no_offrepo_dependency。
RAW = pathlib.Path("/Volumes/data/cce-identified-vault/cce_runs/suspend_fix_confirm/raw.json")
ITEMS = pathlib.Path("/Volumes/data/cce-identified-vault/cce_runs/suspend_confirm_items.json")


def _have_vault():
    return RAW.exists() and ITEMS.exists()
PRE = ROOT / "tests" / "data" / "suspend_fix_confirmation_prereg.json"
RES = ROOT / "tests" / "data" / "suspend_fix_confirmation_result.json"
FAIL_CELLS = ["已决定_延后执行", "历史悬置_现已决定"]
TRUE_CELLS = ["★真悬置_必须仍判"]


def _rows():
    return json.loads(RAW.read_text(encoding="utf-8"))


def _pre():
    return json.loads(PRE.read_text(encoding="utf-8"))


def _res():
    return json.loads(RES.read_text(encoding="utf-8"))


def _mm(r):
    return not r["model"].startswith("glm")


def _rate(rows, cells, arm, fam):
    s = [r for r in rows if r["cell"] in cells and r["arm"] == arm and (_mm(r) if fam == "mm" else not _mm(r))]
    ok = [r for r in s if r["top1"]]
    k = sum(1 for r in ok if r["top1"] == "suspend")
    return k, len(ok), len(s) - len(ok)


def _fisher_lower(a, b, c, d):
    n1, n2, k = a + b, c + d, a + c
    return sum(comb(n1, i) * comb(n2, k - i)
               for i in range(max(0, k - n2), a + 1)) / comb(n1 + n2, k)


def test_c1_recomputed_from_raw_not_quoted():
    """★ C1: V1 在失败方向上的 suspend 率必须 <=20% —— **现算**。"""
    if not _have_vault():
        # ★ 无本机素材(CI): 退回**核对产物内部自洽** —— 「18/40=45.0%」这类串必须自恰。
        for fam in ("MiniMax五员", "GLM跨家族"):
            g = _res()[fam]["★C1_修法在失败方向上有效"]
            for arm in ("V0", "V1"):
                num, pct = g[arm].split("=")
                k, n = (int(x) for x in num.split("/"))
                assert abs(k / n - float(pct.rstrip("%")) / 100) < 5e-3, \
                    f"★ 产物里 {fam} {arm} 的 {g[arm]} 自相矛盾"
            k1, n1 = (int(x) for x in g["V1"].split("=")[0].split("/"))
            assert k1 / n1 <= 0.20, f"★ {fam} 产物里的 C1 就 >20%"
        print("  ★ 降级: 无本机素材, C1 只核对产物自洽(未重算原始读数)")
        return

    rows = _rows()
    for fam in ("mm", "glm"):
        k1, n1, _ = _rate(rows, FAIL_CELLS, "V1", fam)
        k0, n0, _ = _rate(rows, FAIL_CELLS, "V0", fam)
        assert n1 and n0, f"★ {fam} 失败方向无有效读数"
        assert k1 / n1 <= 0.20, f"★ {fam} 的 C1 现算 {k1}/{n1} > 20% —— 与产物不符, 先查哪个错了"
        assert k1 / n1 < k0 / n0, f"★ {fam} 的 V1 并不比 V0 低"


def test_c2_the_direction_the_fix_could_fail_did_not_fail():
    """★★ C2 是修法**可能失败**的方向: 补了负例之后把**真悬置**也排掉。"""
    if not _have_vault():
        for fam in ("MiniMax五员", "GLM跨家族"):
            g = _res()[fam]["★★C2_修法不许压掉真悬置"]
            assert g["V1"] >= 0.70 and abs(g["差"] - (g["V1"] - g["V0"])) < 1e-9, \
                f"★ 产物里 {fam} 的 C2 不自洽或已低于 0.70"
        print("  ★ 降级: 无本机素材, C2 只核对产物自洽(未重算原始读数)")
        return

    rows = _rows()
    for fam in ("mm", "glm"):
        k1, n1, _ = _rate(rows, TRUE_CELLS, "V1", fam)
        k0, n0, _ = _rate(rows, TRUE_CELLS, "V0", fam)
        assert n1 and n0
        assert k1 / n1 >= 0.70, f"★★★ {fam} 的 V1 把真悬置压到 {k1}/{n1} —— **修法过度**"
        assert abs(k1 / n1 - k0 / n0) <= 0.20, f"★★ {fam} 的真悬置率相对 V0 动了太多"


def test_the_significance_is_reported_on_the_correct_tail():
    """★ 我第一版把**上尾**当成「V1<V0」报出去(0.9998), 正确下尾是 0.00129。"""
    if not _have_vault():
        got = _res()["MiniMax五员"]["★C1_修法在失败方向上有效"]
        key = [k for k in got if k.startswith("fisher_p")][0]
        assert "下尾" in key, "★★ 显著性的尾向必须写在键名里"
        k1, n1 = (int(x) for x in got["V1"].split("=")[0].split("/"))
        k0, n0 = (int(x) for x in got["V0"].split("=")[0].split("/"))
        assert abs(got[key] - round(_fisher_lower(k1, n1 - k1, k0, n0 - k0), 5)) < 1e-9, \
            "★ 产物里的 p 与按产物计数现算的下尾不符"
        print("  ★ 降级: 无本机素材, 显著性从**产物计数**现算(未重算原始读数)")
        return

    rows = _rows()
    k1, n1, _ = _rate(rows, FAIL_CELLS, "V1", "mm")
    k0, n0, _ = _rate(rows, FAIL_CELLS, "V0", "mm")
    p = _fisher_lower(k1, n1 - k1, k0, n0 - k0)
    assert p < 0.01, f"★ MiniMax 臂 C1 的下尾 p={p:.5f} 不再显著"
    got = _res()["MiniMax五员"]["★C1_修法在失败方向上有效"]
    key = [k for k in got if k.startswith("fisher_p")][0]
    assert "下尾" in key, "★★ 显著性的**尾向**必须写在键名里 —— 我就是在这里报反过一次"
    assert abs(got[key] - round(p, 5)) < 1e-9, "★ 产物里的 p 与现算不符"


def test_differential_attrition_is_carried_into_the_overall_verdict():
    """★★★ 缺失若集中在一臂, 分母变小会**机械地帮那一臂**。总判必须吃这条。"""
    res = _res()
    for fam in ("MiniMax五员", "GLM跨家族"):
        assert "★★★事后_差后缺失敏感性" in res[fam] or "★★★事后_差别性缺失敏感性" in res[fam], \
            f"★ {fam} 缺敏感性块"
        blk = res[fam].get("★★★事后_差别性缺失敏感性", {})
        assert "★这是事后加的" in blk, "★★ 敏感性块必须自报是**事后加的** —— 不许伪装成预注册"
    ov = res["★★★overall"]
    frail = any(v.get("最坏界下判据") == "**翻成 FAIL**"
                for f in ("MiniMax五员", "GLM跨家族")
                for v in res[f]["★★★事后_差别性缺失敏感性"].values() if isinstance(v, dict))
    if frail:
        assert "不稳健" in ov and "不得据此换代" in ov, \
            "★★★ 有判据在最坏界下会翻 FAIL, 而总判没说 —— 那就是拿脆弱结论当依据"
    else:
        assert "稳健" in ov, "★ 无缺失时总判应明说对缺失稳健"


def test_the_authorship_bias_declaration_survives():
    """★★★ 题是我出的, 而我知道修法是什么。这句声明不许被删。"""
    d = json.dumps(_pre(), ensure_ascii=False)
    assert "题目是我写的" in d and "修法是什么" in d, "★ 作者偏倚声明不见了"
    assert "不知道修法内容的第三方" in d, "★ 「干净做法需要第三方出题」这句不许删"
    assert "SYNTHETIC_DIAGNOSTIC" in d, "★ 合成题标注不许删 —— 它不并入自然语料 n"


def test_it_does_not_claim_to_fix_production():
    """★★ 生产 s2 看不到 negative_examples ⇒ 本修法修不到生产。这句缺了就是夸大。"""
    d = json.dumps(_pre(), ensure_ascii=False) + json.dumps(_res(), ensure_ascii=False)
    assert "修不到生产" in d or "不改变生产" in d, \
        "★★★ 缺「本修法不改变生产分类器」这句 —— 读者会以为 suspend 在产品里修好了"


def test_the_prereg_checksum_still_matches_the_items():
    """★ 题目集合必须与冻结的校验和一致 —— 换题就是换实验。"""
    if not _have_vault():
        assert "6627d70e135d0113" in json.dumps(_pre(), ensure_ascii=False), \
            "★ 预注册里的题目校验和不见了"
        print("  ★ 降级: 无本机素材, 只核对预注册里仍写着校验和(未重算题目)")
        return

    import hashlib
    items = json.loads(pathlib.Path(
        "/Volumes/data/cce-identified-vault/cce_runs/suspend_confirm_items.json"
    ).read_text(encoding="utf-8"))
    # ★ 与出题脚本同一个式子: 排序后**空串**连接。我第一版写成 "|".join 未排序, 自己判红了。
    chk = hashlib.sha256("".join(sorted(x["id"] for x in items)).encode()).hexdigest()[:16]
    want = _pre()["★★why_new_items"]
    want = want if isinstance(want, str) else json.dumps(want, ensure_ascii=False)
    assert chk in want + json.dumps(_pre(), ensure_ascii=False), \
        f"★ 题目校验和 {chk} 与预注册不符 —— 题被换过"


def _force_degraded_path_once():
    """★★ 降级分支必须**实际跑一次**, 不许靠读代码断言它对。

    本仓已经栽过第六次: 「有降级分支」不等于「降级分支是对的」——
    上次是 `if r is not None:` 在本机绿、CI 红, 因为缺席形态被我**读代码推断**错了。
    """
    g = globals()
    saved = g["_have_vault"]
    g["_have_vault"] = lambda: False
    try:
        test_c1_recomputed_from_raw_not_quoted()
        test_c2_the_direction_the_fix_could_fail_did_not_fail()
        test_the_significance_is_reported_on_the_correct_tail()
        test_the_prereg_checksum_still_matches_the_items()
    finally:
        g["_have_vault"] = saved
    return 4


def test_the_all_pass_label_cannot_stand_alone():
    """★★★ 「C1~C4 ALL_PASS」**不许单独出现** —— 它掩盖了一个反向移动的负例组。

    实测(按网页版 GPT 的要求做全组剖面才发现): 「仅收藏」是**不该判 suspend** 的负例组,
    V1 把它从 **30% 推到 50%**。而 C1 只覆盖 6 个负例组里的 2 个 ⇒
    **我预注册的四条判据里没有任何一条会看到它。**
    ⇒ 结论旁必须永远挂着「8 组里 7 组方向正确、1 个负例组方向反转」。
    """
    r = _res()
    blk = r.get("★★★全组副作用剖面_2026-09-09")
    assert blk, "★★★ 全组副作用剖面被删了 —— 那是唯一能看到「仅收藏」反转的地方"
    prof = blk["★★★八组全剖面(题级, MiniMax 五员; 括号内为预期是否该判 suspend)"]
    assert len(prof) == 8, f"★ 剖面应覆盖全部 8 组, 现在只有 {len(prof)}"
    bad = [k for k, v in prof.items() if "方向反了" in v]
    assert bad, ("★ 剖面里不再有方向反转的组 —— 若确实修好了, **请重跑并更新**; "
                 "但不许靠删掉这一行让它消失")
    assert "仅收藏" in bad[0], f"★ 反转的组变了({bad}) —— 请复核结论"
    assert "7 组方向正确、1 个负例组" in json.dumps(blk, ensure_ascii=False),         "★★ 「7 对 1」这个正确说法不许被换回「C1~C4 全过」"


def test_the_item_level_correction_is_present_and_primary():
    """★★★ 原判决把「题 × 模型」当独立样本(伪重复) ⇒ p 值夸大。题级重算必须在, 且被标为准。"""
    r = _res()
    for fam in ("MiniMax五员", "GLM跨家族"):
        blk = r[fam].get("★★★事后_题级统计单位更正")
        assert blk, f"★ {fam} 缺题级统计单位更正"
        assert "伪重复" in blk["★★★读法"], "★ 「伪重复」这个定性不许删"
        assert "以本块为准" in blk["★★★读法"], "★★ 必须写明题级为准, 否则读者会用夸大的 p"
    c1 = r["MiniMax五员"]["★★★事后_题级统计单位更正"]["C1_失败方向"]
    assert c1["题数"] == 8, f"★ C1 的分析单位应是 8 题, 现在 {c1['题数']}"
    assert c1["单侧精确符号检验p"] > 0.01, (
        "★ 题级 p 变得比 0.01 还小了 —— 若属实是好事, 但请复核是不是又把非独立单位当独立了")


def test_the_attempt_ledger_reports_attempts_not_just_successes():
    """★★ 「264 次调用, 零失败」是把补齐后的终态当成全过程。必须报**尝试数**。"""
    r = _res()
    blk = r.get("★★★尝试账本_2026-09-09更正")
    assert blk, "★ 尝试账本更正被删了"
    assert "268" in json.dumps(blk, ensure_ascii=False), "★ 总尝试数 268 不见了"
    assert "事后" in blk["★★重试规则是事前还是事后"],         "★★ 必须承认重试规则是**事后**新增的 —— 不许继续挂「完全按原预注册执行」"
    # ★ 2026-09-24 修: 产物里的键是「★首轮最坏界必须保留」(带 ★), 原断言按**精确键名**查 ⇒ 证据在却恒红;
    #   这条红自 86e8051 起就存在, 被空跑的 runner 盖了两周(见 lesson「dev_runsuite 空跑」)。改为按键名子串查, 并核值非空。
    _wc = [k for k in blk if "首轮最坏界必须保留" in k]
    assert _wc and "最坏界" in str(blk[_wc[0]]), "★ 首轮最坏界不许从证据历史里消失"


def _reverse_checks():
    n, g = 0, globals()
    saved = g["_rows"]
    rows = _rows()

    # ① V1 在失败方向上退回 V0 水平 ⇒ 红
    bad = [dict(r) for r in rows]
    for r in bad:
        if r["arm"] == "V1" and r["cell"] in FAIL_CELLS:
            r["top1"] = "suspend"
    g["_rows"] = lambda: bad
    try:
        test_c1_recomputed_from_raw_not_quoted()
        raise SystemExit("★ 反向验证失败: V1 全判 suspend 后 C1 仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_rows"] = saved

    # ② 修法压掉真悬置 ⇒ C2 红(这是修法可能失败的方向)
    bad2 = [dict(r) for r in rows]
    for r in bad2:
        if r["arm"] == "V1" and r["cell"] in TRUE_CELLS:
            r["top1"] = "itch"
    g["_rows"] = lambda: bad2
    try:
        test_c2_the_direction_the_fix_could_fail_did_not_fail()
        raise SystemExit("★ 反向验证失败: 真悬置被压掉后 C2 仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_rows"] = saved

    # ③ 作者偏倚声明被删 ⇒ 红
    saved_pre = g["_pre"]
    g["_pre"] = lambda: {"x": "y"}
    try:
        test_the_authorship_bias_declaration_survives()
        raise SystemExit("★ 反向验证失败: 删掉作者偏倚声明后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_pre"] = saved_pre
    return n


if __name__ == "__main__":
    test_c1_recomputed_from_raw_not_quoted()
    test_c2_the_direction_the_fix_could_fail_did_not_fail()
    test_the_significance_is_reported_on_the_correct_tail()
    test_differential_attrition_is_carried_into_the_overall_verdict()
    test_the_authorship_bias_declaration_survives()
    test_it_does_not_claim_to_fix_production()
    test_the_prereg_checksum_still_matches_the_items()
    d4 = _force_degraded_path_once()
    n = _reverse_checks()
    rows = _rows()
    a = _rate(rows, FAIL_CELLS, "V0", "mm"); b = _rate(rows, FAIL_CELLS, "V1", "mm")
    c = _rate(rows, TRUE_CELLS, "V0", "mm"); d = _rate(rows, TRUE_CELLS, "V1", "mm")
    print(f"test_cce_suspend_fix_confirmation: OK ("
          f"C1 现算 MiniMax {a[0]}/{a[1]}={a[0]/a[1]:.1%} → {b[0]}/{b[1]}={b[0]/b[1]:.1%} "
          f"(下尾 p={_fisher_lower(b[0], b[1]-b[0], a[0], a[1]-a[0]):.5f}) | "
          f"★★C2 真悬置 {c[0]}/{c[1]} → {d[0]}/{d[1]} **没被压掉**(修法可能失败的方向) | "
          f"显著性**尾向**已写进键名(我报反过一次) | 差别性缺失已吃进总判 | "
          f"作者偏倚声明在 | 「修不到生产」在 | "
          f"★★★题级重算(伪重复更正, p 0.00129→0.01562) · 尝试账本 268 · "
          f"**8 组里 1 个负例组(仅收藏)方向反转** 三者均已钉住 | "
          f"**无本机素材时的降级分支实跑 {d4} 条**(不靠读代码推断) | {n} 条反向验证判红)")
