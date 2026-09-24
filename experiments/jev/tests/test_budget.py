# -*- coding: utf-8 -*-
"""预算: 到上限时下一次预约失败且账本不变(先检查后记账) · 行超长 · 超时 · 下载字节。"""
import pytest

from experiments.jev.budget import Ledger
from experiments.jev.contracts import ExecutionBudget, JevError

B = ExecutionBudget(max_forwards=2, max_rows=2, max_padded_tokens=200, max_row_tokens=100, deadline_s=10.0, max_download_bytes=50)


def test_reserve_at_limit_fails_and_does_not_record():
    L = Ledger(B, clock=lambda: 0.0)
    L.reserve(1, 64, 30); L.reserve(1, 64, 30)
    snap = L.snapshot()
    with pytest.raises(JevError) as e:
        L.reserve(1, 64, 30)
    assert e.value.code == "BUDGET_EXCEEDED"
    assert L.snapshot() == snap and len(L.entries) == 2 and L.forwards == 2


def test_padded_tokens_limit_is_checked_before_recording():
    L = Ledger(B, clock=lambda: 0.0)
    L.reserve(1, 128, 30)
    with pytest.raises(JevError):
        L.reserve(1, 128, 30)               # 128+128 > 200
    assert L.padded_tokens == 128 and L.forwards == 1


def test_row_too_long_and_timeout():
    L = Ledger(B, clock=lambda: 0.0)
    with pytest.raises(JevError) as e:
        L.reserve(1, 128, 101)
    assert e.value.code == "INPUT_TOO_LONG" and L.forwards == 0
    t = [0.0]
    L = Ledger(B, clock=lambda: t[0]); t[0] = 11.0
    with pytest.raises(JevError) as e:
        L.reserve(1, 64, 10)
    assert e.value.code == "TIMEOUT" and L.forwards == 0


def test_download_budget():
    L = Ledger(B, clock=lambda: 0.0)
    L.reserve_download(30, "a")
    with pytest.raises(JevError) as e:
        L.reserve_download(30, "b")
    assert e.value.code == "BUDGET_EXCEEDED" and L.download_bytes == 30


def test_ledger_jsonl(tmp_path):
    L = Ledger(B, clock=lambda: 0.0); L.reserve(1, 64, 5)
    L.write_jsonl(tmp_path / "l.jsonl")
    assert (tmp_path / "l.jsonl").read_text().count("\n") == 1 and '"forwards_total": 1' in (tmp_path / "l.jsonl").read_text()
