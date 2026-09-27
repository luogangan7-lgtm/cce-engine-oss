# -*- coding: utf-8 -*-
"""隐状态采集的合同(零 torch、零 numpy): 深度比例 → 块号的换算与拒绝 · 第二轮策略给两个候选的块号 · 坐标导出模块导入时不拉 numpy。"""
import importlib
import json
import sys
from pathlib import Path

import pytest

from experiments.jev.backend_hf_choice import hidden_plan
from experiments.jev.contracts import JevError

ROOT = Path(__file__).resolve().parents[3]


def test_depth_fractions_map_to_blocks_for_both_candidates():
    pol = json.loads((ROOT / "experiments/jev/policies/cpu_distill2_llm.json").read_text(encoding="utf-8"))
    assert hidden_plan(pol["export_hidden"], 36)["blocks"] == [18, 27]          # Qwen3-4B-Instruct-2507
    assert hidden_plan(pol["export_hidden"], 32)["blocks"] == [16, 24]          # Qwen3.5-4B(24 = full-attention 层之后)
    assert pol["suite_ids"] == ["s0-distill2-v1"] and pol["max_rows"] >= 599


@pytest.mark.parametrize("spec", [{}, {"depth_fractions": []}, {"depth_fractions": [0.5], "prefix_mean_fractions": [0.5]}, {"depth_fractions": [1.0]},
                                  {"depth_fractions": [0.001]}])
def test_bad_export_specs_are_refused(spec):
    with pytest.raises(JevError):
        hidden_plan(spec, 36)


def test_span_export_module_imports_without_numpy(monkeypatch):
    monkeypatch.setitem(sys.modules, "numpy", None)                            # import numpy 会抛 ImportError
    sys.modules.pop("experiments.jev.hidden_export", None)
    m = importlib.import_module("experiments.jev.hidden_export")
    assert callable(m.write_span_coords)
