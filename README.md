# Autonomous Cleaning Support Agent

面向扫地机器人的智能客服 Agent 基础项目。项目将知识库检索、提示词管理、通义千问模型与 Chroma 向量数据库组合，用于回答产品选购、使用、维护和故障排查类问题。

> 当前版本聚焦 Agent 的知识获取与回答基础能力；可在此基础上继续接入工具调用、工作流编排和多轮状态管理。

## 功能

- 支持 TXT 与 PDF 知识文档的加载、切分与向量化
- 使用 Chroma 持久化知识库，并按相似度检索相关片段
- 使用通义千问 `qwen3-max` 生成客服回答
- 将系统提示词、RAG 提示词和配置集中管理
- 用 MD5 记录已处理文件，避免重复入库

## 架构

```text
知识文档 → 文档加载 → 文本切分 → DashScope Embeddings → Chroma
用户问题 → 相似度检索 → RAG Prompt → Qwen Chat Model → 客服回答
```

## 环境要求

- Python 3.10+
- DashScope API Key

安装依赖：

```bash
pip install -r requirements.txt
```

配置通义千问密钥：

```powershell
$env:DASHSCOPE_API_KEY = "your_api_key"
```

不要将 API Key 写入配置文件、日志或提交到仓库。

## 使用方式

在 PyCharm 中将项目根目录标记为 **Sources Root**，然后运行：

```text
rag/vector_store.py
```

该脚本会加载 `data/` 下的知识文档、写入 Chroma，并执行一个检索示例。

运行 RAG 客服服务：

```text
rag/rag_service.py
```

仓库包含扫地机器人知识库示例。你也可以将自己的 `.txt` 或 `.pdf` 文档放入 `data/`；支持类型和切分参数可在 `config/chroma.yml` 中调整。

## 配置说明

| 文件 | 用途 |
| --- | --- |
| `config/rag.yml` | 对话模型与嵌入模型配置 |
| `config/chroma.yml` | Chroma、文档类型和切分配置 |
| `config/prompts.yml` | 提示词文件路径 |
| `prompts/` | 系统、RAG 总结与报告提示词 |

## 目录结构

```text
├── config/             # 模型、向量库和提示词配置
├── data/               # 扫地机器人知识库示例
├── model/              # 通义千问模型与 Embeddings 工厂
├── prompts/            # Prompt 模板
├── rag/                # 知识入库、检索和 RAG 服务
├── utils/              # 路径、日志、配置与文件处理工具
└── requirements.txt    # Python 依赖
```

## 本地运行数据

以下文件包含本地运行状态，已由 `.gitignore` 排除：

- `data/*`：原始知识文档
- `chroma_db/`：本地向量数据库
- `logs/`：运行日志
- `md5.text`：已处理文件记录

如需重新构建知识库，请先停止所有运行中的进程，再备份或删除 `chroma_db/` 和 `md5.text`，随后重新运行 `rag/vector_store.py`。
