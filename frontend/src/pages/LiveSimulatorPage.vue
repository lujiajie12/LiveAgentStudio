<template>
  <section class="live-sim">
    <header class="live-sim__header">
      <div>
        <p class="live-sim__eyebrow">Live Simulator</p>
        <h1>直播弹幕模拟前台</h1>
        <p class="live-sim__intro">
          把这个页面当作上游直播间。你可以在这里同步房间状态、发送弹幕，Studio 会实时收到原始弹幕、在线人数和高优意图。
        </p>
      </div>

      <div class="live-sim__header-actions">
        <button type="button" class="live-sim__ghost" @click="openStudio">打开 Studio</button>
        <button type="button" class="live-sim__primary" @click="toggleAuto">
          {{ autoRunning ? '停止自动模拟' : '启动自动模拟' }}
        </button>
      </div>
    </header>

    <div class="live-sim__grid">
      <aside class="live-sim__panel">
        <div class="live-sim__panel-head">
          <h2>房间控制</h2>
          <span>{{ form.session_id }}</span>
        </div>

        <div class="live-sim__form-grid">
          <label class="live-sim__field">
            <span>会话 ID</span>
            <input v-model="form.session_id" type="text" />
          </label>
          <label class="live-sim__field">
            <span>当前商品</span>
            <input v-model="form.current_product_id" type="text" placeholder="例如：SKU-10086" />
          </label>
          <label class="live-sim__field">
            <span>直播阶段</span>
            <select v-model="form.live_stage">
              <option value="warmup">warmup</option>
              <option value="intro">intro</option>
              <option value="pitch">pitch</option>
              <option value="closing">closing</option>
            </select>
          </label>
          <label class="live-sim__field">
            <span>在线人数</span>
            <input v-model.number="form.online_viewers" type="number" min="0" />
          </label>
          <label class="live-sim__field">
            <span>互动频率</span>
            <input v-model.number="form.interaction_rate" type="number" min="0" step="0.1" />
          </label>
          <label class="live-sim__field">
            <span>转化率</span>
            <input v-model.number="form.conversion_rate" type="number" min="0" step="0.01" />
          </label>
        </div>

        <div class="live-sim__row-actions">
          <button type="button" class="live-sim__secondary" @click="updateOverview">同步房间状态</button>
          <button type="button" class="live-sim__ghost" @click="refreshData">刷新状态</button>
        </div>

        <div class="live-sim__divider"></div>

        <div class="live-sim__panel-head">
          <h2>发送弹幕</h2>
          <span>上游注入</span>
        </div>

        <label class="live-sim__field">
          <span>昵称</span>
          <input v-model="form.display_name" type="text" />
        </label>
        <label class="live-sim__field">
          <span>弹幕内容</span>
          <textarea v-model="form.text" rows="4"></textarea>
        </label>

        <div class="live-sim__row-actions">
          <button type="button" class="live-sim__primary" @click="sendBarrage">发送一条弹幕</button>
          <button type="button" class="live-sim__ghost" @click="fillRandomBarrage">随机一条</button>
        </div>

        <p v-if="statusText" class="live-sim__status">{{ statusText }}</p>
        <p v-if="error" class="live-sim__error">{{ error }}</p>
      </aside>

      <main class="live-sim__content">
        <section class="live-sim__panel">
          <div class="live-sim__panel-head">
            <h2>实时概览</h2>
            <span>{{ overview.updated_at || '--' }}</span>
          </div>

          <div class="live-sim__stats">
            <article class="live-sim__stat">
              <span>在线人数</span>
              <strong>{{ overview.online_viewers ?? 0 }}</strong>
            </article>
            <article class="live-sim__stat">
              <span>当前商品</span>
              <strong>{{ overview.current_product_id || '未设置商品' }}</strong>
            </article>
            <article class="live-sim__stat">
              <span>互动频率</span>
              <strong>{{ formatRate(overview.interaction_rate, '/分钟') }}</strong>
            </article>
            <article class="live-sim__stat">
              <span>转化率</span>
              <strong>{{ formatRate(overview.conversion_rate, '%') }}</strong>
            </article>
          </div>
        </section>

        <section class="live-sim__panel">
          <div class="live-sim__panel-head">
            <h2>高优意图预览</h2>
            <span>{{ priorityCards.length }} 条</span>
          </div>
          <div class="live-sim__priority-list">
            <article v-for="card in priorityCards" :key="card.id" class="live-sim__priority-card">
              <div class="live-sim__priority-meta">
                <span>{{ card.label }}</span>
                <small>{{ card.frequency }}</small>
              </div>
              <p>{{ card.summary }}</p>
            </article>
            <p v-if="!priorityCards.length" class="live-sim__empty">
              发送弹幕后，这里会看到后端聚合出的高优意图。
            </p>
          </div>
        </section>

        <section class="live-sim__panel live-sim__panel--fill">
          <div class="live-sim__panel-head">
            <h2>原始弹幕预览</h2>
            <span>{{ rawBarrages.length }} 条</span>
          </div>
          <div class="live-sim__barrage-list">
            <article v-for="item in rawBarrages" :key="item.id" class="live-sim__barrage-item">
              <strong>{{ item.user }}</strong>
              <span>{{ item.text }}</span>
            </article>
            <p v-if="!rawBarrages.length" class="live-sim__empty">等待上游弹幕进入后端...</p>
          </div>
        </section>
      </main>
    </div>
  </section>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import {
  buildStudioBarrageWsUrl,
  fetchStudioLiveOverview,
  fetchStudioPriorityQueue,
  ingestStudioBarrage,
  updateStudioLiveOverview
} from '@/api/studio'
import { readStudioToken } from '@/utils/studioAuth'

const SAMPLE_BARRAGES = [
  '今天这场直播主推什么？',
  '这款产品适合什么家庭使用？',
  '多久发货？',
  '库存还多吗？',
  '有没有优惠券？',
  '和普通拖把区别是什么？',
  '售后怎么保修？',
  '运费谁出？'
]

const SAMPLE_USERS = ['User_101', '小透明', '李**', '购物狂', 'AAA建材', 'User_882']

const form = reactive({
  session_id: 'studio-live-room-001',
  current_product_id: '',
  live_stage: 'intro',
  online_viewers: 12450,
  interaction_rate: 7.8,
  conversion_rate: 3.24,
  display_name: 'User_101',
  text: '今天这场直播主推什么？'
})

const overview = ref({})
const priorityCards = ref([])
const rawBarrages = ref([])
const error = ref('')
const statusText = ref('')
const autoRunning = ref(false)
const socketRef = ref(null)
const autoTimerRef = ref(null)
const priorityRefreshTimerRef = ref(null)

function normalizeBarrage(item) {
  return {
    id: item.id,
    user: item.display_name || item.user || 'User',
    text: item.text || '',
    created_at: item.created_at || ''
  }
}

function formatRate(value, suffix) {
  return `${Number(value || 0).toFixed(suffix === '%' ? 2 : 1)}${suffix}`
}

function clearStatus() {
  window.clearTimeout(clearStatus.timerId)
  clearStatus.timerId = window.setTimeout(() => {
    statusText.value = ''
  }, 2200)
}
clearStatus.timerId = 0

async function refreshPriorityQueue() {
  priorityCards.value = await fetchStudioPriorityQueue(form.session_id, 5)
}

async function refreshOverview() {
  overview.value = await fetchStudioLiveOverview(form.session_id)
}

async function refreshData() {
  await Promise.all([refreshOverview(), refreshPriorityQueue()])
}

async function updateOverview() {
  error.value = ''
  try {
    overview.value = await updateStudioLiveOverview({
      session_id: form.session_id,
      current_product_id: form.current_product_id || null,
      live_stage: form.live_stage,
      online_viewers: Number(form.online_viewers),
      interaction_rate: Number(form.interaction_rate),
      conversion_rate: Number(form.conversion_rate),
      metadata: { source: 'live-simulator' }
    })
    statusText.value = '房间状态已同步到后端。'
    clearStatus()
  } catch (err) {
    error.value = err?.message || '同步房间状态失败。'
  }
}

function fillRandomBarrage() {
  form.display_name = SAMPLE_USERS[Math.floor(Math.random() * SAMPLE_USERS.length)]
  form.text = SAMPLE_BARRAGES[Math.floor(Math.random() * SAMPLE_BARRAGES.length)]
}

async function sendBarrage(customPayload = null) {
  error.value = ''
  const payload = customPayload || {
    session_id: form.session_id,
    display_name: form.display_name,
    text: form.text,
    source: 'live-simulator',
    current_product_id: form.current_product_id || null,
    live_stage: form.live_stage,
    online_viewers: Number(form.online_viewers),
    interaction_rate: Number(form.interaction_rate),
    conversion_rate: Number(form.conversion_rate),
    metadata: { source: 'live-simulator' }
  }

  try {
    await ingestStudioBarrage(payload)
    statusText.value = '弹幕已注入后端。'
    clearStatus()
    if (!customPayload) {
      fillRandomBarrage()
    }
    schedulePriorityRefresh()
  } catch (err) {
    error.value = err?.message || '发送弹幕失败。'
  }
}

function schedulePriorityRefresh() {
  window.clearTimeout(priorityRefreshTimerRef.value)
  priorityRefreshTimerRef.value = window.setTimeout(() => {
    refreshData()
  }, 1200)
}

function closeSocket() {
  if (socketRef.value) {
    socketRef.value.close()
    socketRef.value = null
  }
}

function connectStream() {
  const token = readStudioToken()
  if (!token) {
    error.value = 'Studio 登录态失效，请重新登录。'
    return
  }
  closeSocket()
  const socket = new WebSocket(buildStudioBarrageWsUrl(form.session_id, token))
  socketRef.value = socket

  socket.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data)
      if (payload.type === 'snapshot') {
        rawBarrages.value = (payload.items || []).map(normalizeBarrage).slice(-30)
        return
      }
      if (payload.type === 'barrage' && payload.item) {
        rawBarrages.value = [...rawBarrages.value.slice(-29), normalizeBarrage(payload.item)]
        schedulePriorityRefresh()
        return
      }
      if (payload.type === 'overview' && payload.item) {
        overview.value = payload.item
      }
    } catch (err) {
      error.value = err?.message || '弹幕流消息解析失败。'
    }
  }

  socket.onerror = () => {
    error.value = '弹幕流连接异常。'
  }
}

function stopAuto() {
  autoRunning.value = false
  if (autoTimerRef.value) {
    window.clearInterval(autoTimerRef.value)
    autoTimerRef.value = null
  }
}

function startAuto() {
  if (autoRunning.value) {
    return
  }
  autoRunning.value = true
  autoTimerRef.value = window.setInterval(async () => {
    const nextViewers = Math.max(0, Number(form.online_viewers) + Math.floor(Math.random() * 80 - 40))
    form.online_viewers = nextViewers
    form.interaction_rate = Number((Number(form.interaction_rate) + Math.random() * 0.8 - 0.4).toFixed(2))
    form.conversion_rate = Number((Math.max(0, Number(form.conversion_rate) + Math.random() * 0.2 - 0.1)).toFixed(2))

    const payload = {
      session_id: form.session_id,
      display_name: SAMPLE_USERS[Math.floor(Math.random() * SAMPLE_USERS.length)],
      text: SAMPLE_BARRAGES[Math.floor(Math.random() * SAMPLE_BARRAGES.length)],
      source: 'live-simulator',
      current_product_id: form.current_product_id || null,
      live_stage: form.live_stage,
      online_viewers: nextViewers,
      interaction_rate: Number(form.interaction_rate),
      conversion_rate: Number(form.conversion_rate),
      metadata: { source: 'live-simulator', auto: true }
    }
    await sendBarrage(payload)
  }, 1800)
}

function toggleAuto() {
  if (autoRunning.value) {
    stopAuto()
    return
  }
  startAuto()
}

function openStudio() {
  window.open('/studio-v2', '_blank', 'noopener')
}

watch(
  () => form.session_id,
  async () => {
    await nextTick()
    await refreshData()
    connectStream()
  }
)

onMounted(async () => {
  await updateOverview()
  await refreshData()
  connectStream()
})

onBeforeUnmount(() => {
  stopAuto()
  closeSocket()
  window.clearTimeout(priorityRefreshTimerRef.value)
  window.clearTimeout(clearStatus.timerId)
})
</script>
