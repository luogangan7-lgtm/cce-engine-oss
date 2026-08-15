---
name: cce
description: 统一处理 CCE 的内容解析、事件与状态建模、主体/人群响应、文案与回复测量，以及 GitHub 权威链路调用。用户提到 CCE、视频/音频/图像/文本解析、跨模态事件、内容拆解、主体、人群、发布文案、评论回复或测量结果时使用。
---

# CCE

## 唯一入口

把本 Skill 当作 CCE 的唯一用户入口。不要再调用旧的 `viral-*`、`b2b-*`、`b2c-*` 或 `cce-github-client` Skill。

每次先从仓库根目录读取：

1. `config/cce_capability_registry_v1.json`：当前能力、状态和入口的权威清单。
2. `config/cce_workflow_registry_v1.json`：GitHub 生产工作流边界。
3. 需要解释全链路时，再读 `docs/cce_chain_architecture_v3_1.md` 和 `config/cce_foundation_contract_v2.json`。

不得仅凭本 Skill 的文字断言某项能力已上线。注册表与实际工作流不一致时，停止并报告漂移。

## 路由

按输入和目标路由，而不是按平台或行业创建 Skill：

- 发布文案测量：`outbound_post`
- 评论、问答、询盘回复测量：`outbound_reply`
- 主体、分群、人群响应：`subject_chain`
- 视频、音频、图像、多模态内容：读取能力注册表；只有状态为 `production_github` 才能声称 GitHub 全链路可用。
- 事件、状态、证据、跨模态融合：采用 Foundation Contract；严格分开 `observed`、`inferred`、`derived`。

Reddit 是平台；subreddit/community 是随时间窗口变化的社区上下文，不是固定主体。产品和行业也是上下文/对象，不是主体根节点。人群结果必须保留分布、异质性、分群权重和时间窗口，不能用一个均值替代。

## GitHub 生产测量

生产测量只运行 `.github/workflows/cce-submit.yml`。先生成符合 `cce.submission.v1` 的 JSON，再运行：

```bash
python3 scripts/cce_github_client.py verify-input /absolute/path/submission.json
python3 scripts/cce_github_client.py run /absolute/path/submission.json \
  --ref master \
  --outdir /absolute/path/result
```

只有客户端同时验证以下条件后才报告完成：

- 工作流成功；
- `workflow-manifest.json` 完整；
- submission/profile/job 集合完全一致；
- 每项 `text_sha256` 与提交输入一致；
- `engine_complete` 与 `measurement_complete` 都为 `true`；
- `failed_at` 为 `null`。

输出必须带 GitHub run URL、submission ID、profile、条目数和输入哈希。不得本地伪算 CCE 数值，也不得把本地脚本执行冒充 GitHub 生产运行。

## 尚未生产化的模态

如果能力注册表显示 `component_only` 或 `missing`：

- 可以解释仓库现有组件、契约和缺口；
- 可以在用户要求实现时修改仓库并增加生产工作流；
- 不得降级到旧 Skill，也不得声称已经跑通 GitHub 全链路；
- 返回明确状态 `NOT_AVAILABLE_PRODUCTION` 和缺失的 gate。

当前视频解析结果必须至少能说明视觉采样/OCR/原始混音音频处理，以及源分离、说话人分离、韵律和混音指标是否真实具备；缺能力必须写 `missing_no_capability`，不能补造结论。

## 验收 Gate

任何变更至少通过：

```bash
python3 tests/test_cce_skill_contract.py
python3 /Users/luolimo/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/cce
python3 scripts/install_cce_skill.py --check
```

涉及生产工作流时，还需运行对应 GitHub Actions 回放，并验证产物哈希。
