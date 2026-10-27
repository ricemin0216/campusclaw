# CampusClaw Freebird

面向班级的 AI 学习平台。教师可以组合角色提示词、教学技能、知识材料和受控 MCP 工具；学生在私有会话中选择智能体与技能，获得可追问、带资料引用的学习支持。

## 主要功能

- A、B 班预置学习助手，以及教师自建智能体和角色提示词。
- 每班六项预置教学技能；教师可上传 UTF-8 单文件技能定义。
- 班级材料上传、切片、关键词/向量/混合检索与资料问答。
- MCP 服务器登记、工具发现、调用与审计；同仓演示服务提供 `formula_hint` 和 `unit_convert`。
- JWT Bearer 认证、班级隔离、私有会话和 SSE 流式回答。

## 运行

需要 Docker Compose、可用的 OpenAI 兼容聊天/嵌入接口，以及在本机配置的密钥：

```bash
cp .env.example .env
# 编辑 .env，替换全部占位值；不要提交该文件
docker compose up --build -d
docker compose ps
```

健康检查：<http://localhost:8000/health>。详细配置、本地 Python 运行方式和 API 示例见 [运行说明](docs/运行说明.md)。OpenAPI 文档位于 `/api/openapi.json`，Swagger 页面位于 `/swagger`。

## 验证

安装 `requirements.txt` 后运行 `pytest -q`。测试使用模拟模型和检索客户端，不调用真实外部服务。系统功能、LLM 请求参数、知识库/Skill/MCP 传递边界及已知限制见 [PDF 验证报告](output/pdf/campusclaw_系统功能与调用验证报告.pdf)。

本学期范围不包含作业提交与自动批改、SSO、多模型编排、生产高可用和跨区域灾备。
