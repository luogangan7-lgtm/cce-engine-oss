"""G-K1 v3 运维偏离(2026-10-03)的守卫: resilient_call 只改「怎么重试、记什么」, 不改「问什么」。

钉住:
  ① 请求体与 run_gates.call 逐项相同(model / messages / max_tokens / temperature=0.0), 端点与鉴权头同源
  ② 每条逻辑调用最多 3 次尝试, 每次尝试前都扣授权单(重试照样计数)
  ③ 失败按「模型|状态码」计数; 成功后不再重试; reasoning_content 回退与 run_gates.call 相同
  ④ 尝试之间有退避(第 1、2 次失败后各等一次), 第 3 次失败后不等
  ⑤ 授权单撞上限时立刻抛出, 不被吞掉
"""
import collections, io, json, os, sys, threading, urllib.error, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "probes"))
import accuracy_gk1_v3_run as G   # noqa: E402


class Budget(Exception):
    pass


Budget.__name__ = "BudgetExceeded"


class FakeM:
    BASE, KEY, BUDGET_ID, BUDGET_LIMIT = "https://example.invalid/v1/chat", "k", "auth", 5

    def __init__(self):
        self.reserved = 0

    def reserve(self, bid, limit, note=""):
        self.reserved += 1
        if self.reserved > limit:
            raise Budget("cap")


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _run(script, limit=5):
    m, errs, sleeps, seen = FakeM(), collections.Counter(), [], []
    m.BUDGET_LIMIT = limit
    it = iter(script)

    def fake_urlopen(req, timeout=None):
        seen.append(json.loads(req.data))
        assert req.full_url == m.BASE and req.headers["Authorization"] == "Bearer k"
        step = next(it)
        if isinstance(step, int):
            raise urllib.error.HTTPError(m.BASE, step, "x", {}, None)
        return Resp(json.dumps(step).encode())

    orig = urllib.request.urlopen
    urllib.request.urlopen = fake_urlopen
    try:
        f = G.make_resilient_call(m, threading.Lock(), errs, sleep=sleeps.append)
        try:
            out = f("MiniMax-M2", "PROMPT", 4000)
        except Budget:
            out = "BUDGET"
    finally:
        urllib.request.urlopen = orig
    return out, m.reserved, errs, sleeps, seen


OK = {"base_resp": {"status_code": 0}, "choices": [{"message": {"content": "{\"knots\":[]}"}}]}
RATE = {"base_resp": {"status_code": 1002, "status_msg": "rate limit"}}
REASON_ONLY = {"base_resp": {"status_code": 0}, "choices": [{"message": {"content": " ", "reasoning_content": "R"}}]}


def test_payload_identical_to_run_gates_call():
    out, n, errs, sleeps, seen = _run([OK])
    assert out == "{\"knots\":[]}" and n == 1 and not errs and not sleeps
    assert seen == [{"model": "MiniMax-M2", "messages": [{"role": "user", "content": "PROMPT"}],
                     "max_tokens": 4000, "temperature": 0.0}]


def test_retry_counts_each_attempt_and_records_codes():
    out, n, errs, sleeps, _ = _run([429, RATE, OK])
    assert out == "{\"knots\":[]}" and n == 3
    assert errs == {"MiniMax-M2|http:429": 1, "MiniMax-M2|base_resp:1002": 1}
    assert len(sleeps) == 2 and sleeps[1] > sleeps[0] - 1


def test_gives_up_after_three_attempts_without_final_sleep():
    out, n, errs, sleeps, _ = _run([500, 500, 500])
    assert out == "" and n == 3 and errs == {"MiniMax-M2|http:500": 3} and len(sleeps) == 2


def test_reasoning_fallback_same_as_run_gates():
    assert _run([REASON_ONLY])[0] == "R"


def test_budget_cap_is_not_swallowed():
    out, n, *_ = _run([500, 500, 500], limit=2)
    assert out == "BUDGET" and n == 3


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
    print("test_cce_gk1_v3_resilient_call: OK")
