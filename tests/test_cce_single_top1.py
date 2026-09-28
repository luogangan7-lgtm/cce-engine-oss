#!/usr/bin/env python3
"""一条链只有一个 top-1(2026-09-28 诊断 #0)。

稳定闸判的是逐 draw argmax 的众数 sampling.top1_mode; 此前 playbook_primary / 不打分建议 / 标签资格取的是 knots[0]
(按出现时强度中位数排序)。存档 11 个 top1_stable 读数里 2 个 knots[0] ≠ top1_mode —— 发出去的打法属于另一个结。
"""
import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_full_run as F  # noqa: E402

base = json.loads((ROOT / "archive/33842088048/cce-subject-item-7-33842088048__s1_readout.json").read_text(encoding="utf-8"))
tmp = Path(tempfile.mkdtemp()); (tmp / "t.txt").write_text("text", encoding="utf-8")


def run_s2(cce):
    F.MANIFEST.clear()
    F.s2({"cce": cce, "text_file": str(tmp / "t.txt"), "outdir": str(tmp)})
    return F.MANIFEST["s2_knots"]


cce = copy.deepcopy(base)
k = cce["stage2"]["knots"]
mode = cce["stage2"]["sampling"]["top1_mode"]
assert cce["stage2"]["sampling"]["top1_stable"] is True and k[0]["key"] == mode
k[0], k[1] = k[1], k[0]                                  # knots[0] 不再是众数结 —— 存档里真实出现过的形状
assert k[0]["key"] != mode
out = run_s2(cce)
want = next(x for x in k if x["key"] == mode)
assert out["playbook_primary"] == want["playbook"][:120], "★ 发出的打法必须属于稳定闸判定的那个结"
assert out["label_qualification"]["knot"] == mode
assert out["playbook_primary"] != k[0]["playbook"][:120] or k[0]["playbook"] == want["playbook"]

cce["stage2"]["sampling"]["top1_stable"] = False          # 不稳 ⇒ 不发
assert run_s2(cce)["playbook_primary"] is None

print("test_cce_single_top1: OK (knots[0] ≠ top1_mode 时, playbook/标签资格跟随 top1_mode | 不稳不发)")

# ── s4 接上 P7 生成物闸(2026-09-28 诊断 #1) ──
import types  # noqa: E402
F.subprocess.run, _keep = (lambda *a, **k: types.SimpleNamespace(
    returncode=0, stdout=json.dumps({"clean": True, "clean_strict": True, "profile_rules_loaded": 13}), stderr="")), F.subprocess.run
try:
    for draft, ok in (("Plain reply with no citations.", True),
                      ("Display is high here [[knot_intensity:display=0.8]].", False)):
        (tmp / "d.txt").write_text(draft, encoding="utf-8")
        F.MANIFEST.clear()
        try:
            F.s4({"text_file": str(tmp / "d.txt"), "guard_profile": "hearing_aid"})
        except RuntimeError:
            pass
        st = F.MANIFEST["s4_guard"]
        assert (st["status"] == "OK") == ok, (draft, st)
        if not ok:
            assert "未达标" in st["error"], st
finally:
    F.subprocess.run = _keep
print("test_cce_single_top1: s4 OK (引用 K1 未达标强度读数的稿子在 s4 被拦)")

# ── s4 守卫不得在规则没装上时给 clean(2026-09-28 诊断 #10) ──
import subprocess  # noqa: E402
_reg = json.loads((ROOT / "config/outbound_guard_registry_v1.json").read_text(encoding="utf-8"))
for _prof in _reg["profiles"]:                           # 注册表里的每个品类, 守卫都真装上了规则
    _r = subprocess.run([sys.executable, str(ROOT / "scripts/cce_outbound_guard.py"), "-", f"--profile={_prof}", "--intl"],
                        input="Plain text.", capture_output=True, text=True)
    assert _r.returncode == 0 and json.loads(_r.stdout)["profile_rules_loaded"] > 0, (_prof, _r.stdout[:200])
_r = subprocess.run([sys.executable, str(ROOT / "scripts/cce_outbound_guard.py"), "-", "--profile=hearing_aids", "--intl"],
                    input="Plain text.", capture_output=True, text=True)
assert _r.returncode == 2 and json.loads(_r.stdout)["clean"] is False, "拼错的品类 key 必须拒绝, 不得只剩硬编层就报 clean"
(tmp / "d.txt").write_text("Plain text.", encoding="utf-8")
F.MANIFEST.clear()
try:
    F.s4({"text_file": str(tmp / "d.txt"), "guard_profile": "hearing_aids"})
except RuntimeError:
    pass
assert F.MANIFEST["s4_guard"]["status"] == "FAIL" and "未装上" in F.MANIFEST["s4_guard"]["error"]
print("test_cce_single_top1: s4 守卫 OK (注册表品类全部装上规则 | 未知品类 fail closed)")
