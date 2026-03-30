<template>
  <section class="studio-chat">
    <header class="studio-chat__header">
      <div>
        <p class="panel__eyebrow">Realtime</p>
        <h2 class="studio-chat__title">
          <AppIcon name="activity" :size="18" />
          <span>直播协同流</span>
        </h2>
      </div>
      <span v-if="isStreaming" class="status-pill status-pill--live">Streaming</span>
    </header>

    <div class="studio-chat__messages">
      <article
        v-for="message in messages"
        :key="message.id"
        class="message-row"
        :class="{ 'message-row--user': message.role === 'user' }"
      >
        <div class="message-avatar" :class="`message-avatar--${message.role}`">
          <AppIcon :name="message.role === 'user' ? 'user' : 'bot'" :size="16" />
        </div>
        <div class="message-bubble" :class="`message-bubble--${message.role}`">
          <p>{{ message.content }}</p>
        </div>
      </article>

      <article v-if="streamBuffer" class="message-row">
        <div class="message-avatar message-avatar--assistant">
          <AppIcon name="bot" :size="16" />
        </div>
        <div class="message-bubble message-bubble--assistant message-bubble--streaming">
          <p>{{ streamBuffer }}</p>
        </div>
      </article>

      <div ref="messagesEndRef"></div>
    </div>

    <div class="studio-chat__composer">
      <form class="composer-shell" @submit.prevent="submit">
        <input
          v-model="draft"
          type="text"
          placeholder="输入观众问题，或主播/场控/运营指令..."
          class="composer-shell__input"
        />
        <button
          class="composer-shell__send"
          :disabled="isStreaming || !draft.trim()"
          type="submit"
        >
          <AppIcon name="send" :size="16" />
        </button>
      </form>
      <p v-if="error" class="error-text">{{ error }}</p>
    </div>
  </section>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue'

import AppIcon from '@/components/AppIcon.vue'

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
const messagesEndRef = ref(null)

async function scrollToBottom() {
  await nextTick()
  messagesEndRef.value?.scrollIntoView({ behavior: 'smooth', block: 'end' })
}

watch(
  () => [props.messages.length, props.streamBuffer],
  () => {
    scrollToBottom()
  }
)

function submit() {
  const value = draft.value.trim()
  if (!value) {
    return
  }
  emit('send', value)
  draft.value = ''
}
</script>
