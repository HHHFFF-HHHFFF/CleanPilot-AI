# 智扫通：多工具扫地机器人智能客服 Agent

面向扫地机器人售前与售后场景的 AI 客服项目。项目基于 LangChain `create_agent` 构建，结合通义千问、Chroma RAG、用户使用记录、浏览器授权定位和实时天气，为用户提供可追溯的智能问答与使用建议。

## 功能亮点

- **RAG 知识问答**：将 TXT、PDF 等产品资料切分、向量化并写入 Chroma，检索后生成依据知识库的回答。
- **多工具 Agent**：模型根据问题自主组合知识库检索、天气查询、当前城市、用户标识、时间范围和外部使用记录等工具。
- **实时位置与天气**：Streamlit 页面会请求浏览器位置授权；授权后解析当前城市，并展示实时天气。Agent 可在需要时使用当前城市上下文。
- **可视化执行摘要**：前端以半透明小字号卡片展示“理解—决策—执行—整合”的处理摘要，最终回答单独以正常聊天样式呈现。
- **动态提示词**：通过中间件识别报告任务，按需切换普通客服与报告生成提示词。
- **会话式前端**：支持多轮聊天、历史消息回放、本地天气刷新和流式状态展示。

## 工作流程

```text
用户在 Streamlit 页面提问
  ↓
Agent 理解问题并选择所需工具
  ├─ RAG：检索 Chroma 中的产品知识
  ├─ 位置 / 天气：读取浏览器授权城市并查询实时天气
  └─ 用户记录：查询外部 CSV 中的模拟使用数据
  ↓
中间件记录调用并按场景注入提示词
  ↓
Agent 整合信息，生成最终客服答复
  ↓
前端区分展示处理摘要与最终回答
```

## 技术栈

- Python 3.10+
- LangChain / LangGraph
- 通义千问（DashScope）Chat 与 Embedding 模型
- ChromaDB
- Streamlit
- Open-Meteo、OpenStreetMap Nominatim

## 环境准备

### 1. 安装依赖

```powershell
pip install -r requirements.txt
```

### 2. 配置 DashScope API Key

```powershell
$env:DASHSCOPE_API_KEY = "your_api_key"
```

请勿将 API Key 写入代码、配置文件或提交到仓库。

## 运行项目

在项目根目录执行：

```powershell
# 首次运行或更新 data/ 中的知识文件后，构建向量库
python -m rag.vector_store

# 启动命令行 Agent（可选）
python -m agent.react_agent

# 启动 Streamlit 前端
python -m streamlit run app.py
```

使用 `python -m streamlit` 可以确保 Streamlit 与项目解释器一致。如出现 `ModuleNotFoundError: streamlit_js_eval`，请确认运行命令中的 `python` 是已安装依赖的项目环境。

## 浏览器位置与隐私

- 位置访问必须由用户在浏览器中主动授权；未授权时不会使用 IP 推断位置。
- 经纬度仅保存在当前 Streamlit 会话中，不写入聊天历史、日志或 Chroma 向量库。
- 为获取城市与天气，授权后的经纬度会请求 OpenStreetMap Nominatim（城市反查）和 Open-Meteo（实时天气）。
- 天气服务不可用时，界面会显示提示；Agent 会使用其余可用信息继续回答。

## 知识库运营

侧边栏的“知识库运营”页面提供面向运营人员的知识文件管理能力：

- 同步并接管 `data/` 目录中已有的 TXT/PDF 与 Chroma 索引状态；不会因已有片段而重复调用 Embedding。
- 上传单个 TXT/PDF，限制文件类型和 10MB 大小，并在入库前扫描常见提示注入式指令。
- 展示文件状态、片段数、风险等级和失败原因；支持单文件重新入库或仅从 Chroma 索引移除。
- 采用 SQLite `data/support.db` 保存文件 Hash、状态和片段数；只有全部批次写入成功后才标记为“已入库”。网络失败时仅清理当前文件的半成品，不影响已成功文件。

`data/support.db` 与 `data/uploads/` 是本地运行数据，默认不提交到仓库。项目内置知识文件应继续通过 Git 管理。

## Agent 工具

| 工具 | 作用 |
| --- | --- |
| `rag_summarize` | 检索扫地机器人知识库并概括回答 |
| `get_weather` | 查询指定城市的实时天气 |
| `get_user_location` | 获取已授权浏览器位置对应的当前城市 |
| `get_user_id` | 返回模拟用户 ID |
| `get_current_month` | 返回模拟月份 |
| `fetch_external_data` | 从 CSV 查询模拟用户使用记录 |
| `fill_context_for_report` | 切换报告生成场景的提示词上下文 |

## 测试与 RAG 评测

项目提供两类质量保障：

- **离线单元测试**：覆盖评测集格式、来源路径归一化、Recall@K 与 MRR 计算。不会调用通义千问、Chroma 或天气服务。
- **真实检索评测**：使用 `evals/rag_cases.json` 中的标注问题，检查 Chroma 返回的 Top-K 文档是否包含预期知识文件。此步骤会调用 Embedding 服务，但不会调用聊天模型。

```powershell
# 运行离线单元测试
python -m pytest

# 运行真实 Chroma 检索评测，默认使用 config/chroma.yml 的 k 值
python -m evals.rag_retrieval

# 指定 Top-5 检索并覆盖报告输出位置
python -m evals.rag_retrieval --k 5 --report evals/reports/retrieval_report.json
```

请始终在项目根目录运行上述命令；评测脚本会固定使用项目根目录的 `chroma_db/`。如果报告中所有 `retrieved_sources` 都为空，先检查是否误在 `evals/` 目录中直接运行脚本，导致打开了错误的空数据库。

报告会输出以下指标：

- **Recall@K**：每个问题的 Top-K 检索结果中，是否至少包含一个预期知识文件；适合监控“资料有没有被找回来”。
- **MRR**：首个正确知识文件的平均倒数排名；数值越高，说明正确资料通常越靠前。

初始评测集包含 15 条覆盖选购、维护、故障与扫拖场景的用例。新增或修改知识库后，应补充对应问题和预期来源文件，再观察指标变化。

## 前端交互说明

1. 打开页面后，根据浏览器提示决定是否授权位置访问。
2. 在“本地天气”卡片中查看当前城市、天气、气温和湿度；可手动刷新。
3. 输入扫地机器人相关问题。
4. 助手消息上方的“处理过程”仅显示可审阅的工具调用与信息整合摘要，不暴露模型的隐藏逐字推理。
5. 下方以正常文本展示最终回答。

## 项目结构

```text
├── app.py                         # Streamlit 对话、位置和天气界面
├── agent/
│   ├── react_agent.py             # Agent 创建与结构化流式事件
│   └── tools/
│       ├── agent_tools.py         # RAG、天气、用户记录等工具
│       └── middleware.py          # 工具监控与动态提示词中间件
├── config/                        # 模型、Chroma、Agent 与 Prompt 配置
├── data/                          # 知识库文档与外部记录示例
├── model/                         # 通义千问 Chat / Embedding 工厂
├── prompts/                       # 系统、RAG 和报告 Prompt
├── rag/                           # 文档入库、检索与 RAG 服务
├── utils/
│   ├── location_weather.py        # 坐标解析、城市反查与实时天气
│   └── ...
└── requirements.txt
```

## 本地运行数据

`chroma_db/`、`logs/`、`data/support.db` 和 `data/uploads/` 是本地运行状态，已由 `.gitignore` 排除。向量化会将 `data/` 中的文本发送至 DashScope Embedding 服务；仅处理你有权使用的内容。

## 后续方向

- 支持用户上传知识文档并在前端触发安全的增量入库。
- 接入真实用户账户与工单系统，替换示例 CSV 数据。
- 为工具调用、RAG 命中率和回答质量补充可观测性与评测。
- 增加会话记忆、人工转接和反馈闭环。
