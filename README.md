# LiveAgentStudio

LiveAgentStudio 是一个面向直播电商场景的多智能体平台，围绕 RAG 检索增强、LangGraph 编排、实时风控、运营控场和后台治理，提供从知识库建设到直播现场执行的完整闭环。

## 产品定位

系统分为两套前端：

- `LiveAgent STUDIO v2.0`
  面向直播操作员、场控、主播和客服，强调实时处理直播现场问题。
- `直播智能体后台管理`
  面向管理员和配置人员，负责知识库、索引、Agent 调试、系统配置和复盘治理。

## 核心能力

- 多 Agent 编排：Router、QA、Script、Analyst、Guardrail
- RAG 检索链路：Rewrite、BM25、向量检索、RRF、Rerank
- 短期记忆与长期记忆：Redis + PostgreSQL
- 实时风控与拦截：敏感词、绝对化表达、引用合规校验
- 运营控场建议：促单、互动、福利、策略分流
- 后台治理：索引管理、在线调试、Agent Flow、报告复盘

## 角色与流程

### 1. 直播操作员视角

操作员使用的是 `LiveAgent STUDIO v2.0`，目标是“实时接住直播现场”。

操作流程：

1. 登录 Studio，进入独立直播操作中台。
2. 查看左侧直播大盘：在线人数、当前讲解商品、转化率、Agent 状态。
3. 关注中间区域：
   - 原始弹幕流持续滚动
   - 高优意图捕捉把值得处理的问题筛出来
4. 对高优问题点击“交由 AI 生成”：
   - 问题先一键填入 RAG 卡片里的输入框
   - 操作员确认后点击发送
5. 后端执行主链路：
   - Router 判断这是 `qa / script / analyst`
   - 如果是 QA，就走 `RAG 检索 + LLM 生成`
   - 如果是 Script，就走话术生成
   - 所有输出都经过 Guardrail
6. 右侧 Action Center 返回结果：
   - `RAG 知识 Agent` 给出知识答复或可口播话术
   - `实时风控与拦截` 在有风险时给出补救提醒
   - `运营控场编排` 给出 A/B 策略建议
7. 操作员根据结果执行动作：
   - 直接口播
   - 推送提词器
   - 触发 TTS 语音插播
   - 忽略或切换方案
8. 整个过程中，会话消息、trace、短期记忆、工具日志都会被系统记录下来。

一句话概括：

`看现场 -> 抓问题 -> 让 AI 出方案 -> 人来决策和执行`

### 2. 管理员视角

管理员使用的是 `直播智能体后台管理`，目标是“让系统可配置、可维护、可优化”。

操作流程：

1. 登录后台管理系统，而不是进入 Studio。
2. 查看后台首页总览，确认系统运行状态。
3. 管理知识库：
   - 维护文档
   - 运行离线索引
   - 查看 ES / Milvus 状态
4. 做在线检索调试：
   - 查看 query rewrite
   - 查看 BM25 / 向量检索 / RRF / rerank
   - 判断某条问题为什么答得好或答得不好
5. 查看 Agent Flow：
   - 某条请求经过了哪些节点
   - 哪一步发生降级
   - 哪一步报错
   - Guardrail 是否拦截
6. 管理系统配置：
   - 主播风格偏好
   - 自定义敏感词
   - 后续可扩展权限与角色策略
7. 查看报告与复盘：
   - 高频问题
   - 未解决问题
   - 哪类脚本使用较多
   - 下一场直播如何优化
8. 根据这些结果反向优化系统：
   - 补知识文档
   - 调检索策略
   - 调 Prompt
   - 调风控规则
   - 调 Agent 配置

一句话概括：

`配系统 -> 看运行 -> 做调优 -> 让前线用得更稳`

## 技术栈

### 后端

- FastAPI
- LangGraph
- LangChain
- PostgreSQL
- Redis
- Elasticsearch
- Milvus

### 前端

- Vue 3
- Vite
- Pinia
- Axios

### 基础设施

- Docker
- Docker Compose
- Nginx

## 目录结构

```text
LiveAgentStudio/
├── backend/              # FastAPI + LangGraph + RAG + 业务服务
├── frontend/             # Vue 3 前端，包含后台管理与 Studio v2
├── deploy/               # Docker Compose 与部署配置
├── docs/                 # 架构文档与设计资料
├── scripts/              # 工具脚本与运维脚本
└── README.md
```

## 本地启动

### 前置要求

- Docker Desktop
- Python 3.11+
- Node.js 18+

### 1. 启动依赖服务

```powershell
cd deploy
docker compose up -d postgres redis etcd minio milvus elasticsearch
```

### 2. 启动后端

```powershell
cd backend
D:\Env\anaconda\envs\liveagent\python.exe -X utf8 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. 启动前端

```powershell
cd frontend
npm install
npm run dev
```

## 访问入口

- 后端接口文档：`http://localhost:8000/docs`
- 管理员登录：`/login`
- 直播工作人员登录：`/studio-login`
- Studio 中台：`/studio-v2`

## 主要页面

### 后台管理

- 首页总览
- 离线索引管理
- 在线检索调试
- Agent Flow
- 报告中心
- 系统设置

### LiveAgent STUDIO v2.0

- 直播大盘
- 高优意图捕捉
- 原始弹幕流
- RAG 知识 Agent
- 实时风控与拦截
- 运营控场编排

## 测试

### 后端测试

```powershell
cd backend
pytest
```

### 前端构建验证

```powershell
cd frontend
npm run build
```

## 开发说明

- Chat 主链统一走 `/api/v1/chat/stream`
- Agent Flow、系统健康、RAG 调试、报告和设置走后台管理接口
- Studio 更强调实时交互与动作执行，后台管理更强调治理、调试和复盘

## 许可证

详见项目中的 `LICENSE` 文件。
