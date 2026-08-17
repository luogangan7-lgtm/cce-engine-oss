# CCE GitHub 工作流与提交协议 v1

## 1. 唯一生产入口

新调用统一发送 `cce.submission.v1` 到：

```text
repo                           = luogangan7-lgtm/cce-engine-oss   ← 2026-08-17 起，公开仓
repository_dispatch event_type = cce-submit
workflow                       = .github/workflows/cce-submit.yml
max parallel                   = 8
```

仓库地址可用环境变量 `CCE_REPO` 覆盖（`scripts/cce_github_client.py` 读它）。
**旧私库 `luogangan7-lgtm/cce-engine` 不再是入口**，见 §7。

旧 `cce.yml`、`reply.yml`、`replybatch.yml` 只保留兼容，不接受新集成。
accuracy 是代码质量闸；其余校准、外部效度、主体模拟 workflow 属研究工作流，不能用它们的成功状态声称生产 CCE 全链通过。

## 2. 共同必填信息

每次提交都必须提供：

| 字段 | 含义 | Gate |
|---|---|---|
| `kind` | 固定 `cce.submission.v1` | 不相等即拒绝 |
| `schema_version` | 固定 `1.1.0` | 禁止静默兼容未知版本 |
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
| 身份 | `job_id`, `content_id`, `platform`, `platform_adapter.id/version`, `domain`, `language`, `speaker_role` |
| 动态空间 | `surface.kind`, `surface.id`, `surface.observed_at` |
| 待发布内容 | `text`, `text_sha256` |
| 情境 | `context.summary`, `context.declaration`, `context.dimensions`, `context.provenance` |
| 出站安全 | `guard_profile` |

情境声明的键值必须来自 `config/context_taxonomy.json`。不知道的面应明确填 taxonomy 允许的 `未知/未提及`，不能猜。

冻结执行链：

```text
s0 context → s1 readout → s2 knots → s3 emotion policy → s4 outbound guard
```

通过定义：精确原文指纹匹配且 `manifest.complete=true`。

`reddit` 是平台注册身份，`reddit@1.0.0` 是协议适配器；`r/HearingAids` 是动态 `surface`。
更换 subreddit 只更换带时间的 surface，不创建新 adapter。旧 s5/s6 与 s7/s8 属研究链，
不再作为 outbound_post 生产完成条件。

平台/surface/domain 只是 Universal Context 的平台场景。正式 Context 还可声明 `time/location/environment/device/session/social/relationship/life/task/current_goal`；每个已声明维度必须有 `value/assertion/evidence_refs`。normalized item 和 artifact metadata 保存完整 Context Snapshot，不能只保留拼接字符串。

### 3.2 `outbound_reply`

用途：准备发送给具体对象的评论、私信或邮件回复。

每个 item 必填：

| 分组 | 字段 |
|---|---|
| 身份 | `job_id`, `content_id`, `platform`, `platform_adapter.id/version`, `surface.kind/id/observed_at`, `domain`, `language`, `speaker_role`, `guard_profile` |
| 情境 | `context.summary`, `context.declaration`, `context.dimensions`, `context.provenance` |
| 对方证据 | `reader.actor_ref`, `evidence_ref`, `observed_at`, `source`, `text`, `text_sha256` |
| 我方草稿 | `draft.text`, `draft.text_sha256` |

冻结执行链：

```text
对方原文 s1/s2 基准
我方草稿 s0 → s1 → s2 → s3 → s4
对方↔草稿 四层/九结响应对齐
```

通过定义：草稿 `manifest.complete=true`。只测草稿不算完整。

`reply_alignment` **不参与通过判定**，它是按需诊断（`cce-submit.yml` 的 `with_alignment`，默认关）。2026-08-10 实测该算子同稿重跑 3/8 翻转、|Δ对齐分| 均值 0.213 与 θ=0.35 同量级，自身口径即「不作放行/拦截依据」；2026-08-15 实测它占单项运行时间 81%，故改为需要时显式打开。关着跑时 `reply_alignment_pass` 为 `null`，属正常关闭态而非缺失。

### 3.3 `subject_chain`

用途：发布后，将真实触达成员的入站响应并发测量并接入主体窗口链。

必填：

- `subject_chain` 与 `response_source` 内联对象；或
- `subject_chain_path/sha256` 与 `response_source_path/sha256` 仓库冻结文件。

每条 response 必须包含：

```text
evidence_ref · actor_ref · observed_at · source · text · text_sha256
```

`response_source.context` 还必须声明 `id/observed_at/platform/platform_adapter/surface/domain/summary/dimensions/provenance`，使观测响应不再依赖
runner 内硬编码的 Reddit 语境。

冻结执行链：

```text
source/chain contract
→ 最多8路并行 response s0-s3
→ SHA-1 + SHA-256 精确回收
→ stable subject + inferred state hypothesis
→ Population Subject mixture（member weights/distributions + marginal/quantiles + composition + heterogeneity + stable segments/unassigned + uncertainty）
→ activated window
→ subject audit + end-to-end audit
```

这是测量链，不是出站回复链。response 不执行出站 s4；activated 聚合只消费成功且原文匹配的 s1。

`subject_chain` 成功只证明响应测量与聚合成功。若 target、action、conversion 或 attribution 证据缺失，整体仍必须是 `NOT_VERIFIED`。

## 4. 并发与失败语义

- 单次最多 8 个 item；第 9 个在提交验证阶段直接拒绝。
- matrix `fail-fast=false`，每个 item 有独立 artifact，不因一条失败而丢失其他证据。
- 聚合必须收齐全部预期 job；少一条、重复、指纹错或业务 gate 失败，aggregate 不得输出 `complete=true`。
- 同一 `submission_id` 的内容不可变。重试允许复用完全相同的包；修改内容必须新建 submission/job ID。
- `complete=true` 只对对应 profile 的冻结链成立，不代表 CCE 准确度、外部效度或商业转化自动成立。

## 5. 标准产物

每次生产运行的 GitHub artifact 保留 90 天（仓库上限），**过期后以 Supabase 归档为准**，见 §8。
运行期内产出：

1. `cce-submission-source`：原始 `submission.json`、规范化 `normalized.json`、冻结 `items.json`。
2. 每项 artifact：outbound_post 的 s0–s4、outbound_reply 的回复链、subject response 的 s0–s3，以及带 submission/job/content/profile/双指纹的 `manifest.json`。
3. `cce-result-<run_id>`：
   - outbound：`workflow-manifest.json`；
   - subject：`subject-chain.json`、`subject-chain-audit.json`、`end-to-end-audit.json`。

## 6. 调用模板

```bash
jq -n --slurpfile submission examples/cce_submission_outbound_post_v1.json \
  '{event_type:"cce-submit",client_payload:{submission:$submission[0]}}' \
| gh api --method POST repos/luogangan7-lgtm/cce-engine-oss/dispatches --input -
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

---

## 7 · 为什么生产入口是公开仓

### 7.1 直接原因：Actions 配额

私库 `cce-engine` 的 GitHub Actions 免费额度是 **2000 分钟/月**，2026-08-16 用尽（100%），
下次重置 2026-09-01。CCE 是逐帖、逐条回复都要跑的链路，停两周等于停产。

GitHub 对 **公开仓库的 Actions 不计分钟数**。这是唯一一条不需要自建机器、不需要付费、
且不改动任何链路代码的出路。已否决的替代方案（不要重做）：

| 方案 | 否决理由 |
|---|---|
| Cloudflare Workers / Pages | 跑不了 CCE 全链：无 Python 运行时、无 matrix 并发、单次执行有 CPU 上限 |
| GitLab CI/CD | 免费额度 400 分钟/月，比现状更少 |
| 自建 runner（本机 Mac） | 用户明确否决："只要不是部署在本地就行了" |

### 7.2 为什么是新仓，不是把旧私库翻公开

**旧私库不能翻公开。** 它有 9 个已合并的 PR，`refs/pull/N/head` 仍然指向历史改写**之前**的提交，
那些提交里含 `hearingaids_others_20260809.json` / `hearingaids_chains_20260809.json`
（1208 个真实 Reddit 用户名）。`git push --force` 改写 master 不会删除 `refs/pull/N/head`，
GitHub 上任何人都能按 commit SHA 访问到。

所以做法是：**新建 `cce-engine-oss`，只推改写后的干净历史（139 提交），旧私库保持私有、不动。**

公开前做过的事，构成这一步的验收 gate：

- 全仓 PII 扫描（**不是只扫 `accuracy/` 和 `corpus/`** —— 第一次只扫这两处，漏了
  `config/knot_taxonomy.json`、`tests/`、`scripts/`，共 23 文件 / 86 个标识符）
- 全局化名替换，带白名单（`BOTS` 集合里的 bot 名、公众人物名不得被改）
- `git filter-repo --replace-text` **加 `--replace-message`** —— 只做前者会漏掉提交信息里的真名（实测漏 6 处）
- 换名后重算 `text_sha256` 指纹（`examples/cce_submission_subject_chain_v1.json` 因此变更）
- 全新克隆做外部人视角审计：无真名、无 `u/xxx`、无密钥、无 `.env`
- `8/8` 测试 PASS

**身份映射表不在这个仓库里，也永远不会进。** 它在本机 `/Volumes/data/cce-identified-vault/`
（git 之外），含 `unified_pseudonym_map.json` 90 条与改写前的 `pre-filter-repo-backup.bundle`。

### 7.3 一条已知的运维坑（会再遇到）

新仓推完整段历史后，`gh workflow run` 会报
`HTTP 404: workflow cce-submit.yml not found on the default branch`，**尽管文件确实在默认分支上**。

原因：GitHub 只在 **workflow 路径出现在某次 push 的 diff 里** 时才索引该 workflow。
一次性强推既有历史不触发索引，推一个不碰 workflow 的普通提交也不触发。

修法：**改动 workflow 文件本身（追加一行注释即可）再推默认分支**，约 40 秒后转 `active`。

派发后核归属必须用 `displayTitle` 或 `submission_id` 比对，
**不能用 `gh run list -L 1` 取"最新 run"** —— 共享仓库里最新 run 往往是别的事件触发的。
另：`gh workflow run ... | tail -1` 会让 `$?` 变成 `tail` 的返回码，派发失败也报成功；
返回码要单独存。

---

## 8 · 数据存储与调用

GitHub artifact 只保 90 天，且公开仓的 artifact **任何人可下载**。因此运行证据与识别态数据
分两处存放，职责不重叠：

| 存放处 | 内容 | 访问 |
|---|---|---|
| GitHub artifact（公开仓） | 90 天内的运行产物，**均为去标识化内容** | 公开可下 |
| Supabase Postgres | 运行与产物的永久归档、识别态快照 | 仅 `service_role` |
| 本机 vault（git 之外） | 化名↔真名映射、改写前 bundle | 不联网 |

### 8.1 Supabase 端点与表

```text
PostgREST  https://ilbzgsghyxgppmpeicfo.supabase.co/rest/v1/
认证       apikey + Authorization: Bearer <SUPABASE_SERVICE_KEY>   ← 走环境变量，禁止硬编码
```

| 表 | 行数（2026-08-17 实测） | 内容 |
|---|---|---|
| `cce_run_archive` | 337 | run 元数据：`run_id / name / display_title / event / conclusion / head_branch / html_url / raw` |
| `cce_artifact_archive` | 1854 | 产物正文：`artifact_name / file_path / content`(jsonb) `/ content_text / size_bytes` |
| `cce_identified_snapshot` | 4843 | 识别态评论快照：`post_id / comment_id / author / body / ups / created_utc / raw` |
| `cce_pseudonym_map` | 17 | 化名↔真名，`kind` = `user_key`(16) / `mention`(1) |

两条会绊人的实际口径（均为 2026-08-17 实测，不是推断）：

1. **`manifest` 在 `file_path`，不在 `artifact_name`。** `artifact_name` 形如
   `cce-item-0-<run_id>` / `cce-result-<run_id>` / `cce-submission-source`；
   `file_path` 才是 `manifest.json` / `workflow-manifest.json` / `s0_context.json` …
   按 `artifact_name=like.*manifest*` 查会返回空。
2. **正文分两列存**：JSON 产物进 `content`(jsonb，1525 行)，非 JSON 进 `content_text`（329 行），
   两者互补正好 1854。取 JSON 字段用 `content->>key`，不要对 `content_text` 用。

`cce_run_archive.billable_minutes` **建了列但从未写入（非空行数 = 0）**，不要拿它算成本。

### 8.2 调用示例

```bash
# 某次 run 的聚合结论
curl -s "$SB_URL/cce_artifact_archive?file_path=eq.workflow-manifest.json\
&artifact_name=eq.cce-result-31956489524&select=content" \
  -H "apikey: $SB_KEY" -H "Authorization: Bearer $SB_KEY"

# 某 item 是否跑完（jsonb 取值用 ->> ）
curl -s "$SB_URL/cce_artifact_archive?file_path=eq.manifest.json\
&artifact_name=like.cce-item-*-31956489524&select=artifact_name,content->>complete" \
  -H "apikey: $SB_KEY" -H "Authorization: Bearer $SB_KEY"

# 按 run 查结论
curl -s "$SB_URL/cce_run_archive?run_id=eq.31956489524&select=display_title,conclusion,html_url" \
  -H "apikey: $SB_KEY" -H "Authorization: Bearer $SB_KEY"
```

DDL 走 PostgREST 做不了。建表/改表必须用 Management API：

```bash
curl -X POST "https://api.supabase.com/v1/projects/<ref>/database/query" \
  -H "Authorization: Bearer $SUPABASE_PAT" -H "Content-Type: application/json" \
  -d '{"query":"<SQL>"}'
```

### 8.3 访问控制现状（2026-08-17 实测，非推断）

四张表 `rls_on = true` 且 **策略数为 0**。启用 RLS 而无任何策略 = 除绕过 RLS 的 `service_role` 外
一律拒绝，读写皆然。用 publishable(匿名) key 实测四表 `SELECT` 全部返回 `[]`。

> **待办（未执行，需先确认）**：`cce_pseudonym_map` 是唯一能反解化名的东西，
> 把它放在云端没有收益 —— 本机 vault 已有完整的 90 条，云上这 17 条既不完整、又是唯一的再识别风险面。
> 建议从 Supabase 删除该表，只留 vault。**删除是破坏性操作，未执行，等确认。**
