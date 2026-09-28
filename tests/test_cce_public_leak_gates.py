#!/usr/bin/env python3
"""公开面泄露三道闸(2026-09-28 诊断 P0 的根因修复, 泄露事故见 scripts/cce_identity.py 顶注)。

① 入口: 身份字段必须是化名; 任何文本里不得有真实 u/xxx、/user/xxx; 报错不回显名字(报错会进公开日志)。
② 工作流: 任何 step 的 run/env 不得把自由文本载荷(client_payload.*、非白名单 inputs.*)展开进去 ——
   GitHub 会把 step env 与展开后的 run 脚本原样印进日志。白名单只放标识/数字/路径类 input。
③ cce_full_run 结束时只印摘要, 完整 meta 只进 manifest.json。
每道闸都带反向测试: 把 2026-09-28 之前的写法放回去, 必须红。
"""
import copy
import glob
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from cce_submission import validate_submission  # noqa: E402
from cce_full_run import run_log_summary  # noqa: E402

# ── ① 入口 ──
base = json.loads((ROOT / "examples" / "cce_submission_outbound_reply_v1.json").read_text(encoding="utf-8"))
assert validate_submission(base)["ok"], "基线样例必须过"
FAKE = "zq_realhandle_77"   # 构造名: 不在放行表, 也不带化名前缀


def with_(mut):
    d = copy.deepcopy(base)
    mut(d)
    return validate_submission(d)


def _set_actor(v):
    return lambda d: d["items"][0]["reader"].__setitem__("actor_ref", v)


for pseudo in ("reddit:u/user_47", "self_op", "redacted_3", "creator_1"):
    r = with_(_set_actor(pseudo))
    assert r["ok"], (pseudo, r["errors"])

r = with_(_set_actor(f"reddit:u/{FAKE}"))
assert not r["ok"] and any("actor_ref must be a pseudonym" in e for e in r["errors"]), r["errors"]
assert not any(FAKE in e for e in r["errors"]), "报错不得回显名字"

text_key = next(k for k, v in base["items"][0]["reader"].items() if isinstance(v, str) and k != "actor_ref")
for leak in (f"as u/{FAKE} said", f"https://www.reddit.com/user/{FAKE}/comments/x"):
    r = with_(lambda d: d["items"][0]["reader"].__setitem__(text_key, leak))
    assert not r["ok"] and any("non-pseudonymous user handle" in e for e in r["errors"]), (leak, r["errors"])
    assert not any(FAKE in e for e in r["errors"]), "报错不得回显名字"
assert with_(lambda d: d["items"][0]["reader"].__setitem__(text_key, "as u/user_12 said"))["ok"], "化名提及不误报"

# ── ② 工作流 ──
SAFE_INPUTS = {"permit_id", "suite_id", "with_alignment", "n", "max_users", "pairs", "posts", "min_posts",
               "task", "probe", "design", "env", "args", "items", "phase"}
EXPR = re.compile(r"\$\{\{(.*?)\}\}", re.S)
REF = re.compile(r"client_payload|(?:github\.event\.)?inputs\.([A-Za-z_][\w-]*)")


def payload_echoes(wf: dict) -> list:
    bad = []
    for jn, job in (wf.get("jobs") or {}).items():
        for i, st in enumerate(job.get("steps") or []):
            for t in [st.get("run") or ""] + [str(v) for v in (st.get("env") or {}).values()]:
                for e in EXPR.findall(t):
                    for m in REF.finditer(e):
                        if m.group(0) == "client_payload" or m.group(1) not in SAFE_INPUTS:
                            bad.append(f"{jn}.steps[{i}]: {m.group(0)}")
    return bad


workflows = {p: yaml.safe_load(open(p, encoding="utf-8")) for p in sorted(glob.glob(str(ROOT / ".github/workflows/*.yml")))}
assert len(workflows) >= 15
for p, wf in workflows.items():
    assert not payload_echoes(wf), (p, payload_echoes(wf))

# 反向: 2026-09-28 之前的 cce-submit prep 写法
sub = copy.deepcopy(workflows[str(ROOT / ".github/workflows/cce-submit.yml")])
pkg = next(s for s in sub["jobs"]["prep"]["steps"] if s.get("id") == "package")
pkg["env"] = {"SUBMISSION_JSON": "${{ github.event_name == 'workflow_dispatch' && inputs.submission_json || toJSON(github.event.client_payload.submission) }}"}
assert payload_echoes(sub), "把信封经 step env 收进来必须红"
# 反向: 2026-09-28 之前的 reply.yml 写法
assert payload_echoes({"jobs": {"loop": {"steps": [{"run": "printf '%s' \"${{ inputs.draft }}\" > d.txt"}]}}})

# ── ③ 日志摘要 ──
meta = {"mode": "outbound_reply", "complete": False, "failed_at": "s2",
        "submission": {"submission_id": "sub-1", "actor_ref": f"reddit:u/{FAKE}", "text": "secret body"},
        "stages": {"s1_readout": {"status": "OK", "sec": 1.0, "readout": {"quote": "secret body"}},
                   "s2": {"status": "FAIL", "sec": 0.5, "error": "ValueError: secret body"}}}
dumped = json.dumps(run_log_summary(meta), ensure_ascii=False)
assert "sub-1" in dumped and '"FAIL"' in dumped
assert FAKE not in dumped and "secret body" not in dumped, dumped

print("test_cce_public_leak_gates: OK (入口化名闸+不回显 | %d 个工作流无载荷回显 + 两条旧写法见红 | 运行日志只印摘要)" % len(workflows))
