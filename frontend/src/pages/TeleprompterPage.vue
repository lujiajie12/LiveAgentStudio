<template>
  <section class="teleprompter-page">
    <header class="teleprompter-page__header">
      <div>
        <p class="teleprompter-page__eyebrow">LiveAgent Teleprompter</p>
        <h1>{{ currentItem?.title || '等待提词内容' }}</h1>
      </div>

      <div class="teleprompter-page__meta">
        <span class="teleprompter-page__chip">
          Session {{ sessionId }}
        </span>
        <span v-if="currentItem?.source_agent" class="teleprompter-page__chip teleprompter-page__chip--agent">
          {{ currentItem.source_agent }}
        </span>
        <span v-if="currentItem?.priority" class="teleprompter-page__chip teleprompter-page__chip--priority">
          {{ currentItem.priority }}
        </span>
      </div>
    </header>

    <main class="teleprompter-page__body">
      <article v-if="currentItem" class="teleprompter-page__card">
        <pre class="teleprompter-page__content">{{ currentItem.content }}</pre>
        <footer class="teleprompter-page__footer">
          <span>来源：{{ currentItem.source_agent || 'qa' }}</span>
          <span>更新时间：{{ formatTime(currentItem.updated_at || currentItem.created_at) }}</span>
        </footer>
      </article>

      <article v-else class="teleprompter-page__empty">
        <p>等待 Studio 推送最新话术...</p>
      </article>

      <p v-if="error" class="teleprompter-page__error">{{ error }}</p>
    </main>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import {
  buildStudioTeleprompterWsUrl,
  fetchStudioTeleprompterCurrent
} from '@/api/studio'
import { readStudioToken } from '@/utils/studioAuth'

const route = useRoute()
const sessionId = computed(() => String(route.params.sessionId || 'studio-live-room-001'))
const currentItem = ref(null)
const error = ref('')
const socketRef = ref(null)
const reconnectTimerRef = ref(null)

function formatTime(value) {
  if (!value) {
    return '--'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString('zh-CN', { hour12: false })
}

async function loadCurrent() {
  try {
    currentItem.value = await fetchStudioTeleprompterCurrent(sessionId.value)
  } catch (err) {
    error.value = err?.message || '获取提词内容失败'
  }
}

function clearReconnect() {
  if (reconnectTimerRef.value) {
    window.clearTimeout(reconnectTimerRef.value)
    reconnectTimerRef.value = null
  }
}

function closeSocket() {
  clearReconnect()
  if (socketRef.value) {
    socketRef.value.close()
    socketRef.value = null
  }
}

function connectStream() {
  const token = readStudioToken()
  if (!token) {
    error.value = 'Studio 登录态失效，请重新登录'
    return
  }

  closeSocket()
  const socket = new WebSocket(buildStudioTeleprompterWsUrl(sessionId.value, token))
  socketRef.value = socket

  socket.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data)
      if (payload.type === 'snapshot') {
        currentItem.value = payload.item || null
        return
      }
      if (payload.type === 'teleprompter') {
        currentItem.value = payload.item || null
      }
    } catch (err) {
      error.value = err?.message || '提词器消息解析失败'
    }
  }

  socket.onerror = () => {
    error.value = '提词器连接异常'
  }

  socket.onclose = () => {
    if (socketRef.value === socket) {
      socketRef.value = null
    }
    clearReconnect()
    reconnectTimerRef.value = window.setTimeout(() => {
      connectStream()
    }, 3000)
  }
}

onMounted(async () => {
  await loadCurrent()
  connectStream()
})

onBeforeUnmount(() => {
  closeSocket()
})
</script>
