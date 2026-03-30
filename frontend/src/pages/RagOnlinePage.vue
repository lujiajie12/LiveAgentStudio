<template>
  <section class="feature-page">
    <header class="feature-page__header">
      <div>
        <p class="panel__eyebrow">RAG Online</p>
        <h1>在线检索调试</h1>
        <p class="muted">查看 query rewrite、BM25、向量检索、RRF、Rerank 和最终上下文。</p>
      </div>
      <button
        class="primary-button"
        type="button"
        :disabled="isRunning"
        @click="runDebug"
      >
        {{ isRunning ? '调试中...' : '运行调试' }}
      </button>
    </header>

    <section class="panel">
      <div class="field-grid field-grid--wide">
        <label class="field field--full">
          <span>查询语句</span>
          <textarea v-model="form.query" rows="4" :disabled="isRunning" />
        </label>
        <label class="field">
          <span>商品 ID</span>
          <input v-model="form.current_product_id" type="text" :disabled="isRunning" />
        </label>
        <label class="field">
          <span>直播阶段</span>
          <select v-model="form.live_stage" :disabled="isRunning">
            <option value="warmup">warmup</option>
            <option value="intro">intro</option>
            <option value="pitch">pitch</option>
            <option value="closing">closing</option>
          </select>
        </label>
        <label class="field">
          <span>Source Hint</span>
          <select v-model="form.source_hint" :disabled="isRunning">
            <option value="">auto</option>
            <option value="mixed">mixed</option>
            <option value="product_detail">product_detail</option>
            <option value="faq">faq</option>
          </select>
          <p class="muted">
            `auto` 会根据问题关键词自动判断；`product_detail` 优先看商品详情资料；
            `faq` 优先看发货、售后、规则类资料；`mixed` 不加来源偏置。
          </p>
        </label>
      </div>

      <article v-if="isRunning" class="panel panel--subtle">
        <p class="panel__eyebrow">Running</p>
        <h2>正在执行在线调试</h2>
        <p class="muted">
          这条链路会顺序执行 query rewrite、扩展检索、BM25、向量检索、RRF 和 Rerank，
          通常需要 8 到 15 秒。页面不是卡死，只是在等待后端返回完整调试结果。
        </p>
      </article>

      <p v-if="ragOps.error" class="error-text">{{ ragOps.error }}</p>
    </section>

    <div v-if="result" class="dashboard-grid">
      <article class="stat-card">
        <span>Rewrite</span>
        <strong>{{ result.rewritten_query }}</strong>
      </article>
      <article class="stat-card">
        <span>Source Hint</span>
        <strong>{{ result.source_hint }}</strong>
      </article>
      <article class="stat-card">
        <span>降级状态</span>
        <strong>BM25={{ result.degraded.bm25 }} / Vector={{ result.degraded.vector }}</strong>
      </article>
      <article class="stat-card">
        <span>耗时</span>
        <strong>{{ formatTimings(result.timings_ms) }}</strong>
      </article>
    </div>

    <section v-if="result" class="split-grid split-grid--tall">
      <article class="panel">
        <header class="panel__header">
          <div>
            <p class="panel__eyebrow">Expanded Queries</p>
            <h2>查询扩展</h2>
          </div>
        </header>
        <pre class="code-block">{{ JSON.stringify(result.expanded_queries, null, 2) }}</pre>
      </article>

      <article class="panel">
        <header class="panel__header">
          <div>
            <p class="panel__eyebrow">Context</p>
            <h2>最终上下文</h2>
          </div>
        </header>
        <pre class="code-block">{{ result.context }}</pre>
      </article>
    </section>

    <section v-if="result" class="three-column-grid">
      <article class="panel">
        <header class="panel__header">
          <div>
            <p class="panel__eyebrow">BM25</p>
            <h2>关键词检索</h2>
          </div>
        </header>
        <pre class="code-block">{{ JSON.stringify(result.bm25_results, null, 2) }}</pre>
      </article>

      <article class="panel">
        <header class="panel__header">
          <div>
            <p class="panel__eyebrow">Vector</p>
            <h2>向量检索</h2>
          </div>
        </header>
        <pre class="code-block">{{ JSON.stringify(result.vector_results, null, 2) }}</pre>
      </article>

      <article class="panel">
        <header class="panel__header">
          <div>
            <p class="panel__eyebrow">Fusion</p>
            <h2>RRF + Rerank</h2>
          </div>
        </header>
        <pre class="code-block">{{ JSON.stringify({ fused: result.fused_results, rerank: result.rerank_results }, null, 2) }}</pre>
      </article>
    </section>
  </section>
</template>

<script setup>
import { computed, nextTick, reactive } from 'vue'

import { useRagOpsStore } from '@/stores/ragOps'

const ragOps = useRagOpsStore()
const result = computed(() => ragOps.onlineDebugResult)
const isRunning = computed(() => ragOps.loading)
const form = reactive({
  query: '青岚超净蒸汽拖洗一体机适合什么家庭用？跟普通拖把的区别是什么？',
  current_product_id: 'SKU-001',
  live_stage: 'pitch',
  source_hint: ''
})

function formatTimings(timings) {
  if (!timings) return '-'
  return Object.entries(timings)
    .map(([key, value]) => `${key}:${value}ms`)
    .join(' / ')
}

async function runDebug() {
  await nextTick()
  await ragOps.runOnlineDebug({
    query: form.query,
    current_product_id: form.current_product_id || null,
    live_stage: form.live_stage,
    source_hint: form.source_hint || null
  })
}
</script>
