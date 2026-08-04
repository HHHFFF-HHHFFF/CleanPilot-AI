# Autonomous Cleaning Support Agent

面向扫地机器人的多工具智能客服 Agent。项目基于 LangChain `create_agent` 构建，将通义千问、Chroma 向量检索、用户使用记录、工具调用监控与动态提示词组合为可扩展的客服工作流。

> 当前已完成命令行 Agent 的核心能力；下一步将接入 Streamlit，提供浏览器端的对话交互界面。

## 核心能力

- **Agent 编排**：使用 LangChain `create_agent` 组织模型推理与工具调用。
- **RAG 检索**：加载 TXT/PDF 知识文档，切分、向量化并写入 Chroma。
- **客服工具**：提供知识库问答、天气、用户位置、用户 ID、当前月份和外部使用记录查询。
- **动态提示词**：根据报告生成场景切换系统提示词与报告提示词。
- **工具中间件**：记录工具调用参数、结果与失败信息，并注入报告场景上下文。
- **流式响应**：按 Agent 运行状态持续输出最新消息。

## 工作流

```text
用户问题
  → Qwen Agent 推理
  → 按需调用工具（天气 / 用户信息 / RAG / 外部记录）
  → 中间件记录与动态 Prompt 切换
  → Qwen 汇总回答
```

## 环境要求

- Python 3.10+
- DashScope API Key

安装依赖：

```bash
pip install -r requirements.txt
```

配置密钥：

```powershell
$env:DASHSCOPE_API_KEY = "your_api_key"
```

不要将 API Key 写入代码、配置文件或提交到仓库。

## 运行方式

在项目根目录执行。首次运行或新增知识文档后，先构建向量库：

```bash
python -m rag.vector_store
```

启动多工具客服 Agent：

```bash
python -m agent.react_agent
```

在 PyCharm 中建议以 **Module name** 运行 `agent.react_agent`，并将项目根目录标记为 **Sources Root**。

## 工具说明

| 工具 | 用途 |
| --- | --- |
| `rag_summarize` | 检索扫地机器人知识库并概括回答 |
| `get_weather` | 返回指定城市的天气信息 |
| `get_user_location` | 返回模拟用户所在城市 |
| `get_user_id` | 返回模拟用户 ID |
| `get_current_month` | 返回模拟当前月份 |
| `fetch_external_data` | 从 CSV 查询用户使用记录 |
| `fill_context_for_report` | 标记报告场景并触发动态提示词切换 |

## 项目结构

```text
├── agent/
│   ├── react_agent.py         # create_agent 与流式执行入口
│   └── tools/
│       ├── agent_tools.py     # Agent 工具集合
│       └── middleware.py      # 工具监控与动态 Prompt 中间件
├── config/                    # 模型、Chroma、Agent 与 Prompt 配置
├── data/                      # 扫地机器人知识库与外部记录示例
├── model/                     # 通义千问 Chat/Embedding 工厂
├── prompts/                   # 系统、RAG 与报告 Prompt
├── rag/                       # 入库、检索与 RAG 总结服务
├── utils/                     # 配置、路径、日志与文件处理工具
└── requirements.txt
```

## 后续计划

- [ ] 使用 Streamlit 构建浏览器端聊天界面
- [ ] 展示 Agent 工具调用过程与运行日志
- [ ] 支持用户上传知识文档并重建向量库
- [ ] 将模拟天气和用户信息工具替换为真实服务

## 本地运行数据

`chroma_db/`、`logs/` 和 `md5.text` 为本地运行状态，已由 `.gitignore` 排除。仓库中的知识库示例会在向量化时发送到 DashScope 嵌入服务；请仅处理你有权使用的内容。