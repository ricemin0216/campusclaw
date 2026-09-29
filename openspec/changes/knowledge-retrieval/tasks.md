# Tasks

## 1. 检索基础设施与配置

- [x] 1.1 在 Compose 中新增 MySQL 8（含 ngram 全文检索配置）和 Qdrant 服务、持久卷、健康检查与应用启动依赖；验证：`docker compose config` 成功，MySQL、Qdrant 与应用均通过健康检查。
- [x] 1.2 增加 OpenAI、MySQL、Qdrant 和种子材料目录的服务端配置加载及启动校验；验证：缺少必填检索变量时给出不含秘密值的失败信息，测试确认 OpenAI 密钥不会出现在响应或日志。
- [x] 1.3 更新依赖清单、`.env.example`、忽略规则与运行文档，说明 `OPENAI_API_KEY`、MySQL/Qdrant 配置、种子目录和重建命令；验证：干净环境按文档可通过 `docker compose config`，示例文件不含真实凭据。
- [ ] 1.4 补充运行文档，说明 `MYSQL_PASSWORD` 与独立 `MYSQL_ROOT_PASSWORD` 的职责、仅服务端 `.env` 配置，以及已有 MySQL 持久卷修改密码时须显式轮换或备份后重建；验证：文档不含真实凭据，并明确仅修改 `.env` 不会自动改变已初始化数据库账户。

## 2. 派生索引存储与客户端适配

- [x] 2.1 创建 MySQL `retrieval_chunks` schema、中文全文索引、稳定切片 ID、状态与幂等唯一约束；验证：迁移测试确认全文查询可按班级返回切片，重复写入不产生重复记录。
- [x] 2.2 实现 Qdrant collection 初始化及切片向量 upsert/delete 适配器，payload 仅保留 `chunk_id`、`material_id`、`class_id`；验证：适配器测试断言 collection 使用 cosine，payload 不含正文、标题或摘录。
- [x] 2.3 实现 OpenAI Embeddings 客户端封装，默认 `text-embedding-3-small`、支持模型覆盖和批量请求；验证：fake client 测试验证输入批次、失败状态和重试路径，不发出真实网络请求。

## 3. 切分、索引与材料生命周期

- [x] 3.1 实现带 Unicode 左闭右开字符区间的 `window`、`line`、`blank_line`、`sentence`、`markdown_heading` 切分器；验证：单元测试覆盖 800/100 默认窗口重叠、替代边界、超长段回退和不遗漏正文。
- [x] 3.2 将教师上传的 `chunk_strategy` 接入材料持久化与索引任务，按顺序写入 MySQL 切片、OpenAI 向量和 Qdrant；验证：上传测试验证每个切片的序号、区间、索引状态和向量定位信息。
- [x] 3.3 实现 `SEED_MATERIALS_DIR/<class-code>/` 的启动时幂等导入，固定使用默认窗口；验证：连续两次启动不重复导入，且种子材料的切分策略和 800/100 窗口符合预期。
- [x] 3.4 实现 `reindex-materials` 补建命令和失败/孤儿索引修复；验证：对已有 SQLite 材料重复运行补建后得到一次可检索切片，失败切片不会处于 ready 状态。
- [x] 3.5 将本班教师删除材料与 MySQL/Qdrant 索引失效及清理关联；验证：删除后 MySQL、Qdrant 与三种检索模式均不再返回该材料，失败时不会留下可检索的孤儿切片。
- [x] 3.6 更新材料上传和种子材料使用说明，列出策略名称、默认窗口与重建行为；验证：文档中的上传字段和 CLI 命令可在本地运行。

## 4. 受保护检索接口与结果呈现

- [x] 4.1 实现受保护的 `GET /api/classes/<class_id>/search`，校验非空查询、模式枚举、服务端班级成员关系、最多 10 条结果及统一空结果消息；验证：未登录返回 401，跨班请求返回 403，空结果严格为 `hits: []` 与“资料中未找到相关内容”。
- [x] 4.2 实现 `keyword` 路径，仅调用 MySQL 全文索引并验证原文直接匹配；验证：使用会在调用时失败的 fake embedding/Qdrant 客户端，确认关键词命中不触发二者且不会返回不含查询词的切片。
- [x] 4.3 实现 `vector` 路径，使用 OpenAI 查询嵌入、Qdrant `class_id` filter、0.35 cosine 阈值和 MySQL 回读；验证：低于 0.35 的 fake score 不返回，结果摘录与标题均来自 MySQL 切片正文。
- [x] 4.4 实现 `hybrid` 路径的双路执行、RRF 名次融合及双路命中优先排序；验证：测试构造双路和单路候选，断言双路命中居前且低分向量候选不参与融合。
- [x] 4.5 返回材料标题、切片序号、字符区间、MySQL 摘录和受保护材料打开链接，并在材料页增加检索入口；验证：本班学生可从命中打开材料，跨班用户无法通过结果或链接获得任何正文。
- [x] 4.6 文档化检索 API、三种模式、阈值、空结果契约和不返回向量正文的安全边界；验证：按文档示例调用可获得指定 JSON 字段。

## 5. 集成验收

- [x] 5.1 使用 MySQL、Qdrant 与 OpenAI fake 的集成测试，覆盖上传索引、五种切分、种子默认策略、三种模式、0.35 阈值、双路优先、MySQL 摘录、删除清理和 A/B 班隔离；验证：完整 `pytest` 测试套件通过且不访问真实 OpenAI 服务。
- [ ] 5.2 在提供测试用环境变量的情况下启动 Compose 并运行索引补建与检索冒烟检查；验证：服务健康、同班可检索并打开材料、无关提问返回空 `hits` 和指定消息。
- [x] 5.3 为 `knowledge-retrieval` 运行 `openspec validate --strict`；验证：命令报告该变更有效。
