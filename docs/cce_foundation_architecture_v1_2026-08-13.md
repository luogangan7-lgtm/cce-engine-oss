# CCE 全链架构纠偏与实证审计 · 2026-08-13

> 状态：post6 实证审计保留；通用架构边界已由 `docs/cce_chain_architecture_v2.md` 接管。
> 纠偏依据：完整回读「CCE下游主体构建建议」全部 16 个往返，并核对 Notion「记忆助听器｜海外社媒运营与 CCE 独立库」的 03/04/05/06/08/09 表。
> 最重要的更正：**主体本体不版本化；主体窗口才是某个时间与数据集合在动态占比空间中的分析投影。**

## 1. 结论

CCE 本身是一台测量仪器。它接收内容/响应事件和测量前冻结的 Context Snapshot，输出动态占比分布、阶段与激活指纹。它不接收主体答案、平台分发结果、询盘或成交。平台身份可以是 Context；浏览/点赞/评论量不是 Context，而是发布后分发/结果证据。

完整业务链不是 `内容 + subject_profile + context -> CCE -> 结果`，而是：

```text
内容证据 -> Event -> CCE 内容测量
                         |
发布记录 -> 平台分发 ------+------> 触达主体窗口
                                    |
成员响应 -> CCE 响应测量 ----------> 激活主体窗口
                                    |
曝光后真实行为 --------------------> 行动主体窗口
                                    |
publish_id -> 询盘/成交/复购 ------> 转化主体窗口
```

平台分发在链里，但它不是主体：浏览 197 次只能证明平台交付，不能证明 197 个什么样的人被触达。只有留下可识别评论、回复或私信证据的成员，才能进入当前可观察的触达主体窗口。

## 2. 四层架构

### 2.1 Measurement Layer：CCE

输入：内容/响应的 observation/event refs + 一个带时间的 context_snapshot_ref。
输出：完整动态分布、阶段、内容指纹、置信与证据。
禁止输入：subject/profile、平台分发结果、发布后互动、行为结果、商业结果。

主体卡可以帮助运营者理解某个成员的历史，但不能条件化同一次 CCE 内容测量。否则“测量仪器”会把目标人群假设偷渡进测量结果。

### 2.2 Subject Layer：主体本体 + 五类动态窗口

主体本体使用稳定 `subject_id`，并拆成三种时间尺度：

- 主体核心（欲望基线）是稳定量；
- 身份线索是 append-only 累加量；
- 情绪、行动倾向与激活占比是带时间戳的瞬时状态。

窗口不是另一个“版本的主体”，而是对主体集合的时窗投影。版本号只属于 schema、模型、适配器和测量产物。

| 窗口 | 真正含义 | 最小证据 | 不能拿什么替代 |
|---|---|---|---|
| 目标主体 | 计划时希望进入链路的人群规则/集合 | 冻结的人群准入规则或目标集合 | 泛化 persona 文案 |
| 触达主体 | 实际留下可识别互动的人 | member_ref + 每人独立互动证据 + 时间窗 | 浏览/曝光/赞评总数 |
| 激活主体 | 触达成员响应的 CCE 动态聚合 | 成员响应文本 + 有效 CCE result + 同窗聚合 | 内容自身 s8、人工“感觉被打中” |
| 行动主体 | 曝光后真实采取动作的人 | actor + action + observed_at + source | 历史经验、意向、CTA |
| 转化主体 | 进入询盘/成交/复购的人 | publish_id join + 商业事实 | GA4 聚合 session、未归因询盘 |

主体窗口至少包含 `time_window` 和 `population_set`，没有 `profile_version`。主体卡、窗口和状态记录可以更新或追加，但不能用业务版本号复制出“新主体”。

### 2.3 Mechanism Layer：四条机制链

1. 内容机制：内容手法 -> Event -> CCE 内容指纹。
2. 分发机制：发布 -> 平台交付 -> 曝光/浏览。它只解释“平台送了多少”，不解释“是谁”。
3. 行为机制：激活状态 + 历史行为条件 -> 曝光后实际动作。必须观察，不能由 LLM 模拟。
4. 商业机制：行动 -> 询盘 -> 成交 -> 复购。必须依赖稳定 join key。

### 2.4 Attribution Layer：四个 delta

| delta | 问题 | 可计算前置 |
|---|---|---|
| target -> reached | 触达的人对不对 | 目标窗、触达窗都存在且特征口径可比 |
| reached -> activated | 内容是否打中触达者 | 每个触达成员有响应测量 |
| activated -> action | 状态是否转成行为 | 激活窗与曝光后行动窗同人/同时间口径 |
| action -> conversion | 行为是否产生商业结果 | 行动与商业记录有 publish_id/等价 join |

任一相邻窗口缺失，delta 必须写 `NOT_TESTABLE`，禁止填 0、估计值或“应该有效”。时间/阶段是正交维度，不是第六种主体。

## 3. 主体卡的正确位置

现有 13 张 Reddit 主体卡保留，但已降级为 `reference_card`：

- 可保存公开历史里的欲望/需求 top-k、身份线索、行为频率与来源；
- 可辅助制定目标窗口规则、解释触达成员、提出行为机制假设；
- 不代表平台总体，不是 response segment，不进入 CCE 请求；
- 不再输出 `subject_type` 或 `profile_version`。

没有共同曝光下的 user × item 响应矩阵，就不能把这些卡聚成经验证的响应 segment。

## 4. post6 的真实链路审计

权威记录：

- [post6 内容对象](https://app.notion.com/p/3ba2588d64fc811aa00efa983519ead3)
- [独立运营库](https://app.notion.com/p/3b72588d64fc81febd12f7eae8d9e3c1)
- [T+2.7h 指标快照](https://app.notion.com/p/3ba2588d64fc816d8c41fd58ee89cfb3)

截至本次读取：

- 内容已发布，Notion 关联 5 个指标快照、17 条互动记录、4 条发布前预测；
- T+1h 浏览增量 197；T+2.7h 为 8 赞、9 评；总票数小于 20，upvote ratio 不作为信号；
- 去除我方出站回复后，当前可从 Notion 逐人举证的入站互动者为 8 人；这构成触达窗口，不代表全部浏览者；
- 其中若干人报告既有使用经验，但这些经验发生在读帖前或时间因果不明，不能计作 post6 造成的行动；
- 05「CCE 分布快照」没有 post6/其互动的关联行；06「痛点触达」也没有关联行；
- 已把上述 8 条逐字入站响应提交到 GitHub CCE workflow；run `31677565181` 的 8/8 matrix job 成功，回收时逐条同时核验 SHA-1 与 SHA-256 输入指纹；
- 08 中 R/H1/H2/H3 均仍为待判，观测时点是 2026-08-14；09 没有 T+48h 完整窗口。

因此当前 gate：

| Gate | 状态 | 证据判决 |
|---|---|---|
| 内容测量 | PARTIAL | GitHub s0-s8 run 存在，但 s8 是 legacy 内容侧成对读出，外部效度为零，不是触达成员响应测量 |
| 平台分发 | PARTIAL | 有 h1 与早期赞评，无完整 T+48h/h2 数据 |
| 目标主体窗 | NOT_MET | post6 有选题/假设，未冻结可比较的目标人口规则 |
| 触达主体窗 | PASS | 8 名入站互动者逐人有 Notion 评论证据 |
| 激活主体窗 | PASS | 8 名触达成员的逐字响应均有有效 s1 结果并聚合进同一时窗；四层分布分别归一化，且出站回复后续阶段不污染该测量 |
| 行动主体窗 | NOT_MET | H1/H2 未到判注；既有经验不能算曝光后行动 |
| 转化主体窗 | NOT_MET | Reddit 发布与询盘/成交无 publish_id join |
| 四段 delta | NOT_TESTABLE | 每一段至少缺一个相邻窗口 |
| 全链 | **NOT_VERIFIED** | 结构可运行不等于业务闭环已通过 |

这也解释了“CCE 的触达在哪”：触达不在 CCE 里面，触达来自平台后的入站成员证据；CCE 在内容测量和成员响应测量两个位置工作，但不能替平台制造受众事实。

## 5. 已落实现

- `config/platform_adapter_registry_v1.json`：平台注册与动态空间语法；社区不进入 adapter identity。
- `scripts/cce_platform_adapter.py`：在模型调用前验证 adapter 版本和带时间的 surface。
- `config/cce_foundation_contract_v1.json` v1.3：CCE 请求改为 event + context snapshot，仍硬拒 subject/outcome/post-exposure 输入。
- `config/cce_subject_window_contract_v1.json`：五窗口、四机制、四 delta 与不可伪造 gate。
- `scripts/cce_case_assemble.py`：只生成 event refs 的测量请求。
- `scripts/cce_subject_profile.py`：保留旧文件名兼容，但只输出 auxiliary reference cards。
- `scripts/cce_window_chain.py`：验证主体窗口并生成 `PASS/PARTIAL/NOT_MET/NOT_TESTABLE` 审计。
- `scripts/cce_end_to_end.py`：交叉校验 measurement case 与下游链的 content_id/result_ref；只有这里允许输出整链 `VERIFIED`。
- `scripts/cce_response_chain.py`：把真实入站文本制成 GitHub batch dispatch；回收 artifact 时只认精确输入指纹，生成稳定主体、瞬时状态和 activated window。
- `examples/cce_reddit_post6_chain_audit.json`：用 Notion 真实 post6 数据制作的可复查链包。
- `scripts/test_cce_contract.py`、`scripts/test_cce_window_chain.py`、`scripts/test_cce_end_to_end.py` 与 `scripts/test_cce_response_chain.py`：阻止版本化主体、曝光冒充触达、无成员证据、subject 输入 CCE、结果泄漏、跨平面断链、错输入 artifact 复用与虚假全链通过。

## 6. 验收 Gate

### 结构 Gate

1. CCE request 必须有可解析的 `context_snapshot_ref`，且不得出现 `subject_refs/context_refs/baseline_ref/profile_version`。
2. reached window 必须逐 member 有入站证据；聚合浏览不能通过。
3. activated/action/conversion 分别必须引用 response measurement、曝光后行动、publish join 商业记录。
4. 相邻窗缺失时 delta 自动 `NOT_TESTABLE`。
5. 真实链报告只有全部必要 gate 为 PASS 才能输出 `VERIFIED`。
6. measurement case 与 subject chain 的 `content.id` 必须相同，且 `content_measurement.result_refs` 必须解析到同一 case 的有效结果。
7. 入站响应 artifact 必须满足 `manifest.text_sha1 == sha1(逐字入站文本)`；我方拟回复的 CCE 产物不得冒充读者响应测量。
8. activated 状态只消费冻结的 `s1_readout`；后续 s2 结分类或 s4 出站禁词闸失败不得污染、替代或否决已经成功的 s1 响应测量，但失败作用域必须写入 provenance。

### post6 数据 Gate

1. 到 2026-08-14 T+48h 拉全评论树、h1/h2、总浏览并回写 Notion。
2. 对 H1/H2 逐条人工判：明确“看帖后做了 shirt-pocket test”才算行动；历史经验不算。
3. 对每个有效入站响应运行同一版 CCE，完整分布进入 activated window；只测内容自身不算。**本次 8 条已通过；T+48h 若新增有效入站，必须增量补测。**
4. 若要商业闭环，发布时必须带 publish_id/UTM，并把询盘/成交表的 join 证据接入 conversion window。

在 1–4 未过之前，只能说“内容发布与互动采集链已发生”，不能说“CCE 整条链验证通过”。

## 7. 已知局限与升级信号

- 当前触达窗口是“可观察互动者”，不是全部看到内容的人；Reddit 不提供 viewer identity 时这一上限不可突破。
- post6 的 T+48h 尚未到点；任何早期胜负判断都属于提前看结果。
- 现有 s8 在 post3 胜、post5 负且样本极小，不能承担激活或效果预测。
- 当同一发布单元累计有完整触达成员响应测量、曝光后行动与 publish_id 商业记录时，才升级为首条可计算四段 delta 的链。
