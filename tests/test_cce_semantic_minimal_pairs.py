# -*- coding: utf-8 -*-
"""五类语义关系最小对照 + 验证器盲区扫描的闸。

★★★ 这份东西**只是度量**, 不是改进。它回答的是: 现有验证器在**每一类**语义关系上漏多少。
★★★ 它测的是**验证器的语义盲区**, **不是**模型的错误率 —— 证书是手构探针, 不经模型。
"""
import difflib, importlib.util, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SRC = ROOT / "tests/data/semantic_minimal_pairs.json"
RES = ROOT / "results/semantic_blindspot_scan.json"
PROBE = ROOT / "probes/semantic_blindspot_scan.py"
CLASSES = {"否定辖域", "归属", "时态", "引用层级", "类型成员资格"}
MX = "**合同明文**"
IN = "**解释(合同没明说)**"


def _d():
    return json.loads(SRC.read_text(encoding="utf-8"))


def _probe():
    spec = importlib.util.spec_from_file_location("blindspot", PROBE)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_五类各两对_且类名与冻结集合一致():
    P = _d()["pairs"]
    got = {}
    for p in P:
        got[p["cls"]] = got.get(p["cls"], 0) + 1
    assert set(got) == CLASSES, "★ 关系类集合变了: %r" % sorted(got)
    assert all(v == 2 for v in got.values()) and len(P) == 10, "★ 每类应 2 对, 共 10 对: %r" % got
    ids = [p["id"] for p in P]
    assert len(set(ids)) == len(ids)


def test_每条的span与object都逐字在各自文本里():
    for p in _d()["pairs"]:
        for side in ("pos", "neg"):
            t = p[side]["text"]
            for k in ("A", "B"):
                sp, ob = p[side][k][0], p[side][k][1]
                assert sp in t, "★%s.%s.%s span 非逐字: %r" % (p["id"], side, k, sp)
                assert ob in t, "★%s.%s.%s object 非逐字: %r" % (p["id"], side, k, ob)


def test_差异必须最小_否则测的就不是那个关系():
    """★★★ 最小对照的**全部**严谨性在这里: 两版若差别太大, 验证器放行就不能归因于目标关系。"""
    for p in _d()["pairs"]:
        a, b = p["pos"]["text"].split(), p["neg"]["text"].split()
        ops = [o for o in difflib.SequenceMatcher(None, a, b).get_opcodes() if o[0] != "equal"]
        words = sum(max(o[2] - o[1], o[4] - o[3]) for o in ops)
        assert len(ops) <= 2, (
            "★★★ %s 有 %d 个编辑区间 —— 超过 2 个就很难说两版**只**在目标关系上不同"
            % (p["id"], len(ops)))
        assert words <= 6, (
            "★★★ %s 改动了 %d 个词 —— 差异过大, 放行不能归因于「%s」这个关系"
            % (p["id"], words, p["cls"]))


def test_依据分层完整_解释类必须带推翻条件():
    """★ 我已经三次把**读法**说成**字面**(五类是闭列 / L1-L3 只依赖合同 / 批不变内核只存在于自托管)。
    这里逐条标依据, 且**解释类**必须自带推翻条件。"""
    d = _d()
    layer = [k for k in d if k.startswith("★★★依据分层")][0]
    assert MX in d[layer] and IN in d[layer], "★ 依据分层两档都要在"
    mx_cls, in_cls = {"否定辖域", "归属", "时态"}, {"引用层级", "类型成员资格"}
    for p in d["pairs"]:
        if p["cls"] in mx_cls:
            assert p["依据"] == MX, "★ %s(%s) 应标为合同明文" % (p["id"], p["cls"])
        else:
            assert p["cls"] in in_cls and p["依据"] == IN, (
                "★ %s(%s) 应标为依赖解释" % (p["id"], p["cls"]))
            assert "推翻条件" in p["推导"] and "自动作废" in p["推导"], (
                "★★★ %s 依赖解释却没写推翻条件 —— 那就又把读法当字面了" % p["id"])


def test_每对都写了验证器为什么看不见():
    for p in _d()["pairs"]:
        k = [x for x in p if "验证器为什么看不见" in x]
        assert k and p[k[0]].strip(), "★ %s 没写验证器为什么看不见" % p["id"]


def test_扫描结果由冻结判据现算():
    """不许把结论手写进档案 —— 用 probe 自己的 judge() 现跑一遍比对。"""
    if not RES.exists():
        return
    import cce_label_qualification as LQ
    m = _probe()
    res = json.loads(RES.read_text(encoding="utf-8"))
    rows = {r["id"]: r for r in res["rows"]}
    for p in _d()["pairs"]:
        r = rows[p["id"]]
        for side in ("pos", "neg"):
            st, _ = m.judge(p[side]["text"], p[side]["A"], p[side]["B"])
            assert r[side]["state"] == st, (
                "★ %s.%s 档案 state %r 与现算 %r 不符" % (p["id"], side, r[side]["state"], st))
            assert r[side]["通过"] == (st == LQ.CITED_UNVERIFIED)
        assert r["★错误放行"] == r["neg"]["通过"]
        assert r["★对照有效"] == r["pos"]["通过"]
    leak = sum(r["★错误放行"] for r in res["rows"])
    ctrl = sum(r["★对照有效"] for r in res["rows"])
    assert res["★★★合计"]["错误放行"] == "%d/%d" % (leak, len(res["rows"]))
    assert res["★★★合计"]["对照有效"] == "%d/%d" % (ctrl, len(res["rows"]))


def test_对照无效的对必须被单列为退化():
    """★ pos 版若没通过, 那一对**什么都测不出** —— 不能混进「错误放行」的分母里当成绩。"""
    if not RES.exists():
        return
    res = json.loads(RES.read_text(encoding="utf-8"))
    bad = [r["id"] for r in res["rows"] if not r["★对照有效"]]
    k = [x for x in res if "退化的对" in x][0]
    assert res[k] == (bad or "无"), "★ 退化清单与现算不符: 档案 %r vs 现算 %r" % (res[k], bad)


def test_产物自带怎么读_不许被当成模型错误率():
    if not RES.exists():
        return
    res = json.loads(RES.read_text(encoding="utf-8"))
    v = res["★★★怎么读"]
    assert "不是模型的错误率" in v and "不得当成误报率" in v, (
        "★★★ 缺「这是验证器盲区不是模型错误率」的声明 —— "
        "半年后只读这份文件的人会把 10/10 读成模型 100% 出错")
    assert "★零调用" in res and "不发起任何模型调用" in res["★零调用"]
    assert "★★★依据分层" in res


def test_度量必须被证明能观察到改进():
    """★★★ 一个恒报 10/10 的度量测不出任何改进 —— 那样它就是个假基线。
    产物必须带**镜像变异实测**: 加一条只拦某一类的规则后, 那一类应当降下来而其余不动。"""
    if not RES.exists():
        return
    res = json.loads(RES.read_text(encoding="utf-8"))
    k = [x for x in res if "度量灵敏度" in x]
    assert k, "★★★ 没有灵敏度证明 ⇒ 这个 10/10 不能当基线用"
    v = res[k[0]]
    assert "镜像" in json.dumps(v, ensure_ascii=False) and "未动仓" in k[0]
    got = v["结果"]
    assert "10/10" in got["基线"] and "8/10" in got["加了只拦否定辖域那一条"], (
        "★ 灵敏度结果不符: %r" % got)
    body = json.dumps(v, ensure_ascii=False)
    assert "其余四类" in body and "错觉" in body, (
        "★★★ 必须写明「补一类会留着其余四类却制造已关住的错觉」—— "
        "那是这份逐类表存在的理由")
    assert "不是建议加那条规则" in body or "仍然被库内禁止" in body, (
        "★ 必须写明镜像变异**不是**在建议真加否定词正则")


def test_probe零调用_不碰任何模型入口():
    src = PROBE.read_text(encoding="utf-8")
    for bad in ("call_model", "MINIMAX", "requests.post", "_load_key"):
        assert bad not in src, "★★★ 盲区扫描里出现了模型调用入口 %r —— 它必须零调用" % bad


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("语义最小对照闸 %d 项全过 —— ★这只是度量, 不是改进" % n)
