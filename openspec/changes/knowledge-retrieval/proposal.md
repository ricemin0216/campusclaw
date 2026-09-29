# Proposal

## Why

班级材料目前可以安全上传、查看和下载，但用户无法按原文关键词或语义表述定位相关内容。增加可解释、按班级隔离的检索能力，能让师生从本班材料中快速定位原文，而不泄露其他班级数据。

## What Changes

- 将材料正文切分为可追溯的切片，并在上传成功后为每个切片生成 OpenAI Embeddings。
- 提供默认约 800 字、100 字重叠的窗口切分；教师可选择按换行、空行、句号或 Markdown 标题切分。启动时导入的种子材料始终采用默认窗口策略。
- 增加 MySQL 切片正文表及全文索引，以及 Qdrant 向量集合；MySQL 是标题、字符区间和摘录的唯一来源，Qdrant 不保存切片正文。
- 提供 `keyword`、`vector` 和 `hybrid` 三种本班检索模式。`vector` 丢弃余弦相似度低于 0.35 的候选；`hybrid` 对两路结果做名次融合并提升双路命中的切片。
- 返回包含材料标题、切片序号、字符区间、MySQL 正文摘录和材料打开链接的命中；没有可信命中时返回 `hits: []` 和“资料中未找到相关内容”。
- 为 OpenAI API 密钥、MySQL 和 Qdrant 配置 Docker Compose 服务与仅服务端环境变量配置；MySQL 应用账户与管理员账户使用不同密码，首次初始化持久卷后须通过显式运维流程轮换密码。

## Capabilities

### New Capabilities

- `knowledge-retrieval`: 班级隔离的材料切分、向量索引、关键词/向量/混合检索及可追溯命中结果。

### Modified Capabilities

无；当前主规范中尚未同步既有材料能力。本变更新增的检索行为通过独立能力定义，并复用现有服务端认证、角色和班级校验。

## Impact

- 修改 Flask 上传与材料删除流程，增加索引、重建和检索 API/页面；现有材料需可补建索引。
- 新增 MySQL 8（含中文全文检索配置）和 Qdrant Compose 服务、持久卷及健康依赖。
- 新增 OpenAI Python SDK、MySQL 驱动、Qdrant 客户端以及 `OPENAI_API_KEY`、模型和连接配置；部署者须在本机 `.env` 或部署环境设置 `MYSQL_PASSWORD` 与独立的 `MYSQL_ROOT_PASSWORD`。
- OpenAI API 调用会产生网络依赖与按量计费；密钥不会进入浏览器、日志、版本控制或 Qdrant 正文 payload。
