# 智扫通：多工具扫地机器人智能客服 Agent

面向扫地机器人售前、使用指导与售后场景的 AI 客服项目。项目基于 LangChain `create_agent` 构建，结合通义千问、Chroma RAG、SQLite 业务数据、浏览器授权定位与实时天气，为用户提供可审阅的智能问答和个性化使用建议。

## 功能亮点

- **RAG 知识问答**：将 TXT、PDF 产品资料切分、向量化并写入 Chroma；检索相关片段后生成有依据的回答。
- **知识库运营**：提供内置资料同步、TXT/PDF 上传、安全扫描、文件状态查看、重试入库和按文件移除索引能力。
- **安全入库**：上传文件限制类型与 10 MB 大小；入库前扫描常见提示注入指令，批量写入失败时清理当前文件的半成品向量。
- **多工具 Agent**：模型按问题自主选择 RAG、天气、当前城市、会话用户标识、当前月份、使用记录与报告上下文切换等 7 个工具。
- **业务数据闭环**：CSV 仅作为版本化演示数据源，首次启动时导入 SQLite；Agent 以参数化查询读取用户、设备和月度使用记录。
- **定位与天气**：用户授权浏览器位置后，解析城市并展示实时天气；Agent 可在需要时使用当前城市上下文。
- **可审阅执行摘要**：前端以半透明小字号卡片展示“理解—决策—执行—整合”摘要，最终答案以正常聊天样式单独显示。
- **本次会话回看**：页面可回看当前 Streamlit 会话中的消息与处理摘要；模型不会自动读取历史页面消息，也未实现跨会话持久化记忆。

## 工作流程

```text
启动 Streamlit
  ├─ 首次运行：data/external/records.csv -> SQLite data/support.db
  ├─ 选择演示用户并展示设备信息
  ├─ 用户可授权浏览器定位 -> 城市反查与实时天气
  └─ 输入问题
       -> Agent 根据系统提示词选择工具
          ├─ RAG：检索 Chroma 中的产品知识
          ├─ 天气 / 定位：读取当前会话定位或查询指定城市
          ├─ 业务记录：按用户 ID 和真实当前月份查询 SQLite
          └─ 使用报告：切换到结构化报告提示词
       -> 中间件记录调用并注入会话上下文
       -> 通义千问整合信息，输出 trace 与最终回答
       -> 前端分别展示处理摘要与最终答案
```

## 技术栈

- Python 3.10+
- LangChain / LangGraph
- 通义千问（DashScope Chat 与 Embedding）
- ChromaDB
- SQLite
- Streamlit / streamlit-js-eval
- Open-Meteo / OpenStreetMap Nominatim
- pytest

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

请在项目根目录执行：

```powershell
# 首次运行，或 data/ 中的知识文件发生变化后：同步知识库
python -m rag.vector_store

# 启动命令行 Agent（可选）
python -m agent.react_agent

# 启动 Streamlit 前端
python -m streamlit run app.py
```

使用 `python -m streamlit` 可以确保 Streamlit 与项目解释器一致。如出现 `ModuleNotFoundError: streamlit_js_eval`，请使用安装了依赖的项目解释器启动，而不要直接调用系统全局的 `streamlit` 命令。

## 知识库运营

侧边栏的“知识库运营”页面支持：

- 同步并接管 `data/` 目录中的 TXT/PDF 与 Chroma 索引状态；已有且内容未变的文件不会重复调用 Embedding。
- 上传单个 TXT/PDF；上传文件保存到本地 `data/uploads/`，不提交到 Git。
- 入库前执行提示注入扫描；检测到高风险文本时标记为 `blocked` 并删除上传副本。
- 展示文件状态、片段数、风险等级和失败原因；支持单文件重试入库或仅移除 Chroma 索引。
- 在 SQLite `knowledge_documents` 表保存文件 Hash、状态、片段数和失败原因；只有全部批次写入成功后才标记为 `indexed`。

当前切片配置为 **300 字符切片、50 字符重叠、Top-3 检索**，配置位于 `config/chroma.yml`。

## 业务数据与演示用户

- `data/external/records.csv` 是受 Git 管理的非敏感演示数据源，包含用户、设备和按月使用记录。
- 首次启动会将数据写入本地 SQLite `data/support.db` 的 `users`、`devices` 与 `usage_records` 表；后续启动不会重复导入。
- Streamlit 侧边栏选择的用户 ID 会传入 Agent 运行时上下文；`get_user_id` 返回当前会话用户，不再随机生成。
- `get_current_month` 返回机器当前日期对应的 `YYYY-MM`；`fetch_external_data` 使用参数化 SQLite 查询返回 JSON 使用记录，不再直接读取 CSV。
- 修改 `records.csv` 后，如需重新初始化演示业务数据，可删除本地 `data/support.db` 再启动项目。该操作会同时清除知识库运营状态记录，但不会删除 Chroma 向量；可在知识库运营页重新同步状态。
- 演示数据不包含真实个人信息。生产接入时应替换为经身份鉴权的账户、设备与工单数据源，并实施访问控制与审计。

## Agent 工具

| 工具 | 当前作用 |
| --- | --- |
| `rag_summarize` | 检索扫地机器人知识库并概括回答 |
| `get_weather` | 查询指定城市的实时天气 |
| `get_user_location` | 返回当前会话中已授权浏览器定位对应的城市 |
| `get_user_id` | 返回当前侧边栏选中的会话用户 ID |
| `get_current_month` | 返回系统当前月份，格式为 `YYYY-MM` |
| `fetch_external_data` | 参数化查询 SQLite 中指定用户、指定月份的使用记录 |
| `fill_context_for_report` | 设置报告场景标记，并切换到报告生成 Prompt |

## 浏览器位置与隐私

- 位置访问必须由用户在浏览器中主动授权；未授权时不会使用 IP 推断位置。
- 经纬度仅保存在当前 Streamlit 会话中，不写入聊天记录、日志、SQLite 或 Chroma。
- 授权后的经纬度仅用于请求 OpenStreetMap Nominatim 的城市反查和 Open-Meteo 的实时天气。
- 天气服务不可用时，页面会提示错误；Agent 会继续使用其他可用信息回答。

## 测试与 RAG 评测

项目包含两类质量保障：

- **离线单元测试**：覆盖知识库安全扫描、状态仓储、业务数据初始化，以及评测集格式、来源路径归一化、Recall@K、MRR 计算；不调用通义千问、Chroma 或天气服务。
- **真实检索评测**：使用 `evals/rag_cases.json` 的标注问题，检查 Chroma Top-K 结果是否包含预期知识文件；会调用 Embedding 服务，但不调用聊天模型。

```powershell
# 运行离线单元测试
python -m pytest

# 运行真实 Chroma 检索评测，默认使用 config/chroma.yml 的 k 值
python -m evals.rag_retrieval

# 指定 Top-5 检索并覆盖报告输出位置
python -m evals.rag_retrieval --k 5 --report evals/reports/retrieval_report.json
```

请始终在项目根目录运行上述命令。评测脚本固定使用项目根目录的 `chroma_db/`；如果报告中所有 `retrieved_sources` 都为空，先确认没有在 `evals/` 目录直接运行脚本而打开了错误的空数据库。

当前评测集包含 15 条选购、维护、故障与扫拖场景用例。已完成一次完整入库后的结果为 **Recall@3 93.33%、MRR 0.9000**。新增或修改知识库后，应补充对应问题和预期来源文件，并重新评测。

## 前端交互说明

1. 在侧边栏选择“智能客服”或“知识库运营”。
2. 在智能客服页选择演示用户；页面会展示其设备信息。
3. 根据浏览器提示决定是否授权位置访问；授权后可查看当前城市、天气、气温与湿度。
4. 输入扫地机器人相关问题。处理摘要仅展示可审阅的工具调用与信息整合过程，不展示模型的隐藏逐字推理。
5. 最终答案与本次页面会话的消息记录一同显示；刷新或关闭会话后不会恢复为长期记忆。

## 项目结构

```text
├── app.py                         # Streamlit 对话、用户选择、定位和天气界面
├── agent/
│   ├── react_agent.py             # Agent 创建与结构化流式事件
│   └── tools/
│       ├── agent_tools.py         # RAG、天气、业务记录、报告工具
│       └── middleware.py          # 工具监控、上下文注入与动态 Prompt
├── config/                        # 模型、Chroma、Agent 配置
├── data/                          # 知识库文件与业务演示数据源
├── docs/                          # 交付路线图
├── evals/                         # RAG 评测案例、脚本与报告输出
├── model/                         # 通义千问 Chat / Embedding 工厂
├── prompts/                       # 系统、RAG 和报告 Prompt
├── rag/                           # 知识库入库、检索与 RAG 服务
├── storage/                       # SQLite 仓储：运营状态与业务数据
├── tests/                         # 离线单元测试
├── ui/                            # Streamlit 知识库运营页面
├── utils/                         # 定位天气、配置、安全扫描等工具
└── requirements.txt
```

## 本地运行数据

`chroma_db/`、`logs/`、`data/support.db`、`data/uploads/` 和 `evals/reports/` 是本地运行或评测输出，已由 `.gitignore` 排除。向量化会将 `data/` 中的知识文本发送至 DashScope Embedding 服务；仅处理你有权使用的内容。

## 后续方向

- 增加知识文件的定时增量导入、审计日志和内容所有者审核工作流。
- 接入真实身份认证、账户设备、工单/CRM 系统，替换演示用户和本地业务数据。
- 在现有检索评测基础上，增加工具调用成功率、答案质量、用户反馈和生产环境监控。
- 增加模型可用的长期会话记忆、人工转接和客服反馈闭环。
