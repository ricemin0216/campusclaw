# Tasks

## 1. JWT 基础设施与安全配置

- [x] 1.1 添加 PyJWT 依赖、`AUTH_TOKEN_SECRET` 启动校验和 Compose/`.env.example` 占位配置；验证：缺少变量时应用失败启动且错误、响应和日志不输出秘密值。
- [x] 1.2 创建 SQLite `revoked_tokens` 表、到期索引和过期撤销记录清理；验证：数据库测试确认重复令牌 ID 幂等、过期记录可清理且不影响有效撤销记录。
- [x] 1.3 实现固定 HS256 算法的 JWT 签发与解码服务，包含 `sub`、`iat`、`exp`、`jti` 和一小时默认有效期；验证：单元测试覆盖有效令牌、篡改签名、算法不匹配、缺失声明和过期令牌。

## 2. Bearer API 认证与撤销

- [x] 2.1 实现 `POST /api/auth/login`，验证账号密码并返回 `access_token`、`Bearer` 和有效期；验证：教师和学生可获得令牌，错误凭据不签发令牌且不暴露密码或哈希。
- [x] 2.2 将所有受保护 API、材料数据端点和授权守卫切换为 `Authorization: Bearer <JWT>`，每次请求重新加载用户、角色和班级关系；验证：无 Token、错误格式、旧 Cookie、无效/过期/撤销 Token 均返回 401，有效 Token 仍保留 403 角色和跨班边界。
- [x] 2.3 实现幂等的 `POST /api/auth/logout`，撤销当前 `jti` 至其过期时间；验证：登出后同一 Token 无法访问 API，重复登出不泄露状态且返回成功响应。
- [x] 2.4 为登录、认证和登出 API 添加回归测试；验证：`pytest` 覆盖登录响应字段、签名/过期/撤销失败、角色限制和 A/B 班隔离，且不使用 Flask 会话。

## 3. 浏览器界面与运行文档迁移

- [x] 3.1 将登录页改为同源前端登录流程，在页面内存保存 JWT，并在 `fetch` 请求中附加 Authorization 头；验证：浏览器回归测试确认登录后 API 请求带 Bearer 头，页面不写入认证 Cookie、URL 或持久化浏览器存储。
- [x] 3.2 将材料、上传、查看、下载、删除和检索页面改为不含受保护数据的前端壳层；验证：无 Token 的页面不展示材料或检索结果并回到登录入口，有效 Token 下本班用户仍可完成对应操作。
- [x] 3.3 更新 Docker Compose、`.env.example` 和运行说明，记录 `AUTH_TOKEN_SECRET`、Bearer API 调用、Token 有效期、登出/撤销和旧 Cookie 失效；验证：示例不含真实秘密，按文档请求受保护 API 可获得预期 401 或成功结果。

## 4. 集成验收

- [x] 4.1 运行完整测试套件并覆盖 JWT 登录后教师/学生访问、上传 403、跨班 403、登出后 401 和原 Cookie 无效；验证：`python -m pytest` 全部通过。
- [x] 4.2 使用 Compose 启动服务并进行本机 Bearer 冒烟检查；验证：`GET /health` 为 200，登录 API 返回 Token，携带 Token 可读取本班材料，登出后同一 Token 返回 401。
- [x] 4.3 为 `replace-session-auth-with-jwt-bearer` 运行 `openspec validate --strict`；验证：命令报告该变更有效。
