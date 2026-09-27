# -*- coding: utf-8 -*-
"""隐状态的上传形式: 不写原始向量, 只写「主帖张成的标准化子空间里的坐标」。

对每个 (向量键, 面): 取该面全部主帖行(指针条目, 非 rep-)的 fp32 向量, float64 逐维去均值除标准差(标准差 ≤ 1e-6 × 最大标准差的维丢弃, 计数上报),
SVD 后保留奇异值 > 1e-9 × 最大奇异值的方向(秩 r ≤ 主帖数 − 1); 每一行(主帖、复跑、冒烟)写它在这 r 个方向上的坐标与残差范数。
均值、标准差、基都不写 ⇒ 上传的只是这些帖子在该层的格拉姆几何: 对任何只依赖内积的 L2 头(岭/多项逻辑回归 + ‖W‖² 罚)无损,
且拿不回原始向量。标准化用了全部主帖(含验收帖)的特征、不含任何标签 —— 这是转导的, 由用它的预注册写明。
numpy 在函数里导入: 合同 CI 只装 pytest, 导入本模块不得需要 numpy。
"""
from __future__ import annotations

import hashlib
import json

SD_FLOOR, RANK_TOL = 1e-6, 1e-9


def write_span_coords(hidden_rows: list, main_item_ids: list, out_dir) -> dict:
    """hidden_rows: [{item_id, question_id, row_sha256, vectors: {键: [float]}}]。写 hidden_coords.jsonl + hidden_basis_meta.json, 返回 meta。"""
    import numpy as np
    from pathlib import Path
    order = {iid: i for i, iid in enumerate(main_item_ids)}
    keys = sorted({k for r in hidden_rows for k in r["vectors"]})
    facets = sorted({r["question_id"] for r in hidden_rows})
    coords = {(r["item_id"], r["question_id"]): {} for r in hidden_rows}
    meta = {"schema": "cce.jev.hidden_span_coords.v1", "sd_floor": SD_FLOOR, "rank_tol": RANK_TOL, "n_rows": len(hidden_rows), "blocks": {}}
    for k in keys:
        for f in facets:
            rows = [r for r in hidden_rows if r["question_id"] == f and k in r["vectors"]]
            main = sorted((r for r in rows if r["item_id"] in order), key=lambda r: order[r["item_id"]])
            if len(main) < 2:
                raise ValueError(f"{k}/{f}: fewer than 2 main rows")
            X = np.array([r["vectors"][k] for r in main], dtype=np.float64)
            mu, sd = X.mean(axis=0), X.std(axis=0)
            keep = sd > SD_FLOOR * sd.max()
            Z = (X[:, keep] - mu[keep]) / sd[keep]
            _u, s, vt = np.linalg.svd(Z, full_matrices=False)
            r_ = int((s > RANK_TOL * s[0]).sum())
            V = vt[:r_].T
            for r in rows:
                z = (np.asarray(r["vectors"][k], dtype=np.float64)[keep] - mu[keep]) / sd[keep]
                c = z @ V
                coords[(r["item_id"], r["question_id"])][k] = {"c": [float("%.9g" % x) for x in c], "resid": float("%.9g" % np.linalg.norm(z - V @ c))}
            meta["blocks"][f"{k}|{f}"] = {"n_main": len(main), "dims_kept": int(keep.sum()), "dims_dropped": int((~keep).sum()), "rank": r_,
                                          "singular_values": [float("%.9g" % x) for x in s[:r_]]}
    out = Path(out_dir)
    with open(out / "hidden_coords.jsonl", "w", encoding="utf-8") as fh:
        for r in hidden_rows:
            fh.write(json.dumps({"item_id": r["item_id"], "question_id": r["question_id"], "row_sha256": r["row_sha256"],
                                 "blocks": coords[(r["item_id"], r["question_id"])]}, ensure_ascii=False) + "\n")
    meta["coords_sha256"] = hashlib.sha256((out / "hidden_coords.jsonl").read_bytes()).hexdigest()
    (out / "hidden_basis_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {k: meta[k] for k in ("schema", "n_rows", "coords_sha256")} | {"ranks": {b: v["rank"] for b, v in meta["blocks"].items()}}
