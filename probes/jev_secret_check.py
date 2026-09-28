# -*- coding: utf-8 -*-
"""生产 s0 读出后端的上线核对(一次 Jev 调用, ≈$0.00005): 在 GitHub Actions 里用 secret TYPESAFE_API_KEY 调生产同一个
scripts/cce_s0_jev.s0_jev_read, 看它是走通 Jev 还是会像 2026-09-27 那次生产运行那样回退 MiniMax(NO_TYPESAFE_API_KEY)。
输入 = experiments/jev/suites/s0-compare-llm-v1.jsonl 的 smoke-01(维护者自写, CC0, 无真人); 面 = 与生产 cce_full_run 同一规则
(可从文本读的面)。只打印后端、选中值与各面最大概率; 不打印密钥、不打印请求体。后端不是 jev ⇒ 退出码 1。
用法: gh workflow run probe.yml -R <repo> --ref master -f probe=probes/jev_secret_check.py
"""
import json, os, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from cce_s0_jev import s0_jev_read  # noqa: E402

facets = [f for f in json.loads((ROOT / "config/context_taxonomy.json").read_text(encoding="utf-8"))["facets"]
          if f.get("readable_from_text") in (True, "partial")]
smoke = next(json.loads(l) for l in (ROOT / "experiments/jev/suites/s0-compare-llm-v1.jsonl").read_text(encoding="utf-8").splitlines()
             if l.strip() and json.loads(l)["item_id"] == "smoke-01-clear-signal")
read, probs, err = s0_jev_read(smoke["text"][:2000], facets)
out = {"backend": "jev" if read is not None else f"minimax_fallback({err})", "key_present": bool(os.environ.get("TYPESAFE_API_KEY", "").strip()),
       "read": read, "max_p": {k: max(v.values()) for k, v in (probs or {}).items()}, "item": smoke["item_id"],
       "run": os.environ.get("GITHUB_RUN_ID")}
print(json.dumps(out, ensure_ascii=False, indent=1))
pathlib.Path("/tmp/jev_secret_check.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
sys.exit(0 if read is not None else 1)
