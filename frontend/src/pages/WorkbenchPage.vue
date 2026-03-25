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
            <h2>直播大盘（LIVE）</h2>
          </header>

          <div class="studio-v2__metric-list">
            <article
              v-for="item in workspace.topMetrics"
              :key="item.key"
              class="studio-v2__metric"
            >
              <div class="studio-v2__metric-label">
                <AppIcon :name="item.icon" :size="14" />
                <span>{{ item.label }}</span>
              </div>
              <strong :class="{ 'studio-v2__metric-chip': item.key === 'product' }">{{ item.value }}</strong>
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

        <footer class="studio-v2__operator">
          <div class="studio-v2__operator-avatar">OP</div>
          <div class="studio-v2__operator-meta">
            <strong>{{ operatorName }}</strong>
            <p>主控台权限</p>
          </div>
          <button type="button" class="studio-v2__operator-link" title="Studio 设置暂未开放" disabled>
            <AppIcon name="settings" :size="16" />
          </button>
        </footer>
      </aside>

      <section class="studio-v2__radar">
        <article class="studio-v2__intent-panel">
          <header class="studio-v2__intent-header">
            <div class="studio-v2__intent-title">
              <AppIcon name="flame" :size="16" />
              <strong>高优意图捕捉（AI过滤）</strong>
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
              <p>{{ card.summary }}</p>
              <div class="studio-v2__intent-actions">
                <button
                  type="button"
                  class="studio-v2__primary-button"
                  :disabled="workspace.isStreaming"
                  @click="fillPrompt(card.prompt)"
                >
                  <AppIcon name="bot" :size="12" />
                  交由 AI 生成
                </button>
                <button type="button" class="studio-v2__ghost-button" @click="workspace.dismissPriority(card.id)">
                  忽略
                </button>
              </div>
            </article>

            <article v-if="!workspace.priorityCards.length" class="studio-v2__intent-card studio-v2__intent-card--empty">
              <p>当前没有待处理的高优意图。发送新问题后，AI 会自动把关键问题聚合到这里。</p>
            </article>
          </div>
        </article>

        <article class="studio-v2__raw-panel">
          <header class="studio-v2__raw-header">
            <div class="studio-v2__intent-title">
              <AppIcon name="message-square" :size="14" />
              <strong>原始弹幕流（Raw Stream）</strong>
            </div>
          </header>

          <div class="studio-v2__raw-list">
            <article
              v-for="item in workspace.rawBarrages"
              :key="item.id"
              class="studio-v2__raw-item"
            >
              <span class="studio-v2__raw-user">{{ item.user }}</span>
              <span class="studio-v2__raw-text">{{ item.text }}</span>
            </article>
            <div ref="barrageEndRef"></div>
          </div>
        </article>
      </section>

      <main class="studio-v2__main">
        <header class="studio-v2__main-header">
          <div>
            <p class="panel__eyebrow">AI Action Center</p>
            <h2>智能编排与输出生成（AI Action Center）</h2>
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
                <span class="studio-v2__action-badge">{{ card.detail }}</span>
              </header>

              <div class="studio-v2__action-body">
                <label>AI 生成话术（可编辑）</label>
                <textarea
                  :value="editorDrafts[card.key] ?? card.content"
                  @input="updateDraft(card.key, $event.target.value)"
                />
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
                <button type="button" class="studio-v2__primary-button" disabled>
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
                    :disabled="workspace.isStreaming"
                    placeholder="输入高频问题或场控指令...（例如：请帮我处理这个直播间问题：今天这场直播主推什么？）"
                    @keydown.enter.prevent="submitCommand"
                  />
                  <button
                    type="button"
                    class="studio-v2__command-send"
                    :disabled="workspace.isStreaming || !commandInput.trim()"
                    @click="submitCommand"
                  >
                    <AppIcon name="send" :size="18" />
                  </button>
                </div>
                <p class="studio-v2__command-hint">点左侧高优问题一键填入，再在这里发送；RAG 结果会直接回流到当前卡片。</p>
                <p v-if="workspace.error" class="error-text">{{ workspace.error }}</p>
              </div>
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
                  <small>{{ card.detail }}</small>
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
                    <textarea
                      :value="editorDrafts[card.key] ?? card.content"
                      @input="updateDraft(card.key, $event.target.value)"
                    />
                  </div>
                </div>

                <footer class="studio-v2__action-footer">
                  <button type="button" class="studio-v2__ghost-button" @click="workspace.dismissAction(card.key)">
                    误报忽略
                  </button>
                  <button
                    type="button"
                    class="studio-v2__primary-button studio-v2__primary-button--danger"
                    disabled
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
                <button type="button" class="studio-v2__primary-button studio-v2__primary-button--warning" @click="executeOpsPlan(card)">
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
import { useWorkspaceStore } from '@/stores/workspace'
import { readStudioUser } from '@/utils/studioAuth'

const workspace = useWorkspaceStore()
const commandInput = ref('')
const commandInputRef = ref(null)
const barrageEndRef = ref(null)
const editorDrafts = reactive({})
const selectedPlans = reactive({ ops: 'A' })
const operatorName = computed(() => readStudioUser()?.username || 'demo-operator')

function updateDraft(cardKey, value) {
  editorDrafts[cardKey] = value
}

async function fillPrompt(prompt) {
  commandInput.value = prompt
  await nextTick()
  commandInputRef.value?.focus()
}

function getOpsPlans(card) {
  return card.metadata?.plans?.length
    ? card.metadata.plans
    : [
        {
          id: 'A',
          title: '方案 A：紧急逼单',
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
  await workspace.sendMessage(value)
  commandInput.value = ''
}

async function playTts(card) {
  const text = editorDrafts[card.key] ?? card.content
  await workspace.playTts(card.key, text)
}

async function executeOpsPlan(card) {
  const plans = getOpsPlans(card)
  const selected = plans.find((item) => item.id === selectedPlans[card.key]) || plans[0]
  if (!selected?.prompt) {
    return
  }
  await fillPrompt(selected.prompt)
}

async function selectSession(sessionId) {
  await workspace.loadMessages(sessionId)
}

async function scrollBarrages() {
  await nextTick()
  barrageEndRef.value?.scrollIntoView({ behavior: 'smooth', block: 'end' })
}

watch(
  () => workspace.rawBarrages.length,
  () => {
    scrollBarrages()
  }
)

onMounted(async () => {
  await workspace.bootstrap()
  await scrollBarrages()
})

onBeforeUnmount(() => {
  workspace.teardown()
})
</script>
