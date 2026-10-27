# Proposal

## Why

现有认证依赖 Flask 签名 Cookie，会话只适合浏览器自动携带 Cookie 的访问方式，无法让 API 客户端以标准 `Authorization` 请求头携带凭据。系统需要改为 JWT Bearer 认证，以便浏览器前端和 API 客户端使用同一种明确、可过期的访问令牌。

## What Changes

- **BREAKING**：移除 Flask Cookie 会话作为受保护页面和 API 的认证依据，所有受保护请求改为 `Authorization: Bearer <JWT>`。
- 登录成功后签发短时 JWT，包含最小身份声明、签发时间、过期时间和唯一令牌 ID；令牌使用独立的服务端 `AUTH_TOKEN_SECRET` 签名。
- 受保护 API 缺少、格式错误、签名无效、过期或已撤销的 Bearer Token 时返回 HTTP 401，且不得读取受保护数据。
- 网页登录页通过同源前端脚本提交凭据、在内存中保存令牌并为后续受保护请求附加 Authorization 请求头；受保护页面不再依赖浏览器自动发送 Cookie。
- 登出撤销当前 JWT 的令牌 ID，撤销记录至少保留至该令牌过期；服务端每次受保护请求仍从 SQLite 重新加载用户、角色和班级成员关系。
- 更新 Docker Compose、`.env.example`、运行文档和测试，要求 `AUTH_TOKEN_SECRET` 仅存在于服务端环境。

## Capabilities

### New Capabilities

- `jwt-bearer-authentication`: JWT 签发、Bearer 校验、令牌过期与撤销，以及浏览器和 API 的统一认证契约。

### Modified Capabilities

- 无；项目尚未同步主规格。该独立能力替代此前变更中以 Flask 会话为基础的认证行为。

## Impact

- 修改 Flask 登录、登出、认证守卫和页面请求方式；现有浏览器 Cookie 会话将不再有效。
- 新增 JWT 库、SQLite 撤销记录与 `AUTH_TOKEN_SECRET` 配置；`AUTH_SECRET` 不再是用户认证令牌的签名密钥。
- 修改受保护 API 的调用示例、网页模板与测试，并更新 Compose 和运行文档。
