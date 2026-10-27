# Spec Delta

## Purpose

为浏览器前端和程序化 API 客户端提供统一的 JWT Bearer 认证契约，使受保护数据仅可在有效、未撤销且未过期的访问令牌下访问。

## ADDED Requirements

### Requirement: JWT 登录令牌签发
系统 SHALL 提供凭账号和密码换取 JWT 访问令牌的登录接口。成功令牌 SHALL 包含用户标识、签发时间、过期时间和唯一令牌标识，默认有效期为一小时；令牌 SHALL 使用仅服务端提供的独立认证秘密签名。成功响应 SHALL 返回 `access_token`、`token_type`（值为 `Bearer`）和有效期秒数，且 SHALL NOT 返回密码、密码哈希或签名秘密。

#### Scenario: 有效凭据换取 Bearer Token
- **WHEN** 教师或学生向登录接口提交有效账号和密码
- **THEN** 系统返回一个有效期为一小时的 JWT `access_token`、`Bearer` token type 和有效期秒数

#### Scenario: 无效凭据不签发令牌
- **WHEN** 调用者提交未知账号或错误密码
- **THEN** 系统返回认证失败，且不签发访问令牌或返回受保护用户数据

### Requirement: Bearer Token 保护受限数据
系统 SHALL 仅接受 `Authorization: Bearer <JWT>` 作为受保护 API 和材料数据请求的认证依据。服务端 SHALL 验证签名、算法、过期时间、令牌标识的撤销状态，并在每次有效令牌请求时重新加载用户、角色和班级成员关系。缺少、格式错误、签名无效、过期、已撤销或对应用户不存在的令牌 SHALL 返回 HTTP 401，且 SHALL NOT 返回受保护数据或执行操作。

#### Scenario: 有效 Bearer Token 访问本班 API
- **WHEN** 已认证用户携带有效 Bearer Token 请求其本班受保护 API
- **THEN** 服务端根据当前用户、角色和班级成员关系继续执行原有授权规则

#### Scenario: 缺少或无效 Token
- **WHEN** 调用者未提供 Bearer Token，或提供无效、过期或已撤销的 Token
- **THEN** 服务端返回 HTTP 401，且不返回材料、检索结果或其他受保护数据

### Requirement: Token 登出与撤销
系统 SHALL 提供撤销当前 Bearer Token 的登出接口。撤销记录 SHALL 至少保留至令牌过期，且后续携带同一令牌的请求 SHALL 返回 HTTP 401。登出接口 SHALL 是幂等的，不得泄露令牌是否已被撤销。

#### Scenario: 登出后令牌不可用
- **WHEN** 已认证调用者撤销当前 Bearer Token 后再次使用该 Token 请求受保护 API
- **THEN** 服务端返回 HTTP 401

#### Scenario: 重复登出
- **WHEN** 调用者重复提交同一有效 Bearer Token 的登出请求
- **THEN** 系统以成功的幂等响应处理请求，且该 Token 保持不可用于受保护请求

### Requirement: 浏览器 Bearer Token 使用方式
系统 SHALL 使浏览器登录页通过同源请求获得 Bearer Token，并由浏览器前端在会话内保存该 Token，向后续受保护 API 请求附加 `Authorization` 请求头。服务端渲染的导航页面 SHALL NOT 因无法自动携带 Authorization 请求头而直接返回受保护材料、班级或检索数据；浏览器缺少 Token 时 SHALL 跳转或显示登录入口。

#### Scenario: 浏览器登录后请求材料数据
- **WHEN** 用户在浏览器登录页获得有效 Bearer Token 并进入材料界面
- **THEN** 浏览器使用 Authorization 请求头获取本班材料、检索结果和正文，且服务端不以 Cookie 会话授权这些数据

#### Scenario: 浏览器缺少 Token
- **WHEN** 浏览器打开材料界面但没有有效的会话内 Bearer Token
- **THEN** 浏览器不显示受保护数据，并引导用户回到登录入口

### Requirement: Cookie 会话认证弃用
系统 SHALL NOT 使用 Flask Cookie 会话作为受保护请求的认证依据，且新登录流程 SHALL NOT 创建登录 Cookie 会话。已有 Cookie 会话 SHALL 不可用于访问受保护 API 或材料数据。

#### Scenario: 仅携带旧 Cookie 的请求
- **WHEN** 调用者只携带旧的 Flask 会话 Cookie 而未提供 Bearer Token
- **THEN** 系统以 HTTP 401 拒绝受保护 API 或材料数据请求

### Requirement: Token 秘密配置保护
系统 SHALL 在启动时要求独立的 `AUTH_TOKEN_SECRET` 服务端环境变量；变量缺失时 SHALL 失败启动。该秘密 SHALL NOT 出现在浏览器代码、API 响应、日志、`.env.example` 的实际值或版本控制文件中。

#### Scenario: 缺少 Token 签名秘密
- **WHEN** 服务在未配置 `AUTH_TOKEN_SECRET` 的情况下启动
- **THEN** 服务启动失败，错误信息仅标识缺少的变量名且不包含任何秘密值
