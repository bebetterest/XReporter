# XReporter 进度日志

## 2026-03-13

### 已完成（报告体验优化 + 中文 HTML）

- 优化静态 HTML 报告布局：
  - 新增 run 摘要仪表区（元数据 + 计数）
  - 改进聚合区/时间线/告警卡片可读性与响应式表现
  - 增加分区计数与更清晰的跳转导航
- 补齐报告层 `en`/`zh` 双语渲染：
  - 将此前硬编码英文（`by/at/open/open post/unknown`）收敛为可本地化文案
  - 在聚合区与时间线中本地化活动类型展示（`tweet|retweet|quote|reply`）
- 扩展告警渲染明细：新增告警类型与记录时间展示。
- 聚合区已扩展包含 `tweet` 活动（不再仅限转发/引用/回复），原始发帖也会出现在聚合卡片中。
- 聚合区与完整活动时间线已支持折叠/展开，且默认均为折叠状态。
- 已更新排序规则：
  - 完整活动时间线固定按时间从近到远排序
  - 聚合区按活动数降序，活动数相同按最新活动时间降序
- 已新增“按用户聚合”区（位于按原帖聚合与完整时间线之间）：
  - 按同一用户的活动进行聚合
  - 按活动数降序，活动数相同按最新活动时间降序
  - 支持折叠/展开且默认折叠
- 已新增聚合 item 级折叠能力（按原帖聚合/按用户聚合卡片），默认折叠以提升长内容可读性。
- 已重构开源导向 README：
  - 信息层次更清晰（总览 -> 技术路线 -> 快速上手 -> 参考）
  - 增强首次使用者友好的导航与故障排查
  - 中英文 README 结构保持同步
- 新增中文 HTML 渲染测试，并扩展双语 e2e 用例，验证 zh 报告输出。
- 已在 `XReporter` 环境执行全量测试（报告 UX/i18n 改造后）：**35 项通过**。

## 2026-03-10

### 已完成（v0.1 基线）

- 完成 Python 项目脚手架（`src/`、`tests/`、`pyproject.toml`、`environment.yml`）。
- 完成 CLI 命令：
  - `config init`
  - `config show`
  - `collect`
  - `render`
  - `doctor`
- 完成官方 X API 客户端：
  - 用户名解析
  - 关注列表分页
  - 时间线拉取
  - 缺失引用原帖回补
  - `429/5xx` 指数退避重试
- 完成 fixture API 客户端（离线测试）。
- 完成 `tweet|retweet|quote|reply` 归一化层。
- 完成 SQLite 模型与 upsert 去重策略。
- 完成单页静态 HTML 报告渲染。
- 完成 CLI i18n（`en`、`zh`、`auto` 回退英文）。
- 补齐单元、集成、端到端测试。
- 补齐双语文档：
  - `README.md` / `README_cn.md`
  - `doc/tech_route.md` / `doc/tech_route_cn.md`
  - `doc/progress.md` / `doc/progress_cn.md`
  - `AGENTS.md` / `AGENTS_cn.md`
- 已创建并验证 conda 环境 `XReporter`。
- 修复配置默认路径在运行时解析的问题（提升测试可用性与环境可移植性）。
- 已在 `XReporter` 环境执行全量测试：**16 项通过**。
- 已完成真实 API 冒烟链路（在 `XReporter` 环境）：
  - 使用真实 token 执行 `config init`（密钥来自 `.env`，未持久化）
  - `collect --last 12h --following-cap 5` 成功（`run_id=2`，`activities=3`）
  - `render --run-id 2` 成功（`.xreporter-local/reports/run_2.html`）
- 已修复 X API RFC3339 时间格式问题：请求时间按“秒级精度”序列化。
- 已按指定参数完成高上限真实测试：
  - `username=betterestli`，执行 `collect --last 12h --following-cap 500`
  - run `3` 在时间线进度 `243/411` 时因 X API `402 CreditsDepleted` 失败
  - 已保留部分数据（`173` 条活动），并可正常渲染报告（`run_3.html`）
- 已完成通过配置切换的多 provider 采集：
  - 新增 `api_provider`（`official|twscrape|socialdata`）
  - 新增 `twscrape_accounts_db_path`
  - 旧配置缺失字段时默认回退 `official`
- 已新增 `SocialDataApiClient` 与 `TwscrapeApiClient` 适配层，归一化/存储/渲染主链路保持不变。
- 已完成 provider 感知的 client 工厂与 doctor 检查：
  - fixture 环境变量仍为最高优先级
  - 凭据检查按当前 provider 执行
- 已改进 twscrape 凭据策略：
  - 若账号池数据库已有账号，doctor/collect 不再强制邮箱凭据
  - 若账号池为空，首次引导仍需完整凭据
- 已新增 twscrape 账号池复用与 doctor 凭据判定的测试用例。
- 已在 `XReporter` 环境执行全量测试（twscrape 凭据回退改造后）：**31 项通过**。
- 已为 `runs` 表新增 `api_provider` 字段，并补齐已有数据库的自动迁移逻辑。
- 已新增配置兼容、provider 选路、存储迁移、新 provider 适配层测试。
- 已完成 SocialData 私密内容容错改造：
  - 时间线拉取遇到 `403` 隐私限制时，记录 run 告警并继续采集，不再整次失败
  - 新增 `run_warnings` 表，并接入报告红色告警区（用户名/链接/API 路径/原始错误体）
  - 新增服务层告警流程、告警持久化、告警渲染测试
- 已在 `XReporter` 环境执行全量测试（隐私告警改造后）：**34 项通过**。
- 已从运行时与配置中移除 `twscrape` 支持：
  - provider 现仅支持 `official|socialdata`
  - 已删除 `TwscrapeApiClient` 及 twscrape 凭据/账号池流程
  - 已从 `pyproject.toml` 移除 `twscrape` 依赖
- 已同步更新测试与中英文文档，确保 provider 清理后一致。
- 已在 `XReporter` 环境执行全量测试（provider 清理后）：**30 项通过**。

### 待办 / 下一步

- 使用真实 X API 凭据进行联调，并根据真实流量调优限流策略。
- 增强报告内容深度（媒体预览、链接元数据）。
- 增加增量采集策略，减少重复 API 读取。
- 增加可观测性（结构化日志与可选 run trace 导出）。
