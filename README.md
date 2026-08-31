# CleanPilot AI：多智能体设备服务平台

面向智能清洁设备售前咨询、使用指导、故障诊断与用户运营场景的企业级多智能体服务平台。项目基于 LangChain `create_agent` 与 LangGraph 构建“调度 Agent + 知识问答、故障诊断、用户运营三个功能 Agent”，结合通义千问、Chroma RAG、SQLite 业务数据、FastAPI 身份认证、React 会话工作台、浏览器授权定位与实时天气，形成从知识运营、任务路由、工具执行到服务结果沉淀的完整业务闭环。

## 功能亮点

- **RAG 知识问答**：将 TXT、PDF 产品资料切分、向量化并写入 Chroma；检索相关片段后生成有依据的回答。
- **知识库运营**：提供内置资料同步、TXT/PDF 上传、安全扫描、文件状态查看、重试入库和按文件移除索引能力。
- **安全入库**：上传文件限制类型与 10 MB 大小；入库前扫描常见提示注入指令，批量写入失败时清理当前文件的半成品向量。
- **受控多 Agent 协作**：调度 Agent 输出结构化路由结果，将问题交给知识问答、故障诊断或用户运营 Agent；功能 Agent 按最小权限使用各自工具。
- **用户运营动态 Prompt**：调度结果中的 `task_mode` 会写入运行上下文，用户运营 Agent 在普通服务和使用报告 Prompt 之间切换，不再依赖额外工具修改报告状态。
- **业务数据闭环**：CSV 仅作为版本化演示数据源，首次启动时导入 SQLite；Agent 以参数化查询读取用户、设备和月度使用记录。
- **API 与身份边界**：FastAPI 提供登录、当前用户和 NDJSON 流式对话接口；密码使用 PBKDF2 哈希保存，JWT 负责短期身份认证，Agent 用户 ID 只从令牌注入。
- **独立 React 用户端**：提供账户登录、设备概览、自动定位天气、Agent 团队状态、流式处理摘要与 Markdown 回答；令牌仅保存在当前浏览器标签页。
- **定位与天气**：用户授权浏览器位置后，解析城市并展示实时天气；Agent 可在需要时使用当前城市上下文。
- **可审阅执行摘要**：前端以半透明小字号卡片展示“理解—决策—执行—整合”摘要，最终答案以正常聊天样式单独显示。
- **账户会话历史**：React 左侧栏展示当前用户的历史会话，支持新建、切换和删除；问题、最终回答及处理摘要写入 SQLite，并按登录用户隔离。

## 工作流程

```text
启动 FastAPI 或 Streamlit
  ├─ 首次运行：data/external/records.csv -> SQLite data/support.db
  ├─ FastAPI：登录 -> JWT -> 获取当前用户和设备
  ├─ Streamlit：暂时保留演示用户选择，作为内部调试客户端
  └─ 发起对话
       -> 调度 Agent 输出 target_agent + task_mode
          ├─ 知识问答 Agent：RAG、城市和天气
          ├─ 故障诊断 Agent：RAG、安全诊断、必要时天气环境
          └─ 用户运营 Agent：当前用户、月份、SQLite 使用记录、RAG
       -> 用户运营 Agent 根据 task_mode 动态切换普通/报告 Prompt
       -> 中间件记录调用、注入定位，并强制绑定当前会话用户
       -> 功能 Agent 整合信息，输出 trace 与最终回答
       -> 前端分别展示处理摘要与最终答案
```

## 技术栈

- Python 3.10+
- LangChain / LangGraph
- 通义千问（DashScope Chat 与 Embedding）
- ChromaDB
- SQLite
- FastAPI / Uvicorn / PyJWT
- PBKDF2-HMAC-SHA256 / Bearer Token
- React 19 / TypeScript / Vite
- Streamlit / streamlit-js-eval（内部知识库运营）
- Open-Meteo / OpenStreetMap Nominatim
- pytest

## 环境准备

前端需要 Node.js `^20.19.0` 或 `>=22.12.0`，并建议使用 pnpm；后端继续使用 Python 3.10+。

### 1. 安装依赖

```powershell
pip install -r requirements.txt
```

### 2. 配置 DashScope API Key

```powershell
$env:DASHSCOPE_API_KEY = "your_api_key"
```

请勿将 API Key 写入代码、配置文件或提交到仓库。

### 3. 配置 API 登录密钥

复制 `.env.example` 中的变量到本地环境。项目不会自动读取 `.env`，PowerShell 可按下面方式设置：

```powershell
$env:APP_JWT_SECRET = "使用随机生成的至少32位密钥"
$env:APP_JWT_EXPIRE_SECONDS = "3600"
$env:APP_CORS_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173"
```

可以使用 `python -c "import secrets; print(secrets.token_urlsafe(48))"` 生成随机密钥。开发环境如需为尚无凭证的演示用户统一初始化密码，可临时设置 `APP_DEMO_PASSWORD`；生产环境不要使用统一密码。

## 运行项目

请在项目根目录执行：

```powershell
# 首次运行，或 data/ 中的知识文件发生变化后：同步知识库
python -m rag.vector_store

# 启动命令行 Agent（可选）
python -m agent.react_agent

# 启动 Streamlit 前端
python -m streamlit run app.py

# 启动 FastAPI，默认地址 http://127.0.0.1:8000
python -m uvicorn api.main:app --reload

# 为单个已导入用户设置或重置密码
python -m scripts.set_user_password 1001

# 安装并启动 React 用户端，默认地址 http://127.0.0.1:5173
cd web
pnpm install
pnpm dev
```

前端默认请求 `http://127.0.0.1:8000`。如后端地址不同，可复制 `web/.env.example` 为 `web/.env.local`，并修改 `VITE_API_BASE_URL`。

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
- Streamlit 侧边栏选择的用户 ID 会传入 Agent 运行时上下文；该入口暂时用于内部调试。
- FastAPI 将密码哈希写入 `user_credentials` 表；登录成功后，受保护接口只接受 Bearer Token，不接收客户端提交的 Agent 用户 ID。
- `get_user_id` 返回当前运行上下文中的用户；FastAPI 模式下该值来自已验证令牌，而不是模型或请求正文。
- `get_current_month` 返回机器当前日期对应的 `YYYY-MM`；`fetch_external_data` 使用参数化 SQLite 查询返回 JSON 使用记录，不再直接读取 CSV。
- 修改 `records.csv` 后，如需重新初始化演示业务数据，可删除本地 `data/support.db` 再启动项目。该操作会同时清除知识库运营状态记录，但不会删除 Chroma 向量；可在知识库运营页重新同步状态。
- 演示数据不包含真实个人信息。生产接入时应替换为经身份鉴权的账户、设备与工单数据源，并实施访问控制与审计。

## FastAPI 接口

| 方法与路径 | 鉴权 | 作用 |
| --- | --- | --- |
| `GET /health` | 无 | 存活检查，不加载模型和向量库 |
| `POST /api/v1/auth/login` | 无 | 使用用户 ID 和密码换取短期 JWT |
| `GET /api/v1/users/me` | Bearer Token | 返回当前用户与绑定设备 |
| `POST /api/v1/context/location-weather` | Bearer Token | 根据浏览器授权坐标返回城市与实时天气 |
| `POST /api/v1/context/city-weather` | Bearer Token | 浏览器无法定位时查询账户城市天气 |
| `GET/POST /api/v1/conversations` | Bearer Token | 查询当前用户会话或创建新会话 |
| `GET/DELETE /api/v1/conversations/{id}` | Bearer Token | 读取或删除当前用户指定会话 |
| `POST /api/v1/chat/stream` | Bearer Token | 以 NDJSON 流输出 Agent 处理摘要和最终回答 |

`/api/v1/chat/stream` 请求包含 `query`、`conversation_id` 和可选的 `location_profile`。接口拒绝额外的 `user_id` 字段，并强制把令牌中的当前用户传给多 Agent 运行上下文，从 API 层、会话仓储和工具中间件三层阻止跨用户查询。

## Agent 工具

### Agent 职责与权限

| Agent | 负责场景 | 可用能力 |
| --- | --- | --- |
| 调度 Agent | 意图识别与结构化路由 | 不调用业务工具，不直接回答问题 |
| 知识问答 Agent | 通用选购、使用、维护和环境适配 | RAG、当前城市、天气 |
| 故障诊断 Agent | 报警码、无法启动、回充失败、异响、漏水等异常 | RAG、当前城市、天气；包含安全停止与转人工规则 |
| 用户运营 Agent | 个人使用报告、设备记录、保修与个性化建议 | 当前用户、当前月份、SQLite 使用记录、RAG、城市和天气 |

用户运营工具由中间件强制绑定当前会话 `user_id`。即使模型生成了其他用户 ID，实际查询参数仍会被覆盖为当前用户；缺少会话身份时直接拒绝查询。

### 公共工具

| 工具 | 当前作用 |
| --- | --- |
| `rag_summarize` | 检索扫地机器人知识库并概括回答 |
| `get_weather` | 查询指定城市的实时天气 |
| `get_user_location` | 返回当前会话中已授权浏览器定位对应的城市 |
| `get_user_id` | 返回当前侧边栏选中的会话用户 ID |
| `get_current_month` | 返回系统当前月份，格式为 `YYYY-MM` |
| `fetch_external_data` | 参数化查询 SQLite 中当前会话用户、指定月份的使用记录 |

## 浏览器位置与隐私

- 位置访问必须由用户在浏览器中主动授权；未授权时不会使用 IP 推断位置。
- 经纬度仅保存在当前 Streamlit 会话中，不写入聊天记录、日志、SQLite 或 Chroma。
- 授权后的经纬度仅用于请求 OpenStreetMap Nominatim 的城市反查和 Open-Meteo 的实时天气。
- 天气服务不可用时，页面会提示错误；Agent 会继续使用其他可用信息回答。

## 测试与 RAG 评测

项目包含两类质量保障：

- **离线单元测试**：覆盖密码哈希、JWT、登录接口、身份伪造拦截、多 Agent 兜底路由、功能 Agent 委派、用户数据权限绑定、知识库安全扫描、状态仓储、业务数据初始化，以及 Recall@K、MRR 计算；不调用通义千问、Chroma 或天气服务。
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

## React 用户端

1. 使用已经设置密码的用户 ID 登录；JWT 仅保存在 `sessionStorage`，关闭标签页后自动清除。
2. 登录后自动读取当前用户和绑定设备，浏览器会请求位置授权并通过 FastAPI 查询实时天气；无法定位时自动降级为账户城市天气。
3. 输入扫地机器人相关问题；前端逐行解析 NDJSON，实时展示调度、工具执行和信息整合摘要。
4. 处理摘要使用弱化卡片显示，并在最终回答完成后自动折叠；最终内容支持 Markdown 排版。
5. 左侧栏按更新时间展示账户历史会话，可新建、切换或删除；移动端通过顶部会话按钮打开历史抽屉。
6. 用户可以中止正在生成的回答；令牌过期或接口返回 `401` 时自动退出到登录页。

会话历史用于跨刷新恢复页面消息，但当前 Agent 每次仍以本轮问题为主要输入，不会自动把整段历史发送给模型。后续长期记忆会增加历史摘要、上下文窗口控制和敏感信息过滤。

Streamlit 客服页目前仍可作为内部调试入口，知识库上传与索引运营继续由 Streamlit 承担。React 完成全部功能验收后，再移除 Streamlit 面向用户的演示用户选择流程。

## 项目结构

```text
├── app.py                         # Streamlit 对话、用户选择、定位和天气界面
├── api/                           # FastAPI 应用、接口契约与环境配置
├── auth/                          # 密码哈希、JWT 与认证服务
├── agent/
│   ├── contracts.py               # 结构化路由契约
│   ├── router_agent.py            # 调度 Agent 与本地兜底路由
│   ├── specialist_agents.py       # 三个功能 Agent 及工具白名单
│   ├── react_agent.py             # 多 Agent 兼容入口与流式事件
│   └── tools/
│       ├── agent_tools.py         # 懒加载的 RAG、天气与业务记录工具
│       └── middleware.py          # 工具监控、用户权限与动态 Prompt
├── config/                        # 模型、Chroma、Agent 配置
├── data/                          # 知识库文件与业务演示数据源
├── docs/                          # 交付路线图
├── evals/                         # RAG 评测案例、脚本与报告输出
├── model/                         # 通义千问 Chat / Embedding 工厂
├── prompts/                       # 调度、三个功能 Agent、RAG 和报告 Prompt
├── rag/                           # 知识库入库、检索与 RAG 服务
├── scripts/                       # 用户密码等本地维护脚本
├── storage/                       # SQLite 仓储：运营状态、业务数据与登录凭证
├── tests/                         # 离线单元测试
├── ui/                            # Streamlit 知识库运营页面
├── utils/                         # 定位天气、配置、安全扫描等工具
├── web/                           # React 登录、设备概览与流式对话用户端
└── requirements.txt
```

## 本地运行数据

`chroma_db/`、`logs/`、`data/support.db`、`data/uploads/` 和 `evals/reports/` 是本地运行或评测输出，已由 `.gitignore` 排除。向量化会将 `data/` 中的知识文本发送至 DashScope Embedding 服务；仅处理你有权使用的内容。

## 后续方向

- 增加知识文件的定时增量导入、审计日志和内容所有者审核工作流。
- 增加 React 设备详情、历史报告与账户设置页面，将 Streamlit 完全降级为内部运营工具。
- 增加刷新令牌、登录限流、审计日志和账户管理流程，并接入真实工单/CRM 系统。
- 在现有检索评测基础上，增加工具调用成功率、答案质量、用户反馈和生产环境监控。
- 为故障诊断 Agent 增加图片报警码、设备部件和 App 截图的多模态识别。
- 增加模型可用的长期会话记忆、人工转接和客服反馈闭环，并将成熟流程沉淀为可复用 Skill。
