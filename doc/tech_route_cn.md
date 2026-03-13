# XReporter 技术路线（v0.1）

## 原则

- 第一性原理设计：仅保留端到端价值所需组件。
- 对齐 bitter lesson：优先可扩展的数据管线基础能力（归一化存储、显式编排、可回放 run），避免脆弱硬编码。
- 模块化优先：分离 API、归一化、持久化、渲染与 i18n。

## 架构

```text
CLI (Typer + Rich)
  -> Config + i18n + logging bootstrap
  -> CollectorService
       -> provider 适配层（XApiClient / SocialDataApiClient / FixtureXApiClient）
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
- `run_followings`：按 following 记录检查点状态（`pending|in_progress|success|warning|failed`），用于断点续跑

## 采集流程

1. 从配置读取 `api_provider` 选择数据源（fixture 环境变量优先覆盖）。
2. 按用户名解析目标用户。
3. 分页拉取关注列表并应用上限。
4. 拉取每个关注用户在指定时间范围内的时间线（并发 worker，可通过 `--api-concurrency` 配置）。
   - 对 SocialData 返回的 `403` 隐私限制，记录告警并继续后续用户。
5. 持续落库 following 级检查点状态（`run_followings`）。
6. 按 ID 回补缺失的被引用原帖（若 provider 支持批量接口则优先批量）。
7. 将事件归一化为 activity 记录。
8. Upsert 用户/推文/活动并绑定到 run。
9. 写入 run 结束状态与计数（`runs.api_provider` 持久化用于追溯）。
10. 若中断或失败，可通过 `--resume-run-id` 仅继续未完成 following。

## 渲染流程

1. 选择 run（`--run-id` 或最新）。
2. 加载该 run 关联的活动数据。
3. 按 `original_tweet_id` 聚合发帖/转发/引用/回复（发帖使用 `event_tweet_id` 作为聚合键）。
4. 输出单页静态 HTML，包含：
   - 按配置语言（`en`/`zh`）输出完整本地化文案
   - run 摘要仪表区（元数据 + 计数）
   - 时间线按时间从近到远排序
   - 聚合块按活动数降序，活动数相同则按最新活动时间降序
   - 按用户聚合块按活动数降序，活动数相同则按最新活动时间降序
   - 告警区 + 按原帖聚合区 + 按用户聚合区 + 时间线区。

## i18n 规则

- 支持语言：`en`、`zh`、`auto`。
- `auto` 使用本地系统语言。
- 如果本地语言不是中文或英文，使用英文。

## 可靠性

- 对 `429` 和 `5xx` 执行指数退避 + 抖动重试。
- SocialData 适配层复用 `429/5xx` 重试策略。
- 重试事件会同时写入日志，并通过 CLI 回调打印到终端。
- SocialData 适配层避免发送不支持的时间线过滤参数，并使用文档定义的 followings/批量推文接口，减少无效调用。
- 分页循环具备保护：当 cursor/token 重复时记录告警日志并中断循环，避免无界拉取。
- SocialData 的 `403` 隐私限制会降级为 run 告警（不终止整次采集）。
- 采集中失败会将 run 标记为 `failed` 并记录错误信息。
- Upsert 策略保证重复采集不产生重复数据。

## 可观测性

- 统一运行时日志写入 `$XREPORTER_HOME/logs/xreporter.log`（默认 `~/.xreporter/logs/xreporter.log`）。
- CLI 记录 `config/collect/render/doctor` 的命令开始、结束与关键入参。
- API 适配层记录请求生命周期：方法、路径、状态码、耗时、重试、回退、失败响应摘要。
- Service 与 Storage 记录 run 级关键节点：run 创建、warning 落库、batch 持久化、run 结束状态。

## 迭代路线

- v0.2：增强链接/媒体提取，改进时间线过滤，支持增量采集。
- v0.3：可选多用户观察列表，增强报告交互能力。
- v0.4：分析视图与可选远程存储后端。
