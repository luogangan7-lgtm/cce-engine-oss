# -*- coding: utf-8 -*-
"""上传白名单: 模型扩展名 / tokenizer 资产 / 目录越界 / 超大小 / 秘密形状 各自拒绝。"""
import pytest

from experiments.jev.contracts import JevError
from experiments.jev.report import check_upload, write_manifest_sha256


def test_ok_files(tmp_path):
    (tmp_path / "report.json").write_text("{}"); (tmp_path / "summary.md").write_text("ok")
    assert check_upload(tmp_path, [tmp_path / "report.json", tmp_path / "summary.md"], 1000) == ["report.json", "summary.md"]
    m = write_manifest_sha256(tmp_path); assert m.read_text().count("\n") == 2


@pytest.mark.parametrize("name", ["model.safetensors", "w.gguf", "w.pt", "tokenizer.json", "x.bin", "state.ckpt"])
def test_model_assets_refused(tmp_path, name):
    (tmp_path / name).write_bytes(b"x")
    with pytest.raises(JevError) as e:
        check_upload(tmp_path, [tmp_path / name], 1000)
    assert e.value.code == "OUTPUT_INVALID"


def test_escape_and_size_and_secret(tmp_path):
    other = tmp_path.parent / (tmp_path.name + "_other"); other.mkdir(); (other / "a.json").write_text("{}")
    with pytest.raises(JevError):
        check_upload(tmp_path, [other / "a.json"], 1000)
    big = tmp_path / "big.txt"; big.write_bytes(b"0" * 2000)
    with pytest.raises(JevError):
        check_upload(tmp_path, [big], 1000)
    for s in ("apikey_ABCDEFGHIJK1234", "ghp_" + "a" * 30, "hf_" + "b" * 30, "-----BEGIN PRIVATE KEY-----"):
        f = tmp_path / "log.txt"; f.write_text("x " + s + " y")
        with pytest.raises(JevError) as e:
            check_upload(tmp_path, [f], 10 ** 6)
        assert "secret" in e.value.detail
