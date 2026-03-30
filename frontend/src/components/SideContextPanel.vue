<template>
  <section class="studio-panel studio-panel--context">
    <header class="studio-panel__header">
      <div>
        <p class="panel__eyebrow">Context</p>
        <h2>直播状态</h2>
      </div>
    </header>

    <div class="context-stack">
      <article class="context-card">
        <span class="context-card__icon context-card__icon--blue">
          <AppIcon name="box" :size="18" />
        </span>
        <div>
          <p class="context-card__label">当前商品</p>
          <strong>{{ liveContext.current_product_id }}</strong>
        </div>
      </article>

      <article class="context-card">
        <span class="context-card__icon context-card__icon--purple">
          <AppIcon name="tag" :size="18" />
        </span>
        <div>
          <p class="context-card__label">直播阶段</p>
          <strong>{{ formatStage(liveContext.live_stage) }}</strong>
        </div>
      </article>
    </div>

    <article class="queue-card">
      <p class="panel__eyebrow queue-card__eyebrow">
        <AppIcon name="info" :size="14" />
        <span>Script Queue</span>
      </p>
      <p>
        话术建议、QA 引用和后续 Guardrail 告警会在这里呈现并提示。
      </p>
      <small class="queue-card__status">
        <AppIcon name="activity" :size="12" />
        系统正在监听中...
      </small>
    </article>
  </section>
</template>

<script setup>
import AppIcon from '@/components/AppIcon.vue'

defineProps({
  liveContext: {
    type: Object,
    required: true
  }
})

function formatStage(stage) {
  const labels = {
    warmup: 'Warmup',
    intro: 'Intro（介绍阶段）',
    pitch: 'Pitch（主推阶段）',
    closing: 'Closing（收尾阶段）'
  }
  return labels[stage] || stage
}
</script>
