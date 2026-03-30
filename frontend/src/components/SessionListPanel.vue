<template>
  <section class="studio-panel studio-panel--sessions">
    <header class="studio-panel__header">
      <div>
        <p class="panel__eyebrow">Sessions</p>
        <h2>直播会话</h2>
      </div>
    </header>

    <div class="session-list session-list--studio">
      <button
        v-for="session in sessions"
        :key="session.id"
        type="button"
        class="session-card session-card--studio"
        :class="{ 'session-card--active': session.id === activeSessionId }"
        @click="$emit('select', session.id)"
      >
        <div class="session-card__marker" v-if="session.id === activeSessionId"></div>
        <div class="session-card__row">
          <strong>{{ session.title }}</strong>
          <span v-if="session.id === activeSessionId" class="live-indicator">
            <span class="live-indicator__dot"></span>
            Live
          </span>
        </div>
        <p class="session-card__meta">{{ session.current_product_id }} · {{ formatStage(session.live_stage) }}</p>
      </button>
    </div>
  </section>
</template>

<script setup>
defineProps({
  sessions: {
    type: Array,
    required: true
  },
  activeSessionId: {
    type: String,
    default: ''
  }
})

defineEmits(['select'])

function formatStage(stage) {
  const labels = {
    warmup: 'Warmup',
    intro: 'Intro',
    pitch: 'Pitch',
    closing: 'Closing'
  }
  return labels[stage] || stage
}
</script>
