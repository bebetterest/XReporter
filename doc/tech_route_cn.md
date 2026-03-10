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
       -> provider 适配层（XApiClient / TwscrapeApiClient / SocialDataApiClient / FixtureXApiClient）
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
- `run_warnings`：非致命采集告警（provider/状态码/用户/链接/原始错误）

## 采集流程

1. 从配置读取 `api_provider` 选择数据源（fixture 环境变量优先覆盖）。
   - Twscrape 鉴权策略：若 `twscrape_accounts_db_path` 已有账号则复用账号池登录；否则首次引导需完整 `XREPORTER_TWS_*` 凭据。
2. 按用户名解析目标用户。
3. 分页拉取关注列表并应用上限。
4. 拉取每个关注用户在指定时间范围内的时间线。
   - 对 SocialData 返回的 `403` 隐私限制，记录告警并继续后续用户。
5. 按 ID 回补缺失的被引用原帖。
6. 将事件归一化为 activity 记录。
7. Upsert 用户/推文/活动并绑定到 run。
8. 写入 run 结束状态与计数（`runs.api_provider` 持久化用于追溯）。

## 渲染流程

1. 选择 run（`--run-id` 或最新）。
2. 加载该 run 关联的活动数据。
3. 按 `original_tweet_id` 聚合转发/引用/回复。
4. 输出单页静态 HTML（告警区 + 聚合区 + 时间线区）。

## i18n 规则

- 支持语言：`en`、`zh`、`auto`。
- `auto` 使用本地系统语言。
- 如果本地语言不是中文或英文，使用英文。

## 可靠性

- 对 `429` 和 `5xx` 执行指数退避 + 抖动重试。
- SocialData 适配层复用 `429/5xx` 重试策略。
- SocialData 的 `403` 隐私限制会降级为 run 告警（不终止整次采集）。
- 采集中失败会将 run 标记为 `failed` 并记录错误信息。
- Upsert 策略保证重复采集不产生重复数据。

## 迭代路线

- v0.2：增强链接/媒体提取，改进时间线过滤，支持增量采集。
- v0.3：可选多用户观察列表，增强报告交互能力。
- v0.4：分析视图与可选远程存储后端。
