#!/usr/bin/env python3
"""reply_loop 两侧读数并行化的唯一自检。

只防一件事: 并行化把 (文本, tag) 配错。
串行版配错会被人眼看出来; 并行版配错是静默的——A_reader 拿到草稿、
B_draft 拿到对方原文, 对齐分照样算得出来, 只是在拿草稿跟草稿比。

顺带确认两侧确实并发(而不是被 max_workers 或 .result() 顺序退化回串行)。
"""
import os, sys, json, time, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
os.environ.setdefault("MINIMAX_API_KEY", "test-not-used")
import reply_loop

CALLS = []


def fake_readout(text, context, k, tag, outdir):
    rec = {"tag": tag, "text": text, "start": time.monotonic()}
    CALLS.append(rec)                     # 不能用 CALLS[-1] 回写: 两线程会写到对方的记录上
    time.sleep(0.5)                       # 模拟一次模型往返
    rec["end"] = time.monotonic()
    n = 4
    return {"stage1": {"layers": {L: [1.0] + [0.0] * (n - 1) for L in reply_loop.LAYERS}},
            "stage2": {"knots": [{"key": "display", "weight": 1.0}]}}


def fake_align(a, b, text, mode="post"):
    return {"alignment_score": 1.0, "resonance": 1.0, "dissolution": 0.0, "detail": []}


def main():
    reply_loop.readout = fake_readout
    reply_loop.knot_align = fake_align
    # 四层标签数与 fake_readout 的向量长度对齐, 否则 zip 会静默截断
    reply_loop.LAYERS = {L: ["d0", "d1", "d2", "d3"] for L in reply_loop.LAYERS}

    d = tempfile.mkdtemp()
    reader_f, draft_f, out_f = (os.path.join(d, x) for x in ("r.txt", "w.txt", "o.json"))
    open(reader_f, "w").write("READER SIDE")
    open(draft_f, "w").write("DRAFT SIDE")

    sys.argv = ["reply_loop.py", "--reader", reader_f, "--draft", draft_f,
                "--context", "t", "--out", out_f]
    t0 = time.monotonic()
    reply_loop.main()
    wall = time.monotonic() - t0

    by_tag = {c["tag"]: c for c in CALLS}
    assert set(by_tag) == {"A_reader", "B_draft"}, f"读数侧数量或命名不对: {list(by_tag)}"
    assert by_tag["A_reader"]["text"] == "READER SIDE", "A_reader 拿到的不是对方原文"
    assert by_tag["B_draft"]["text"] == "DRAFT SIDE", "B_draft 拿到的不是我方草稿"

    overlap = (min(by_tag["A_reader"]["end"], by_tag["B_draft"]["end"])
               - max(by_tag["A_reader"]["start"], by_tag["B_draft"]["start"]))
    assert overlap > 0, f"两侧读数没有并发(重叠 {overlap:.3f}s), 退回串行了"
    assert wall < 0.9, f"总墙钟 {wall:.2f}s 接近串行的 1.0s"

    v = json.load(open(out_f))["verdict"]
    assert "九结对齐" in v and "四层触达" in v, "输出结构变了"
    print(f"OK reply_loop 并行: 重叠 {overlap:.2f}s, 墙钟 {wall:.2f}s (串行下限 1.0s)")


if __name__ == "__main__":
    main()
