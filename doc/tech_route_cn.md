# XReporter 技术路线（v0.1）

## 原则

- 第一性原理设计：仅保留端到端价值所需组件。
- 对齐 bitter lesson：优先可扩展的数据管线基础能力（归一化存储、显式编排、可回放 run），避免脆弱硬编码。
- 模块化优先：分离 API、归一化、持久化、渲染与 i18n。

## 架构

```text
CLI (Typer + Rich)
  -> Config + i18n
  -> CollectorService
       -> XApiClient / FixtureXApiClient
       -> Normalizer
       -> SQLiteStorage
  -> Report Renderer (static HTML)
```

## 数据模型

- `users`：活动用户与引用作者
- `tweets`：事件推文与被引用推文
- `tweet_links`：从 tweet entities 提取的链接
- `activities`：标准化活动行（`tweet|retweet|quote|reply`）
- `runs`：采集任务元数据与状态
- `run_activities`：run 到 activity 的映射，保证可复现

## 采集流程

1. 按用户名解析目标用户。
2. 分页拉取关注列表并应用上限。
3. 拉取每个关注用户在指定时间范围内的时间线。
4. 按 ID 回补缺失的被引用原帖。
5. 将事件归一化为 activity 记录。
6. Upsert 用户/推文/活动并绑定到 run。
7. 写入 run 结束状态与计数。

## 渲染流程

1. 选择 run（`--run-id` 或最新）。
2. 加载该 run 关联的活动数据。
3. 按 `original_tweet_id` 聚合转发/引用/回复。
4. 输出单页静态 HTML（聚合区 + 时间线区）。

## i18n 规则

- 支持语言：`en`、`zh`、`auto`。
- `auto` 使用本地系统语言。
- 如果本地语言不是中文或英文，使用英文。

## 可靠性

- 对 `429` 和 `5xx` 执行指数退避 + 抖动重试。
- 采集中失败会将 run 标记为 `failed` 并记录错误信息。
- Upsert 策略保证重复采集不产生重复数据。

## 迭代路线

- v0.2：增强链接/媒体提取，改进时间线过滤，支持增量采集。
- v0.3：可选多用户观察列表，增强报告交互能力。
- v0.4：分析视图与可选远程存储后端。
