# CCE Engine

认知因果引擎的执行链。**每次运行都有永久 URL 和完整日志——"跑没跑完整"是可核事实,不是口头声明。**

## 链路

| 模式 | 段 |
|---|---|
| `reply` | s1_readout → s2_knots → s3_emotion_policy → s4_guard |
| `post` | 上述4段 + s5_audience → s6_alignment → s7_ruler → s8_pairwise_bet |

任一段失败即 `complete=false`,链路中止,manifest 记录 `failed_at`。

## 投料规范

| 字段 | 必填 | 说明 |
|---|---|---|
| `mode` | ✓ | `reply` 或 `post` |
| `text` | ✓ | 待评内容逐字原文 |
| `context` | ✓ | 语境(板块/平台/上下文) |
| `audience` | post必填 | **目标读者原话语料**,≥3条/≥80词。留空回退 `corpus/` 默认语料 |
| `ref_tag` | post必填 | 运行标识,用于回溯 |

⚠️ `audience` **不能传人群画像描述**(如"美国普通消费者")。s5 受众逆推吃的是真实发言;传描述等于让模型给一句话做九结分类,读数退化且方差极大(实测4轮4个不同主结)。校验在 `.github/prepare.py`,不合规直接失败。

## s6 对齐算子 v2

```
对齐分 = Σ(推动族受众结) w × 稿件该结权重        [共鸣]
       + Σ(阻挡族受众结) w × 拆除动作命中度(0-1)  [拆除]
```

v1 的裸 argmax + 集合成员判定已废弃:阻挡族(suspend/inertia/audit)按定义不可能出现在稿件结里,内容只能**拆除**它不能**携带**它,旧规则在受众主结落阻挡族时恒不可满足。

阈值 `CCE_ALIGN_THETA`(仓库变量,默认 0.35)。**标定状态:未完成**——四篇已发布帖真语料得分 0.175~0.315,跨run方差与样本间差异同量级,4样本不足以立硬阈值。

## 触发

```bash
# 单条
gh workflow run cce.yml -f mode=post -f text="..." -f context="..." -f ref_tag=xxx

# 批量(matrix 并行)
gh api repos/OWNER/REPO/dispatches -f event_type=cce-batch \
  -F 'client_payload[items][]=...'
```

## Secrets / Variables

| 名 | 类型 | 用途 |
|---|---|---|
| `MINIMAX_API_KEY` | Secret | 九结分类与情绪面板的模型调用 |
| `CCE_ALIGN_THETA` | Variable | s6 阈值,默认 0.35 |
