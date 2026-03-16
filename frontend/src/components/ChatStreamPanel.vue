<template>
  <section class="panel panel--chat">
    <header class="panel__header">
      <div>
        <p class="panel__eyebrow">Realtime</p>
        <h2>问答流</h2>
      </div>
      <span v-if="isStreaming" class="status-pill">Streaming</span>
    </header>

    <div class="message-list">
      <article
        v-for="message in messages"
        :key="message.id"
        class="message"
        :class="`message--${message.role}`"
      >
        <small>{{ message.role }}</small>
        <p>{{ message.content }}</p>
      </article>
      <article v-if="streamBuffer" class="message message--assistant message--streaming">
        <small>assistant</small>
        <p>{{ streamBuffer }}</p>
      </article>
    </div>

    <form class="composer" @submit.prevent="submit">
      <textarea
        v-model="draft"
        rows="4"
        placeholder="输入用户问题、话术需求或直播复盘请求"
      />
      <div class="composer__footer">
        <p v-if="error" class="error-text">{{ error }}</p>
        <button class="primary-button" :disabled="isStreaming || !draft.trim()" type="submit">
          发送
        </button>
      </div>
    </form>
  </section>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  messages: {
    type: Array,
    required: true
  },
  streamBuffer: {
    type: String,
    default: ''
  },
  isStreaming: {
    type: Boolean,
    default: false
  },
  error: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['send'])
const draft = ref('')

function submit() {
  emit('send', draft.value)
  draft.value = ''
}
</script>
