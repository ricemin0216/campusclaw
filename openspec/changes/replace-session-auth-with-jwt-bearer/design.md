# Design

## Context

当前 Flask 应用将 `user_id` 写入 Flask 签名 Cookie，并让服务端渲染页面与 API 共用该会话。JWT Bearer 迁移需要替换认证加载器、所有认证守卫、登录/登出路由、浏览器材料界面的数据获取方式和测试；动机见 `proposal.md`。

## Goals / Non-Goals

**Goals:**

- 让 API 客户端使用标准 Authorization Bearer 头认证，并使班级与角色授权继续由服务端执行。
- 将 JWT 签名秘密与现有 Flask 配置秘密分离，并使令牌可过期、可撤销。
- 保留浏览器端材料上传、查看、下载、删除和检索能力，同时不依赖 Cookie 认证。

**Non-Goals:**

- 不实现刷新令牌、第三方 OAuth/OIDC、SSO、多设备会话列表或全局令牌吊销。
- 不在浏览器持久化存储中保存 Bearer Token；页面刷新后重新登录是该最小实现的预期行为。
- 不改变用户、角色、班级、材料或检索数据模型的授权语义。

## Decisions

### JWT 结构、签名与过期

使用 PyJWT 生成 HS256 JWT，声明为 `sub`（用户 ID）、`iat`、`exp` 和随机 `jti`，默认时长为一小时。使用必需的 `AUTH_TOKEN_SECRET` 而非复用 Flask `AUTH_SECRET`，以便独立轮换 Token 签名秘密。服务端在解码时固定允许 HS256，要求必要声明并拒绝过期令牌。选择自包含 JWT 而非不透明 Token，满足用户指定的 JWT 且无需为每次认证查询 Token 表；撤销表只存 `jti` 和到期时间，作为登出的最小状态。

### 登录、认证与撤销流程

`POST /api/auth/login` 接受 JSON 或表单凭据，验证密码后返回 JSON Token 响应。认证装饰器从 Authorization 头解析 Bearer Token，完成 JWT 和撤销验证，再用 `sub` 从 SQLite 加载当前用户到请求上下文。原有页面/API 授权帮助函数复用该上下文，保持角色和班级判断。

`POST /api/auth/logout` 将当前 `jti` 与 `exp` 写入 SQLite `revoked_tokens`，唯一 Token ID 保证幂等；认证时只接受未撤销的 Token。每次登录 Token 都使用新的 `jti`。旧 `/logout` 页面路由不再清除 Cookie，而应改为调用撤销 API 的浏览器前端入口或返回迁移指引。

### 浏览器界面迁移

普通浏览器导航不会在顶层页面请求中自动附加 Authorization 头，因此服务端页面不再渲染材料或检索数据。`/login` 由同源 JavaScript 调用登录 API，将 Token 仅保存在页面内存；材料和检索界面作为不含受保护数据的壳层，脚本使用 `fetch` 添加 Bearer 头并渲染 API 返回的数据。未获得 Token 的壳层立即回到登录页；登出调用撤销 API 后清除内存 Token 并跳转登录页。

这一选择避免了将 Token 放入 URL、localStorage 或 Cookie。代价是刷新受保护页面后用户需要重新登录；替代方案是 HttpOnly JWT Cookie，但它不满足用户指定的 Authorization Bearer 方式。

### 数据与配置迁移

SQLite 新增 `revoked_tokens(jti PRIMARY KEY, expires_at)` 及到期索引。启动或登出时清理已过期撤销记录。Compose 向应用传入 `AUTH_TOKEN_SECRET`，`.env.example` 仅提供占位值。现有 `AUTH_SECRET` 可暂时保留给 Flask 应用配置，但不参与用户认证；部署时应在切换前通知客户端丢弃旧 Cookie。

## Risks / Trade-offs

- [Bearer Token 被浏览器脚本窃取] → Token 仅保留在内存、实施同源请求与转义输出，避免 URL、localStorage 和日志。
- [刷新页面导致需要重新登录] → 这是不持久化 Token 的有意安全折中；后续可通过单独变更引入刷新令牌。
- [JWT 过期前无法仅靠签名立即登出] → 用 SQLite `jti` 撤销记录在每次认证时检查。
- [旧服务器页面依赖 Cookie] → 改为数据为空的前端壳层，所有受保护数据经 Bearer API 获取，并增加浏览器回归测试。
- [签名秘密泄露或轮换] → 独立环境变量、启动校验、日志脱敏；轮换会使现有 Token 失效并要求重新登录。

## Migration Plan

1. 增加 PyJWT、`AUTH_TOKEN_SECRET`、撤销表和 JWT 单元测试，不修改现有班级授权语义。
2. 增加登录/登出 API 和 Bearer 认证守卫，并将受保护 API 切换为该守卫。
3. 将浏览器登录、材料和检索界面改为 Token 驱动的壳层和 API 请求，移除 Cookie 会话写入与读取。
4. 更新 Compose、示例环境、运行文档和集成测试；部署时使旧 Cookie 会话失效。
5. 回滚时恢复 Cookie 会话版本并移除前端 Token 流程；已签发 JWT 不应在回滚版本中被接受。
