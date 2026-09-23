# -*- coding: utf-8 -*-
"""r5 预注册草案**已被否决**这件事的闸 —— 与 tests/test_cce_refusal_gradient_r3.py 同例。

★★★ 它守的不是「这个设计好不好」, 而是三件:
  ① 这版**从未投料**, 且文件名/状态必须一直说得清楚;
  ② 30 条 BLOCKING 的**根因归纳**不许被删或稀释;
  ③ ★★★ 最要紧的一条 —— **不许把「已修四条」读成「草案已可用」**。
     决定性的否决理由(信号量只有 2 格)**没修, 也修不了**, 它不是判据措辞问题。
"""
import json, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = ROOT / "tests/data/slot_filling_prereg_r5_REJECTED.json"
OLD = ROOT / "tests/data/slot_filling_prereg_r5_DRAFT.json"


def _d():
    return json.loads(DOC.read_text(encoding="utf-8"))


def test_草案已改名为REJECTED_旧名不许还在():
    assert DOC.exists(), "★ 否决留档不见了"
    assert not OLD.exists(), (
        "★★★ DRAFT 还在 ⇒ 下一个人会拿那份**已被 30 条 BLOCKING 否决**的草案去投料")
    assert _d()["block"].endswith("REJECTED")


def test_从未投料这件事必须写明():
    v = _d()["★★★状态"]
    assert "从未投料" in v and "零调用" in v, "★ 没写明这版一次调用都没发起"
    assert "280" in v and "BLOCKING 30" in v, "★ 评审规模与否决强度要写清楚"
    assert "留档不删" in v


def test_十条根因都在_且各自说清会导致什么():
    k = [x for x in _d() if "否决的根因" in x][0]
    r = _d()[k]
    assert len(r) >= 10, "★ 根因少于 10 条: %d" % len(r)
    for name, body in r.items():
        assert len(body) > 60, "★ 根因「%s」写得太短, 归纳不成立" % name


def test_决定性理由必须标明没修也修不了():
    """★★★ 这是本文件最要紧的一条。修掉四条真缺陷**不等于**这个设计变得可跑。"""
    d = _d()
    k = [x for x in d if "不许把这四条读成" in x][0]
    v = d[k]
    assert "决定性理由是 ③" in v, "★ 必须点名哪一条是决定性的"
    assert "没修, 也修不了" in v, (
        "★★★ 必须写明决定性理由**修不了** —— 否则下一个人会以为改改判据措辞就能投料")
    assert "只有 2 个正确答案" in v, "★ 必须写明根因是对照集的信号量, 不是判据写法"


def test_信号量那条根因必须带现算的数():
    k = [x for x in _d() if "否决的根因" in x][0]
    body = [v for n, v in _d()[k].items() if "信号量" in n]
    assert body, "★ 信号量那条根因不见了"
    v = body[0]
    for num in ("20 : 2 : 2", "20/24", "0.25"):
        assert num in v, "★ 缺现算的数 %r —— 没有数就只是个说法" % num
    assert "D6 判不动" in v, (
        "★★★ 必须写明 D6 在假说为真时也会印出「零增益」—— 那是这条根因最要命的部分")


def test_下一版的前提必须列出且标为未做():
    d = _d()
    k = [x for x in d if "下一版的前提" in x][0]
    assert "未做" in k, "★ 前提必须标明是未做的, 不许读成已具备"
    items = d[k]
    assert len(items) >= 6
    assert any("扩充" in i and "鉴别格" in i for i in items), (
        "★★★ 第一条前提必须是扩充对照对把信号量提上去 —— 那才是决定性根因的解法")
    assert any("浅层线索臂" in i for i in items)


def test_已修的四条必须逐条指向真实文件():
    d = _d()
    k = [x for x in d if "本轮已修的四条" in x][0]
    fixed = d[k]
    assert len(fixed) == 4
    for line in fixed:
        paths = re.findall(r"[\w./-]+\.(?:py|json|md)", line)
        assert paths, "★ 「%s」没指向具体文件" % line[:40]
        for p in paths:
            assert (ROOT / p).exists(), "★ 指向了不存在的文件: %s" % p


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("r5 草案否决闸 %d 项全过" % n)
