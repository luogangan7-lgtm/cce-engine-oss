# -*- coding: utf-8 -*-
"""真实预算账本: 每次 backbone 前向**之前**原子预约 forward / rows / padded tokens / 时间; 撞上限即失败, 不先算后补记。
不设自动减批、不换 dtype、不切模型、不重复取结果; 失败保留账本退出。"""
from __future__ import annotations

import json
import threading
import time

from .contracts import ExecutionBudget, JevError


class Ledger:
    def __init__(self, budget: ExecutionBudget, clock=time.monotonic):
        self.b, self.clock, self.t0 = budget, clock, clock()
        self._lock = threading.Lock()
        self.forwards = self.rows = self.padded_tokens = self.download_bytes = 0
        self.entries = []

    def elapsed(self) -> float:
        return self.clock() - self.t0

    def reserve(self, rows: int, padded_tokens: int, row_tokens_max: int, kind: str = "forward") -> dict:
        with self._lock:
            el = self.elapsed()
            if el > self.b.deadline_s:
                raise JevError("TIMEOUT", f"{el:.1f}s > deadline {self.b.deadline_s}s before reservation")
            if row_tokens_max > self.b.max_row_tokens:
                raise JevError("INPUT_TOO_LONG", f"row {row_tokens_max} tokens > {self.b.max_row_tokens}")
            if self.forwards + 1 > self.b.max_forwards:
                raise JevError("BUDGET_EXCEEDED", f"forwards {self.forwards}+1 > {self.b.max_forwards}")
            if self.rows + rows > self.b.max_rows:
                raise JevError("BUDGET_EXCEEDED", f"rows {self.rows}+{rows} > {self.b.max_rows}")
            if self.padded_tokens + padded_tokens > self.b.max_padded_tokens:
                raise JevError("BUDGET_EXCEEDED", f"padded tokens {self.padded_tokens}+{padded_tokens} > {self.b.max_padded_tokens}")
            # 全部检查通过后才记账(原子)
            self.forwards += 1; self.rows += rows; self.padded_tokens += padded_tokens
            e = {"seq": len(self.entries) + 1, "kind": kind, "rows": rows, "padded_tokens": padded_tokens,
                 "row_tokens_max": row_tokens_max, "elapsed_s": round(el, 3),
                 "forwards_total": self.forwards, "rows_total": self.rows, "padded_total": self.padded_tokens}
            self.entries.append(e)
            return e

    def reserve_download(self, nbytes: int, name: str = "") -> dict:
        with self._lock:
            if self.download_bytes + nbytes > self.b.max_download_bytes:
                raise JevError("BUDGET_EXCEEDED", f"download {self.download_bytes}+{nbytes} > {self.b.max_download_bytes} bytes ({name})")
            self.download_bytes += nbytes
            e = {"seq": len(self.entries) + 1, "kind": "download", "bytes": nbytes, "name": name,
                 "elapsed_s": round(self.elapsed(), 3), "download_total": self.download_bytes}
            self.entries.append(e)
            return e

    def snapshot(self) -> dict:
        return {"forwards": self.forwards, "rows": self.rows, "padded_tokens": self.padded_tokens,
                "download_bytes": self.download_bytes, "elapsed_s": round(self.elapsed(), 3),
                "limits": {"max_forwards": self.b.max_forwards, "max_rows": self.b.max_rows, "max_padded_tokens": self.b.max_padded_tokens,
                           "max_row_tokens": self.b.max_row_tokens, "deadline_s": self.b.deadline_s, "max_download_bytes": self.b.max_download_bytes}}

    def write_jsonl(self, path) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            for e in self.entries:
                fh.write(json.dumps(e, ensure_ascii=False) + "\n")
