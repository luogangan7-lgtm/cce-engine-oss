# CCE 全链架构 v2：平台稳定，场景动态，主体在测量下游形成

状态：Draft PR 的规范基线。本文以《CCE下游主体构建建议》中已经形成的
`Subject → Context → Input → Observation/Event → CCE → Response → Aggregation → Feedback`
为主干，只修正工程接线，不另造一套以 Reddit、助听器或 GitHub 为根的架构。

## 1. 核心决策

### 1.1 根节点不是平台、产品或社区

CCE 的根对象是：

```text
Subject Space × Context Snapshot × Stimulus Event
                         ↓
                    CCE Measurement
                         ↓
              Response / State Observation
                         ↓
      Individual → Dynamic Segment → Population
```

助听器是 `domain/category/need`，Reddit 是 `platform`，`r/HearingAids` 是某个时点的
`community context`。三者都不是 CCE 核心或主体本体。

### 1.2 平台和社区不是同一层

```text
platform_adapter = reddit@1.0.0       # 稳定代码与协议
platform         = reddit             # 稳定平台身份
surface.kind     = community          # 场景类型
surface.id       = r/HearingAids      # 运行时动态值
surface.observed_at = ...             # 该场景快照的时间
```

平台适配器只负责 Reddit 的帖子、评论、作者、时间、链接、指标和证据如何归一化。
它不保存 subreddit 名单，也不拥有助听器领域、受众语料、主体画像或结果指标。

从 `r/HearingAids` 换成 `r/HearingLoss`：只换 Context，不创建新 adapter，不复制解析代码。
从 Reddit 换成 TikTok：新增平台 adapter，但 CCE Event/Measurement/Subject 合同不变。

### 1.3 Context 必须进入测量，但平台分发结果不得进入

同一事件在不同平台、社区、关系、会话和目标下可能产生不同读数，因此 CCE 请求引用一个
不可变的 `context_snapshot_ref`。允许进入的是测量前已知的场景；禁止进入的是浏览、点赞、
评论量、成交等发布后结果。

```text
允许：reddit / r/HearingAids / 半匿名 / 首次接触 / 2026-08-13
禁止：197 views / 9 comments / 后来成交了
```

### 1.4 主体不塞进 Event，也不作为同一次内容测量的先验答案

Event 描述发生了什么；Context 描述在哪里、何时、以什么关系发生；CCE 测量动态分布；
Subject 由带 actor 证据的多次 Response Measurement 在时间窗口内聚合形成。

主体本体使用稳定 `subject_id`，不使用 `profile_version/subject_version`：

- 稳定核心：长期证据足够时才形成；
- 身份证据：append-only；
- 当前状态：带时间戳的瞬时观测；
- Segment/Population：按响应相似性和分析窗口动态形成，不是永久标签。

## 2. 七层所有权

| 层 | 拥有什么 | 不拥有什么 |
|---|---|---|
| GitHub Control Plane | 提交、并发、重试、artifact、manifest、gate | 平台语义、社区身份、主体定义 |
| Platform Adapter | 平台协议和字段归一化 | 社区名单、行业、受众、测量结论 |
| Context Plane | 平台、动态空间、时间、关系、目标、环境 | 发布后效果、主体画像 |
| Evidence/Event Plane | 原文、媒体、Observation、Event、来源链 | 主体结论、商业结论 |
| CCE Measurement | 欲望/需求/情绪/行动等动态分布与置信 | 平台分发、名单修复、效果预测 |
| Subject/Response Plane | Individual/Segment/Population、状态与窗口聚合 | 无证据的 viewer 身份、静态 persona 冒充真人 |
| Outcome/Learning Plane | 曝光、行动、询盘、成交、实验、反馈 | 回灌同一次 ex-ante 测量造成泄漏 |

GitHub 是执行与证据控制面，不是 CCE 领域架构的一层；Notion/Humaux 是事实与知识来源，
也不能改变 Event、Measurement、Subject 的所有权。

## 3. 标准对象

### 3.1 Platform Adapter

```json
{
  "platform": "reddit",
  "platform_adapter": {"id": "reddit", "version": "1.0.0"}
}
```

adapter 版本只在平台字段映射或协议语义变化时升级。新增社区不是升级信号。

### 3.2 Context Snapshot

```json
{
  "id": "context:reddit:r/HearingAids:2026-08-13T08:00:00Z",
  "observed_at": "2026-08-13T08:00:00Z",
  "platform": "reddit",
  "platform_adapter": {"id": "reddit", "version": "1.0.0"},
  "surface": {
    "kind": "community",
    "id": "r/HearingAids",
    "observed_at": "2026-08-13T08:00:00Z"
  },
  "domain": "hearing_aid",
  "summary": "public educational post in a semi-anonymous community"
}
```

Context Snapshot 是事实快照，append-only。社区规则、活跃成员和话题会变化，因此不能把
社区等同于永久受众，也不能把社区写进 adapter id。

### 3.3 Observation / Event / Evidence

原始文本、音视频和行为先形成 Observation，再形成原子/复合 Event。Observed、Inferred、
Derived 必须分开；所有结果可反向追溯到逐字文本或媒体时间片段。

### 3.4 CCE Measurement Request

```json
{
  "id": "req:content:001",
  "measurement_adapter": "event_packet@v1",
  "event_refs": ["evt:001"],
  "context_snapshot_ref": "context:reddit:r/HearingAids:2026-08-13T08:00:00Z",
  "prediction_time": "pre_exposure"
}
```

请求不包含 subject、浏览量、互动量、行动或成交结果。

### 3.5 Subject Entity 与 Subject Window

```text
Subject Entity
├── stable subject_id
├── core                    # 证据不足就 unknown
├── identity_evidence[]     # append-only
└── state_observations[]    # observed_at + measurement ref

Subject Window
├── target
├── reached                 # 逐 actor 入站证据
├── activated               # 逐 actor response measurement
├── action                  # 曝光后行为事实
└── conversion              # publish_id 等稳定 join
```

浏览量只属于 distribution record。平台不提供 viewer identity 时，reached 的可观测上限就是
留下可识别响应的人，不能用聚合浏览数补齐。

## 4. GitHub 三条生产 Profile

### outbound_post

```text
submission contract
→ platform/context normalization
→ s0 context
→ s1 dynamic readout
→ s2 knots
→ s3 emotion policy
→ s4 domain guard
→ exact manifest
```

它不要求固定社区语料、上一篇正文或效果指标。旧 s5/s6 受众对齐以及 s7/s8 尺子/下注属于
单独声明的研究实验，不能决定生产 `complete=true`，也不能声称预测平台效果。

### outbound_reply

```text
reader evidence measurement
+ draft s0-s4
→ reader/draft alignment
```

reader 必须是逐字入站证据；draft 是我方待发送文本，两者不能互换。

### subject_chain

```text
platform response evidence
→ response s0-s3 (最多8路并发)
→ exact SHA join
→ stable subject entities
→ reached/activated windows
→ end-to-end audit
```

入站 response 不运行出站 guard；出站医疗/凭证闸不能否决已经成功的响应测量。

## 5. 并发与端到端闭环

一个提交最多 8 个 item/response，matrix `fail-fast=false`。聚合必须收齐全部预期 job，
并以原文 SHA-256 连接，不以文件名或 artifact 名连接。

```text
Content/Event Measurement ──────────────┐
Platform Distribution ─────────────────┤
Identified Inbound Evidence ── Response Measurement
                                       ↓
                               Subject Windows
                                       ↓
Action Evidence ────────────────────────┤
Commercial Join ────────────────────────┘
```

只有端到端审计确认相同 `content_id`、真实 measurement refs、窗口证据和商业 join 时，才允许
输出 `VERIFIED`。单个 profile 完成只说明该 profile 合同完成。

## 6. 验收 Gate

1. 同一个 `reddit@1.0.0` 必须同时接受 `r/HearingAids` 和其他合法 subreddit；不得复制 adapter。
2. `surface` 必须是包含 `kind/id/observed_at` 的对象；裸字符串社区必须失败。
3. adapter 版本错误或不支持的 surface kind 必须在模型调用前失败。
4. outbound_post 生产 manifest 的 chain 必须恰为 s0-s4，不得出现 s5-s8。
5. CCE request 必须解析到一个 Context Snapshot，同时拒绝 subject/outcome/post-exposure 输入。
6. response profile 不得运行出站 s4 guard；subject 聚合只消费精确匹配的响应测量。
7. reached window 每个 member 必须有 actor/evidence/time/source；浏览量不得冒充成员。
8. 缺少相邻窗口时 delta 必须为 `NOT_TESTABLE`，全链不得输出 `VERIFIED`。
9. GitHub contract、accuracy 与端到端测试必须全部通过，PR 才具备合并资格。

## 7. 已知局限与升级信号

- 当前只实现 `reddit@1.0.0` 平台 adapter；增加 TikTok/YouTube 时新增 adapter 和 fixture。
- 当前生产出站 guard 只登记 `hearing_aid`；支持其他行业时新增 guard profile，而不是复制 Reddit adapter。
- Context Snapshot 已进入结构合同，但多模态 parser 仍需由调用方显式提供/连接 Context，不能自行猜平台。
- 现有 CCE 读数可以用于结构化测量、诊断和跨响应聚合；不能据此预测浏览量、评论量或转化。
- 没有共同曝光下的 user × item 响应矩阵时，Segment 只能是描述性动态窗口，不能声称稳定因果分群。
- 当平台字段语义或 API 证据结构变化时升级 platform adapter；当 Event/Measurement 字段变化时升级对应 schema；社区变化不触发版本升级。

## 8. 明确否决

- 否决 `reddit_hearingaids_adapter`：把平台、社区和行业粘死，无法表达动态社区。
- 否决为每个 subreddit 复制 adapter：重复协议代码且导致同平台数据不可比较。
- 否决把 s7/s8 固定效果下注作为生产 CCE 完成条件：它是未建立外部效度的研究层。
- 否决把社区语料作为每次内容测量准入门槛：社区/受众是动态 Context/Subject 证据，不是平台 adapter。
- 否决把浏览数当 reached subjects：平台交付不等于可识别主体。
- 否决以 GitHub workflow 名称定义领域架构：workflow 只编排已冻结的合同。
