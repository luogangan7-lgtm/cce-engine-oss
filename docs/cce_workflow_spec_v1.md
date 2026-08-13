# CCE GitHub 工作流与提交协议 v1

## 1. 唯一生产入口

新调用统一发送 `cce.submission.v1` 到：

```text
repository_dispatch event_type = cce-submit
workflow                       = .github/workflows/cce-submit.yml
max parallel                   = 8
```

旧 `cce.yml`、`reply.yml`、`replybatch.yml` 只保留兼容，不接受新集成。
accuracy 是代码质量闸；其余校准、外部效度、主体模拟 workflow 属研究工作流，不能用它们的成功状态声称生产 CCE 全链通过。

## 2. 共同必填信息

每次提交都必须提供：

| 字段 | 含义 | Gate |
|---|---|---|
| `kind` | 固定 `cce.submission.v1` | 不相等即拒绝 |
| `schema_version` | 固定 `1.0.0` | 禁止静默兼容未知版本 |
| `submission_id` | 一次不可变提交的幂等标识 | 改任何原文必须换 ID |
| `profile` | `outbound_post` / `outbound_reply` / `subject_chain` | 决定冻结的执行链 |
| `submitted_at` | ISO-8601 提交时点 | 用于审计，不是内容事件时间 |
| `producer.system` | 谁生成提交包 | 追溯来源 |
| `producer.trace_id` | 上游任务/运行关联 ID | 串联 Notion、Agent、发布记录 |

所有进入模型的文本必须同时给出：

```json
{
  "text": "逐字原文",
  "text_sha256": "sha256:<UTF-8原文字节的64位小写hex>"
}
```

空格、换行或标点变化都算新输入，必须重新计算指纹。GitHub artifact 名、文件名和 `ref_tag` 都不能替代指纹。

## 3. 三种标准 Profile

### 3.1 `outbound_post`

用途：帖子、邮件正文、文章或社媒内容发布前验收。

每个 item 必填：

| 分组 | 字段 |
|---|---|
| 身份 | `job_id`, `content_id`, `platform`, `surface`, `domain`, `language`, `speaker_role` |
| 目标 | `objective.metric` |
| 待发布内容 | `text`, `text_sha256` |
| 情境 | `context.summary`, `context.declaration` |
| 目标受众证据 | `audience.corpus_path + sha256`，或 `audience.utterances + sha256` |
| 成对基准 | `comparator.content_id`, `comparator.text`, `comparator.text_sha256` |

受众语料至少 30 条、1000 词，必须是真实受众原话；“美国普通消费者”等 persona 描述不合格。
情境声明的键值必须来自 `config/context_taxonomy.json`。不知道的面应明确填 taxonomy 允许的 `未知/未提及`，不能猜。

冻结执行链：

```text
s0 context → s1 readout → s2 knots → s3 emotion policy → s4 outbound guard
→ s5 audience → s6 alignment → s7 ruler → s8 pairwise bet
```

通过定义：精确原文指纹匹配且 `manifest.complete=true`。

当前 post adapter 只允许 `hearing_aid / reddit / r/HearingAids / otc_hearing_aid_oem`，
且 `objective.metric=model_comment_rate_per_1000_views`。这是因为 s7/s8 的锚点、账号身份和
落点指标仍冻结在该范围。其他行业、平台或目标必须新增版本化 adapter，不能只改 context 冒充可用。

### 3.2 `outbound_reply`

用途：准备发送给具体对象的评论、私信或邮件回复。

每个 item 必填：

| 分组 | 字段 |
|---|---|
| 身份 | `job_id`, `content_id`, `platform`, `surface`, `domain`, `language`, `speaker_role` |
| 情境 | `context.summary`, `context.declaration` |
| 对方证据 | `reader.actor_ref`, `evidence_ref`, `observed_at`, `source`, `text`, `text_sha256` |
| 我方草稿 | `draft.text`, `draft.text_sha256` |

冻结执行链：

```text
对方原文 s1/s2 基准
我方草稿 s0 → s1 → s2 → s3 → s4
对方↔草稿 四层/九结响应对齐
```

通过定义：草稿 `manifest.complete=true`，且 `reply_alignment.verdict.PASS=true`。只测草稿或只跑 reply alignment 都不算完整。

### 3.3 `subject_chain`

用途：发布后，将真实触达成员的入站响应并发测量并接入主体窗口链。

必填：

- `subject_chain` 与 `response_source` 内联对象；或
- `subject_chain_path/sha256` 与 `response_source_path/sha256` 仓库冻结文件。

每条 response 必须包含：

```text
evidence_ref · actor_ref · observed_at · source · text · text_sha256
```

`response_source.context` 还必须声明 `platform/surface/domain/summary`，使观测响应不再依赖
runner 内硬编码的 Reddit 语境。

冻结执行链：

```text
source/chain contract
→ 最多8路并行 response s0/s1
→ SHA-1 + SHA-256 精确回收
→ stable subject + activated window
→ subject audit + end-to-end audit
```

这是测量链，不是出站回复链。s2/s3/s4 即使为了兼容 runner 被执行，也不能进入 activated 聚合；只消费成功且原文匹配的 s1。

`subject_chain` 成功只证明响应测量与聚合成功。若 target、action、conversion 或 attribution 证据缺失，整体仍必须是 `NOT_VERIFIED`。

## 4. 并发与失败语义

- 单次最多 8 个 item；第 9 个在提交验证阶段直接拒绝。
- matrix `fail-fast=false`，每个 item 有独立 artifact，不因一条失败而丢失其他证据。
- 聚合必须收齐全部预期 job；少一条、重复、指纹错或业务 gate 失败，aggregate 不得输出 `complete=true`。
- 同一 `submission_id` 的内容不可变。重试允许复用完全相同的包；修改内容必须新建 submission/job ID。
- `complete=true` 只对对应 profile 的冻结链成立，不代表 CCE 准确度、外部效度或商业转化自动成立。

## 5. 标准产物

每次生产运行保留 180 天：

1. `cce-submission-source`：原始 `submission.json`、规范化 `normalized.json`、冻结 `items.json`。
2. 每项 artifact：s0–s8 或响应测量文件，以及带 submission/job/content/profile/双指纹的 `manifest.json`。
3. `cce-result-<run_id>`：
   - outbound：`workflow-manifest.json`；
   - subject：`subject-chain.json`、`subject-chain-audit.json`、`end-to-end-audit.json`。

## 6. 调用模板

```bash
jq -n --slurpfile submission examples/cce_submission_outbound_post_v1.json \
  '{event_type:"cce-submit",client_payload:{submission:$submission[0]}}' \
| gh api --method POST repos/luogangan7-lgtm/cce-engine/dispatches --input -
```

三个可执行样例：

- `examples/cce_submission_outbound_post_v1.json`
- `examples/cce_submission_outbound_reply_v1.json`
- `examples/cce_submission_subject_chain_v1.json`

提交前可本地只做零模型契约预检：

```bash
python3 scripts/cce_submission.py examples/cce_submission_outbound_post_v1.json
```

本地预检不是 CCE 执行。只有 GitHub run URL、artifact 和对应 manifest 才是运行证据。
