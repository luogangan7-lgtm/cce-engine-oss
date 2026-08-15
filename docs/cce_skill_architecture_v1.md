# CCE Skill architecture v1

## Decision

Codex 只暴露一个 `CCE` Skill。它不是测量引擎的复制品，而是读取仓库当前能力注册表、判断路由并调用 GitHub 权威入口的薄入口。

```text
User task
  └─ CCE Skill (one visible entry)
       ├─ capability registry: what is live / component-only / missing
       ├─ content and context routing
       └─ GitHub cce-submit.yml (production profiles only)
            └─ verified aggregate artifact
```

旧的 `viral-*`、`b2b-*`、`b2c-*` 和 `cce-github-client` Skill 已删除。它们把输入模态、业务场景和内部处理步骤错误地做成了并列产品入口，容易过时，也让用户误以为每个开关都是独立能力。

## Authority layers

| Layer | Authority | Meaning |
|---|---|---|
| Capability | `config/cce_capability_registry_v1.json` | 当前能力状态与真实缺口 |
| Production workflow | `config/cce_workflow_registry_v1.json` | 哪个 GitHub workflow 可称为生产入口 |
| Foundation | `config/cce_foundation_contract_v2.json` | observation/event/state/evidence 契约 |
| Architecture | `docs/cce_chain_architecture_v3_1.md` | 完整链路与边界 |
| User entry | `skills/cce/` | 读取上述权威源、路由、提交和解释 |

Skill 不保存分类学镜像，不在本地计算 CCE，不用平台/行业/产品创建新入口。

## Current capability truth

| Capability | State | Boundary |
|---|---|---|
| outbound post | `production_github` | `cce-submit.yml`, profile `outbound_post` |
| outbound reply | `production_github` | `cce-submit.yml`, profile `outbound_reply` |
| subject/population | `production_github` | `cce-submit.yml`, profile `subject_chain` |
| video parser v5 | `component_only` | visual/OCR/original-mix audio exists; no production media workflow |
| Foundation adapter | `component_only` | emits observations, not semantic/cross-modal events |
| event assembly | `component_only` | conservative atomic/composite events |
| standalone image/audio ingest | `missing` | no production route |

This distinction is deliberate: having code in the repository is not the same as having a production GitHub chain.

## Subject and context boundary

- Reddit is a platform.
- A subreddit is a dynamic community context identified with an observation window.
- A post is content/event evidence.
- Comments are observed responses with actors, timestamps and provenance.
- A subject is a time-bounded evidence projection, not a product label.
- A population is a distribution/mixture formed after evidence passes the subject chain; it is never a simple average person.
- Products, industries and platforms are context variables or objects, not root subjects.

## Acceptance gates

1. Repository `skills/` contains exactly one directory: `cce`.
2. Global Codex skill directory contains only one managed CCE entry: `cce`.
3. The Skill reads the capability and workflow registries before asserting current status.
4. Production runs include URL, profile, submission ID, exact item set, completion flags and input hashes.
5. Manifest drift or hash mismatch fails closed.
6. `component_only` and `missing` capabilities return `NOT_AVAILABLE_PRODUCTION`; no silent local fallback.
7. Subject/population output retains time window, distribution, heterogeneity, provenance and uncertainty.
8. Contract tests, Skill validation and installation drift check pass before merge.

## Known limits and upgrade signals

- Video parsing is not yet a production GitHub workflow. Promote it only after defining media transport, dependency/runtime limits, artifacts and an end-to-end replay gate.
- Audio source separation, speaker diarization, prosody and mix metrics remain missing capabilities; do not infer them from the original mix.
- No vector database is introduced until evidence volume demonstrates an actual retrieval/recall bottleneck.
