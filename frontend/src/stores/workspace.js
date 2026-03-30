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
    subtitle: `SKU-001 · ${stageLabel('intro')}`,
    current_product_id: 'SKU-001',
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
      current_product_id: 'SKU-001',
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
    current_product_id: 'SKU-001',
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
      title: 'RAG 知识 Agent',
      subtitle: '实时解答',
      tone: 'indigo',
      status: 'idle',
      editable: true,
      content: '左侧高优问题交给 AI 生成后，这里会流式显示结合知识库与大模型生成的结果。',
      detail: '等待新的 QA 请求',
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
      content: '当前暂无运营控场建议。可从左侧高优问题区或 RAG 卡片输入框触发 Script Agent。',
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
  if (intent === 'script' || intent === 'analyst') {
    return 'ops'
  }
  return 'qa'
}

function normalizeActionCardFromMessage(message) {
  const metadata = message.metadata || {}
  const intent = message.intent || metadata.agent_name || message.agent_name || 'qa'

  if (intent === 'qa') {
    return {
      key: 'qa',
      title: 'RAG 知识 Agent',
      subtitle: '实时解答',
      tone: 'indigo',
      status: metadata.unresolved ? 'warning' : 'ready',
      editable: true,
      content: message.content || '',
      detail: metadata.unresolved
        ? '知识库命中不足，建议人工复核'
        : `引用 ${metadata.references?.length || 0} 条知识片段`,
      references: metadata.references || [],
      metadata
    }
  }

  if (intent === 'script' || intent === 'analyst') {
    return {
      key: 'ops',
      title: '运营控场编排',
      subtitle: intent === 'analyst' ? '复盘辅助' : '流量策略提醒',
      tone: intent === 'analyst' ? 'blue' : 'yellow',
      status: 'ready',
      editable: true,
      content: message.content || '',
      detail: metadata.script_reason || metadata.route_reason || '已生成新的运营建议',
      references: metadata.references || [],
      metadata
    }
  }

  return null
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
    teleprompterBusyKeys: []
  }),
  getters: {
    activeSession(state) {
      return state.sessions.find((item) => item.id === state.activeSessionId) || state.sessions[0] || null
    },
    activeMessages(state) {
      return state.messagesBySession[state.activeSessionId] || []
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
          value: state.overview.current_product_id || 'SKU-001',
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
      return state.overview.agent_status_summary?.length
        ? state.overview.agent_status_summary
        : defaultOverview().agent_status_summary
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
      session.current_product_id = this.overview.current_product_id || session.current_product_id
      session.live_stage = this.overview.live_stage || session.live_stage
      session.subtitle = `${session.current_product_id || 'SKU-001'} · ${stageLabel(session.live_stage)}`
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
            this.rawBarrages = (payload.items || []).map(normalizeBarrage).slice(-30)
            return
          }
          if (payload.type === 'barrage' && payload.item) {
            this.rawBarrages = [...this.rawBarrages.slice(-29), normalizeBarrage(payload.item)]
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
          this.error = error?.message || '弹幕流数据解析失败。'
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
      this.actionCenter = cards
      this.dismissedActionKeys = []
    },
    async loadMessages(sessionId) {
      this.activeSessionId = sessionId
      const messages = await fetchStudioMessages(sessionId)
      this.messagesBySession[sessionId] = messages
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
    upsertSessionMessages(sessionId, messages) {
      const existing = this.messagesBySession[sessionId] || []
      this.messagesBySession[sessionId] = upsertMessages(existing, messages)
    },
    primeStreamingCard(intent, userInput) {
      const key = mapIntentToActionKey(intent)
      const template = defaultActionCards()[key]
      this.streamingKey = key
      this.actionCenter = {
        ...this.actionCenter,
        [key]: {
          ...template,
          status: 'streaming',
          tone: key === 'ops' ? 'yellow' : 'indigo',
          content: '',
          detail: `正在处理：${userInput.slice(0, 24)}${userInput.length > 24 ? '...' : ''}`
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
    },
    async sendMessage(text) {
      const content = String(text || '').trim()
      if (!content) {
        return
      }

      const session = this.ensureLiveSession()
      const token = readStudioToken()
      this.error = ''
      this.isStreaming = true

      const optimisticUserMessage = {
        id: `local-user-${Date.now()}`,
        session_id: session.id,
        role: 'user',
        content,
        created_at: new Date().toISOString(),
        metadata: {}
      }
      this.upsertSessionMessages(session.id, [optimisticUserMessage])

      try {
        await streamChat({
          token,
          payload: {
            session_id: session.id,
            user_input: content,
            current_product_id: this.overview.current_product_id || session.current_product_id,
            live_stage: this.overview.live_stage || session.live_stage
          },
          onEvent: (event) => {
            if (event.event === 'meta') {
              this.currentTraceId = event.data.trace_id || ''
              this.primeStreamingCard(event.data.intent, content)
              return
            }
            if (event.event === 'token') {
              this.appendStreamingChunk(event.data.content || '')
              return
            }
            if (event.event === 'final') {
              if (event.data.message) {
                this.upsertSessionMessages(session.id, [event.data.message])
                this.finalizeStreamingMessage(event.data.message)
              }
              return
            }
            if (event.event === 'error') {
              this.error = event.data.message || '请求处理失败，请稍后重试。'
            }
          }
        })
      } catch (error) {
        this.error = error?.message || '发送失败，请检查后端状态。'
      } finally {
        this.isStreaming = false
        await Promise.allSettled([this.refreshPriorityQueue(), this.refreshActionCenter(), this.refreshDashboard()])
      }
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
        this.error = error?.message || 'TTS 插播失败。'
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
