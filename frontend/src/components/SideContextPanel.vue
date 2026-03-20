<template>
  <section class="panel panel--context">
    <header class="panel__header">
      <div>
        <p class="panel__eyebrow">Context</p>
        <h2>直播状态</h2>
      </div>
    </header>
    <div class="context-grid">
      <div class="stat-card">
        <span>当前商品</span>
        <strong>{{ liveContext.current_product_id }}</strong>
      </div>
      <div class="stat-card">
        <span>直播阶段</span>
        <strong>{{ liveContext.live_stage }}</strong>
      </div>
    </div>
    <div class="note-card">
      <p class="panel__eyebrow">Script Queue</p>
      <p>话术建议、QA 引用和后续 Guardrail 告警会在这里并排展示。</p>
    </div>
  </section>
</template>

<script setup>
defineProps({
  liveContext: {
    type: Object,
    required: true
  }
})
</script>
