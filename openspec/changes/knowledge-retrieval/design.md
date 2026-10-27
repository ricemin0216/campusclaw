# Design

## Context

当前 Flask 应用将用户、班级、材料元数据和 UTF-8 正文保存于 SQLite，并已在所有材料入口实施服务端班级校验。Docker Compose 目前仅运行应用和 SQLite 持久卷。为满足检索结果必须从 MySQL 切片正文生成的约束，本设计保留 SQLite 作为现有业务主数据源，并新增 MySQL 作为可重建的检索正文索引、Qdrant 作为可重建的向量索引。动机和行为契约见 `proposal.md` 与 `specs/knowledge-retrieval/spec.md`。

## 本次更新记录

### 新增

- 明确 MySQL 应用账户与管理员账户的密码职责、Compose 的必填变量校验以及持久卷首次初始化语义。
- 将 Qdrant 容器健康检查记录为 TCP 6333 探测，匹配当前 Compose 实现。

### 删除或替代

- 替代 Qdrant 使用 HTTP 健康端点的旧描述；检索架构、存储边界和 API 契约不变。

## Goals / Non-Goals

**Goals:**

- 为上传和种子材料建立有字符区间、可复现、可追溯的切片与向量索引。
- 让关键词、向量和混合模式都只能检索由服务端授权的班级，并返回可打开的原材料链接。
- 将切片正文固定保存在 MySQL，确保摘录不依赖 Qdrant payload。
- 在外部服务或 OpenAI 调用失败时避免返回过期或跨班切片。

**Non-Goals:**

- 不实现问答生成、聊天历史、重排序模型或引用以外的生成式 AI 功能。
- 不把 OpenAI 密钥、材料正文或摘录暴露给浏览器客户端、日志或 Qdrant payload。
- 不改变现有 `.txt`/`.md`、10 MB、材料查看、下载和删除的访问规则。
- 不承诺跨数据库的分布式事务；索引是可重建的派生数据。

## Decisions

### 派生索引的存储边界

SQLite 继续保存身份、班级成员关系及 `materials` 主记录。MySQL 8 新增 `retrieval_chunks`，字段包括稳定 UUID `chunk_id`、`material_id`、`class_id`、冗余的 `material_title`、从 1 开始的 `chunk_number`、`char_start`、`char_end`、`chunk_text`、源内容哈希和索引状态；对 `chunk_text` 建立 `FULLTEXT ... WITH PARSER ngram` 索引，以支持中文原文词检索。`(material_id, source_hash, chunk_number)` 唯一约束使重试和补建幂等。

Qdrant 使用一个 cosine collection。每个 point 的 ID 是 `chunk_id`，payload 仅有 `chunk_id`、`material_id` 与 `class_id`，不写入 `chunk_text`、标题或摘录。检索后服务端用 `chunk_id` 与 `class_id` 回查 MySQL，再构造结果。这样即使 Qdrant 配置或数据意外扩大，也不是正文存储系统。

保留 SQLite 主数据而非整体迁移到 MySQL，可将变更限定为检索派生索引，并允许索引损坏后从既有材料重建；代价是每次检索需要 MySQL 与 SQLite/Qdrant 协同校验。

### 切分策略与字符坐标

切分器以 Python Unicode 码点计算正文偏移，使用左闭右开区间 `[char_start, char_end)`。默认 `window` 策略每块 800 个字符，重叠 100 个字符，步长 700；最后不足窗口的正文仍生成一个切片。教师上传通过 `chunk_strategy` 指定 `window`、`line`、`blank_line`、`sentence` 或 `markdown_heading`；后四种策略先按边界分段，超长分段再按默认窗口拆分，确保不遗漏正文并维持有界嵌入大小。

种子材料由启动加载器从 `SEED_MATERIALS_DIR/<class-code>/` 的 `.txt`/`.md` 文件幂等导入。加载器不读取上传请求的策略，始终传入 `window`。使用源哈希记录避免每次启动重复生成材料或向量。目录中没有文件时，启动成功且不产生种子材料。

### OpenAI Embeddings 与索引任务

使用 OpenAI Embeddings API，默认模型为 `text-embedding-3-small`，可由 `OPENAI_EMBEDDING_MODEL` 覆盖。`OPENAI_API_KEY` 只从服务端环境变量读取。切片按批次发送，响应中的向量先 upsert 到 Qdrant，再将同一组可用切片标记为 MySQL ready；失败切片保持 pending/failed，不参与任何检索，并可由 CLI 的 `reindex-materials` 重试。

上传或种子导入在主材料成功持久化后创建幂等索引任务；删除则先将材料标记为不可检索、删除 Qdrant point 和 MySQL 切片，最后执行现有材料删除。任何中断都由补建任务根据源哈希修复。此派生索引与主材料不做跨库事务，但查询仅接受 MySQL ready 且仍能在 SQLite 中通过班级授权的材料，避免孤儿向量成为结果。

### 三种检索路径与融合

公共接口为 `GET /api/classes/<class_id>/search?query=<query>&mode=<keyword|vector|hybrid>`；查询不能为空，结果最多返回 10 条。路由先复用现有 `require_class_membership(class_id)`，从不相信前端传来的班级范围。

- `keyword`：仅执行 MySQL `MATCH(chunk_text) AGAINST (...)` 的全文检索，且对候选正文验证问句词确实直接出现；不创建 OpenAI 客户端、不调用 OpenAI、也不访问 Qdrant。
- `vector`：将问句嵌入后，在 Qdrant 使用 `class_id` 过滤做 cosine 搜索。只保留 score ≥ 0.35 的 point，并以 `chunk_id`、`class_id` 回查 ready MySQL 切片。
- `hybrid`：执行上述两条路径，对各路径名次做 reciprocal-rank fusion（常量 60）。排序键先是是否双路命中、再是融合分数和稳定的 `chunk_id`，因而双路命中固定排在仅单路命中之前；低于 0.35 的向量候选根本不进入融合。

命中序列化为 `title`、`chunk_number`、`char_range`、`excerpt`、`material_url`（及内部需要的 ID）。摘录最多 240 字，关键词模式围绕首次原文匹配生成，其他模式从切片开头截取；所有摘录直接来自 MySQL `chunk_text`。没有候选时统一返回 `{ "hits": [], "message": "资料中未找到相关内容" }`，不以低分或跨班候选凑数。

### Compose、健康与秘密

Compose 新增 MySQL 8、Qdrant 和各自持久卷。应用通过 `MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_DATABASE`、`MYSQL_USER`、`MYSQL_PASSWORD`、`QDRANT_URL`、`OPENAI_API_KEY`、`OPENAI_EMBEDDING_MODEL` 配置；`MYSQL_PASSWORD` 用于应用账户，独立的 `MYSQL_ROOT_PASSWORD` 仅用于 MySQL 管理员账户初始化和健康检查。Compose 对必需变量使用失败即停的插值校验。`.env.example` 只列占位变量，真实密码、OpenAI 密钥和连接字符串均保持忽略。MySQL 数据卷首次初始化后，单独修改 `.env` 不会修改数据库内现有账户密码，必须保留原值，或先备份后显式轮换/重建。

MySQL 配置 ngram 全文检索所需参数和健康检查；Qdrant 容器使用 TCP 6333 端口探测健康。应用在检索依赖未就绪时不接受索引任务，`GET /health` 继续报告现有应用就绪状态，新增检索就绪检查用于 Compose 启动依赖和运维诊断，避免将仅 SQLite 可用的状态误判为检索可用。

## Risks / Trade-offs

- [OpenAI 延迟、配额或费用] → 批量调用、指数退避、显式索引状态和可重试补建；测试使用 fake embedding client，绝不发真实请求。
- [MySQL ngram 召回与“原文直接出现”语义不完全一致] → 先用全文索引召回，再以 MySQL 返回的切片正文做直接匹配验证。
- [Qdrant 与 MySQL 索引漂移] → 使用稳定 `chunk_id`、ready 状态、删除前失效标记和幂等补建；查询只接受两端均存在的 ready 切片。
- [向量或 MySQL 查询绕过班级边界] → 入口先做 SQLite 成员校验，Qdrant filter 与 MySQL `class_id` 条件双重过滤，并覆盖跨班直接 API 测试。
- [种子材料反复导入] → 使用 class、相对路径和内容哈希组成的幂等键；空种子目录是合法状态。
- [升级引入外部服务] → Compose healthcheck、清晰的必填变量、迁移前备份现有 SQLite 卷以及可单独停用检索路由的回滚步骤。

## Migration Plan

1. 在不修改现有 SQLite 材料数据的前提下，添加 MySQL、Qdrant、环境变量、持久卷和依赖健康检查。
2. 创建 MySQL 切片表、全文索引及 Qdrant collection；部署受保护的检索路由，但在完成补建前仅返回无命中。
3. 运行 `reindex-materials` 对已有材料执行幂等补建，再启用启动时的种子材料导入和后续上传索引任务。
4. 通过预置 A/B 班账户验证三种模式、无命中、0.35 阈值、MySQL 摘录来源、材料删除和跨班拒绝。
5. 回滚时停用检索路由和新索引任务，保留 SQLite 主数据及 MySQL/Qdrant 卷以便恢复；确认无回滚需要后再按运维策略清理派生索引。
