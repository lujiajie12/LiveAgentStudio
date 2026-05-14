# LiveAgentStudio

LiveAgentStudio 是一个面向直播电商场景的大模型多智能体系统，覆盖直播操作中台、后台管理、商品知识问答、直播话术生成、实时控场建议、直播复盘、长短期记忆、RAG 检索、多模态直播理解和 LangSmith 评测观测。

项目目标不是做单轮聊天 Demo，而是把直播间真实业务里的“问商品、写话术、识别当前 SKU、回答弹幕、查工具、记住偏好、做复盘、后台运维”拆成可路由、可观测、可评测、可回归的生产链路。

## 界面截图



| 直播操作中台 | 后台管理首页 | 多模态直播观察 |
| --- | --- | --- |
| <img width="360" alt="LiveAgent Studio 直播操作中台" src="https://github.com/user-attachments/assets/2065e752-fb00-4ecc-9ba0-3f38c5169011" /> | <img width="360" alt="LiveAgentStudio 后台管理首页" src="https://github.com/user-attachments/assets/186fdeee-be0f-493e-bb0d-a6aa9270e9f0" /> | <img width="360" alt="LiveAgentStudio 多模态直播观察" src="https://github.com/user-attachments/assets/abc4fc64-257b-49c4-826d-88c0bc8dbf18" /> |

| 在线检索调试 | QA Memory | Agent Flow |
| --- | --- | --- |
| 待补充 | 待补充 | 待补充 |

| 复盘报告 | 系统设置 | 深浅色主题 |
| --- | --- | --- |
| 待补充 | 待补充 | 待补充 |

## 1. Project Highlights

- 多智能体编排：基于 FastAPI + LangGraph 构建 Router、QA、Script、Analyst、Guardrail、Tool Executor、Memory 等节点。
- 混合意图路由：采用“规则边界约束 + LLM 语义分类 + Schema 校验 + fallback 兜底”的路由策略，解决直播场景 direct、QA、script、tool、memory 等边界模糊的问题。
- 商品 RAG 问答：接入 Elasticsearch BM25、Milvus 向量检索、RRF 融合和 Rerank，对商品详情、售后政策、活动规则、FAQ 进行检索增强问答。
- 直播话术生成：根据当前商品、直播阶段、库存、优惠、主播风格生成口播脚本、促单话术和重点讲解建议。
- 长短期记忆：短期记忆维护 session 上下文，Mem0 长期记忆沉淀主播偏好、常见 FAQ、商品事实和历史偏好。
- 多模态直播理解：支持直播回放文件分析，融合智能抽帧、OCR、Qwen Omni 视觉理解、ASR、弹幕意图和商品资料，识别当前 SKU 并生成场控/客服回复建议。
- LiveReplyAgent：输入“弹幕问题 + 当前 SKU + 商品资料 + 最近 ASR”，输出建议回复、依据、置信度和是否需要人工确认。
- 后台可观测：提供离线索引管理、在线检索调试、QA Memory、Agent Flow、复盘报告、系统设置和多模态观察页面。
- 主题系统：后台与中台支持深浅色主题，主题切换带从左下角按钮扩散的柔和波纹动效。
- 评测闭环：接入 LangSmith 和本地 eval 脚本，输出 Accuracy、Precision、Recall、F1、Confusion Matrix，并按 router/tool/long_memory/multimodal 拆分统计。

## 2. Architecture

```text
用户 / 主播 / 场控 / 客服
        |
        v
Vue 3 Studio / Admin Console
        |
        v
FastAPI API Layer
        |
        +--> LangGraph Runtime
        |       +--> Router Agent
        |       +--> QA Agent
        |       +--> Script Agent
        |       +--> Analyst Agent
        |       +--> Guardrail
        |       +--> Tool Executor
        |       +--> Memory Recall / Memory Write
        |
        +--> RAG Pipeline
        |       +--> Elasticsearch BM25
        |       +--> Milvus Vector Search
        |       +--> RRF Fusion
        |       +--> Rerank
        |
        +--> Multimodal Pipeline
        |       +--> Frame Sampler
        |       +--> OCR Service
        |       +--> Qwen Omni Vision Analyzer
        |       +--> ASR Transcriber
        |       +--> Product Matcher
        |       +--> LiveReplyAgent
        |
        +--> Storage / Infra
                +--> PostgreSQL
                +--> Redis
                +--> Mem0
                +--> MinIO / Etcd / Milvus / Elasticsearch
                +--> LangSmith
```

## 3. Repository Structure

```text
LiveAgentStudio/
├── backend/
│   ├── app/
│   │   ├── agents/             # Router / QA / Script / Analyst 等智能体
│   │   ├── graph/              # LangGraph 状态机与运行时
│   │   ├── rag/                # 文档解析、BM25、向量检索、RRF、Rerank
│   │   ├── multimodal/         # 抽帧、OCR、ASR、视觉理解、商品匹配、LiveReplyAgent
│   │   ├── api/                # FastAPI 路由
│   │   ├── core/               # 配置、日志、LangSmith 等基础能力
│   │   └── services/
│   ├── scripts/                # 索引、评测、smoke test、下载脚本
│   ├── tests/                  # 单元测试、集成测试、回归测试
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── pages/              # Studio、Admin、多模态观察等页面
│   │   ├── api/
│   │   ├── layouts/
│   │   └── styles/
│   └── package.json
├── deploy/
│   ├── docker-compose.yml
│   └── .env.example
├── docs/
│   ├── data/                   # 商品详情、FAQ、真实回放补充商品资料
│   └── architecture/
└── README.md
```

## 4. Core Capabilities

### 4.1 Multi-Agent Routing

系统将用户输入先交给 Router / Planner 决策，再进入不同处理链路：

| 意图 | 目标链路 | 典型问题 |
| --- | --- | --- |
| `direct` | 直接回复 | 你好、你是谁、你能做什么 |
| `qa` | 商品 RAG 问答 | 这款适合什么家庭、保修多久、材质是什么 |
| `script` | 话术生成 | 写一段促单话术、生成开场脚本、强调库存紧张 |
| `analyst` | 复盘分析 | 总结本场直播问题、分析高频弹幕 |
| `datetime` | 时间工具 | 今天几号、下周一是哪天 |
| `memory_recall` | 短期记忆回溯 | 刚刚我问了什么、上一轮你怎么回答的 |
| `long_memory` | 长期记忆写入/召回 | 记住我的话术偏好、下次还按这个风格 |

路由策略：

- 高置信硬规则优先：问候、身份说明、时间问题、话术生成、记忆元问题先由规则拦截。
- LLM 语义分类补充：规则覆盖不到的开放表达交给 Router LLM 判断。
- Schema 校验：路由输出必须满足结构化字段，避免自由文本导致后续链路不可控。
- fallback 兜底：低置信度或异常输出进入安全链路，防止误查库、误写记忆或误触工具。

### 4.2 RAG Retrieval

RAG 链路面向直播电商商品资料：

1. 文档加载：支持 Markdown、TXT、PDF、DOCX、XLSX、CSV。
2. 文档切分：Markdown 商品块结构化切分，通用文本使用递归切分。
3. 召回：
   - Elasticsearch BM25 负责关键词、SKU、商品名、售后字段召回。
   - Milvus 向量检索负责语义召回。
4. 融合：RRF 将 BM25 和向量结果进行多路融合。
5. 精排：Rerank 对候选片段排序，降低无关 FAQ、过期信息和相似商品污染。
6. 生成：QA Agent 只基于高置信上下文回答，并给出降级与人工确认策略。

### 4.3 Memory

记忆系统分为两层：

- 短期记忆：Redis 保存当前会话上下文，PostgreSQL 做会话持久化兜底，用于“刚刚问了什么”这类元问题。
- 长期记忆：Mem0 保存跨 session 的主播偏好、商品 FAQ、话术风格、用户历史偏好。

长期记忆测试覆盖：

- memory write：偏好、FAQ、商品事实是否写入。
- memory recall：新 session 是否能召回历史偏好。
- relevance：召回结果是否与当前 SKU 和问题相关。
- dedup：重复写入是否避免产生大量重复记忆。
- isolation：不同用户、不同 session 是否隔离。
- pollution control：错误事实、临时状态、无意义噪声是否避免写入。

### 4.4 Multimodal Live Understanding

多模态链路用于解决“当前直播间到底在讲哪个商品、主播刚刚说了什么、弹幕该怎么回”的问题。

```text
直播视频流 / 回放文件
        |
        +--> Smart Frame Sampler
        |       +--> 固定抽帧
        |       +--> 场景切分
        |       +--> 商品展示检测
        |
        +--> OCR Service
        |       +--> RapidOCR
        |       +--> 价格、库存、风险词结构化抽取
        |
        +--> Vision Analyzer
        |       +--> Qwen3.5-Omni-Flash / Qwen VL
        |       +--> 商品可见性、画面摘要、类目、风险提示
        |
        +--> ASR
        |       +--> faster-whisper
        |       +--> VAD
        |       +--> 关键帧附近窗口转写
        |
        +--> Product Matcher
        |       +--> OCR + Vision + ASR + 商品资料 + 排品队列融合打分
        |       +--> 强证据门槛，避免仅靠排品队列误判
        |
        +--> LiveReplyAgent
                +--> 弹幕问题 + 当前 SKU + 商品资料 + 最近 ASR
                +--> 建议回复、依据、置信度、人工确认标记
```

当前已验证的真实回放样例：

- 视频：`backend/storage/李佳琪直播带货.mp4`
- 商品：`老卤豆干（SKU-005）`
- 链路：智能抽帧 + OCR + Qwen Omni 视觉摘要 + 窗口 ASR + 商品匹配 + LiveReplyAgent。
- 结果：真实回放 smoke test 中识别 `current_product=SKU-005`，并生成带价格、活动口径和食品风险边界的回复建议。

### 4.5 Frontend

前端由两个主要入口组成：

- `LiveAgent Studio`：面向主播、场控、客服，提供直播大盘、实时弹幕、AI Action Center、QA 历史、风控提示、多模态观察。
- `Admin Console`：面向管理员，提供离线索引管理、在线检索调试、QA Memory、Agent Flow、复盘报告和系统设置。

主题系统：

- 深色主题：更偏直播中台和实时监控。
- 浅色主题：更偏后台工具和可读性。
- 主题切换：从左下角按钮触发柔和径向波纹动画，减少主题切换的突兀感。

## 5. Tech Stack

| Layer | Stack |
| --- | --- |
| Frontend | Vue 3, Vite, Pinia, Vue Router, Lucide Icons, native CSS variables |
| Backend | Python 3.11, FastAPI, LangGraph, SQLAlchemy, Pydantic, SSE |
| Agents | Router Agent, QA Agent, Script Agent, Analyst Agent, Guardrail, Tool Executor |
| RAG | Elasticsearch BM25, Milvus, RRF, Rerank, Markdown/XLSX parser |
| Memory | Redis, PostgreSQL, Mem0 |
| Multimodal | OpenCV, RapidOCR, faster-whisper, FFmpeg, Qwen3.5-Omni-Flash / Qwen VL |
| Evaluation | LangSmith tracing/evaluate, local eval scripts, confusion matrix metrics |
| Infra | Docker Compose, PostgreSQL, Redis, Milvus, MinIO, Etcd, Elasticsearch |

## 6. Environment Variables

配置职责分离：

| File | Responsibility | Examples |
| --- | --- | --- |
| `backend/.env` | 后端运行时配置 | DB、Redis、LLM、Router、Planner、SerpAPI、LangSmith、Mem0、Milvus、ES、Embedding、多模态模型 |
| `deploy/.env` | Docker Compose 基础设施配置 | PostgreSQL 账号、端口、Milvus 镜像、Elasticsearch JVM 参数、前后端镜像 |

不要把业务配置重复放到 `deploy/.env`。以下配置只放 `backend/.env`：

- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL`
- `ROUTER_MODEL`
- `PLANNER_MODEL`
- `SERPAPI_API_KEY`
- `LANGSMITH_*`
- `QA_MEMORY_*`
- `MEM0_*`
- `EMBEDDING_*`
- `MULTIMODAL_*`

多模态推荐配置：

```dotenv
MULTIMODAL_VISION_PROVIDER=qwen_omni
MULTIMODAL_VISION_MODEL=qwen3.5-omni-flash
MULTIMODAL_VISION_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

MULTIMODAL_ASR_PROVIDER=faster_whisper
MULTIMODAL_ASR_MODEL_SIZE=small
MULTIMODAL_ASR_LANGUAGE=zh
MULTIMODAL_ASR_BEAM_SIZE=5
```

## 7. Installation

### 7.1 Python

```powershell
conda create -n liveagent python=3.11 -y
conda activate liveagent
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
```

如果要启用 Mem0：

```powershell
python -m pip install "mem0ai[async]"
```

如果要启用 GPU embedding，请按你的 CUDA 版本先安装 PyTorch。例如 CUDA 12.4：

```powershell
python -m pip install torch==2.6.0+cu124 --index-url https://download.pytorch.org/whl/cu124
```

### 7.2 Frontend

```powershell
cd frontend
npm install
```

### 7.3 FFmpeg

多模态回放分析需要 FFmpeg 用于音频窗口截取。确认命令可用：

```powershell
ffmpeg -version
```

## 8. Local Development

### 8.1 Start Infrastructure

```powershell
cd deploy
docker compose up -d postgres redis etcd minio milvus elasticsearch
docker compose ps
```

### 8.2 Start Backend

```powershell
cd backend
python -X utf8 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

API docs:

- `http://localhost:8000/docs`

### 8.3 Start Frontend

```powershell
cd frontend
npm run dev
```

Frontend:

- `http://localhost:5173`

## 9. Knowledge Base Indexing

### 9.1 Data Sources

知识库文档位于：

```text
docs/data/
```

当前包含：

- `直播电商商品详情模拟资料库_1000商品.md`
- `直播电商FAQ资料库_6000条.xlsx`
- `直播电商真实回放商品补充资料_老卤豆干.md`

支持格式：

- `.md`
- `.txt`
- `.pdf`
- `.docx`
- `.xlsx`
- `.xls`
- `.csv`

### 9.2 Rebuild Index

```powershell
cd backend
python scripts/index_data.py --docs-dir ../docs/data --reset
```

常用参数：

| Parameter | Description |
| --- | --- |
| `--reset` | 重建 Milvus collection，再 swap 成正式 collection |
| `--es-only` | 只写 Elasticsearch |
| `--milvus-only` | 只写 Milvus |
| `--chunk-size` | 文档切分长度 |
| `--chunk-overlap` | 切分重叠长度 |

当前索引写入策略：

- Elasticsearch 用于 BM25 召回。
- Milvus 用于向量召回。
- reset 场景使用临时 collection 重建，再切换为正式 collection。
- Milvus insert 改为多批累计后 flush，避免每个 batch 都 flush 导致写入过慢。

## 10. Docker Compose Deployment

复制配置：

```powershell
Copy-Item backend/.env.example backend/.env
Copy-Item deploy/.env.example deploy/.env
```

启动：

```powershell
cd deploy
docker compose up -d --build
```

说明：

- `deploy/.env` 只负责基础设施和镜像。
- `backend/.env` 通过 `env_file` 注入 backend 容器。
- 如果拉不到 Docker Hub 镜像，请在 `deploy/.env` 中替换基础镜像地址。

## 11. Testing and Evaluation

本项目测试分为五层：

1. 后端单元测试：Agent、RAG、记忆、多模态模块。
2. 前端构建测试：Vite production build。
3. 多模态 smoke test：真实或合成直播回放文件。
4. Router/Memory 分类评测：本地 eval 和 LangSmith dataset/experiment。
5. 业务 contract 评测：按 direct、qa、script、analyst、datetime、memory_recall、long_memory 拆分统计。

### 11.1 Backend Unit Tests

```powershell
cd backend
pytest
```

多模态核心测试：

```powershell
cd backend
python -m pytest `
  tests/test_live_reply_agent.py `
  tests/test_multimodal_product_matcher.py `
  tests/test_multimodal_pipeline.py `
  tests/test_qwen_vl_vision_analyzer.py `
  tests/test_multimodal_product_feed.py `
  -q
```

当前已验证结果：

```text
16 passed
```

覆盖点：

- LiveReplyAgent 回复建议、置信度和人工确认策略。
- ProductMatcher 多通道融合打分。
- 排品队列不能单独决定当前 SKU。
- ASR 明确命中商品时优先于排品顺序。
- 回放分析使用关键帧附近窗口 ASR，不做全片污染。
- Qwen Vision Analyzer JSON 解析和 fallback。
- Product Feed 商品卡/排品接口解析。

### 11.2 Frontend Build

```powershell
cd frontend
npm run build
```

当前已验证结果：

```text
vite build passed
```

### 11.3 Multimodal Smoke Test

合成视频测试：

```powershell
cd backend
$env:PYTHONPATH='.'
python scripts/smoke_multimodal_pipeline.py --max-frames 6
```

真实回放测试：

```powershell
cd backend
$env:PYTHONPATH='.'
$env:MULTIMODAL_ASR_MODEL_SIZE='tiny'
python scripts/smoke_multimodal_pipeline.py `
  --video "storage\李佳琪直播带货.mp4" `
  --session-id mm-real-smoke `
  --strategy smart `
  --interval 45 `
  --max-frames 2 `
  --enable-asr
```

当前真实回放 smoke 记录：

| Item | Result |
| --- | --- |
| Video | `backend/storage/李佳琪直播带货.mp4` |
| Strategy | smart frame sampling |
| Frames | 2 |
| ASR | windowed faster-whisper tiny for smoke |
| Current Product | `SKU-005` |
| Product Name | 老卤豆干 |
| Suggestions | 2 |
| Local Runtime | about 38 seconds on CPU smoke setting |

说明：

- smoke 中使用 `tiny` 是为了快速验证链路；正式配置推荐 `small` 或更高。
- 真实 ASR 会受音质、背景声、口音和模型大小影响。
- 当前多模态 smoke 是链路可用性验证，不是生产级并发压测。

### 11.4 Router / Memory Evaluation

评测入口：

```powershell
cd backend
python scripts/eval_router_memory_langsmith.py --mode all
```

模式：

| Mode | Scope |
| --- | --- |
| `router` | direct、qa、script、analyst、datetime |
| `memory` | 短期记忆回溯 |
| `long_memory` | Mem0 长期记忆写入、召回、去重、隔离、污染控制 |
| `all` | router + memory + long_memory |

常用命令：

```powershell
cd backend

# compact seed suite，用于快速回归
python scripts/eval_router_memory_langsmith.py --mode all --dataset-size 0

# 默认扩展集，脚本默认 200 条
python scripts/eval_router_memory_langsmith.py --mode all --dataset-size 200

# 大规模扩展集，适合同步到 LangSmith 后做批量实验
python scripts/eval_router_memory_langsmith.py --mode all --dataset-size 1000

# 只同步 LangSmith dataset，不调用后端
python scripts/eval_router_memory_langsmith.py --mode all --dataset-size 1000 --langsmith --create-dataset --sync-dataset-only

# 运行 LangSmith experiment
python scripts/eval_router_memory_langsmith.py --mode all --dataset-size 200 --langsmith --create-dataset

# 单独跑长期记忆
python scripts/eval_router_memory_langsmith.py --mode long_memory --langsmith --create-dataset
```

### 11.5 Evaluation Dataset Scale

评测脚本支持按目标规模自动扩展样例。当前默认分布如下。

启用 Mem0 长期记忆时，`--dataset-size 200` 分布：

| Label | Count |
| --- | ---: |
| direct | 25 |
| qa | 35 |
| script | 35 |
| analyst | 25 |
| datetime | 25 |
| memory_recall | 25 |
| long_memory | 30 |
| Total | 200 |

启用 Mem0 长期记忆时，`--dataset-size 1000` 会按同等比例放大：

| Label | Approx Count |
| --- | ---: |
| direct | 125 |
| qa | 175 |
| script | 175 |
| analyst | 125 |
| datetime | 125 |
| memory_recall | 125 |
| long_memory | 150 |
| Total | 1000 |

未启用 Mem0 时，long_memory 样例会自动跳过，分布会重新分配到 router 和 memory_recall 类别，避免因为外部服务未配置导致整体评测不可用。

### 11.6 Current Evaluation Result

当前 compact acceptance suite 验收结果：

| Metric | Value |
| --- | ---: |
| Accuracy | 91.89% |
| Contract Pass Rate | 91.89% |
| Macro F1 | 83.33% |
| Weighted F1 | 91.89% |
| Router Subset | 100% |
| Tool Subset | 100% |
| Long Memory Subset | 57.14% |

解释：

- Router/Tool 已达到当前验收目标，说明 direct、qa、script、analyst、datetime、tool calling 的边界已经比较稳定。
- Long Memory 仍是主要短板，去重、跨用户隔离、污染控制已经通过；写入后即时召回仍受 Mem0 异步处理和严格 contract 影响。
- 大规模 `--dataset-size 200/1000` 主要用于扩大样例覆盖面和同步 LangSmith UI 做回归，不建议把外部服务波动和核心路由能力混成一个指标。

### 11.7 Metrics Definition

| Metric | Meaning |
| --- | --- |
| Accuracy | 所有样例中预测类别与期望类别一致的比例 |
| Precision | 预测为某类的样例中，真实属于该类的比例 |
| Recall | 某真实类别中，被正确召回为该类的比例 |
| F1 | Precision 和 Recall 的调和平均 |
| Macro F1 | 每个类别 F1 的简单平均，适合观察小类问题 |
| Weighted F1 | 按 support 加权的 F1，适合观察整体稳定性 |
| Confusion Matrix | 行为真实类别，列为预测类别，用于定位混淆方向 |
| Contract Pass Rate | 不只看 route label，还检查 agent_name、tool_intent、planner_action 等契约字段 |

### 11.8 Known Historical Evaluation Findings

早期 200 条扩展评测暴露过以下问题，并已经作为修复目标：

- direct recall 低：问候、身份、能力说明被 QA 吃掉。
- script recall 低：话术、促单、优惠、库存类生成请求被 QA 吃掉。
- QA precision 低：QA 吸收了 direct 和 script 的问题。
- long_memory error：Mem0 写入、即时召回、跨 session 召回契约不稳定。

当前修复策略：

- direct 不查库。
- script 不被 QA 吃掉。
- memory_recall 与 long_memory write 分离。
- router/tool/long_memory 分开评测。
- 商品识别不允许仅靠排品队列命中，必须有 OCR、ASR、视觉或商品资料强证据。

## 12. LangSmith Usage

`.env` 配置：

```dotenv
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your_langsmith_key
LANGSMITH_PROJECT=liveagent-router-memory-dev
```

同步 dataset：

```powershell
cd backend
python scripts/eval_router_memory_langsmith.py --mode all --dataset-size 1000 --langsmith --create-dataset --sync-dataset-only
```

运行 experiment：

```powershell
python scripts/eval_router_memory_langsmith.py --mode all --dataset-size 200 --langsmith --create-dataset
```

在 LangSmith UI 中重点观察：

- 每个 case 的 input/output。
- Router trace。
- Memory write/recall trace。
- tool_intent 和 planner_action。
- 错误样例对应的 confusion matrix。
- Prompt 或规则修改前后的 experiment 对比。

## 13. API Examples

### 13.1 Chat

```http
POST /api/v1/chat
```

典型输入：

```json
{
  "message": "这款老卤豆干多少钱？",
  "session_id": "demo-session",
  "current_product_id": "SKU-005"
}
```

### 13.2 Multimodal Video Analysis

```http
POST /api/v1/multimodal/sessions/analyze-video
```

典型输入：

```json
{
  "session_id": "mm-real-demo",
  "video_path": "storage/李佳琪直播带货.mp4",
  "frame_config": {
    "strategy": "smart",
    "interval_seconds": 45,
    "max_frames": 2
  },
  "enable_ocr": true,
  "enable_vision": true,
  "enable_asr": true,
  "enable_product_match": true,
  "barrage_texts": [
    "多少钱？",
    "这款辣不辣？",
    "保质期多久？"
  ],
  "product_catalog": [
    {
      "product_id": "SKU-005",
      "name": "老卤豆干",
      "tags": ["豆制品", "零食", "香辣", "辣油", "芝麻", "45天"],
      "price": 29.9,
      "aliases": ["香辣豆干", "豆干", "卤豆干"]
    }
  ]
}
```

### 13.3 Live Reply Suggestion

```http
POST /api/v1/multimodal/live-reply/suggest
```

输出包含：

- `reply_text`
- `confidence`
- `evidence`
- `needs_human_review`
- `already_covered_by_anchor`
- `policy_flags`

## 14. Development Commands

```powershell
# Backend tests
cd backend
pytest

# Frontend build
cd frontend
npm run build

# Rebuild knowledge index
cd backend
python scripts/index_data.py --docs-dir ../docs/data --reset

# Router/memory compact eval
cd backend
python scripts/eval_router_memory_langsmith.py --mode all --dataset-size 0

# Router/memory large eval
python scripts/eval_router_memory_langsmith.py --mode all --dataset-size 1000

# Multimodal smoke
$env:PYTHONPATH='.'
python scripts/smoke_multimodal_pipeline.py --max-frames 6
```

## 15. Troubleshooting

### 15.1 Milvus `channel not found`

```powershell
cd deploy
docker compose restart etcd minio milvus
```

如果仍失败：

```powershell
cd deploy
docker compose down
docker compose up -d etcd minio milvus
```

### 15.2 Docker Hub Image Pull Failed

如果出现：

- `failed to fetch anonymous token`
- `registry-1.docker.io connection timeout`
- `dial tcp auth.docker.io`

处理：

1. 确认 Docker Desktop 网络代理。
2. 在 `deploy/.env` 中替换：
   - `BACKEND_BASE_IMAGE`
   - `FRONTEND_NODE_BASE_IMAGE`
   - `FRONTEND_NGINX_BASE_IMAGE`
3. 重新构建：

```powershell
cd deploy
docker compose build --no-cache backend frontend
docker compose up -d
```

### 15.3 Memory Not Working

检查：

```dotenv
QA_MEMORY_ENABLED=true
MEM0_API_KEY=your_mem0_key
```

并确认安装：

```powershell
python -m pip install "mem0ai[async]"
```

### 15.4 ASR Too Slow

本地 CPU 跑 faster-whisper `small` 可能较慢。开发 smoke 可以临时使用：

```powershell
$env:MULTIMODAL_ASR_MODEL_SIZE='tiny'
```

正式效果建议使用 `small` 或更高模型，并优先使用 GPU。

### 15.5 Real Replay Product Match Is Wrong

排查顺序：

1. 是否启用了真实 ASR，而不是使用 demo ASR。
2. 当前商品是否在 `product_catalog` 或商品卡接口里。
3. 商品资料是否已写入 `docs/data` 并重建索引。
4. ASR 是否命中商品名、别名、价格、口味、规格等强证据。
5. ProductMatcher 的 candidates 中查看 `features` 和 `matched_channels`。

## 16. Roadmap

短期：

- 完善 long_memory 写入后即时召回契约，降低 Mem0 异步延迟对评测的影响。
- 将多模态候选 SKU 的 `features` 和 `matched_channels` 展示到前端。
- 增加更多真实直播回放样例，覆盖食品、美妆、小家电、母婴、宠物等类目。
- 补充前端 Playwright 端到端测试。

中期：

- 接入直播排品接口和商品卡接口，减少手动传入 product_catalog。
- 引入可学习排序模型替代纯手工权重 ProductMatcher。
- 将商品图片、直播帧接入 CLIP/SigLIP 多模态向量检索。
- 建立多模态 RAG：当前画面 + 当前 SKU + 商品知识库联合问答。

长期：

- 支持 RTMP/直播流实时接入。
- 建立直播多模态复盘报告，结合画面、口播、弹幕、转化事件分析。
- 完善线上压测，输出并发、P95/P99 延迟、ASR 吞吐和多模态事件处理延迟。

## 17. Project Summary for Resume

LiveAgentStudio 是一个面向直播电商场景的大模型多智能体系统。项目基于 FastAPI、LangGraph、Vue 3、Milvus、Elasticsearch、Redis、PostgreSQL、Mem0 和 Qwen Omni 构建，覆盖商品 RAG 问答、直播话术生成、实时控场建议、短期/长期记忆、LangSmith 评测和多模态直播理解。系统通过规则边界 + LLM 路由 + Schema 校验解决 direct、QA、script、tool、memory 的路由混淆问题；通过 BM25 + 向量检索 + RRF + Rerank 提升商品知识召回质量；通过 OpenCV 抽帧、RapidOCR、faster-whisper ASR 和 Qwen Omni 视觉理解识别当前直播商品，并由 LiveReplyAgent 生成可落地的客服/场控回复建议。当前 compact acceptance suite 达到 91.89% Accuracy，Router/Tool 子集达到 100%，多模态核心链路已通过真实直播回放 smoke test。

## 18. License

See `LICENSE`.
