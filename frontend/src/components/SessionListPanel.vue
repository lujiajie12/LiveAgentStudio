<template>
  <section class="panel">
    <header class="panel__header">
      <div>
        <p class="panel__eyebrow">Sessions</p>
        <h2>直播会话</h2>
      </div>
    </header>
    <div class="session-list">
      <button
        v-for="session in sessions"
        :key="session.id"
        type="button"
        class="session-card"
        :class="{ 'session-card--active': session.id === activeSessionId }"
        @click="$emit('select', session.id)"
      >
        <strong>{{ session.title }}</strong>
        <span>{{ session.current_product_id }}</span>
        <small>{{ session.live_stage }}</small>
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
</script>
