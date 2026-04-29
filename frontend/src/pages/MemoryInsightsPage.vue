<template>
  <section class="feature-page">
    <header class="feature-page__header">
      <div>
        <p class="panel__eyebrow">QA Memory</p>
        <h1>长期记忆洞察</h1>
        <p class="muted">
          面向 QA Agent 的长期记忆展示页，按“直播管理员偏好 / 商品 facts / FAQ 热点”分层展示。
        </p>
      </div>
      <div class="toolbar">
        <button class="ghost-button" type="button" @click="loadInsights">刷新</button>
      </div>
    </header>

    <article class="panel panel--subtle">
      <div class="field-grid field-grid--wide">
        <label class="field">
          <span>用户范围（可选）</span>
          <input
            v-model="filters.userId"
            type="text"
            placeholder="留空查看全部用户的 QA 长期记忆"
          />
        </label>
        <label class="field">
          <span>数量上限</span>
          <input v-model.number="filters.limit" type="number" min="10" max="500" />
        </label>
      </div>
      <div class="toolbar">
        <button class="primary-button" type="button" @click="loadInsights">应用过滤</button>
      </div>
      <p v-if="error" class="error-text">{{ error }}</p>
      <p v-else-if="!insights?.enabled" class="muted">
        QA 长期记忆当前未启用。请配置 `QA_MEMORY_ENABLED=true` 和 Mem0 相关环境变量后重启后端。
      </p>
    </article>

    <div v-if="insights?.enabled" class="dashboard-grid">
      <article class="stat-card">
        <span>总记忆数</span>
        <strong>{{ insights.overview?.total_memories ?? 0 }}</strong>
      </article>
      <article class="stat-card">
        <span>管理员偏好</span>
        <strong>{{ insights.overview?.operator_preferences ?? 0 }}</strong>
      </article>
      <article class="stat-card">
        <span>商品 Facts</span>
        <strong>{{ insights.overview?.product_fact_groups ?? 0 }}</strong>
      </article>
      <article class="stat-card">
        <span>FAQ 热点</span>
        <strong>{{ insights.overview?.faq_hotspots ?? 0 }}</strong>
      </article>
    </div>

    <div v-if="insights?.enabled" class="split-grid split-grid--wide">
      <article class="panel">
        <header class="panel__header">
          <div>
            <p class="panel__eyebrow">Preferences</p>
            <h2>直播管理员偏好</h2>
          </div>
          <span class="pill">{{ insights.operator_preferences?.length || 0 }} 条</span>
        </header>
        <div v-if="insights.operator_preferences?.length" class="list-grid">
          <article
            v-for="item in insights.operator_preferences"
            :key="item.memory_id"
            class="list-card"
          >
            <div class="list-card__row">
              <strong>{{ item.question_preview || '偏好记录' }}</strong>
              <span class="pill">{{ formatTime(item.updated_at) }}</span>
            </div>
            <p class="muted">{{ item.summary }}</p>
          </article>
        </div>
        <p v-else class="muted">暂无直播管理员偏好记忆。</p>
      </article>

      <article class="panel">
        <header class="panel__header">
          <div>
            <p class="panel__eyebrow">Product Facts</p>
            <h2>商品 Facts</h2>
          </div>
          <span class="pill">{{ insights.product_facts?.length || 0 }} 组</span>
        </header>
        <div v-if="insights.product_facts?.length" class="list-grid">
          <article
            v-for="item in insights.product_facts"
            :key="`${item.product_id}-${item.topic}`"
            class="list-card"
          >
            <div class="list-card__row">
              <strong>{{ item.topic }}</strong>
              <span class="pill">{{ item.product_id }}</span>
            </div>
            <p class="muted">出现 {{ item.count }} 次，最近一次 {{ formatTime(item.last_seen) }}</p>
          </article>
        </div>
        <p v-else class="muted">暂无商品 facts 记忆。</p>
      </article>
    </div>

    <article v-if="insights?.enabled" class="panel">
      <header class="panel__header">
        <div>
          <p class="panel__eyebrow">FAQ Hotspots</p>
          <h2>FAQ 热点</h2>
        </div>
        <span class="pill">{{ insights.faq_hotspots?.length || 0 }} 个问题</span>
      </header>
      <div v-if="insights.faq_hotspots?.length" class="list-grid">
        <article v-for="item in insights.faq_hotspots" :key="item.question" class="list-card">
          <div class="list-card__row">
            <strong>{{ item.question }}</strong>
            <span class="pill">{{ item.count }} 次</span>
          </div>
          <p class="muted">
            最近一次 {{ formatTime(item.last_seen) }}
            <template v-if="item.products?.length">，商品：{{ item.products.join(', ') }}</template>
          </p>
        </article>
      </div>
      <p v-else class="muted">暂无 FAQ 热点记忆。</p>
    </article>

    <article v-if="insights?.enabled" class="panel">
      <header class="panel__header">
        <div>
          <p class="panel__eyebrow">Recent Memories</p>
          <h2>最近记忆</h2>
        </div>
      </header>
      <div v-if="insights.recent_memories?.length" class="list-grid">
        <article v-for="item in insights.recent_memories" :key="item.memory_id" class="list-card">
          <div class="list-card__row">
            <strong>{{ item.question_preview || '记忆条目' }}</strong>
            <span class="pill">{{ formatTime(item.updated_at) }}</span>
          </div>
          <p class="muted">{{ item.summary }}</p>
        </article>
      </div>
      <p v-else class="muted">暂无最近记忆。</p>
    </article>
  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'

import { fetchQaMemoryInsights } from '@/api/memory'

const insights = ref(null)
const error = ref('')
const filters = reactive({
  userId: '',
  limit: 120
})

function formatTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

async function loadInsights() {
  error.value = ''
  try {
    insights.value = await fetchQaMemoryInsights({
      user_id: filters.userId || undefined,
      limit: filters.limit || 120
    })
  } catch (err) {
    error.value = err.response?.data?.message || err.message || '加载长期记忆失败'
  }
}

onMounted(loadInsights)
</script>
