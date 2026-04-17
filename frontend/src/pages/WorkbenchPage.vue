<template>
  <section class="studio-v2">
    <div class="studio-v2__grid">
      <aside class="studio-v2__sidebar">
        <header class="studio-v2__brand">
          <div class="studio-v2__brand-icon">
            <AppIcon name="bot" :size="20" />
          </div>
          <div>
            <h1>LiveAgent</h1>
            <p>STUDIO v2.0</p>
          </div>
        </header>

        <section class="studio-v2__sidebar-section">
          <header class="studio-v2__section-header">
            <p class="panel__eyebrow">Live</p>
            <h2>直播大盘 (LIVE)</h2>
          </header>

          <div class="studio-v2__metric-list">
            <article v-for="item in dashboardMetrics" :key="item.key" class="studio-v2__metric">
              <div class="studio-v2__metric-label">
                <AppIcon :name="item.icon" :size="14" />
                <span>{{ item.label }}</span>
              </div>

              <div class="studio-v2__metric-value">
                <strong :class="{ 'studio-v2__metric-chip': item.key === 'product' }">{{ item.value }}</strong>
                <small
                  v-if="item.trend"
                  class="studio-v2__metric-trend"
                  :class="`studio-v2__metric-trend--${item.trend.direction}`"
                >
                  {{ item.trend.label }}
                </small>
              </div>
            </article>
          </div>
        </section>

        <section class="studio-v2__sidebar-section">
          <header class="studio-v2__section-header">
            <p class="panel__eyebrow">Sessions</p>
            <h2>直播会话</h2>
          </header>

          <div class="studio-v2__session-list">
            <button
              v-for="session in workspace.sessions"
              :key="session.id"
              type="button"
              class="studio-v2__session-card"
              :class="{ 'studio-v2__session-card--active': session.id === workspace.activeSessionId }"
              @click="selectSession(session.id)"
            >
              <div class="studio-v2__session-card-head">
                <strong>{{ session.title }}</strong>
                <span class="studio-v2__session-chip" :class="`studio-v2__session-chip--${session.status}`">
                  {{ session.status === 'live' ? 'LIVE' : 'HISTORY' }}
                </span>
              </div>
              <p>{{ session.subtitle }}</p>
            </button>
          </div>
        </section>

        <section class="studio-v2__sidebar-section studio-v2__sidebar-section--fill">
          <header class="studio-v2__section-header">
            <p class="panel__eyebrow">Multi Agent</p>
            <h2>多 Agent 状态</h2>
          </header>

          <div class="studio-v2__agent-list">
            <article
              v-for="agent in workspace.agentStatuses"
              :key="agent.key"
              class="studio-v2__agent-item"
              :class="`studio-v2__agent-item--${agent.status}`"
            >
              <div class="studio-v2__agent-content">
                <AppIcon :name="agent.icon" :size="15" />
                <div>
                  <strong>{{ agent.label }}</strong>
                  <p>{{ agent.detail }}</p>
                </div>
              </div>
              <span class="studio-v2__agent-dot" :class="`studio-v2__agent-dot--${agent.status}`"></span>
            </article>
          </div>
        </section>

        <footer class="studio-v2__operator" @click.stop>
          <div class="studio-v2__operator-avatar" @click="toggleOperatorMenu">OP</div>
          <div class="studio-v2__operator-meta" @click="toggleOperatorMenu">
            <strong>{{ operatorName }}</strong>
            <p>主控台权限</p>
          </div>
          <button type="button" class="studio-v2__operator-link" title="Studio 设置暂未开放" disabled>
            <AppIcon name="settings" :size="16" />
          </button>
          <!-- 退出登录下拉菜单 -->
          <div v-if="showOperatorMenu" class="studio-v2__operator-dropdown">
            <div class="studio-v2__operator-dropdown-user">
              <div class="studio-v2__operator-dropdown-avatar">OP</div>
              <div>
                <strong>{{ operatorName }}</strong>
                <p>主控台权限</p>
              </div>
            </div>
            <div class="studio-v2__operator-dropdown-divider"></div>
            <button type="button" class="studio-v2__operator-dropdown-item" @click="handleLogout">
              <AppIcon name="log-out" :size="14" />
              退出登录
            </button>
          </div>
        </footer>
      </aside>

      <section class="studio-v2__radar">
        <article class="studio-v2__intent-panel">
          <header class="studio-v2__intent-header">
            <div class="studio-v2__intent-title">
              <AppIcon name="flame" :size="16" />
              <strong>高优意图捕捉 (AI 过滤)</strong>
            </div>
            <span class="studio-v2__intent-badge">{{ workspace.priorityCards.length }} 待处理</span>
          </header>

          <div class="studio-v2__intent-list">
            <article
              v-for="card in workspace.priorityCards"
              :key="card.id"
              class="studio-v2__intent-card"
              :class="`studio-v2__intent-card--${card.tone}`"
            >
              <div class="studio-v2__intent-card-row">
                <span class="studio-v2__intent-tag">{{ card.label }}</span>
                <span class="studio-v2__intent-freq">{{ card.frequency }}</span>
              </div>
              <p class="studio-v2__intent-summary" :title="card.summary">{{ card.summary }}</p>
              <div class="studio-v2__intent-actions">
                <button type="button" class="studio-v2__primary-button" @click="fillPrompt(card.prompt)">
                  <AppIcon name="bot" :size="12" />
                  交由 AI 生成
                </button>
                <button type="button" class="studio-v2__ghost-button" @click="workspace.dismissPriority(card.id)">
                  忽略
                </button>
              </div>
            </article>

            <article v-if="!workspace.priorityCards.length" class="studio-v2__intent-card studio-v2__intent-card--empty">
              <div class="studio-v2__empty-state">
                <AppIcon name="flame" :size="18" />
                <div>
                  <strong>当前没有待处理的高优意图</strong>
                  <p>真实弹幕接入后，系统会自动把高频问题聚合到这里。</p>
                </div>
              </div>
            </article>
          </div>
        </article>

        <article class="studio-v2__raw-panel">
          <header class="studio-v2__raw-header">
            <div class="studio-v2__intent-title">
              <AppIcon name="message-square" :size="14" />
              <strong>原始弹幕流 (Raw Stream)</strong>
            </div>
          </header>

          <div ref="rawListRef" class="studio-v2__raw-list studio-v2__custom-scrollbar">
            <template v-if="workspace.rawBarrages.length">
              <article v-for="item in workspace.rawBarrages" :key="item.id" class="studio-v2__raw-item">
                <span class="studio-v2__raw-user">{{ item.user }}</span>
                <span class="studio-v2__raw-text">{{ item.text }}</span>
              </article>
            </template>

            <article v-else class="studio-v2__raw-item studio-v2__raw-item--empty">
              <AppIcon name="message-square" :size="16" />
              <div>
                <span class="studio-v2__raw-user">System</span>
                <span class="studio-v2__raw-text">等待弹幕流接入...</span>
              </div>
            </article>
          </div>
        </article>
      </section>

      <main class="studio-v2__main">
        <header class="studio-v2__main-header">
          <div>
            <p class="panel__eyebrow">AI Action Center</p>
            <h2>智能编排与输出生成 (AI Action Center)</h2>
          </div>

          <div class="studio-v2__main-status">
            <span class="status-chip">
              <AppIcon name="monitor-up" :size="14" />
              提词器连接正常
            </span>
            <span class="status-chip">
              <AppIcon name="mic" :size="14" />
              TTS 通道待命
            </span>
            <button type="button" class="status-chip" @click="openLiveSimulator">
              <AppIcon name="message-square" :size="14" />
              打开直播模拟页
            </button>
            <button type="button" class="status-chip" @click="openTeleprompterPreview">
              <AppIcon name="monitor-up" :size="14" />
              打开提词器
            </button>
          </div>
        </header>

        <section class="studio-v2__action-list">
          <article
            v-for="card in workspace.actionCards"
            :key="card.key"
            class="studio-v2__action-card"
            :class="[
              `studio-v2__action-card--${card.tone}`,
              card.key === 'guardrail' ? 'studio-v2__action-card--alert' : '',
              card.key === 'ops' ? 'studio-v2__action-card--strategy' : ''
            ]"
          >
            <template v-if="card.key === 'qa'">
              <header class="studio-v2__action-header">
                <div class="studio-v2__action-title">
                  <AppIcon name="bot" :size="18" />
                  <span>{{ card.title }} · {{ card.subtitle }}</span>
                </div>
                <span class="studio-v2__action-badge" :class="qaBadgeClass()">{{ qaBadgeLabel(card) }}</span>
              </header>

              <!-- AI 输出结果区域 -->
              <div class="studio-v2__action-body">
                <label>AI 当前输出结果</label>

                <!-- 思考中状态 -->
                <div v-if="workspace.awaitingFirstToken && workspace.streamingKey === 'qa'" class="studio-v2__ai-thinking">
                  <div class="studio-v2__ai-thinking-avatar">
                    <AppIcon name="bot" :size="24" />
                  </div>
                  <div class="studio-v2__ai-thinking-content">
                    <div class="studio-v2__ai-thinking-dots">
                      <span></span><span></span><span></span>
                    </div>
                    <p class="studio-v2__ai-thinking-text">
                      {{ workspace.slowRequest ? '响应较慢，AI 仍在思考中...' : 'AI 正在思考，请稍候...' }}
                    </p>
                    <p class="studio-v2__ai-thinking-hint">首次响应可能需要 5-10 秒，请耐心等待</p>
                  </div>
                </div>

                <!-- 流式输出状态 -->
                <div v-else-if="workspace.isStreaming && workspace.streamingKey === 'qa'" class="studio-v2__ai-streaming">
                  <div class="studio-v2__ai-streaming-header">
                    <div class="studio-v2__ai-avatar">
                      <AppIcon name="bot" :size="16" />
                    </div>
                    <span class="studio-v2__ai-streaming-label">AI 正在生成回答</span>
                  </div>
                  <div class="studio-v2__ai-streaming-content">
                    <p class="studio-v2__ai-streaming-text">
                      {{ resolveDraft(card) }}<span class="studio-v2__ai-cursor"></span>
                    </p>
                  </div>
                </div>

                <!-- 最终结果/空闲状态 -->
                <div v-else class="studio-v2__ai-result">
                  <textarea
                    v-if="card.editable"
                    :value="resolveDraft(card)"
                    @input="updateDraft(card.key, $event.target.value)"
                  ></textarea>
                  <div v-else class="studio-v2__ai-result-text">
                    <p>{{ resolveDraft(card) || '左侧高优问题交给 AI 生成后，这里会显示结合知识库与大模型生成的结果。' }}</p>
                  </div>
                </div>
              </div>

              <footer class="studio-v2__action-footer">
                <button type="button" class="studio-v2__ghost-button" @click="workspace.dismissAction(card.key)">
                  忽略
                </button>
                <button
                  type="button"
                  class="studio-v2__secondary-button"
                  :disabled="workspace.ttsBusyKeys.includes(card.key)"
                  @click="playTts(card)"
                >
                  <AppIcon name="mic" :size="14" />
                  TTS 语音插播
                </button>
                <button
                  type="button"
                  class="studio-v2__primary-button"
                  :disabled="workspace.teleprompterBusyKeys.includes(card.key)"
                  @click="pushCardToTeleprompter(card)"
                >
                  <AppIcon name="monitor-up" :size="14" />
                  推送至前方提词器
                </button>
              </footer>

              <div class="studio-v2__qa-command">
                <div class="studio-v2__command-shell studio-v2__command-shell--embedded">
                  <button type="button" class="studio-v2__command-prefix">
                    <span>@ Agent</span>
                    <AppIcon name="chevron-right" :size="14" />
                  </button>
                  <input
                    ref="commandInputRef"
                    v-model="commandInput"
                    type="text"
                    placeholder="输入高优问题或场控指令...（例如：请帮我处理这个直播间问题：今天这场直播主推什么？）"
                    @keydown.enter.prevent="submitCommand"
                  />
                  <button
                    type="button"
                    class="studio-v2__command-send"
                    :disabled="!commandInput.trim()"
                    @click="submitCommand"
                  >
                    <AppIcon name="send" :size="18" />
                  </button>
                </div>

                <div
                  v-if="workspace.awaitingFirstToken || workspace.slowRequest || workspace.queuedCommands.length"
                  class="studio-v2__command-status"
                >
                  <span v-if="workspace.awaitingFirstToken" class="studio-v2__command-pill studio-v2__command-pill--pending">
                    AI 正在思考
                  </span>
                  <span v-if="workspace.slowRequest" class="studio-v2__command-pill studio-v2__command-pill--slow">
                    响应较慢，仍在处理中
                  </span>
                  <span v-if="workspace.queuedCommands.length" class="studio-v2__command-pill studio-v2__command-pill--queue">
                    队列 {{ workspace.queuedCommands.length }} 条
                  </span>
                </div>

                <div v-if="workspace.queuedCommands.length" class="studio-v2__command-queue">
                  <article
                    v-for="(item, index) in visibleQueuedCommands"
                    :key="item.id"
                    class="studio-v2__command-queue-item"
                  >
                    <div class="studio-v2__command-queue-copy">
                      <strong>#{{ index + 1 }}</strong>
                      <p>{{ item.text }}</p>
                    </div>
                    <button
                      type="button"
                      class="studio-v2__command-queue-remove"
                      @click="workspace.removeQueuedCommand(item.id)"
                    >
                      移除
                    </button>
                  </article>
                  <p v-if="queuedOverflowCount" class="studio-v2__command-queue-more">
                    还有 {{ queuedOverflowCount }} 条待处理指令
                  </p>
                </div>

                <p class="studio-v2__command-hint">
                  点击左侧高优问题一键填入，再在这里发送；结果会直接回流到当前卡片。
                </p>
                <p v-if="workspace.error" class="error-text">{{ workspace.error }}</p>
              </div>

              <RecentQAHistory
                :items="qaTimeline"
                @copy="copyQaHistoryAnswer"
                @push="pushQaHistoryToTeleprompter"
                @remove="dismissQaHistoryItem"
              />
            </template>

            <template v-else-if="card.key === 'guardrail'">
              <template v-if="card.status === 'pass' || card.status === 'idle'">
                <header class="studio-v2__action-header studio-v2__action-header--safe">
                  <div class="studio-v2__action-title studio-v2__action-title--safe">
                    <AppIcon name="shield-check" :size="18" />
                    <span>{{ card.title }} · 系统安全</span>
                  </div>
                  <span class="studio-v2__action-badge studio-v2__action-badge--safe">安全</span>
                </header>
                <div class="studio-v2__action-safe">
                  <p>{{ card.content }}</p>
                </div>
              </template>

              <template v-else>
                <header class="studio-v2__action-header studio-v2__action-header--danger">
                  <div class="studio-v2__action-title studio-v2__action-title--danger">
                    <AppIcon name="shield-alert" :size="18" />
                    <span>{{ card.title }} · 紧急告警</span>
                  </div>
                  <span class="studio-v2__action-badge studio-v2__action-badge--danger">需立即干预</span>
                </header>

                <div class="studio-v2__guardrail-body">
                  <div class="studio-v2__guardrail-grid">
                    <article class="studio-v2__guardrail-panel studio-v2__guardrail-panel--danger">
                      <p class="studio-v2__guardrail-label">系统监听原文</p>
                      <p class="studio-v2__guardrail-text">{{ card.metadata?.original_text || card.content }}</p>
                    </article>
                    <article class="studio-v2__guardrail-panel">
                      <p class="studio-v2__guardrail-label">触发规则</p>
                      <p class="studio-v2__guardrail-text">{{ card.metadata?.rule || card.detail }}</p>
                    </article>
                  </div>

                  <div class="studio-v2__action-body studio-v2__action-body--compact">
                    <label>AI 补救话术建议</label>
                    <textarea :value="resolveDraft(card)" @input="updateDraft(card.key, $event.target.value)"></textarea>
                  </div>
                </div>

                <footer class="studio-v2__action-footer">
                  <button type="button" class="studio-v2__ghost-button" @click="workspace.dismissAction(card.key)">
                    误报忽略
                  </button>
                  <button
                    type="button"
                    class="studio-v2__primary-button studio-v2__primary-button--danger"
                    :disabled="workspace.teleprompterBusyKeys.includes(card.key)"
                    @click="pushCardToTeleprompter(card)"
                  >
                    <AppIcon name="monitor-up" :size="14" />
                    紧急下发补救
                  </button>
                </footer>
              </template>
            </template>

            <template v-else-if="card.key === 'ops'">
              <header class="studio-v2__action-header studio-v2__action-header--warning">
                <div class="studio-v2__action-title studio-v2__action-title--warning">
                  <AppIcon name="activity" :size="18" />
                  <span>{{ card.title }} · {{ card.subtitle }}</span>
                </div>
                <span class="studio-v2__action-badge studio-v2__action-badge--warning">
                  {{ card.metadata?.trigger || '策略建议' }}
                </span>
              </header>

              <div class="studio-v2__ops-body">
                <div class="studio-v2__ops-insight">
                  <AppIcon name="trending-up" :size="18" />
                  <div>
                    <strong>运营洞察</strong>
                    <p>{{ card.metadata?.insight || card.detail }}</p>
                  </div>
                </div>

                <div class="studio-v2__ops-plans">
                  <label>请选择下一步方案</label>
                  <button
                    v-for="plan in getOpsPlans(card)"
                    :key="plan.id"
                    type="button"
                    class="studio-v2__ops-plan"
                    :class="{ 'studio-v2__ops-plan--active': selectedPlans[card.key] === plan.id }"
                    @click="selectPlan(card.key, plan.id)"
                  >
                    <div class="studio-v2__ops-plan-radio">
                      <span v-if="selectedPlans[card.key] === plan.id"></span>
                    </div>
                    <div class="studio-v2__ops-plan-copy">
                      <strong>{{ plan.title }}</strong>
                      <p>{{ plan.summary }}</p>
                    </div>
                  </button>
                </div>
              </div>

              <footer class="studio-v2__action-footer">
                <button type="button" class="studio-v2__ghost-button" @click="workspace.dismissAction(card.key)">
                  暂不干预
                </button>
                <button
                  type="button"
                  class="studio-v2__secondary-button"
                  :disabled="workspace.teleprompterBusyKeys.includes(card.key)"
                  @click="pushCardToTeleprompter(card)"
                >
                  <AppIcon name="monitor-up" :size="14" />
                  推送提词器
                </button>
                <button
                  type="button"
                  class="studio-v2__primary-button studio-v2__primary-button--warning"
                  @click="executeOpsPlan(card)"
                >
                  执行方案 {{ selectedPlans[card.key] || 'A' }}
                  <AppIcon name="chevron-right" :size="14" />
                </button>
              </footer>
            </template>
          </article>
        </section>
      </main>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import AppIcon from '@/components/AppIcon.vue'
import RecentQAHistory from '@/components/RecentQAHistory.vue'
import { useStudioAuthStore } from '@/stores/studioAuth'
import { useWorkspaceStore } from '@/stores/workspace'
import { readStudioUser } from '@/utils/studioAuth'

const workspace = useWorkspaceStore()
const studioAuth = useStudioAuthStore()
const commandInput = ref('')
const commandInputRef = ref(null)
const rawListRef = ref(null)
const previousOverview = ref(null)
const dismissedQaHistoryIds = ref([])
const editorDrafts = reactive({})
const selectedPlans = reactive({ ops: 'A' })
const showOperatorMenu = ref(false)

const operatorName = computed(() => {
  const studioUser = readStudioUser()
  return studioUser?.username || studioUser?.name || 'demo-operator'
})

const visibleQueuedCommands = computed(() => workspace.queuedCommands.slice(0, 3))
const queuedOverflowCount = computed(() => Math.max(0, workspace.queuedCommands.length - visibleQueuedCommands.value.length))

const dashboardMetrics = computed(() => {
  const overview = workspace.overview || {}
  return [
    {
      key: 'viewers',
      label: '在线人数',
      value: Number(overview.online_viewers || 0).toLocaleString('zh-CN'),
      icon: 'users'
    },
    {
      key: 'product',
      label: '当前讲解',
      value: overview.current_product_id || '未设置商品',
      icon: 'shopping-cart'
    },
    {
      key: 'interaction',
      label: '互动频率',
      value: `${Number(overview.interaction_rate || 0).toFixed(2)}/分钟`,
      icon: 'activity',
      trend: buildTrend(overview.interaction_rate, previousOverview.value?.interaction_rate, '/分钟')
    },
    {
      key: 'conversion',
      label: '转化率',
      value: `${Number(overview.conversion_rate || 0).toFixed(2)}%`,
      icon: 'trending-up',
      trend: buildTrend(overview.conversion_rate, previousOverview.value?.conversion_rate, '%')
    }
  ]
})

const qaTimeline = computed(() => {
  const items = [...workspace.activeQaHistory]

  if (workspace.isStreaming && workspace.streamingKey === 'qa') {
    // 流式期间 activeRequestText 保留当前问题，不依赖已清空的 activeMessages
    const currentQuestion = workspace.activeRequestText || ''
    const currentAnswer = workspace.actionCenter.qa?.content || ''
    if (currentQuestion && currentAnswer) {
      items.push({
        id: `streaming-${Date.now()}`,
        question: currentQuestion,
        answer: currentAnswer,
        references: workspace.actionCenter.qa?.references || [],
        type: workspace.actionCenter.qa?.metadata?.response_kind === 'direct' ? 'Direct' : 'RAG',
        tagTone: workspace.actionCenter.qa?.metadata?.response_kind === 'direct' ? 'stream' : 'rag',
        streaming: true,
        createdAt: new Date().toISOString(),
        timeLabel: '刚刚',
        citation: buildCitation(
          workspace.actionCenter.qa?.references || [],
          workspace.actionCenter.qa?.metadata?.response_kind
        )
      })
    }
  }

  return items
    .filter((item) => !dismissedQaHistoryIds.value.includes(item.id))
    .slice(-10)
    .reverse()
    .map((item) => ({
      ...item,
      timeLabel: item.timeLabel || formatRelativeTime(item.createdAt)
    }))
})

function buildTrend(currentValue, previousValue, suffix = '') {
  if (previousValue === null || previousValue === undefined) {
    return null
  }

  const current = Number(currentValue || 0)
  const previous = Number(previousValue || 0)
  const delta = current - previous

  if (Math.abs(delta) < 0.01) {
    return { direction: 'flat', label: '持平' }
  }

  return {
    direction: delta > 0 ? 'up' : 'down',
    label: `${delta > 0 ? '↑' : '↓'} ${Math.abs(delta).toFixed(2)}${suffix}`
  }
}

function formatRelativeTime(value) {
  if (!value) {
    return '刚刚'
  }

  const target = new Date(value).getTime()
  if (Number.isNaN(target)) {
    return '刚刚'
  }

  const diffMs = Date.now() - target
  if (diffMs < 60_000) {
    return '刚刚'
  }

  const diffMinutes = Math.floor(diffMs / 60_000)
  if (diffMinutes < 60) {
    return `${diffMinutes} 分钟前`
  }

  const diffHours = Math.floor(diffMinutes / 60)
  if (diffHours < 24) {
    return `${diffHours} 小时前`
  }

  return `${Math.floor(diffHours / 24)} 天前`
}

function buildCitation(references, responseKind) {
  if (Array.isArray(references) && references.length) {
    return `引用 ${references.length} 条知识片段`
  }
  if (responseKind === 'direct') {
    return '快速直答，无需知识库检索'
  }
  return '引用系统问答记录'
}

function updateDraft(cardKey, value) {
  editorDrafts[cardKey] = value
}

function resolveDraft(card) {
  return editorDrafts[card.key] !== undefined ? editorDrafts[card.key] : card.content
}

async function fillPrompt(prompt) {
  const nextPrompt = String(prompt || '').trim()
  if (!nextPrompt) {
    return
  }

  if (!workspace.isStreaming && !workspace.queueProcessing && !commandInput.value.trim()) {
    commandInput.value = nextPrompt
    await nextTick()
    commandInputRef.value?.focus()
    return
  }

  workspace.enqueueCommand(nextPrompt, 'priority')
}

function getOpsPlans(card) {
  return card.metadata?.plans?.length
    ? card.metadata.plans
    : [
        {
          id: 'A',
          title: '方案 A：维持当前节奏',
          summary: card.content,
          prompt: card.content
        }
      ]
}

function selectPlan(cardKey, planId) {
  selectedPlans[cardKey] = planId
}

async function submitCommand() {
  const value = commandInput.value.trim()
  if (!value) {
    return
  }

  await workspace.sendMessage(value, 'manual')
  commandInput.value = ''
  await nextTick()
  commandInputRef.value?.focus()
}

function qaBadgeLabel(card) {
  if (workspace.slowRequest && workspace.streamingKey === 'qa') {
    return '响应较慢'
  }
  if (workspace.awaitingFirstToken && workspace.streamingKey === 'qa') {
    return '处理中'
  }
  if (workspace.isStreaming && workspace.streamingKey === 'qa') {
    return '流式生成中'
  }
  if (card?.metadata?.response_kind === 'direct') {
    return '快速直答'
  }
  if (Array.isArray(card.references) && card.references.length) {
    return `引用 ${card.references.length} 条知识片段`
  }
  return '等待新的 QA 请求'
}

function qaBadgeClass() {
  if (workspace.slowRequest && workspace.streamingKey === 'qa') {
    return 'studio-v2__action-badge--slow'
  }
  if (workspace.awaitingFirstToken && workspace.streamingKey === 'qa') {
    return 'studio-v2__action-badge--pending'
  }
  if (workspace.isStreaming && workspace.streamingKey === 'qa') {
    return 'studio-v2__action-badge--streaming'
  }
  return ''
}

async function selectSession(sessionId) {
  dismissedQaHistoryIds.value = []
  await workspace.loadMessages(sessionId)
}

async function playTts(card) {
  const text = resolveDraft(card)
  await workspace.playTts(card.key, text)
}

function buildTeleprompterPayload(item, sourceAgent) {
  return {
    title: item.question || item.title || '直播提词内容',
    content: item.answer || item.content || '',
    source_agent: sourceAgent,
    priority: item.streaming ? 'high' : 'normal'
  }
}

async function pushCardToTeleprompter(card) {
  await workspace.pushTeleprompter(card.key, {
    title: `${card.title} · ${card.subtitle}`,
    content: resolveDraft(card),
    source_agent: card.key,
    priority: card.key === 'guardrail' ? 'high' : 'normal'
  })
}

async function pushQaHistoryToTeleprompter(item) {
  await workspace.pushTeleprompter('qa', buildTeleprompterPayload(item, item.type === 'Direct' ? 'direct' : 'qa'))
}

function dismissQaHistoryItem(itemId) {
  if (!dismissedQaHistoryIds.value.includes(itemId)) {
    dismissedQaHistoryIds.value = [...dismissedQaHistoryIds.value, itemId]
  }
}

async function copyQaHistoryAnswer(item) {
  if (item.answer && navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(item.answer)
  }
}

function resolveOpsPrompt(card) {
  const planId = selectedPlans[card.key] || 'A'
  const target = getOpsPlans(card).find((item) => item.id === planId)
  return target?.prompt || target?.summary || card.content
}

async function executeOpsPlan(card) {
  const prompt = resolveOpsPrompt(card)
  if (!prompt) {
    return
  }
  await workspace.sendMessage(prompt, 'ops-plan')
}

function openLiveSimulator() {
  window.open('/live-simulator', '_blank', 'noopener')
}

function openTeleprompterPreview() {
  workspace.openTeleprompterPreview()
}

function toggleOperatorMenu() {
  showOperatorMenu.value = !showOperatorMenu.value
}

async function handleLogout() {
  showOperatorMenu.value = false
  await studioAuth.logout()
  window.location.href = '/studio-login'
}

watch(
  () => workspace.rawBarrages.length,
  async () => {
    await nextTick()
    const el = rawListRef.value
    if (el) {
      el.scrollTop = el.scrollHeight
    }
  }
)

watch(
  () => [workspace.overview.interaction_rate, workspace.overview.conversion_rate],
  () => {
    previousOverview.value = {
      interaction_rate: workspace.overview.interaction_rate,
      conversion_rate: workspace.overview.conversion_rate
    }
  },
  { immediate: true }
)

watch(
  () => [workspace.streamingKey, workspace.isStreaming, workspace.awaitingFirstToken],
  ([streamingKey, isStreaming, awaitingFirstToken]) => {
    if (streamingKey === 'qa' && (isStreaming || awaitingFirstToken)) {
      editorDrafts.qa = undefined
    }
  }
)

watch(
  () => [workspace.actionCenter.qa?.content, workspace.actionCenter.guardrail?.content, workspace.actionCenter.ops?.content],
  () => {
    editorDrafts.qa = undefined
    editorDrafts.guardrail = undefined
    editorDrafts.ops = undefined
  }
)

onMounted(async () => {
  await workspace.bootstrap()
  document.addEventListener('click', closeOperatorMenu)
})

onBeforeUnmount(() => {
  workspace.teardown()
  document.removeEventListener('click', closeOperatorMenu)
})

function closeOperatorMenu() {
  showOperatorMenu.value = false
}
</script>

<style scoped>
.studio-v2__ai-thinking {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 18px 20px;
  background: rgba(16, 185, 129, 0.06);
  border: 1px solid rgba(16, 185, 129, 0.18);
  border-radius: 16px 16px 4px 16px;
  min-height: 80px;
}

.studio-v2__ai-thinking-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 999px;
  background: linear-gradient(135deg, #10b981, #059669);
  color: #fff;
  flex-shrink: 0;
}

.studio-v2__ai-thinking-content {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.studio-v2__ai-thinking-dots {
  display: flex;
  gap: 5px;
  align-items: center;
}

.studio-v2__ai-thinking-dots span {
  width: 7px;
  height: 7px;
  background: #10b981;
  border-radius: 50%;
  animation: studio-v2__bounce 1.4s ease-in-out infinite;
}

.studio-v2__ai-thinking-dots span:nth-child(1) { animation-delay: 0s; }
.studio-v2__ai-thinking-dots span:nth-child(2) { animation-delay: 0.2s; }
.studio-v2__ai-thinking-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes studio-v2__bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.5; }
  40% { transform: scale(1); opacity: 1; }
}

.studio-v2__ai-thinking-text {
  margin: 0;
  color: #10b981;
  font-size: 14px;
  font-weight: 500;
  line-height: 1.5;
}

.studio-v2__ai-thinking-hint {
  margin: 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.4;
}

.studio-v2__ai-streaming {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 20px;
  background: rgba(16, 185, 129, 0.08);
  border: 1px solid rgba(16, 185, 129, 0.28);
  border-radius: 16px 16px 4px 16px;
  min-height: 60px;
}

.studio-v2__ai-streaming-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.studio-v2__ai-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 999px;
  background: linear-gradient(135deg, #10b981, #059669);
  color: #fff;
  flex-shrink: 0;
}

.studio-v2__ai-streaming-label {
  color: #10b981;
  font-size: 12px;
  font-weight: 500;
}

.studio-v2__ai-streaming-content {
  padding-left: 34px;
}

.studio-v2__ai-streaming-text {
  margin: 0;
  color: #f8fafc;
  font-size: 14px;
  line-height: 1.7;
}

.studio-v2__ai-cursor {
  display: inline-block;
  width: 2px;
  height: 16px;
  background: #10b981;
  margin-left: 2px;
  vertical-align: middle;
  animation: studio-v2__blink 0.8s ease-in-out infinite;
}

@keyframes studio-v2__blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

.studio-v2__ai-result {
  min-height: 80px;
}

.studio-v2__ai-result-text {
  padding: 12px 16px;
  background: rgba(30, 41, 59, 0.4);
  border-radius: 12px;
}

.studio-v2__ai-result-text p {
  margin: 0;
  color: #94a3b8;
  font-size: 13px;
  line-height: 1.6;
}

.studio-v2__action-badge--streaming {
  color: #10b981;
  background: rgba(16, 185, 129, 0.15);
  border: 1px solid rgba(16, 185, 129, 0.3);
}

.studio-v2__action-badge--slow {
  color: #fcd34d;
  background: rgba(245, 158, 11, 0.15);
  border: 1px solid rgba(245, 158, 11, 0.3);
}

.studio-v2__action-badge--pending {
  color: #a5b4fc;
  background: rgba(99, 102, 241, 0.15);
  border: 1px solid rgba(99, 102, 241, 0.3);
}

/* Operator 下拉菜单 */
.studio-v2__operator {
  position: relative;
}

.studio-v2__operator-dropdown {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 16px;
  right: 16px;
  background: rgba(22, 26, 35, 0.98);
  border: 1px solid rgba(51, 65, 85, 0.72);
  border-radius: 12px;
  overflow: hidden;
  z-index: 100;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
}

.studio-v2__operator-dropdown-user {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
}

.studio-v2__operator-dropdown-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 999px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
}

.studio-v2__operator-dropdown-user strong {
  display: block;
  color: #f8fafc;
  font-size: 14px;
  margin-bottom: 2px;
}

.studio-v2__operator-dropdown-user p {
  margin: 0;
  color: #64748b;
  font-size: 11px;
}

.studio-v2__operator-dropdown-divider {
  height: 1px;
  background: rgba(51, 65, 85, 0.56);
}

.studio-v2__operator-dropdown-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 12px 16px;
  border: none;
  background: transparent;
  color: #fca5a5;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s ease;
  text-align: left;
}

.studio-v2__operator-dropdown-item:hover {
  background: rgba(239, 68, 68, 0.12);
}
</style>
