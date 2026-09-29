# Spec Delta

## Purpose

定义应用的可复现容器启动方式与健康检查契约，使部署环境能够确认服务已正常运行并可接受请求。

## 本次增删记录

### 新增

- Compose 运行拓扑扩展为应用、MySQL 和 Qdrant，并为三者记录持久卷、依赖健康检查与必需环境变量。
- 新增 MySQL 应用账户/管理员账户使用独立密码、首次初始化及已有持久卷密码变更的运行契约。

### 删除或替代

- 替代“Compose 仅以 SQLite 启动应用”的表述；SQLite 仍是主数据存储，但检索运行还依赖 MySQL 与 Qdrant。

## ADDED Requirements

### Requirement: Docker Compose 启动
系统 SHALL 提供 Docker Compose 配置，以持久化的 SQLite 主数据、MySQL 检索正文索引和 Qdrant 向量索引启动应用，并通过容器环境变量提供认证密钥、OpenAI API 密钥与 MySQL 凭据等必需的服务端配置。应用 SHALL 等待 MySQL 与 Qdrant 健康后启动；配置与示例文件 SHALL NOT 包含真实密钥或密码值。

#### Scenario: 使用 Docker Compose 启动应用
- **WHEN** 运维人员使用 Docker Compose 启动项目并提供必需的环境配置
- **THEN** SQLite、MySQL 与 Qdrant 的持久卷可用，应用在 MySQL 和 Qdrant 通过健康检查后启动，且可通过其配置的服务端点访问

#### Scenario: 未提供必需秘密
- **WHEN** 运维人员未提供 `AUTH_SECRET`、`SEED_PASSWORD`、`OPENAI_API_KEY`、`MYSQL_PASSWORD` 或 `MYSQL_ROOT_PASSWORD` 中的任一必需环境变量
- **THEN** Compose 或应用启动失败，而不会生成、持久化或暴露备用秘密

### Requirement: MySQL 首次初始化凭据
系统 SHALL 在创建新的 MySQL 持久卷时使用 `MYSQL_PASSWORD` 创建应用账户，并使用独立的 `MYSQL_ROOT_PASSWORD` 初始化管理员账户。系统 SHALL NOT 因运维人员仅修改 `.env` 中的上述变量而自动修改已经初始化的 MySQL 账户密码；运行说明 SHALL 明确要求保留原密码，或在备份后执行显式轮换或重建操作。

#### Scenario: 首次初始化 MySQL 卷
- **WHEN** Compose 使用此前不存在的 MySQL 持久卷启动且提供两个不同的 MySQL 密码
- **THEN** MySQL 使用它们分别初始化应用账户和管理员账户

#### Scenario: 修改已初始化卷的环境变量
- **WHEN** 运维人员仅修改已有 MySQL 持久卷部署的 `.env` 密码变量后重新启动 Compose
- **THEN** 系统不将该修改误认为已完成数据库密码轮换，并要求运维人员保留原凭据或执行显式的备份后轮换/重建流程

### Requirement: 健康检查端点
应用 SHALL 暴露无需认证的 `GET /health`；当应用能够访问其 SQLite 数据库并处理请求时，端点 SHALL 返回 HTTP 200 及健康状态响应。

#### Scenario: 健康探针成功
- **WHEN** 健康探针向运行中的应用发送 `GET /health`
- **THEN** 应用返回 HTTP 200 和健康状态响应

#### Scenario: Compose 健康检查探测服务
- **WHEN** Docker Compose 应用服务正在运行
- **THEN** 其配置的健康检查调用 `GET /health`，并且仅在收到成功响应后将服务报告为健康
