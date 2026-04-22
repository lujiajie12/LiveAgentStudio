import { defineStore } from 'pinia'

import { streamChat } from '@/api/chat'
import {
  broadcastStudioTts,
  buildStudioBarrageWsUrl,
  fetchStudioActionCenter,
  fetchStudioLiveOverview,
  fetchStudioMessages,
  fetchStudioPriorityQueue,
  fetchStudioSystemHealth,
  fetchStudioSystemMetrics,
  fetchStudioTraces,
  pushStudioTeleprompter
} from '@/api/studio'
import { readStudioToken, readStudioUser } from '@/utils/studioAuth'

const DEFAULT_SESSION_ID = 'studio-live-room-001'
const MAX_RAW_BARRAGES = 400

function shortenText(text, limit = 18) {
  const normalized = String(text || '').replace(/\s+/g, ' ').trim()
  if (!normalized) {
    return ''
  }
  return normalized.length > limit ? `${normalized.slice(0, limit)}...` : normalized
}

function stageLabel(stage) {
  return (
    {
      warmup: 'Warmup',
      intro: 'Intro',
      pitch: 'Pitch',
      closing: 'Closing'
    }[stage] || stage || 'Intro'
  )
}

function createLiveSession() {
  return {
    id: DEFAULT_SESSION_ID,
    title: '当前直播会话',
    subtitle: '待同步商品 · ' + stageLabel('intro'),
    current_product_id: null,
    live_stage: 'intro',
    status: 'live'
  }
}

function createHistorySessions(traces, activeSessionId) {
  const sessions = []
  const seen = new Set([activeSessionId])
  for (const trace of traces || []) {
    if (!trace.session_id || seen.has(trace.session_id)) {
      continue
    }
    seen.add(trace.session_id)
    sessions.push({
      id: trace.session_id,
      title: `历史会话 ${sessions.length + 1}`,
      subtitle: trace.session_id,
      current_product_id: null,
      live_stage: 'pitch',
      status: trace.degraded_count ? 'warning' : 'history'
    })
    if (sessions.length >= 3) {
      break
    }
  }
  return sessions
}

function defaultOverview() {
  return {
    session_id: DEFAULT_SESSION_ID,
    online_viewers: 0,
    current_product_id: null,
    live_stage: 'intro',
    interaction_rate: 0,
    conversion_rate: 0,
    conversion_rate_estimated: true,
    agent_status_summary: [
      {
        key: 'qa',
        label: 'RAG 知识答疑',
        detail: '等待新请求',
        icon: 'bot',
        status: 'idle'
      },
      {
        key: 'guardrail',
        label: '实时风控与拦截',
        detail: '拦截 0 次',
        icon: 'shield-alert',
        status: 'idle'
      },
      {
        key: 'ops',
        label: '运营控场编排',
        detail: '等待直播事件',
        icon: 'activity',
        status: 'idle'
      }
    ]
  }
}

function defaultActionCards() {
  return {
    qa: {
      key: 'qa',
      title: 'AI 当前输出',
      subtitle: '等待请求',
      tone: 'indigo',
      status: 'idle',
      editable: true,
      content: '左侧高优问题或下方指令交给 AI 生成后，这里会展示 QA、直答、脚本和复盘的最新结果。',
      detail: '等待新的 AI 请求',
      references: [],
      metadata: {}
    },
    guardrail: {
      key: 'guardrail',
      title: '实时风控与拦截',
      subtitle: '输出治理',
      tone: 'neutral',
      status: 'idle',
      editable: false,
      content: '当前暂无风控记录。发送一条请求后，这里会展示最近一次合规校验结果和拦截说明。',
      detail: '等待新的输出结果',
      references: [],
      metadata: {
        severity: 'safe',
        rule: '暂无触发规则',
        original_text: ''
      }
    },
    ops: {
      key: 'ops',
      title: '运营控场编排',
      subtitle: '流量策略提醒',
      tone: 'yellow',
      status: 'idle',
      editable: true,
      content: '当前暂无运营控场建议。可以从左侧高优问题区或主输出输入框触发 Script Agent。',
      detail: '等待新的控场脚本输出',
      references: [],
      metadata: {
        trigger: '策略建议',
        insight: '当前没有新的运营建议。',
        plans: [
          {
            id: 'A',
            title: '方案 A：维持当前节奏',
            summary: '继续观察弹幕和互动走势，等待下一轮事件。',
            prompt: '帮我生成一段运营控场话术，先保持当前节奏并观察互动变化。'
          }
        ]
      }
    }
  }
}

function mapIntentToActionKey(intent) {
  // 主输出卡统一承载 QA / direct / script / analyst / tool 结果。
  // Ops 卡只展示策略和下一步方案，不再承载完整脚本文案。
  void intent
  return 'qa'
}

function normalizeIntentName(intent) {
  return String(intent || '').trim().toLowerCase()
}

function resolveToolPresentation(metadata = {}) {
  const toolIntent = normalizeIntentName(metadata.tool_intent)
  const plannerAction = normalizeIntentName(metadata.planner_action)
  const toolsUsed = Array.isArray(metadata.tools_used) ? metadata.tools_used.map(normalizeIntentName) : []

  if (toolIntent === 'datetime' || plannerAction === 'call_datetime') {
    return {
      title: 'Tool Agent',
      subtitle: '日期时间',
      tone: 'blue',
      responseKind: 'tool_datetime',
      type: '日期时间',
      tagTone: 'tool',
      detail: '已调用日期时间工具'
    }
  }

  if (
    toolIntent === 'web_search'
    || plannerAction === 'call_web_search'
    || toolsUsed.includes('google_search')
  ) {
    return {
      title: 'Tool Agent',
      subtitle: '联网搜索',
      tone: 'blue',
      responseKind: 'tool_web_search',
      type: '联网搜索',
      tagTone: 'tool',
      detail: '已调用联网搜索工具'
    }
  }

  if (toolIntent === 'memory_recall' || plannerAction === 'recall_memory') {
    return {
      title: 'Tool Agent',
      subtitle: '记忆召回',
      tone: 'blue',
      responseKind: 'tool_memory',
      type: '记忆召回',
      tagTone: 'tool',
      detail: '已调用记忆召回工具'
    }
  }

  return null
}

function resolveOutputPresentation(intent, metadata = {}) {
  if (metadata.pending) {
    return {
      title: 'AI 当前输出',
      subtitle: '路由判断中',
      tone: 'indigo',
      responseKind: 'pending',
      type: '处理中',
      tagTone: 'stream',
      detail: '正在判断应该由哪个 Agent 或工具处理'
    }
  }

  const toolPresentation = resolveToolPresentation(metadata)
  if (toolPresentation) {
    return toolPresentation
  }

  const normalized = normalizeIntentName(intent)
  if (normalized === 'direct' || normalized === 'direct_reply' || normalized === 'skill') {
    return {
      title: 'Direct Agent',
      subtitle: '快速直答',
      tone: 'indigo',
      responseKind: 'direct',
      type: 'Direct',
      tagTone: 'stream',
      detail: normalized === 'skill' ? 'Skill 预设回答' : '直接回复，无需知识库检索'
    }
  }

  if (normalized === 'script') {
    return {
      title: 'Script Agent',
      subtitle: '口播脚本',
      tone: 'yellow',
      responseKind: 'script',
      type: '脚本',
      tagTone: 'script',
      detail: metadata.script_reason || metadata.route_reason || '已生成直播口播脚本'
    }
  }

  if (normalized === 'analyst') {
    return {
      title: 'Analyst Agent',
      subtitle: '复盘分析',
      tone: 'blue',
      responseKind: 'analyst',
      type: '复盘',
      tagTone: 'analyst',
      detail: metadata.route_reason || '已生成复盘分析'
    }
  }

  return {
    title: 'RAG 知识 Agent',
    subtitle: '实时解答',
    tone: 'indigo',
    responseKind: 'qa',
    type: 'RAG',
    tagTone: 'rag',
    detail: metadata.unresolved
      ? '知识库命中不足，建议人工复核'
      : `引用 ${metadata.references?.length || 0} 条知识片段`
  }
}

function qaCardIsPlaceholder(card) {
  const template = defaultActionCards().qa
  return !card || card.status === 'idle' || !card.content || card.content === template.content
}

function qaCardTimestamp(card) {
  const value = card?.metadata?.message_created_at
  if (!value) {
    return 0
  }
  const timestamp = new Date(value).getTime()
  return Number.isFinite(timestamp) ? timestamp : 0
}

function opsCardIsPlaceholder(card) {
  const template = defaultActionCards().ops
  return !card || card.status === 'idle' || !card.content || card.content === template.content
}

function shouldKeepCurrentOpsCard(currentOps, incomingOps, isStreamingOps = false) {
  if (!currentOps || opsCardIsPlaceholder(currentOps)) {
    return false
  }
  if (isStreamingOps) {
    return true
  }
  if (opsCardIsPlaceholder(incomingOps)) {
    return true
  }
  const currentTs = qaCardTimestamp(currentOps)
  const incomingTs = qaCardTimestamp(incomingOps)
  if (currentTs && !incomingTs) {
    return true
  }
  return currentTs > incomingTs
}

function shouldKeepCurrentQaCard(currentQa, incomingQa, isStreamingQa = false) {
  if (!currentQa || qaCardIsPlaceholder(currentQa)) {
    return false
  }

  if (isStreamingQa) {
    return true
  }

  if (qaCardIsPlaceholder(incomingQa)) {
    return true
  }

  const currentTimestamp = qaCardTimestamp(currentQa)
  const incomingTimestamp = qaCardTimestamp(incomingQa)

  if (currentTimestamp && !incomingTimestamp) {
    return true
  }

  return currentTimestamp > incomingTimestamp
}

function normalizeActionCardFromMessage(message) {
  const metadata = message.metadata || {}
  const intent = metadata.agent_name || message.agent_name || metadata.response_kind || message.intent || 'qa'
  const presentation = resolveOutputPresentation(intent, metadata)

  if (!presentation) {
    return null
  }

  return {
    key: 'qa',
    title: presentation.title,
    subtitle: presentation.subtitle,
    tone: presentation.tone,
    status: metadata.unresolved ? 'warning' : 'ready',
    editable: true,
    content: message.content || '',
    detail: presentation.detail,
    references: metadata.references || [],
    metadata: {
      ...metadata,
      message_id: message.id,
      message_created_at: message.created_at || new Date().toISOString(),
      response_kind: presentation.responseKind,
      display_type: presentation.type,
      tag_tone: presentation.tagTone,
      display_detail: presentation.detail
    }
  }
}

function buildGuardrailCardFromMessage(message) {
  const metadata = message?.metadata || {}
  const action = String(metadata.guardrail_action || 'pass').toLowerCase()
  const violations = metadata.guardrail_violations || []
  const guardrailPass = metadata.guardrail_pass !== false

  if (!message) {
    return defaultActionCards().guardrail
  }

  if (!guardrailPass || action === 'block' || action === 'hard_block') {
    return {
      key: 'guardrail',
      title: '实时风控与拦截',
      subtitle: '输出治理',
      tone: 'danger',
      status: 'blocked',
      editable: false,
      content: metadata.guardrail_reason || '命中高风险规则，系统已拦截本次输出。',
      detail: '高风险内容已拦截',
      references: [],
      metadata: {
        ...metadata,
        severity: 'danger',
        original_text: metadata.original_text || message.content
      }
    }
  }

  if (action === 'modified' || action === 'soft_block' || violations.length) {
    return {
      key: 'guardrail',
      title: '实时风控与拦截',
      subtitle: '输出治理',
      tone: 'warning',
      status: 'modified',
      editable: false,
      content: metadata.guardrail_reason || `检测到 ${violations.join('、')} 等风险点，系统已软处理后放行。`,
      detail: '已做软拦截改写',
      references: [],
      metadata: {
        ...metadata,
        severity: 'warning',
        original_text: metadata.original_text || message.content
      }
    }
  }

  return {
    key: 'guardrail',
    title: '实时风控与拦截',
    subtitle: '输出治理',
    tone: 'success',
    status: 'pass',
    editable: false,
    content: '当前无拦截事件。最近一次输出已通过敏感词、绝对化表达和引用合规校验。',
    detail: '最近一次输出已通过合规校验',
    references: [],
    metadata: {
      ...metadata,
      severity: 'safe',
      original_text: metadata.original_text || message.content
    }
  }
}

function normalizeBarrage(item) {
  return {
    id: item.id,
    user: item.display_name || item.user || 'User',
    text: item.text || '',
    created_at: item.created_at || new Date().toISOString()
  }
}

function resolveHistoryAgentName(message) {
  const metadata = message?.metadata || {}
  return metadata.agent_name || message?.agent_name || metadata.response_kind || message?.intent || ''
}

function buildHistoryCitation(message) {
  const metadata = message?.metadata || {}
  const toolPresentation = resolveToolPresentation(metadata)
  if (toolPresentation) {
    return toolPresentation.detail
  }
  const references = metadata.references
  if (Array.isArray(references) && references.length) {
    return `引用 ${references.length} 条知识片段`
  }
  const agentName = resolveHistoryAgentName(message)
  if (agentName === 'direct' || agentName === 'direct_reply') {
    return '快速直答，无需知识库检索'
  }
  if (agentName === 'script') {
    return '脚本生成记录'
  }
  if (agentName === 'analyst') {
    return '复盘分析记录'
  }
  if (agentName === 'skill') {
    return 'Skill 预设回答'
  }
  return '引用系统问答记录'
}

function buildQaHistoryEntry(message, question = '') {
  const agentName = resolveHistoryAgentName(message)
  const metadata = message.metadata || {}
  const presentation = resolveOutputPresentation(agentName, metadata)
  if (!['qa', 'direct', 'direct_reply', 'skill', 'script', 'analyst'].includes(agentName) && !resolveToolPresentation(metadata)) {
    return null
  }

  return {
    id: message.id,
    question: question || '',
    answer: message.content || '',
    references: metadata.references || [],
    type: presentation.type,
    tagTone: presentation.tagTone,
    sourceAgent: presentation.responseKind,
    createdAt: message.created_at || new Date().toISOString(),
    citation: buildHistoryCitation(message),
    messageId: message.id
  }
}

function upsertMessages(existing, incoming) {
  const indexById = new Map(existing.map((item, index) => [item.id, index]))
  const next = existing.slice()
  for (const item of incoming) {
    const index = indexById.get(item.id)
    if (index === undefined) {
      next.push(item)
      indexById.set(item.id, next.length - 1)
    } else {
      next[index] = item
    }
  }
  next.sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
  return next
}

export const useWorkspaceStore = defineStore('workspace', {
  state: () => ({
    sessions: [createLiveSession()],
    activeSessionId: DEFAULT_SESSION_ID,
    messagesBySession: {},
    overview: defaultOverview(),
    health: null,
    metrics: null,
    traces: [],
    priorityQueue: [],
    actionCenter: defaultActionCards(),
    rawBarrages: [],
    qaHistoryBySession: {},
    isStreaming: false,
    error: '',
    refreshTimerId: null,
    barrageSocket: null,
    barrageReconnectTimerId: null,
    priorityRefreshTimerId: null,
    dismissedPriorityIds: [],
    dismissedActionKeys: [],
    streamingKey: '',
    currentTraceId: '',
    ttsBusyKeys: [],
    teleprompterBusyKeys: [],
    queuedCommands: [],
    queueProcessing: false,
    awaitingFirstToken: false,
    slowRequest: false,
    slowTimerId: null,
    activeRequestText: ''
  }),
  getters: {
    activeSession(state) {
      return state.sessions.find((item) => item.id === state.activeSessionId) || state.sessions[0] || null
    },
    activeMessages(state) {
      return state.messagesBySession[state.activeSessionId] || []
    },
    activeQaHistory(state) {
      return state.qaHistoryBySession[state.activeSessionId] || []
    },
    topMetrics(state) {
      return [
        {
          key: 'viewers',
          label: '在线人数',
          value: Number(state.overview.online_viewers || 0).toLocaleString('zh-CN'),
          icon: 'users'
        },
        {
          key: 'product',
          label: '当前讲解',
          value: state.overview.current_product_id || '未设置商品',
          icon: 'shopping-cart'
        },
        {
          key: 'interaction',
          label: '互动频率',
          value: `${Number(state.overview.interaction_rate || 0).toFixed(2)}/分钟`,
          icon: 'activity'
        },
        {
          key: 'conversion',
          label: '转化率',
          value: `${Number(state.overview.conversion_rate || 0).toFixed(2)}%`,
          icon: 'trending-up'
        }
      ]
    },
    agentStatuses(state) {
      const base = state.overview.agent_status_summary?.length
        ? state.overview.agent_status_summary
        : defaultOverview().agent_status_summary

      return base.map((item) => {
        const next = { ...item }

        if (next.key === 'qa') {
          if (state.awaitingFirstToken) {
            next.status = state.slowRequest ? 'degraded' : 'busy'
            next.detail = state.slowRequest
              ? `响应较慢 · ${shortenText(state.activeRequestText, 14) || '仍在生成'}`
              : `处理中 · ${shortenText(state.activeRequestText, 14) || '等待首个响应'}`
          } else if (state.isStreaming || state.queueProcessing) {
            next.status = 'busy'
            next.detail = state.queuedCommands.length
              ? `流式输出中 · 队列 ${state.queuedCommands.length}`
              : '流式输出中...'
          } else if (state.queuedCommands.length) {
            next.status = 'busy'
            next.detail = `待处理 ${state.queuedCommands.length} 条，按点击顺序排队`
          }
        }

        if (next.key === 'ops' && state.priorityQueue.length) {
          next.status = state.priorityQueue.length > 3 ? 'busy' : next.status
          next.detail = `最近 ${state.priorityQueue.length} 条待处理直播事件`
        }

        return next
      })
    },
    priorityCards(state) {
      return state.priorityQueue.filter((item) => !state.dismissedPriorityIds.includes(item.id))
    },
    actionCards(state) {
      return ['qa', 'guardrail', 'ops']
        .map((key) => state.actionCenter[key] || defaultActionCards()[key])
        .filter((card) => !state.dismissedActionKeys.includes(card.key))
    }
  },
  actions: {
    ensureLiveSession() {
      if (!this.sessions.length) {
        this.sessions = [createLiveSession()]
      }
      if (!this.activeSessionId) {
        this.activeSessionId = this.sessions[0].id
      }
      return this.activeSession
    },
    updateLiveSessionFromOverview() {
      const session = this.ensureLiveSession()
      session.current_product_id = this.overview.current_product_id ?? null
      session.live_stage = this.overview.live_stage ?? session.live_stage
      session.subtitle = (session.current_product_id || '待同步商品') + ' · ' + stageLabel(session.live_stage)
    },
    syncSessionsWithTraces() {
      this.updateLiveSessionFromOverview()
      const current = this.ensureLiveSession()
      this.sessions = [current, ...createHistorySessions(this.traces, current.id)]
    },
    async bootstrap() {
      this.ensureLiveSession()
      await this.connectBarrageStream()
      await this.refreshDashboard()
      await this.loadMessages(this.activeSessionId)
      this.startAutoRefresh()
    },
    teardown() {
      if (this.refreshTimerId) {
        window.clearInterval(this.refreshTimerId)
        this.refreshTimerId = null
      }
      if (this.barrageReconnectTimerId) {
        window.clearTimeout(this.barrageReconnectTimerId)
        this.barrageReconnectTimerId = null
      }
      if (this.priorityRefreshTimerId) {
        window.clearTimeout(this.priorityRefreshTimerId)
        this.priorityRefreshTimerId = null
      }
      if (this.slowTimerId) {
        window.clearTimeout(this.slowTimerId)
        this.slowTimerId = null
      }
      if (this.barrageSocket) {
        this.barrageSocket.close()
        this.barrageSocket = null
      }
      if (window.speechSynthesis) {
        window.speechSynthesis.cancel()
      }
    },
    startAutoRefresh() {
      if (this.refreshTimerId) {
        window.clearInterval(this.refreshTimerId)
      }
      this.refreshTimerId = window.setInterval(() => {
        this.refreshDashboard()
      }, 15000)
    },
    schedulePriorityRefresh() {
      if (this.priorityRefreshTimerId) {
        window.clearTimeout(this.priorityRefreshTimerId)
      }
      this.priorityRefreshTimerId = window.setTimeout(async () => {
        this.priorityRefreshTimerId = null
        await Promise.allSettled([this.refreshPriorityQueue(), this.refreshOverview()])
      }, 1200)
    },
    async connectBarrageStream() {
      const session = this.ensureLiveSession()
      const token = readStudioToken()
      if (!token) {
        return
      }

      if (this.barrageReconnectTimerId) {
        window.clearTimeout(this.barrageReconnectTimerId)
        this.barrageReconnectTimerId = null
      }

      if (this.barrageSocket) {
        this.barrageSocket.close()
        this.barrageSocket = null
      }

      const socket = new WebSocket(buildStudioBarrageWsUrl(session.id, token))
      this.barrageSocket = socket

      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data)
          if (payload.type === 'snapshot') {
            this.rawBarrages = (payload.items || []).map(normalizeBarrage).slice(-MAX_RAW_BARRAGES)
            return
          }
          if (payload.type === 'barrage' && payload.item) {
            this.rawBarrages = [...this.rawBarrages.slice(-(MAX_RAW_BARRAGES - 1)), normalizeBarrage(payload.item)]
            this.schedulePriorityRefresh()
            return
          }
          if (payload.type === 'overview' && payload.item) {
            this.overview = {
              ...this.overview,
              ...payload.item
            }
            this.syncSessionsWithTraces()
          }
        } catch (error) {
        this.error = error?.message || 'Failed to send request. Please check the backend.'
      }
      }

      socket.onclose = () => {
        if (this.barrageSocket === socket) {
          this.barrageSocket = null
        }
        this.barrageReconnectTimerId = window.setTimeout(() => {
          this.connectBarrageStream()
        }, 3000)
      }

      socket.onerror = () => {
        this.error = '原始弹幕流连接异常。'
      }
    },
    async refreshDashboard() {
      const session = this.ensureLiveSession()
      const results = await Promise.allSettled([
        fetchStudioLiveOverview(session.id),
        fetchStudioSystemHealth(),
        fetchStudioSystemMetrics(),
        fetchStudioTraces(),
        fetchStudioPriorityQueue(session.id),
        fetchStudioActionCenter(session.id)
      ])

      if (results[0].status === 'fulfilled') {
        this.overview = results[0].value
      }
      if (results[1].status === 'fulfilled') {
        this.health = results[1].value
      }
      if (results[2].status === 'fulfilled') {
        this.metrics = results[2].value
      }
      if (results[3].status === 'fulfilled') {
        this.traces = results[3].value
      }
      if (results[4].status === 'fulfilled') {
        this.priorityQueue = results[4].value
      }
      if (results[5].status === 'fulfilled') {
        this.applyActionCenterPayload(results[5].value)
      }

      this.syncSessionsWithTraces()
    },
    applyActionCenterPayload(payload) {
      const cards = defaultActionCards()
      for (const card of payload?.cards || []) {
        cards[card.key] = card
      }
      const currentQa = this.actionCenter.qa
      const isStreamingQa = this.isStreaming && (this.streamingKey === 'qa' || this.awaitingFirstToken)
      if (shouldKeepCurrentQaCard(currentQa, cards.qa, isStreamingQa)) {
        cards.qa = currentQa
      }
      const currentOps = this.actionCenter.ops
      const isStreamingOps = this.isStreaming && this.streamingKey === 'ops'
      if (shouldKeepCurrentOpsCard(currentOps, cards.ops, isStreamingOps)) {
        cards.ops = currentOps
      }
      this.actionCenter = cards
      this.dismissedActionKeys = []
    },
    async loadMessages(sessionId) {
      this.activeSessionId = sessionId
      const messages = await fetchStudioMessages(sessionId)
      this.messagesBySession[sessionId] = messages
      this.hydrateQaHistoryFromMessages(sessionId, messages)
      await Promise.allSettled([
        this.refreshPriorityQueue(),
        this.refreshActionCenter(),
        this.refreshOverview(),
        this.connectBarrageStream()
      ])
      this.syncSessionsWithTraces()
    },
    async refreshOverview() {
      if (!this.activeSessionId) {
        return
      }
      this.overview = await fetchStudioLiveOverview(this.activeSessionId)
      this.syncSessionsWithTraces()
    },
    async refreshPriorityQueue() {
      if (!this.activeSessionId) {
        return
      }
      this.priorityQueue = await fetchStudioPriorityQueue(this.activeSessionId)
      this.dismissedPriorityIds = []
    },
    async refreshActionCenter() {
      if (!this.activeSessionId) {
        return
      }
      const payload = await fetchStudioActionCenter(this.activeSessionId)
      this.applyActionCenterPayload(payload)
    },
    dismissPriority(priorityId) {
      if (!this.dismissedPriorityIds.includes(priorityId)) {
        this.dismissedPriorityIds = [...this.dismissedPriorityIds, priorityId]
      }
    },
    dismissAction(actionKey) {
      if (!this.dismissedActionKeys.includes(actionKey)) {
        this.dismissedActionKeys = [...this.dismissedActionKeys, actionKey]
      }
    },
    enqueueCommand(text, source = 'manual') {
      const content = String(text || '').trim()
      if (!content) {
        return null
      }
      const entry = {
        id: `queue-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        text: content,
        source,
        created_at: new Date().toISOString()
      }
      this.queuedCommands = [...this.queuedCommands, entry]
      return entry
    },
    removeQueuedCommand(commandId) {
      this.queuedCommands = this.queuedCommands.filter((item) => item.id !== commandId)
    },
    setPendingRequestState(content) {
      this.activeRequestText = content
      this.awaitingFirstToken = true
      this.slowRequest = false

      if (this.slowTimerId) {
        window.clearTimeout(this.slowTimerId)
      }

      this.slowTimerId = window.setTimeout(() => {
        if (this.awaitingFirstToken && this.activeRequestText === content) {
          this.slowRequest = true
        }
      }, 4500)
    },
    markFirstTokenReceived() {
      if (this.slowTimerId) {
        window.clearTimeout(this.slowTimerId)
        this.slowTimerId = null
      }
      this.awaitingFirstToken = false
      this.slowRequest = false
    },
    clearPendingRequestState() {
      if (this.slowTimerId) {
        window.clearTimeout(this.slowTimerId)
        this.slowTimerId = null
      }
      this.awaitingFirstToken = false
      this.slowRequest = false
      this.activeRequestText = ''
    },
    upsertSessionMessages(sessionId, messages) {
      const existing = this.messagesBySession[sessionId] || []
      const merged = upsertMessages(existing, messages)
      this.messagesBySession[sessionId] = merged
      this.hydrateQaHistoryFromMessages(sessionId, merged)
    },
    hydrateQaHistoryFromMessages(sessionId, messages) {
      const items = []
      let pendingQuestion = ''

      for (const message of messages || []) {
        if (message.role === 'user') {
          pendingQuestion = message.content || ''
          continue
        }

        if (message.role !== 'assistant') {
          continue
        }

        const entry = buildQaHistoryEntry(message, pendingQuestion)
        if (entry) {
          items.push(entry)
        }
        pendingQuestion = ''
      }

      this.qaHistoryBySession = {
        ...this.qaHistoryBySession,
        [sessionId]: items.slice(-20)
      }
    },
    primeStreamingCard(intent, userInput, metadata = {}) {
      const key = mapIntentToActionKey(intent)
      const template = defaultActionCards()[key]
      const presentation = resolveOutputPresentation(intent, metadata)
      this.streamingKey = key
      this.actionCenter = {
        ...this.actionCenter,
        [key]: {
          ...template,
          title: presentation.title,
          subtitle: presentation.subtitle,
          status: 'streaming',
          tone: presentation.tone,
          content: '',
          detail: `处理中 · ${shortenText(userInput, 24)}`,
          metadata: {
            ...template.metadata,
            ...metadata,
            response_kind: presentation.responseKind,
            display_type: presentation.type,
            tag_tone: presentation.tagTone,
            display_detail: presentation.detail
          }
        }
      }
      this.dismissedActionKeys = this.dismissedActionKeys.filter((item) => item !== key)
    },
    appendStreamingChunk(chunk) {
      if (!this.streamingKey) {
        return
      }
      const current = this.actionCenter[this.streamingKey]
      if (!current) {
        return
      }
      this.actionCenter = {
        ...this.actionCenter,
        [this.streamingKey]: {
          ...current,
          content: `${current.content || ''}${chunk}`
        }
      }
    },
    updateStreamingStatus(message) {
      if (!this.streamingKey) {
        return
      }
      const current = this.actionCenter[this.streamingKey]
      if (!current) {
        return
      }
      this.actionCenter = {
        ...this.actionCenter,
        [this.streamingKey]: {
          ...current,
          detail: message || current.detail
        }
      }
    },
    finalizeStreamingMessage(message) {
      const actionCard = normalizeActionCardFromMessage(message)
      const guardrailCard = buildGuardrailCardFromMessage(message)
      this.actionCenter = {
        ...this.actionCenter,
        ...(actionCard ? { [actionCard.key]: actionCard } : {}),
        guardrail: guardrailCard
      }
      this.dismissedActionKeys = []
      this.streamingKey = ''
      // Refresh QA history so the final answer appears immediately
      this.hydrateQaHistoryFromMessages(this.activeSessionId, this.messagesBySession[this.activeSessionId] || [])
    },
    async executeMessage(text, source = 'manual') {
      const content = String(text || '').trim()
      if (!content) {
        return
      }

      const session = this.ensureLiveSession()
      const token = readStudioToken()
      this.error = ''
      this.isStreaming = true
      this.setPendingRequestState(content)

      const optimisticUserMessage = {
        id: `local-user-${Date.now()}`,
        session_id: session.id,
        role: 'user',
        content,
        created_at: new Date().toISOString(),
        metadata: {
          queued_source: source
        }
      }
      this.upsertSessionMessages(session.id, [optimisticUserMessage])

      try {
        await streamChat({
          token,
          payload: {
            session_id: session.id,
            user_input: content,
            current_product_id: this.overview.current_product_id ?? null,
            live_stage: this.overview.live_stage ?? session.live_stage
          },
          onEvent: (event) => {
            if (event.event === 'meta') {
              this.currentTraceId = event.data.trace_id || ''
              this.primeStreamingCard(event.data.intent, content, event.data)
              return
            }
            if (event.event === 'status') {
              this.updateStreamingStatus(event.data.message || '')
              return
            }
            if (event.event === 'token') {
              this.markFirstTokenReceived()
              this.appendStreamingChunk(event.data.content || '')
              return
            }
            if (event.event === 'final') {
              this.markFirstTokenReceived()
              if (event.data.message) {
                this.upsertSessionMessages(session.id, [event.data.message])
                this.finalizeStreamingMessage(event.data.message)
              }
              return
            }
            if (event.event === 'error') {
              this.markFirstTokenReceived()
              this.error = event.data.message || 'Request failed. Please retry.'
            }
          }
        })
      } catch (error) {
        this.error = error?.message || 'Failed to send request. Please check the backend.'
      } finally {
        this.isStreaming = false
        this.clearPendingRequestState()
        await Promise.allSettled([this.refreshPriorityQueue(), this.refreshDashboard()])
      }
    },
    async sendMessage(text, source = 'manual') {
      const content = String(text || '').trim()
      if (!content) {
        return { queued: false }
      }

      if (this.queueProcessing || this.isStreaming) {
        const entry = this.enqueueCommand(content, source)
        return { queued: true, entry }
      }

      this.queueProcessing = true
      try {
        let current = { text: content, source }

        while (current) {
          await this.executeMessage(current.text, current.source)

          const [next] = this.queuedCommands
          if (!next) {
            current = null
            continue
          }

          this.removeQueuedCommand(next.id)
          current = {
            text: next.text,
            source: next.source
          }
        }
      } finally {
        this.queueProcessing = false
      }

      return { queued: false }
    },
    async playTts(cardKey, text) {
      const content = String(text || '').trim()
      if (!content || !this.activeSessionId) {
        return
      }

      if (!this.ttsBusyKeys.includes(cardKey)) {
        this.ttsBusyKeys = [...this.ttsBusyKeys, cardKey]
      }

      try {
        await broadcastStudioTts({
          session_id: this.activeSessionId,
          text: content,
          voice: 'xiaoyun'
        })

        if (window.speechSynthesis) {
          window.speechSynthesis.cancel()
          const utterance = new SpeechSynthesisUtterance(content)
          utterance.lang = 'zh-CN'
          window.speechSynthesis.speak(utterance)
        }
      } catch (error) {
        this.error = error?.message || 'TTS 语音插播失败。'
      } finally {
        this.ttsBusyKeys = this.ttsBusyKeys.filter((item) => item !== cardKey)
      }
    },
    async pushTeleprompter(cardKey, payload) {
      if (!this.activeSessionId) {
        return
      }
      if (!this.teleprompterBusyKeys.includes(cardKey)) {
        this.teleprompterBusyKeys = [...this.teleprompterBusyKeys, cardKey]
      }
      try {
        await pushStudioTeleprompter({
          session_id: this.activeSessionId,
          ...payload
        })
      } catch (error) {
        this.error = error?.message || '推送提词器失败。'
      } finally {
        this.teleprompterBusyKeys = this.teleprompterBusyKeys.filter((item) => item !== cardKey)
      }
    },
    openTeleprompterPreview() {
      const sessionId = this.activeSessionId || DEFAULT_SESSION_ID
      window.open(`/teleprompter/${encodeURIComponent(sessionId)}`, '_blank', 'noopener')
    }
  }
})

export { DEFAULT_SESSION_ID }
