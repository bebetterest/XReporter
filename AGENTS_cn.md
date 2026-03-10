# AGENTS_cn.md

该文件定义本仓库中人类与智能体协作的工作原则。

## 核心原则

- 以第一性原理替代偶然复杂度。
- 优先简单且可组合的模块，接口清晰。
- 始终保证端到端主链路可运行。
- 关注正确性、可观测性与可复现性。

## 工程规则

- 模块职责聚焦：
  - `x_api.py`：多 provider API 访问、数据映射与重试策略
  - `normalizer.py`：活动归一化
  - `storage.py`：持久化、幂等与 run 级告警记录
  - `render.py`：报告生成（时间线/聚合/告警分区）
  - `cli.py`：命令接口与编排
- 尽量使用类型标注和明确的数据契约。
- 避免隐藏全局状态，通过构造参数/函数参数传递依赖。
- 将重复执行视为一等场景，核心记录不得重复。
- 构建、开发与测试命令必须在名为 `XReporter` 的 conda 环境中执行（`conda activate XReporter`）。

## 测试策略

- 单元测试覆盖纯逻辑与边界情况。
- 集成测试覆盖适配层行为（API、分页、重试、回补）。
- 端到端测试覆盖 `collect -> render` 主路径。
- 新行为必须至少附带一个相关测试。

## 文档策略

- 文档必须与代码变更同步。
- 英文文档必须有同步中文版本（`*_cn.md`）。
- 行为变化时至少更新以下文档：
  - `README.md` / `README_cn.md`
  - `doc/tech_route.md` / `doc/tech_route_cn.md`
  - `doc/progress.md` / `doc/progress_cn.md`
  - `AGENTS.md` / `AGENTS_cn.md`

## i18n 策略

- CLI 支持 `en`、`zh`、`auto`。
- `auto` 使用本地系统语言。
- 若本地语言不是中文或英文，回退英文。

## 安全与密钥

- 严禁将 `X_BEARER_TOKEN` 持久化到项目文件。
- 严禁将 `SOCIALDATA_API_KEY` 持久化到项目文件。
- 严禁将 `XREPORTER_TWS_*` 凭据持久化到项目文件。
- Twscrape 在账号池为空时首次引导需完整 `XREPORTER_TWS_*` 凭据；若账号池已有账号，则不强制邮箱凭据。
- 使用环境变量管理密钥。
- fixture 文件不得包含真实凭据。

## 迭代策略

- 以最小可用增量交付。
- 在 `doc/progress*.md` 记录里程碑状态。
- 尽量采用向后兼容的数据结构扩展方式。
