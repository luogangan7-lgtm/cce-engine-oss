#!/usr/bin/env python3
"""§44.9 P5 的验收 gate: 任一历史 run 可按 run_id 完整重建其 manifest 与 artifacts。

文档指定的反向测试: 删一个 artifact, 重建必须失败而不是静默补空。
"""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cce_archive as A  # noqa: E402

INDEX = json.load(open(os.path.join(ROOT, "config", "cce_archive_index.json"), encoding="utf-8"))
ARCHIVED = sorted(r for r, row in INDEX["runs"].items() if row["status"] == A.LOCALLY_ARCHIVED)

# ── 正向: 闸绿, 且确有可重建的 run ─────────────────────────────────────
ok, errors, stats = A.check()
assert ok, f"基线: Archive 闸必须通过: {errors}"
assert ARCHIVED, "必须至少有一个本地可重建的 run, 否则这条 gate 无从验证"
for rid in ARCHIVED:
    r = A.rebuild(rid)
    assert r["run_id"] == rid and r["verified_sha"] and r["manifest"], rid
    assert r["artifacts"], f"{rid} 重建出来一个 artifact 都没有"

# ── 反向 1(文档指定): 删一个 artifact -> 必须失败, 不许静默补空 ────────
rid = ARCHIVED[0]
src = os.path.join(A.ARCHIVE_DIR, rid)
with tempfile.TemporaryDirectory() as td:
    alt_root = os.path.join(td, "archive")
    shutil.copytree(src, os.path.join(alt_root, rid))
    listing = json.load(open(os.path.join(alt_root, rid, "_listing.json"), encoding="utf-8"))
    victim = sorted(n for n in listing["files"] if n != "_listing.json")[0]
    os.remove(os.path.join(alt_root, rid, victim))
    try:
        got = A.rebuild(rid, archive_dir=alt_root)
    except A.ArchiveRebuildError as exc:
        assert victim in str(exc) and "不静默补空" in str(exc)
    else:
        raise AssertionError(f"★ 反向失败: 删了 artifact {victim} 却重建成功 -> {got['artifacts']}")

# ── 反向 2: artifact 内容被改 -> 也必须失败(不只是「文件在不在」) ───────
with tempfile.TemporaryDirectory() as td:
    alt_root = os.path.join(td, "archive")
    shutil.copytree(src, os.path.join(alt_root, rid))
    listing = json.load(open(os.path.join(alt_root, rid, "_listing.json"), encoding="utf-8"))
    victim = sorted(n for n in listing["files"] if n != "_listing.json")[0]
    with open(os.path.join(alt_root, rid, victim), "ab") as fh:
        fh.write(b"\n# tampered\n")
    try:
        A.rebuild(rid, archive_dir=alt_root)
    except A.ArchiveRebuildError as exc:
        assert "内容变了" in str(exc)
    else:
        raise AssertionError("★ 反向失败: artifact 内容被改却重建成功 —— 只查了文件存在与否")

# ── 反向 3: 未归档的 run 不许返回空壳 ─────────────────────────────────
try:
    A.rebuild("39999999999")
except A.ArchiveRebuildError as exc:
    assert "不返回空壳" in str(exc)
else:
    raise AssertionError("★ 反向失败: 从没归档过的 run 也能「重建」")

# ── 反向 4: 长期学习链不得建在会过期的东西上 ──────────────────────────
for mech_id, ref in A.evidence_refs_in_registries():
    assert not A.RUN_ID.fullmatch(str(ref)), \
        f"★ 机制 {mech_id} 直接引用 run_id {ref} —— GitHub artifact 会过期"
    assert os.path.exists(os.path.join(ROOT, ref)), f"机制 {mech_id} 的证据 {ref} 本地不存在"
assert stats["evidence_refs"] >= 14

# ★ 2026-09-27 根因修复: 反向 4-6 以前**原地改写** config/mechanism_registry.json、往 docs/ 写探针文件再还原。
#   runsuite 8 路并行时, test_cce_mechanism_registry 恰好在改写窗口里读到 reverse_probe ⇒「并行红/串行绿」
#   (两次「并行红 1 / 真红 0」查不出是谁, 2026-09-27 runsuite 点名后定位到这里)。改写窗口里读 docs/ 的闸同样会被探针污染。
#   ⇒ 反向探针只注入 check() 的两个读取层, 共享树一个字节不碰; 读取层本身「真读登记表 / 真 walk 到 docs/*.md」另由只读断言守(下两行)。
_orig_refs, _orig_scan = A.evidence_refs_in_registries, A.scan_referenced_run_ids
_live = _orig_scan()
assert any(s.startswith("docs/") and s.endswith(".md") for v in _live.values() for s in v), "★ 扫描没走进 docs/*.md —— 反向 5/6 的注入就失去了对照"
assert "tests/test_cce_archive_plane.py" in _live.get("39999999999", []), "★ 扫描没读到本文件里的反向探针 id"


def _check_with(refs=(), sources=()):
    """在读取层追加 (mech_id, ref) 与 (run_id, 出处) 后跑真 check(); 不写任何文件。"""
    def scan():
        live = _orig_scan()
        for rid, src in sources:
            live[rid] = sorted(set(live.get(rid, [])) | {src})
        return live
    A.evidence_refs_in_registries = lambda: _orig_refs() + list(refs)
    A.scan_referenced_run_ids = scan
    try:
        return A.check()
    finally:
        A.evidence_refs_in_registries, A.scan_referenced_run_ids = _orig_refs, _orig_scan


# 反向: 造一条引 run_id 的机制, 闸必须红
ok2, errors2, _ = _check_with(refs=[("reverse_probe", "31306754953")])
assert not ok2 and any("run_id" in e for e in errors2), \
    "★ 反向失败: 机制直接引用 run_id 作证据, 闸却是绿的"

# ── 反向 5: 新出现的 run_id 不许静默不入册 ────────────────────────────
#    用一个**未登记**的 id, 否则测到的是「探针位置规则」而不是「未入册规则」。
FRESH = "3" + "1234567890"
assert FRESH not in INDEX["runs"] and FRESH not in INDEX["negative_test_run_ids"]
ok3, errors3, _ = _check_with(sources=[(FRESH, "docs/_archive_reverse_probe.md")])
assert not ok3 and any(FRESH in e and "未入归档索引" in e for e in errors3), \
    f"★ 反向失败: 新 run_id 被引用却没入册, 闸是绿的: {errors3}"

# ── 反向 6: 反向探针 id 只许出现在本文件里 ────────────────────────────
ok4, errors4, _ = _check_with(sources=[("39999999999", "docs/_archive_reverse_probe2.md")])
assert not ok4 and any("只许出现在" in e for e in errors4), \
    "★ 反向失败: 把反向探针 id 抄到别处也照样绿 —— 那「登记一下」就成了绕闸的办法"
assert A.check()[0] and A.scan_referenced_run_ids is _orig_scan, "注入必须还原"

# ── 已发生的损失必须如实登记, 不许留一份「看起来完整」的索引 ───────────
# 2026-09-03 大幅更正: 原「32 个 run 全部不可重建」是**查错仓**得出的 ——
# 只查了私仓 cce-engine, 而生产入口 2026-08-17 起在公开仓 cce-engine-oss。
# 换仓复查后 23 个 run 仍活着, 已全部取回落档。
assert stats["irrecoverable"] == 19, stats
assert stats["locally_archived"] >= 28, stats
# ★ P3 首次生产运行必须在册: 它是「P3 进生产」这句话的证据本身
_p3 = INDEX["runs"].get("33743931309")
assert _p3 and _p3["status"] == "LOCALLY_ARCHIVED", "★ P3 首次生产运行未入册"
assert "complete=true" in _p3["reason"] and "首次生产运行" in _p3["reason"]
A.rebuild("33743931309")   # 必须真能重建
# ★ 2026-09-03: 26 -> 25。archive/31993570335 的 actor_ref 是两个真实论坛 handle,
#   已整目录移出仓库树(RESTRICTED_OFFTREE)。本仓可 fast-forward 到**公开仓**,
#   含真名的产物不得留在树内; 但**不就地改写以求过闸** —— 改写破坏字节保真,
#   宁可它不在树里, 不可它在树里却是假的。
_r = INDEX["runs"]["31993570335"]
assert _r["status"] == "RESTRICTED_OFFTREE" and _r.get("location"), _r
assert "不就地改" in _r["★why_not_pseudonymize"] or "字节保真" in _r["★why_not_pseudonymize"]
assert not os.path.isdir(os.path.join(ROOT, "archive", "31993570335")), \
    "★ 含真实身份的归档又回到树里了"

# ── 仓外归档: 只登「文件名 + sha256」, 内容与真名一律不越界 ─────────────
#    ★ 为什么登: 保险库副本损坏或丢失时, 仓里要能证明它本该是什么。
#    ★ 为什么只登哈希: 识别层的设计原则是「风险不在存, 在**流出**」——
#      推到任何远端(私库也算)都是流出, 私有与否只改变谁能看见。
import re as _re
_off = {r: v for r, v in INDEX["runs"].items() if v["status"] == "RESTRICTED_OFFTREE"}
assert _off, "★ 至少应有一条仓外归档(否则本段检查恒绿)"
for _rid, _row in _off.items():
    _lst = _row.get("offtree_listing")
    assert _lst and _row.get("offtree_file_count") == len(_lst), \
        f"★ {_rid} 缺 offtree_listing 或件数对不上"
    for _n, _h in _lst.items():
        assert _re.fullmatch(r"[0-9a-f]{16}", _h), f"★ {_rid}/{_n} 哈希形态不对"
        # 文件名本身要进公开仓, 必须是**已知的产物命名形状**。
        # ★ 用白名单不用黑名单: 黑名单式的「不许含 XXX」**必须把 XXX 写进仓里**,
        #   我在本轮已因此四次把真名抄进记录。白名单不需要点名任何人。
        assert _re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,200}", _n), \
            f"★ {_rid} 的归档文件名不是已知产物形状: 只允许字母数字与 _ . - "
        assert _n.startswith(("cce-", "probe-out", "workflow-")) or _n == "manifest.json", \
            f"★ {_rid} 出现非产物命名的文件 —— 只允许 cce-* / probe-out* / workflow-* / manifest.json"
    assert "现场重算" in _row["★why_listing_here"], \
        "★ 必须写明哈希是现场重算的 —— 照抄 _listing 只能证明它自洽, 证明不了它没漂"
assert "查错了仓" in INDEX["finding"], "更正必须写在 finding 里, 不能悄悄改数字"

# ── 反向 7: ★「不可恢复」缺出处 / 漏查一个 push 远端 -> 必须红 ──────────
#    这条闸就是为上面那次更正而设: 只查一个仓得出的「不可恢复」不是结论。
import copy, json as _json, tempfile, os as _os

def _alt(mut):
    idx = copy.deepcopy(INDEX)
    mut(idx)
    fd, tmp = tempfile.mkstemp(suffix=".json"); _os.close(fd)
    _json.dump(idx, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    orig = A.INDEX
    try:
        A.INDEX = tmp
        return A.check()
    finally:
        A.INDEX = orig; _os.unlink(tmp)

_dead = next(r for r, v in INDEX["runs"].items() if v["status"] == "IRRECOVERABLE")

ok7a, e7a, _ = _alt(lambda i: i["runs"][_dead].pop("checked_against"))
assert not ok7a and any("没写 checked_against" in x for x in e7a), \
    "★ 不写在哪儿查的就断言不可恢复 —— 必须红"

ok7b, e7b, _ = _alt(lambda i: i["runs"][_dead].update(
    {"checked_against": ["luogangan7-lgtm/cce-engine"]}))
assert not ok7b and any("漏查了 push 远端" in x for x in e7b), \
    "★ 只查一个仓 —— 必须红(这正是 2026-09-03 那次错的形状)"

ok7c, e7c, _ = _alt(lambda i: i["runs"][_dead].pop("checked_at"))
assert not ok7c and any("没写 checked_at" in x for x in e7c), \
    "★ 可用性会随时间变, 无日期的判定不可复核"

# ★ 2026-09-28 (诊断 #29): 取自公开远端的 RESTRICTED_OFFTREE 必须登记公开副本已清 —— 移出树不等于没了
_pub = next(r for r, v in INDEX["runs"].items()
            if v["status"] == "RESTRICTED_OFFTREE" and v.get("recovered_from") in INDEX["public_remotes"])
ok8a, e8a, _ = _alt(lambda i: i["runs"][_pub].pop("public_copies_cleared"))
assert not ok8a and any("公开副本已清" in x for x in e8a), "★ 公开 artifact/日志可能还在 —— 必须红"
ok8b, e8b, _ = _alt(lambda i: i["runs"][_pub]["public_copies_cleared"].update({"artifacts_remaining": 2}))
assert not ok8b, "★ 公开远端还剩 artifact —— 必须红"
# 统计口径: 此前第二个 `live` 遮蔽了第一个, referenced 数的是远端个数
assert stats["referenced"] == len(set(A.scan_referenced_run_ids()) - set(INDEX["negative_test_run_ids"])) > 2, stats

# ★ 2026-09-28: --pull(archive_run 的第一个调用方)落树前过化名闸 —— 与入口同一份规则
_fake = "u/" + "zq_realhandle_77"   # 构造名; 拆开写, 否则本文件自己就会被保险库的提及闸判成泄露源
assert A._identity_hits("m.json", ('{"reader": {"actor_ref": "reddit:%s"}}' % _fake).encode()) >= 1   # 身份位 + 文本提及各算一次
assert A._identity_hits("m.json", b'{"reader": {"actor_ref": "reddit:u/user_4"}}') == 0
assert A._identity_hits("log.txt", ("thanks %s for this" % _fake).encode()) == 1
assert A._identity_hits("log.txt", b"thanks u/user_12") == 0

# ★ 2026-09-03 CI 实跑更正: 原断言是 `set(A.push_remotes()) >= {两个仓}` ——
#   那是把**我这台机器的 git 配置**当成了全局不变量。CI 的 checkout 只有一个 remote,
#   于是 ①测试在 CI 上必红 ②闸本身在 CI 上自动变松(「全部 push 远端」缩水成「那一个」)。
#   **检查的强度不该取决于它在哪台机器上跑。** 改为断言**索引里的声明**。
assert set(INDEX["required_remotes"]) == {"luogangan7-lgtm/cce-engine",
                                          "luogangan7-lgtm/cce-engine-oss"}, INDEX.get("required_remotes")
assert "不该取决于它在哪台机器上跑" in INDEX["★why_required_remotes_declared"]
# 本机若多出未声明的 remote, 闸必须红(否则会有一个从没查过的仓)
ok7d, e7d, _ = _alt(lambda i: i.__setitem__("required_remotes", ["luogangan7-lgtm/cce-engine"]))
if set(A.push_remotes()) - {"luogangan7-lgtm/cce-engine"}:
    assert not ok7d and any("未声明的 push 远端" in x for x in e7d), \
        "★ 本机多出的 remote 没被要求补进声明"

print(f"test_cce_archive_plane: OK "
      f"(可重建 {len(ARCHIVED)} run · 不可恢复 {stats['irrecoverable']} 已如实登记, "
      f"两仓复查 {INDEX['required_remotes']}(声明值, 非本机现读) | "
      "删件/改件/未归档/引 run_id 作证据/新 run 不入册/不可恢复缺出处或漏查仓 —— 各自见红)")
