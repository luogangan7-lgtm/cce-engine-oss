#!/usr/bin/env python3
"""去重「被并掉」≠「被丢掉」—— 现算, 不靠自觉。

## 为什么有这个文件
`scripts/cce_open_items.py` 的去重按**主题词**保留证据最长的一条, 并在末尾自报
「并掉了 N 条」, 还自己写下了判据:

    「被并掉的不代表不存在, 只代表它的内容应当能在同主题那条里读到。
      ★★ 若某条的内容在同主题那条里**读不到**, 那就是被静默丢了。」

**它写了判据, 但没人在算。** 2026-09-11 逐句核了被并掉的三条, 三条全部读不到 ——
它们是注册表 missing 条目, 而 OPEN 类的证据只写 `status=...`、「项」只截 64 字
⇒ 一旦被并掉, **原文在输出里一个字都不剩**。实测丢掉的实质信息:

  · 根因句 `speech = audio.present` 把「素材本就无口播(空转写是对的)」
    与「ASR 失败(空转写是错的)」压成一个 true —— 幸存那条只写「判定已修为五态」,
    **只有结论没有根因**(本仓最敏感的那种伪修复形状)
  · 正确的界是 **<0.15 字/秒**, 错的界是 **<20 字** —— 幸存那条只说「按字/秒」, 没有数
  · 语言/密度 **2.84 倍**、录音难度 **4.96 倍** 的出处 `tests/data/phase2/transfer_across_conditions.json`
  · 「要测域需每域 >=30 份, **现有真实素材仅 6 张分 3 类**」—— 差距没了
  · 「**缺陷本身与规模无关, 修法照旧**」—— 没有这句, 「罕见(2 份)」会被读成「不用修」
  · 「**历史产物未按新判定重跑**」—— 一件真的没做完的事整条消失
  · 这个缺口**同时属于 `standalone_image_ingest`** —— 幸存那条是链路阶段 P3, 不提它

## 修法(已落在被守脚本里)
按该脚本自己给的两条处方取第一条「**把内容并进去**」: 去重时把被并掉那条的
**原文逐字追加**到幸存条目的证据里(前缀「★ 并入同主题条目」)。
不改任何一条条目的措辞与分类 —— 只是把文字搬过去。

## 本文件守什么(三条, 全部**现算**)
① 每条被并掉的条目, 它原文里的**每一句**与**每一个带数字的记号**都必须在最终清单里读得到
   —— 断言锚在**值**上(句子原文 / `2.84` / `<0.15` / 文件路径), **不锚键名**。
② 末尾那条自报的「并掉了 N 条」逐条列出的每一项, 都必须真的有一处「并入」痕迹。
③ 合计数 = 三类逐类之和, 且不存在第四类(否则逐类相加对不上合计)。
④ 反向: 两处变异(去掉合并 / 去掉原文承载)必须让①判红 —— 恒绿的闸不是闸。

## 离线
本文件只读仓内 JSON 与 .py, 零网络。进程内装 socket 绊线并在末尾断言未被触发。
"""
import io
import json
import os
import re
import socket
import sys
import types

# ── R1 离线绊线: 任何新建连接都判红 ─────────────────────────────────
_TRIPPED = []
_ORIG_CONNECT = socket.socket.connect


def _guard(_s, addr, *a, **k):
    _TRIPPED.append(addr)
    raise AssertionError(f"★★★ 离线隔离被突破: {addr}")


socket.socket.connect = _guard

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "scripts", "cce_open_items.py")
REG = os.path.join(ROOT, "config", "cce_capability_registry_v1.json")
CAPS = json.load(io.open(REG, encoding="utf-8"))["capabilities"]
OPEN, BLOCKED, DECIDED = "OPEN_WORK", "BLOCKED_EXTERNAL", "DECIDED_NOT_DOING"

# 带数字的记号(阈值/倍数/路径/文件名) —— 这些是「读不到」最先蒸发的东西
_TOK = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./%-]*[A-Za-z0-9%]")


def _values(s):
    return sorted({t for t in _TOK.findall(s)
                   if len(t) >= 3 and any(ch.isdigit() for ch in t)})


def _sentences(s):
    return [p.strip() for p in re.split(r"[。;；]", s) if len(p.strip()) >= 12]


def _run(mutator=None):
    """内存内 exec 被测源码。**仓里文件一字不改** —— 变异只作用于内存字符串。"""
    src = io.open(SRC, encoding="utf-8").read()
    if mutator is not None:
        new = mutator(src)
        assert new != src, "★ 变异没生效 —— 锚变了, 反向测试会假绿。先修锚, 不许放过"
        src = new
    mod = types.ModuleType("open_items_probe")
    mod.__file__ = SRC                      # ★ 让被测代码推出的 ROOT 与真仓一致
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    try:
        exec(compile(src, SRC, "exec"), mod.__dict__)
        return mod.items()
    finally:
        sys.path.remove(os.path.join(ROOT, "scripts"))


def silently_lost(rs):
    """**现算**: 注册表里每条 missing, 若它没有以自己的名义出现在清单里(= 被并掉了),
    它的每一句与每一个带数字的记号就必须在清单**别处**读得到。读不到 = 被静默丢了。"""
    text = "\n".join(r["项"] + " " + r["证据"] for r in rs)
    titles = {r["项"] for r in rs}
    lost = []
    for c in CAPS:
        for m in (c.get("missing") or []):
            if f"{c['id']}: {m[:64]}" in titles:
                continue                                  # 没被并掉, 自己还在
            gone_s = [p for p in _sentences(m) if p not in text]
            gone_v = [v for v in _values(m) if v not in text]
            if gone_s or gone_v:
                lost.append({"item": f"{c['id']}: {m[:48]}",
                             "lost_sentences": gone_s[:4], "lost_values": gone_v[:8]})
    return lost


rs = _run()
assert rs, "★ 清单为空 —— 下面所有检查都会空过"

# ── ① 被并掉的条目, 内容必须读得到 ────────────────────────────────
_lost = silently_lost(rs)
assert not _lost, (
    "★★★ 去重把内容**静默丢了** —— 这些条目被并掉了, 但它们的实质信息在幸存条目里读不到:\n"
    + "\n".join(f"  · {d['item']}\n      丢句: {d['lost_sentences']}\n"
                f"      丢值: {d['lost_values']}" for d in _lost)
    + "\n  ⇒ 修法(被守脚本自己写的, 二选一): 把内容**并进去**, 或给它换一个不同的主题词。"
      "\n  ⇒ **不要**改这个闸去迁就 —— 判据是被守脚本自己立的。")

# ★ 这条检查不能是空过的: 必须真的有条目被并掉, 否则上面恒真
_merged_n = sum(1 for c in CAPS for m in (c.get("missing") or [])
                if f"{c['id']}: {m[:64]}" not in {r["项"] for r in rs})
assert _merged_n >= 1, ("★ 一条都没被并掉 ⇒ 上面那条断言是**空过**的。"
                        "若去重真的不再合并任何条目, 本闸该改成断言「不再有合并」, 而不是留着恒绿")

# ── ② 自报的「并掉了 N 条」, 每一条都要有并入痕迹 ──────────────────
_mark = [r for r in rs if "并掉了" in r["项"]]
assert len(_mark) == 1, f"★ 找不到(或不止一条)去重自述 —— 自述是 ② 的锚: {[r['项'] for r in _mark]}"
_n = int(re.search(r"并掉了\s*(\d+)\s*条", _mark[0]["项"]).group(1))
_listed = re.search(r"\*\*逐条列出\*\*:\s*(.+?)\s*★★", _mark[0]["证据"], re.S).group(1)
_entries = [e.strip() for e in _listed.split(" | ") if e.strip()]
assert len(_entries) == _n, f"★ 自述说并掉 {_n} 条, 实际列出 {len(_entries)} 条"
assert _n == _merged_n, f"★ 自述 {_n} 条, 现算被并掉 {_merged_n} 条 —— 自述与事实不符"
_evid = "\n".join(r["证据"] for r in rs if r is not _mark[0])
for _e in _entries:
    _title = re.sub(r"^\[[A-Z_]+\]\s*", "", _e)
    assert f"并入同主题条目「{_title}" in _evid, \
        f"★★ 自述列了「{_title[:40]}…」被并掉, 但清单里找不到它的并入痕迹 —— 那就是只列名没搬内容"

# ── ③ 合计 = 逐类之和, 且没有第四类 ───────────────────────────────
_tally = {k: sum(1 for r in rs if r["类"] == k) for k in (OPEN, BLOCKED, DECIDED)}
assert {r["类"] for r in rs} <= {OPEN, BLOCKED, DECIDED}, \
    f"★ 出现了第四类 ⇒ 逐类相加必然对不上合计: {{r['类'] for r in rs}}"
assert sum(_tally.values()) == len(rs), \
    f"★★ 合计对不上: 逐类 {_tally} 相加 = {sum(_tally.values())}, 合计报 {len(rs)}"

# ── ④ 反向: 两处变异必须让 ① 判红 ────────────────────────────────
_A = '            _add = f" ★ 并入同主题条目'
_B = "            continue                      # 同主题已有证据更细的一条"


def _mut_no_merge(s):
    """变异一: 去掉「并进去」这一步, 退回 2026-09-11 之前的纯丢弃。"""
    i, j = s.index(_A), s.index(_B)
    assert i < j, "★ 锚 A/B 顺序变了"
    return s[:i] + s[j:]


def _mut_no_source(s):
    """变异二: 保留合并动作, 但不再承载原文 ⇒ 并进去的只剩 `status=...`, 内容照样没了。"""
    return s.replace('                        "原文": m,\n', "", 1)


_reverse = []
for _name, _mut in (("去掉合并动作", _mut_no_merge), ("去掉原文承载", _mut_no_source)):
    _l = silently_lost(_run(_mut))
    _reverse.append((_name, bool(_l), len(_l)))
    assert _l, f"★★★ 反向失败: 变异「{_name}」后 ① 仍然绿 ⇒ 这个闸是恒绿的, 它什么都没守"

# ★ 变异只在内存里 —— 仓里的源码必须一字未动
assert io.open(SRC, encoding="utf-8").read().count(_A) == 1, "★ 变异写回了仓里源码"

socket.socket.connect = _ORIG_CONNECT
assert not _TRIPPED, f"★★★ 本闸发了网络请求: {_TRIPPED}"

print("test_cce_open_items_dedup_no_silent_loss: OK "
      f"(现算 {_merged_n} 条被并掉的条目 · 每句与每个带数字记号都在清单里读得到 | "
      f"自述 {_n} 条逐条都有并入痕迹 | 合计 {len(rs)} = "
      f"OPEN {_tally[OPEN]} + BLOCKED {_tally[BLOCKED]} + DECIDED {_tally[DECIDED]} | "
      f"反向两条实测见红: {_reverse} | 零网络, 绊线未触发)")
