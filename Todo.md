P0：必须先做

WebSocket /api/v1/live/barrages/stream 或 GET /api/v1/live/barrages/poll
作用：把真实弹幕流接进来。没有它，高优意图捕捉就还是假链路。

POST /api/v1/live/barrages/ingest
作用：如果弹幕源不是前端直连，而是第三方推流侧回调/采集器推送，就需要一个写入入口。

GET /api/v1/live/overview
作用：直播大盘真实化，返回在线人数、当前讲解商品、转化率、互动率等。现在左侧大盘很多还是前端假数据。

POST /api/v1/teleprompter/push
作用：右侧卡片里的“推送至前方提词器”真正落地。这个是 Studio 最核心动作之一，现在还是 disabled。

P1：强相关，做完体验才完整
5. POST /api/v1/ops/priority-queue/{item_id}/ignore
作用：忽略某条高优意图时，不只是前端临时消失，而是后端真正标记掉。

POST /api/v1/ops/priority-queue/{item_id}/promote
作用：把某条高优意图正式送入 AI 处理队列，方便后续审计，不只是“填入输入框”。

POST /api/v1/ops/action-center/{card_key}/execute
作用：执行右侧卡片动作，比如“执行方案 A”“紧急下发补救”。

GET /api/v1/sessions
作用：返回当前直播会话和历史会话列表。现在会话区还是半模拟状态。

GET /api/v1/live/context
作用：返回当前直播阶段、当前商品、活动主题、展示库存口径。Studio 很多卡片都依赖这类上下文。

P2：锦上添花，但后面也得补
10. POST /api/v1/tts/broadcast/real
作用：现在 TTS 只是 MVP，本地浏览器播报 + 后端记日志。后面如果要接真正播报通道，需要独立实现。

GET /api/v1/integrations/status
作用：提词器、TTS、直播中控通道状态统一返回，顶栏状态才会可信。

GET /api/v1/ops/guardrail/events
作用：单独拉最近风控事件，方便做风控历史和高危告警列表。

GET /api/v1/ops/strategy/history
作用：运营控场建议历史，方便复盘和统计“执行了哪些策略”。

如果只按“最小闭环”来说，你下一步最该做的是这 4 个：

live barrages stream/ingest
live overview
teleprompter push
sessions list
因为这 4 个一补，Studio 就从“能演示”变成“真的能跑业务”。



查看某个端口进程命令行：
netstat -ano | findstr :8000



$ports = netstat -ano | findstr :8000
$pids = $ports | ForEach-Object { ($_ -split '\s+')[-1] } | Sort-Object -Unique
$pids | ForEach-Object { taskkill /PID $_ /F }



模拟页发弹幕 -> 后端 ingest -> 存储/聚合 -> WebSocket 广播 -> Studio 实时显示


3. Studio 不是轮询弹幕，而是订阅流
Studio 页面在 workspace.js 里有：

connectBarrageStream()
它会连到：

WebSocket /api/v1/live/barrages/stream
一旦后端 LiveBarrageService 收到新弹幕，就会 _broadcast()：

type = "barrage" 给原始弹幕流
type = "overview" 给左侧直播大盘
所以你在 Studio 里看到的“原始弹幕流”和“在线人数变化”，不是模拟页本地共享状态，而是后端实时广播出来的。

4. 高优意图捕捉是基于这些真实注入的弹幕再聚合出来的
这一步不在模拟页，而在后端的 ops_service.py。

现在 get_priority_queue() 读的是：

当前 session 最近一批 LiveBarrageEvent
然后做轻量聚类/频次归并，产出：

label
frequency
summary
prompt
所以“高优意图捕捉”并不是前端硬编码，而是基于模拟页注入的弹幕，再由后端聚合出来的二次结果。


这套实现的本质是：

模拟页不直接操作 Studio，而是伪装成直播平台上游，通过 ingest 和 overview/update 把数据送进后端；后端再像真实直播系统一样，把弹幕、在线人数和高优意图分发给 Studio。