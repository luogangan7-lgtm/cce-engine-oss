# docs/ 索引 —— 哪份是现行，哪份已被取代

> **为什么需要这份索引**：这个项目已经**三次**栽在「拿退役组件当现行标准」上
> （2026-08-13 旧 s0–s8 当尺子 · 08-14 s8 写进判注 · 08-14 帖 15 九条 run 全跑旧链）。
> 六份架构文档跨 v2/v3/v3.1，各自在正文里自述状态 —— 但**要打开文件才知道**。
> 一份不可执行的索引自己会腐烂，所以它由 `tests/test_cce_docs_index.py` 钉住：
> 漏登一份、状态与文件自述不符、或声称的后继不存在，都会红。

| 文档 | 状态 | 说明 |
|---|---|---|
| `CCE_full_architecture_workflow_parameters_v1.md` | **现行 · 主文档** | 5700+ 行，含 §19.5 实测记录、§43 铁律、§44 八阶段、§45 矩阵。持续追加，不重写历史。 |
| `cce_chain_architecture_v3_1.md` | **现行 · 链路架构** | v3.1 修正 v3 的矫枉过正：禁止「均值冒充人群」不等于禁止合成人群。 |
| `cce_workflow_spec_v1.md` | **现行 · 提交协议** | 唯一生产入口 = 公开仓 `cce-engine-oss` 的 `.github/workflows/cce-submit.yml`（已与注册表核对一致）。 |
| `cce_skill_architecture_v1.md` | **现行 · Skill 入口** | Skill 是薄入口：读注册表、判路由、调 GitHub 权威入口，不复制测量引擎。 |
| `cce_chain_architecture_v3.md` | 已被取代 → `cce_chain_architecture_v3_1.md` | v3 正确禁止均值冒充人群，但错在没有正式合成 Population Subject。 |
| `cce_chain_architecture_v2.md` | 已被取代 → `cce_chain_architecture_v3.md` | 平台/社区边界仍有效；「主体只在测量下游形成」已被 v3 修正。 |
| `cce_foundation_architecture_v1_2026-08-13.md` | 部分被取代 → `cce_chain_architecture_v3.md` | post6 实证审计部分**保留**；通用架构边界已由 v3 接管。 |

## 权威顺序（冲突时以上位为准）

1. **代码与注册表** —— `config/cce_capability_registry_v1.json` · `config/cce_workflow_registry_v1.json`
2. **主文档** `CCE_full_architecture_workflow_parameters_v1.md`
3. 其余专题文档

★ 文档与代码冲突时**以代码为准**，并把分歧登记进 `config/cce_doc_reconciliation.json`
（`scripts/cce_doc_reconcile.py` 会强制每条分歧带判定与证据）。

## 不在 docs/ 里的权威件

- 铁律分档与文档核对：`config/cce_doc_reconciliation.json`
- 链路一致性：`config/cce_chain_conformance.json`
- 归档与损失登记：`config/cce_archive_index.json`
