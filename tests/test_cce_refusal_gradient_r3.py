# -*- coding: utf-8 -*-
"""梯度设计(r3 初版)**已被否决且从未投料** —— 本文件从「守设计」改成「守否决」。

★ 库里铁律: 被否决的方案**必须留档带 reject_reason + superseded_by**,
  否则下一个 agent 会重做它。本项目实际发生过。
★ 原来的 12 道设计闸已作废 —— 它们守的是一个不该被运行的设计,
  而且其中**没有一道碰过 main()**(那正是它被否决时暴露的最大漏洞)。
"""
import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
P = ROOT / "tests/data/refusal_gradient_prereg_r3.json"
T = ROOT / "tests/data/refusal_gradient_templates_r3.json"
RUN = ROOT / "probes/refusal_gradient_run_r3.py"


def test_留档完整_status与reject_reason与superseded_by():
    d = json.loads(P.read_text(encoding="utf-8"))
    assert d["★★★status"].startswith("**REJECTED"), "★ 否决状态被改回去了"
    assert "未发起任何调用" in d["★★★status"], (
        "★ 必须写明**从未投料** —— 否则以后会有人以为它跑过、去引用它的读数")
    rr = [k for k in d if k.startswith("★★★REJECTED_reason")]
    assert rr, "★★★ 没写 reject_reason ⇒ 下一个 agent 会重做它"
    body = json.dumps(d[rr[0]], ensure_ascii=False)
    for must in ("断点判据", "轴不成立", "假声称", "换了维度", "共线",
                 "第四次「假保证」", "KeyError"):
        assert must in body, "★ reject_reason 里缺: %s" % must
    assert "superseded_by" in d[rr[0]] and "repeat_measure" in d[rr[0]]["superseded_by"]
    assert "★★★REJECTED" in json.loads(T.read_text(encoding="utf-8"))


def test_执行器入口封死():
    """★ 仓里每多一份**可运行**的分叉执行器, 就多一份**旧闸守不到**的代码。
    配对变异实测: 同一变异打 r2 文件被抓, 打这份分叉文件 96 道全绿。"""
    body = RUN.read_text(encoding="utf-8")
    assert "raise SystemExit" in body and "已被否决" in body, "★ 入口没封死"
    assert "def main()" in body and "\n    main()" not in body


def test_那个KeyError刻意留着当留证():
    """★ 它是「跑完 16 次才崩、而 12 道闸全绿」的物证。修掉它等于抹掉证据。"""
    body = RUN.read_text(encoding="utf-8")
    assert 'PREREG["★★★已知局限(两轮评审确认_测量前写下)"]' in body, (
        "★ 那处 KeyError 被修掉了 —— 它是留证, 应当保留并在 docstring 里说明")
    assert "刻意不修" in body


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); n += 1; print("  ✅", k)
    print("梯度设计否决留档闸 %d 项全过 —— ★该设计从未投料" % n)
