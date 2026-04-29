<template>
  <section class="feature-page">
    <header class="feature-page__header">
      <div>
        <p class="panel__eyebrow">Agent Flow</p>
        <h1>监控与调试双模式</h1>
        <p class="muted">当前页只看摘要和发起调试，完整链路跳转到详情页查看。</p>
      </div>
      <div class="toolbar">
        <button class="ghost-button" type="button" @click="refreshTraces">刷新监控</button>
        <button class="primary-button" type="button" @click="runDebug">发起调试</button>
      </div>
    </header>

    <div class="split-grid split-grid--wide">
      <article class="panel">
        <header class="panel__header">
          <div>
            <p class="panel__eyebrow">Monitor</p>
            <h2>最近 Trace</h2>
          </div>
        </header>
        <div class="list-grid">
          <article
            v-for="trace in agentFlow.traces"
            :key="trace.trace_id"
            class="list-card"
          >
            <div class="list-card__row">
              <strong>{{ trace.trace_id }}</strong>
              <span class="pill">{{ trace.session_id }}</span>
            </div>
            <p class="muted">节点：{{ summarizeNodes(trace.nodes) }}</p>
            <p class="muted">错误：{{ trace.error_count }}，降级：{{ trace.degraded_count }}</p>
            <div class="toolbar toolbar--tight">
              <button class="ghost-button" type="button" @click="openTrace(trace.trace_id)">查看详情</button>
            </div>
          </article>
        </div>
      </article>

      <article class="panel">
        <header class="panel__header">
          <div>
            <p class="panel__eyebrow">Debug</p>
            <h2>直接调后端</h2>
          </div>
        </header>
        <div class="field-grid field-grid--wide">
          <label class="field field--full">
            <span>用户输入</span>
            <textarea v-model="agentFlow.debugPayload.user_input" rows="4" />
          </label>
          <label class="field">
            <span>会话 ID</span>
            <input v-model="agentFlow.debugPayload.session_id" type="text" />
          </label>
          <label class="field">
            <span>商品 ID</span>
            <input v-model="agentFlow.debugPayload.current_product_id" type="text" />
          </label>
          <label class="field">
            <span>直播阶段</span>
            <select v-model="agentFlow.debugPayload.live_stage">
              <option value="warmup">warmup</option>
              <option value="intro">intro</option>
              <option value="pitch">pitch</option>
              <option value="closing">closing</option>
            </select>
          </label>
        </div>

        <div v-if="agentFlow.debugMeta" class="stack">
          <div class="detail-grid">
            <div><span class="muted">Trace</span><strong>{{ agentFlow.debugMeta.trace_id }}</strong></div>
            <div><span class="muted">Intent</span><strong>{{ agentFlow.debugMeta.intent }}</strong></div>
          </div>
          <div class="toolbar toolbar--tight">
            <button class="ghost-button" type="button" @click="openTrace(agentFlow.debugMeta.trace_id)">
              打开链路详情
            </button>
          </div>
        </div>

        <pre class="code-block code-block--preview">{{ agentFlow.debugStream || '等待调试输出...' }}</pre>
        <p v-if="agentFlow.error" class="error-text">{{ agentFlow.error }}</p>
      </article>
    </div>
  </section>
</template>

<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'

import { useAgentFlowStore } from '@/stores/agentFlow'

const agentFlow = useAgentFlowStore()
const router = useRouter()

function summarizeNodes(nodes) {
  if (!nodes?.length) {
    return '暂无'
  }
  const unique = [...new Set(nodes)]
  if (unique.length <= 6) {
    return unique.join(' / ')
  }
  return `${unique.slice(0, 6).join(' / ')} / ...`
}

async function refreshTraces() {
  await agentFlow.loadTraces()
}

async function runDebug() {
  await agentFlow.runDebugChat()
}

function openTrace(traceId) {
  if (!traceId) {
    return
  }
  router.push({ name: 'agent-flow-detail', params: { traceId } })
}

onMounted(refreshTraces)
</script>
