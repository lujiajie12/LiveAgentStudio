# LiveAgentStudio

LiveAgentStudio 是一个面向直播电商场景的多智能体系统，覆盖问答检索、实时控场、话术生成、风控拦截、记忆管理、知识库索引和后台运维。

当前项目由三部分组成：
- `backend/`：FastAPI + LangGraph + RAG + 业务服务
- `frontend/`：Vue 3 Studio 前端与后台管理界面
- `deploy/`：Docker Compose 基础设施与部署文件

## 1. 系统能力概览

### 1.1 核心链路

- `Router / Planner`：做轻量路由、工具选择和多步规划
- `QA Agent`：负责知识问答、时间查询、搜索结果整合、记忆回溯回复
- `Script Agent`：负责生成直播场景话术
- `Analyst Agent`：负责分析建议和策略输出
- `Guardrail`：负责敏感表达、合规风险、极限词拦截

### 1.2 RAG 检索链路

- 文档加载：PDF / DOCX / XLSX / CSV / Markdown / TXT
- 文档切分：Markdown 结构化切分 + 通用文本切分
- 召回：Elasticsearch BM25 + Milvus 向量检索
- 融合：RRF + rerank
- 生成：LLM 最终回答

### 1.3 记忆体系

- 短期记忆：Redis + PostgreSQL 回放兜底
- 长期记忆：可选 Mem0 平台接入
- 记忆回溯：通过 LLM 识别 `memory_recall` 意图，再由记忆工具取数、LLM 总结回复

## 2. 目录结构

```text
LiveAgentStudio/
├── backend/                 # FastAPI 后端、Agent、RAG、脚本与测试
│   ├── app/
│   ├── scripts/
│   ├── tests/
│   ├── requirements.txt
│   └── .env.example
├── frontend/                # Vue 3 前端
├── deploy/                  # Docker Compose、Nginx、初始化脚本
│   ├── docker-compose.yml
│   └── .env.example
├── docs/                    # 设计文档与补充说明
└── README.md
```

## 3. 环境变量职责划分

这是这次统一后的标准，不要再把两边混着写。

| 文件 | 职责 | 应该放什么 |
| --- | --- | --- |
| `backend/.env` | 后端运行时配置 | 数据库连接串、Redis、LLM、Planner、Router、SerpAPI、记忆开关、Milvus/ES 地址、Embedding 参数、SSE/日志等 |
| `deploy/.env` | Docker Compose 基础设施配置 | PostgreSQL 账户、数据库名、容器对外端口、Milvus 镜像、Elasticsearch JVM 参数 |

不要重复放：
- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL`
- `SERPAPI_API_KEY`
- `QA_MEMORY_*`
- `EMBEDDING_*`

这些都只应该放在 `backend/.env`。

## 4. 依赖安装

### 4.1 Python 环境

推荐继续使用你当前的 Conda 环境名：

```powershell
conda create -n liveagent python=3.11 -y
conda activate liveagent
python -m pip install --upgrade pip
```

### 4.2 PyTorch

项目的 embedding 走 `sentence-transformers`，如果你要用 GPU，请先按你的 CUDA 版本单独安装 PyTorch。

CUDA 12.4 示例：

```powershell
python -m pip install torch==2.6.0+cu124 --index-url https://download.pytorch.org/whl/cu124
```

如果你只跑 CPU，可以先跳过这一步，直接安装 requirements。

### 4.3 安装后端依赖

```powershell
python -m pip install -r backend/requirements.txt
```

如果你要启用 Mem0 长期记忆，再额外安装：

```powershell
python -m pip install "mem0ai[async]"
```

### 4.4 安装前端依赖

```powershell
cd frontend
npm install
```

## 5. 初始化配置

### 5.1 backend/.env

先复制模板：

```powershell
Copy-Item backend/.env.example backend/.env
```

然后重点填写：
- `DATABASE_URL`
- `REDIS_URL`
- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL`
- `ROUTER_MODEL`
- `PLANNER_MODEL`
- `SERPAPI_API_KEY`
- `EMBEDDING_MODEL`

说明：
- 本地开发时，`DATABASE_URL` 和 `REDIS_URL` 一般写 `localhost`
- Docker Compose 启动的 backend 容器，会在 `deploy/docker-compose.yml` 中自动覆盖成容器内地址
- `EMBEDDING_MODEL` 可以填本地模型目录，也可以填 Hugging Face 模型 ID

### 5.2 deploy/.env

再复制部署模板：

```powershell
Copy-Item deploy/.env.example deploy/.env
```

这里只改基础设施参数：
- `DB_USER`
- `DB_PASSWORD`
- `DB_NAME`
- `POSTGRES_PORT`
- `REDIS_PORT`
- `BACKEND_PORT`
- `FRONTEND_PORT`
- `BACKEND_BASE_IMAGE`
- `FRONTEND_NODE_BASE_IMAGE`
- `FRONTEND_NGINX_BASE_IMAGE`
- `ELASTICSEARCH_PORT`
- `MILVUS_PORT`
- `MILVUS_IMAGE`

## 6. 本地开发启动

### 6.1 启动依赖服务

```powershell
cd deploy
docker compose up -d postgres redis etcd minio milvus elasticsearch
```

检查状态：

```powershell
docker compose ps
```

### 6.2 启动后端

```powershell
cd backend
python -X utf8 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

后端接口文档：
- `http://localhost:8000/docs`

### 6.3 启动前端

```powershell
cd frontend
npm run dev
```

前端默认入口：
- `http://localhost:5173`

## 7. 知识库索引流程

### 7.1 准备文档

把待索引文档放到知识库目录，例如：

```text
backend/kb_output/
docs/data/
```

支持格式：
- `.pdf`
- `.docx`
- `.xlsx`
- `.xls`
- `.csv`
- `.md`
- `.txt`

### 7.2 执行索引

```powershell
cd backend
python scripts/index_data.py --docs-dir ../docs/data --reset
```

常用参数：
- `--reset`：重建 Milvus collection，再 swap 成正式 collection
- `--es-only`：只写 Elasticsearch
- `--milvus-only`：只写 Milvus

### 7.3 当前索引策略

这次已经改成企业化一点的写法：
- 不再每个 batch 都 `flush`
- 改成连续 insert，多批累计后再 flush
- `reset` 场景保留“临时 collection 重建再 swap”

## 8. Docker Compose 部署

如果你希望直接把前后端和依赖都拉起来：

```powershell
cd deploy
docker compose up -d --build
```

说明：
- `deploy/.env` 只负责容器和端口
- `backend/.env` 会通过 `env_file` 注入 backend 容器
- `docker-compose.yml` 里已经移除了过时的 `version` 字段
- 如果机器不能直连 Docker Hub，可以把 `BACKEND_BASE_IMAGE`、`FRONTEND_NODE_BASE_IMAGE`、`FRONTEND_NGINX_BASE_IMAGE` 改成你能访问的镜像仓库地址

## 9. 常用开发命令

### 9.1 后端测试

```powershell
cd backend
pytest
```

### 9.2 前端构建验证

```powershell
cd frontend
npm run build
```

### 9.3 查看 Milvus / Compose 状态

```powershell
cd deploy
docker compose ps
docker compose logs --tail=200 milvus
```

## 10. 常见问题排查

### 10.1 `version is obsolete`

这是旧版 Compose 字段警告。当前 `deploy/docker-compose.yml` 已经移除了 `version`，如果你仍然看到它，请确认你运行的是最新文件。

### 10.2 Milvus `channel not found`

优先执行：

```powershell
cd deploy
docker compose restart etcd minio milvus
```

如果还是失败，再执行更彻底的恢复：

```powershell
cd deploy
docker compose down
docker compose up -d etcd minio milvus
```

如果 Milvus 元数据仍然损坏，再考虑删除 Milvus volume 后重建。

### 10.3 Docker build 拉不到基础镜像

如果构建时出现：
- `failed to fetch anonymous token`
- `dial tcp ... auth.docker.io`
- `registry-1.docker.io` 连接超时

这不是前后端代码问题，而是当前机器拉不到 Docker Hub。

处理顺序：
1. 先确认 Docker Desktop 自己能联网，必要时配置代理或镜像加速
2. 在 `deploy/.env` 里把以下变量改成你能访问的镜像地址：
   - `BACKEND_BASE_IMAGE`
   - `FRONTEND_NODE_BASE_IMAGE`
   - `FRONTEND_NGINX_BASE_IMAGE`
3. 再重新构建：

```powershell
cd deploy
docker compose build --no-cache backend frontend
docker compose up -d
```

### 10.4 向量模型加载慢

这是正常现象，尤其是首次加载大 embedding 模型时。请重点确认：
- `EMBEDDING_MODEL` 路径是否正确
- `EMBEDDING_DEVICE` 是否与机器硬件匹配
- GPU 环境是否先正确安装了 PyTorch

### 10.5 记忆功能没生效

先检查：
- `QA_MEMORY_ENABLED=true`
- 是否额外安装了 `mem0ai[async]`
- `MEM0_API_KEY` 等配置是否正确

### 10.6 Web 搜索没结果

先检查：
- `SERPAPI_API_KEY`
- 外网访问能力
- `SERPAPI_GL` / `SERPAPI_HL` 是否符合目标地区

## 11. 当前项目约定

- 所有后端运行时参数以 `backend/app/core/config.py` 为单一配置源
- Docker Compose 只负责基础设施，不再兜底后端业务配置
- 依赖安装以 `backend/requirements.txt` 为准，不直接拿整份 `pip freeze` 当项目依赖
- 新增配置项时，必须同时更新：
  - `backend/app/core/config.py`
  - `backend/.env.example`
  - `README.md`

## 12. 许可证

详见仓库根目录下的 `LICENSE`。
