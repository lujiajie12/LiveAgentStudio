# LiveAgentStudio 简历与面试准备

## 简历项目写法

### 简历标题

LiveAgentStudio：面向直播电商的大模型多智能体中台

### 一句话描述

独立设计并实现一个直播电商场景的大模型多智能体系统，支持商品 RAG 问答、主播话术生成、直播复盘、短期/长期记忆、后台索引管理、LangSmith 评测观测和深浅色中后台界面。

### 推荐简历版本

**LiveAgentStudio｜直播电商大模型多智能体中台**

- 基于 FastAPI + LangGraph 搭建多智能体编排链路，将用户输入路由到 Direct、QA、Script、Analyst、Tool Executor 等节点，解决直播场景中“闲聊直答、商品问答、口播生成、数据复盘、工具调用”混杂的问题。
- 构建商品知识库 RAG 链路，接入 Elasticsearch BM25、Milvus 向量检索、RRF 融合和 Rerank，支持商品详情、售后政策、活动规则、FAQ 等资料的检索问答。
- 设计短期记忆与 Mem0 长期记忆体系：短期记忆支持“刚刚问了什么/刚才怎么回答”，长期记忆支持跨 session 的主播偏好、FAQ 和商品事实召回，并实现去重、跨用户隔离和污染控制测试。
- 接入 LangSmith 和本地 eval 脚本，构建 router/tool/long_memory 分层评测，输出 Accuracy、Precision、Recall、F1、Confusion Matrix；compact acceptance suite 达到 91.89% Accuracy，Router/Tool 子集达到 100%。
- 使用 Vue 3 + Vite 实现后台管理系统和直播操作中台，包含离线索引、在线检索调试、QA Memory、Agent Flow、复盘报告、系统设置、主题切换波纹动效等页面。
- 针对评测中 direct 被 QA 吃掉、script 被 QA 吃掉、Mem0 SDK 兼容、session_id 超长、长期记忆污染等问题做系统边界修复，提升系统稳定性和可解释性。

### 更偏大模型应用开发的简短版本

**LiveAgentStudio｜大模型多智能体直播电商中台**

基于 FastAPI、LangGraph、Vue 3、Milvus、Elasticsearch、Redis、PostgreSQL 和 Mem0 构建直播电商多智能体系统。负责 Router/QA/Script/Analyst/Guardrail 编排、RAG 商品问答、长短期记忆、LangSmith 评测和中后台界面开发。通过规则边界 + LLM 路由结合的方式解决 direct/script/QA 混淆问题，构建 Accuracy、Precision、Recall、F1、Confusion Matrix 指标体系，compact suite 达到 91.89% Accuracy。

### 面试时可以强调的关键词

多智能体编排、RAG、LangGraph、LangSmith、Mem0、长期记忆、短期记忆、路由边界、工具调用、SSE、可观测性、混淆矩阵、Precision/Recall/F1、直播电商业务场景。

## 面试官高频问题与回答

### 1. 这个项目解决什么问题？

回答：

直播电商场景不是普通聊天，主播、场控、客服会在同一个入口里问不同类型的问题，比如“你是谁”“这款适合什么人”“写一段促单话术”“刚刚我问了什么”“今天几号”“生成复盘”。如果全部交给一个大模型，很容易查错库、走错链路、回答不可控。我做的是把这些需求拆成多智能体系统，通过 Router 决策边界把请求分发到 Direct、QA、Script、Analyst、Tool 和 Memory 链路，再用评测体系验证边界是否稳定。

### 2. 为什么用多智能体，不直接一个 Prompt 搞定？

回答：

一个 Prompt 可以做 Demo，但生产里会出现两个问题：第一是边界不稳定，比如写话术被当成知识问答，问候也去查库；第二是可观测和评测困难，很难知道到底是路由错、检索错、生成错还是记忆错。多智能体拆分后，每个节点职责明确，可以单独评测 router、tool、long_memory，也方便定位问题。

### 3. Router 是怎么做的？

回答：

Router 采用“硬边界规则 + LLM 分类”的方式。明确高置信场景先走规则，比如问候、身份、能力介绍直接进入 Direct；包含话术、脚本、口播、促单、库存、优惠等生成意图进入 Script；时间类进入 datetime tool；“刚刚/之前/记得/回忆”类元问题进入 memory_recall。规则覆盖不了的再交给 LLM 判断。这样比单纯调 prompt 更稳定，尤其能避免 direct 被 QA 吃掉、script 被 QA 吃掉。

### 4. RAG 链路怎么设计？

回答：

知识来源包括商品详情、售后政策、活动规则、FAQ 等文档。离线阶段做文档解析、切分和索引，在线阶段同时走 BM25 和向量检索，再通过 RRF 融合和 rerank 排序，最后把证据交给 QA Agent 生成答案。这样兼顾关键词匹配和语义召回，适合商品参数、售后规则这种既需要精确词又需要语义理解的场景。

### 5. 短期记忆和长期记忆怎么区分？

回答：

短期记忆服务当前 session，比如“刚刚我问了什么”“你刚才怎么回答我的”，主要来自 Redis 和 PostgreSQL 会话历史。长期记忆面向跨 session 的用户偏好和高价值事实，比如主播偏好“短句、有紧迫感”、某 SKU 的常见 FAQ。长期记忆接入 Mem0，写入时经过 policy 做过滤，召回时按 user/agent/app scope 限制，避免跨用户污染。

### 6. 长期记忆遇到过什么坑？

回答：

主要有三个坑：

第一，评测脚本生成的 session_id 太长，超过数据库 `varchar(36)`，导致 long_memory 一进聊天流就失败。后来把评测 session_id 改成 hash 短 ID。

第二，Mem0 SDK 版本变化后，`get_all(user_id=...)` 和 `search(user_id=...)` 兼容性有问题，需要按新 API 使用实体过滤，并处理 metadata 格式差异。

第三，Mem0 写入存在异步处理和可见性延迟，所以评测不能写完马上断言，要轮询 insights 或单独拆 long_memory 指标，避免外部服务延迟污染 router 指标。

### 7. LangSmith 在项目里怎么用？

回答：

我用 LangSmith 做两件事：第一是 tracing，把 router、memory search、memory write、工具调用等节点串起来，方便看一次请求具体走了哪些节点；第二是 evaluation，把路由和记忆测试集同步为 dataset，然后跑 expected contract，输出 Accuracy、Precision、Recall、F1 和 Confusion Matrix。后来我把评测拆成 router/tool/long_memory，避免不同能力互相污染指标。

### 8. 你怎么判断路由效果好不好？

回答：

我不只看总体 Accuracy，还看每类 Precision、Recall、F1 和 Confusion Matrix。比如早期 200 条评测里 direct recall 是 0，说明所有 direct 都被 QA 吃掉；script recall 只有 0.57，说明大量脚本生成请求也进了 QA；QA precision 低是因为它吃进了 direct 和 script。通过混淆矩阵能直接定位系统边界问题，而不是盲目调大模型回答。

### 9. 为什么说“不是继续调大模型回答，而是理清系统决策边界”？

回答：

因为当 direct、script、QA 边界错了，后面的回答质量再调也没用。例如“你好，在吗”如果进 QA，就会查商品知识库并生成商品回答；“写一段促单话术”如果进 QA，也会变成商品资料解释。这个时候问题不在生成，而在系统决策。所以我先把 direct 不查库、script 不被 QA 吃掉、long_memory 单独评测这些边界定清楚。

### 10. Guardrail 做了什么？

回答：

Guardrail 负责最终输出前的风险控制，包括敏感词、夸大承诺、极限词、售后/医疗/专业建议等风险。直播电商里不能随便承诺绝对效果、最低价、绝不出问题，所以 Guardrail 会把高风险内容拦截或降级成更稳妥的表达。

### 11. 为什么要做后台管理系统？

回答：

大模型应用不是只有聊天入口，生产里还需要索引管理、检索调试、记忆观测、Agent Flow、复盘报告和系统设置。后台管理系统让管理员能看到知识库状态、检索效果、记忆命中、路由过程和系统健康状态，方便定位线上问题。

### 12. 前端你做了什么？

回答：

前端用 Vue 3 + Vite 实现了两个主要界面：LiveAgent Studio 直播操作中台和后台管理系统。中台面向主播/场控/客服，展示直播大盘、实时弹幕、AI Action Center、QA 历史和风控提示；后台面向 admin，包含离线索引、检索调试、QA Memory、Agent Flow、复盘报告和系统设置。另外做了深浅色主题和从左下角按钮扩散的主题切换波纹效果。

### 13. SSE 流式响应为什么需要？

回答：

直播场景对实时性敏感，用户不能等完整生成后才看到结果。SSE 可以把生成过程流式返回前端，同时后端仍能在最终结果完成后落库、刷新短期记忆、写入长期记忆和记录可观测信息。

### 14. 项目的测试怎么做？

回答：

分三层：

第一是前端构建测试，确保 Vue/Vite 构建通过。

第二是 compact acceptance suite，覆盖 direct、qa、script、analyst、datetime、memory_recall 和 long_memory，当前 37 条样本 Accuracy 91.89%。

第三是 LangSmith 或本地 eval 指标输出，包含 Accuracy、Precision、Recall、F1、Confusion Matrix，并按 router/tool/long_memory 分组统计。

### 15. 如果让你继续优化，会做什么？

回答：

我会继续做四件事：

1. 把 long_memory 的写入确认和召回契约继续稳定化，减少 Mem0 异步处理带来的评测波动。
2. 增加更多真实直播语料，让路由测试集从模板扩展到真实用户表达。
3. 给 RAG 增加 citation 质量评估和答案一致性评估。
4. 把 Agent Flow 做成更完整的线上调试视图，支持按 trace_id 回放一次请求的所有节点。

## 面试时的项目总结

这个项目最有价值的地方不是单点功能，而是把一个大模型应用按生产思路做完整：有多智能体边界，有 RAG，有工具调用，有长短期记忆，有 Guardrail，有后台管理，有可观测和可量化评测。过程中我不是只调 prompt，而是通过混淆矩阵发现 direct/script/QA 的边界问题，再用规则前置、SDK 兼容修复、评测拆分和契约测试把系统稳定性拉上来。
