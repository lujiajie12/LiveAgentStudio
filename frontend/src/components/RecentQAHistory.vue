<template>
  <section class="recent-qa">
    <div class="recent-qa__header">
      <div class="recent-qa__title">
        <div class="recent-qa__title-icon">
          <AppIcon name="history" :size="16" />
        </div>
        <h3>最近问答</h3>
        <span class="recent-qa__count">{{ filteredItems.length }} 条</span>
      </div>

      <button
        v-if="hasMore"
        type="button"
        class="recent-qa__view-all"
        @click="toggleShowAll"
      >
        {{ showAll ? '收起' : '查看全部' }}
        <AppIcon name="chevron-right" :size="14" />
      </button>
    </div>

    <div v-if="visibleItems.length" class="recent-qa__list studio-v2__custom-scrollbar">
      <article
        v-for="item in visibleItems"
        :key="item.id"
        class="recent-qa__item"
        :class="{ 'recent-qa__item--streaming': item.streaming }"
      >
        <!-- 用户问题 -->
        <div class="recent-qa__question-row">
          <div class="recent-qa__avatar recent-qa__avatar--user">
            <AppIcon name="user" :size="12" />
          </div>
          <div class="recent-qa__question-bubble">
            <p>{{ item.question || '等待新的提问...' }}</p>
          </div>
          <span class="recent-qa__time">
            <AppIcon name="clock" :size="10" />
            {{ item.timeLabel || '刚刚' }}
          </span>
        </div>

        <!-- AI 回答 -->
        <div class="recent-qa__answer-row">
          <div class="recent-qa__avatar recent-qa__avatar--ai">
            <AppIcon name="bot" :size="14" />
          </div>
          <div class="recent-qa__answer-content">
            <div class="recent-qa__answer-meta">
              <span class="recent-qa__answer-badge" :class="`recent-qa__answer-badge--${resolveTagTone(item)}`">
                {{ resolveType(item) }}
              </span>
              <span class="recent-qa__citation">{{ resolveCitation(item) }}</span>
            </div>

            <!-- 思考中状态 -->
            <div v-if="item.streaming && !item.answer" class="recent-qa__thinking">
              <div class="recent-qa__thinking-dots">
                <span></span><span></span><span></span>
              </div>
              <span class="recent-qa__thinking-text">AI 正在思考...</span>
            </div>

            <!-- 回答内容 -->
            <div v-else class="recent-qa__answer-bubble" :class="{ 'recent-qa__answer-bubble--streaming': item.streaming }">
              <span v-if="item.streaming" class="recent-qa__cursor"></span>
              <p class="recent-qa__answer-text">{{ item.answer || '当前暂无回答内容。' }}</p>
            </div>

            <!-- 操作按钮 -->
            <div class="recent-qa__actions">
              <button
                type="button"
                class="recent-qa__action-button"
                title="复制回答"
                @click="copyAnswer(item)"
              >
                <AppIcon name="copy" :size="12" />
              </button>
              <button
                type="button"
                class="recent-qa__action-button recent-qa__action-button--accent"
                title="推送至提词器"
                @click="$emit('push', item)"
              >
                <AppIcon name="send" :size="12" />
              </button>
              <button
                type="button"
                class="recent-qa__action-button recent-qa__action-button--danger"
                title="删除记录"
                @click="dismissItem(item.id)"
              >
                <AppIcon name="trash-2" :size="12" />
              </button>
            </div>
          </div>
        </div>
      </article>
    </div>

    <div v-else class="recent-qa__empty">
      <AppIcon name="message-square" :size="18" />
      <div>
        <strong>最近问答会沉淀在这里</strong>
        <p>发送新的 QA 或直答请求后，系统会把最近的问答记录保存在这里，便于快速回看。</p>
      </div>
    </div>

    <div class="recent-qa__footer">
      <button
        v-if="hasMore"
        type="button"
        class="recent-qa__older"
        @click="toggleShowAll"
      >
        <AppIcon name="more-vertical" :size="12" />
        {{ showAll ? '收起历史记录' : '显示更早的历史记录' }}
      </button>
    </div>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

import AppIcon from '@/components/AppIcon.vue'

const props = defineProps({
  items: {
    type: Array,
    default: () => []
  },
  collapsedCount: {
    type: Number,
    default: 4
  }
})

const emit = defineEmits(['copy', 'push', 'remove'])

const showAll = ref(false)
const hiddenIds = ref([])

const filteredItems = computed(() => props.items.filter((item) => !hiddenIds.value.includes(item.id)))
const hasMore = computed(() => filteredItems.value.length > props.collapsedCount)
const visibleItems = computed(() => (
  showAll.value ? filteredItems.value : filteredItems.value.slice(0, props.collapsedCount)
))

watch(
  () => props.items.map((item) => item.id).join('|'),
  () => {
    hiddenIds.value = hiddenIds.value.filter((id) => props.items.some((item) => item.id === id))
  }
)

async function copyAnswer(item) {
  if (item.answer && navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(item.answer)
  }
  emit('copy', item)
}

function dismissItem(itemId) {
  hiddenIds.value = [...hiddenIds.value, itemId]
  emit('remove', itemId)
}

function toggleShowAll() {
  showAll.value = !showAll.value
}

function resolveType(item) {
  if (item.type) {
    return item.type
  }

  const question = String(item.question || '')
  if (question.includes('售后') || question.includes('保修')) {
    return 'Service'
  }
  if (question.includes('发货') || question.includes('物流') || question.includes('运费')) {
    return 'Logistics'
  }
  if (question.includes('适合') || question.includes('参数') || question.includes('区别')) {
    return 'Product'
  }
  return 'RAG'
}

function resolveTagTone(item) {
  if (item.tagTone) {
    return item.tagTone
  }

  const type = resolveType(item)
  if (type === 'Service') {
    return 'service'
  }
  if (type === 'Logistics') {
    return 'logistics'
  }
  if (type === 'Product') {
    return 'product'
  }
  if (type === 'Direct') {
    return 'stream'
  }
  return 'rag'
}

function resolveCitation(item) {
  if (item.citation) {
    return item.citation
  }
  if (Array.isArray(item.references) && item.references.length) {
    return `引用 ${item.references.length} 条`
  }
  if (typeof item.references === 'number' && item.references > 0) {
    return `引用 ${item.references} 条`
  }
  return item.streaming ? '回答生成中...' : '系统记录'
}
</script>

<style scoped>
.recent-qa {
  display: grid;
  gap: 0;
  margin: 0 20px 20px;
  border: 1px solid rgba(51, 65, 85, 0.72);
  border-radius: 18px;
  background: rgba(15, 17, 23, 0.88);
  overflow: hidden;
}

.recent-qa__header,
.recent-qa__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  background: rgba(22, 26, 35, 0.96);
}

.recent-qa__header {
  border-bottom: 1px solid rgba(51, 65, 85, 0.56);
}

.recent-qa__footer {
  border-top: 1px solid rgba(51, 65, 85, 0.56);
  justify-content: center;
}

.recent-qa__title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.recent-qa__title-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 10px;
  background: rgba(99, 102, 241, 0.12);
  color: #818cf8;
}

.recent-qa__title h3 {
  margin: 0;
  font-size: 16px;
  color: #f8fafc;
}

.recent-qa__count {
  padding: 3px 10px;
  border-radius: 999px;
  background: rgba(30, 41, 59, 0.88);
  color: #94a3b8;
  font-size: 11px;
}

.recent-qa__view-all,
.recent-qa__older {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: none;
  background: transparent;
  color: #818cf8;
  cursor: pointer;
}

.recent-qa__list {
  max-height: 520px;
  overflow-y: auto;
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.recent-qa__item {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(22, 26, 35, 0.6);
  border: 1px solid rgba(51, 65, 85, 0.4);
}

.recent-qa__item--streaming {
  border-color: rgba(16, 185, 129, 0.3);
  background: rgba(16, 185, 129, 0.04);
}

/* 用户问题行 */
.recent-qa__question-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.recent-qa__avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 999px;
  flex-shrink: 0;
  margin-top: 2px;
}

.recent-qa__avatar--user {
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: #fff;
}

.recent-qa__avatar--ai {
  background: linear-gradient(135deg, #10b981, #059669);
  color: #fff;
}

.recent-qa__question-bubble {
  flex: 1;
  background: rgba(99, 102, 241, 0.12);
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: 12px 12px 12px 4px;
  padding: 10px 14px;
}

.recent-qa__question-bubble p {
  margin: 0;
  color: #e2e8f0;
  line-height: 1.5;
  font-size: 13px;
}

.recent-qa__time {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #64748b;
  font-size: 11px;
  white-space: nowrap;
  margin-top: 6px;
}

/* AI 回答行 */
.recent-qa__answer-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding-left: 34px;
}

.recent-qa__answer-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.recent-qa__answer-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.recent-qa__answer-badge {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 500;
}

.recent-qa__answer-badge--rag {
  color: #a5b4fc;
  background: rgba(99, 102, 241, 0.15);
  border: 1px solid rgba(99, 102, 241, 0.3);
}

.recent-qa__answer-badge--product {
  color: #93c5fd;
  background: rgba(59, 130, 246, 0.15);
  border: 1px solid rgba(59, 130, 246, 0.3);
}

.recent-qa__answer-badge--service {
  color: #fcd34d;
  background: rgba(245, 158, 11, 0.15);
  border: 1px solid rgba(245, 158, 11, 0.3);
}

.recent-qa__answer-badge--logistics {
  color: #86efac;
  background: rgba(34, 197, 94, 0.15);
  border: 1px solid rgba(34, 197, 94, 0.3);
}

.recent-qa__answer-badge--stream {
  color: #c4b5fd;
  background: rgba(139, 92, 246, 0.15);
  border: 1px solid rgba(139, 92, 246, 0.3);
}

.recent-qa__citation {
  color: #64748b;
  font-size: 11px;
}

/* 思考动画 */
.recent-qa__thinking {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: rgba(16, 185, 129, 0.06);
  border: 1px solid rgba(16, 185, 129, 0.18);
  border-radius: 12px 12px 4px 12px;
}

.recent-qa__thinking-dots {
  display: flex;
  gap: 4px;
}

.recent-qa__thinking-dots span {
  width: 6px;
  height: 6px;
  background: #10b981;
  border-radius: 50%;
  animation: recent-qa__bounce 1.4s ease-in-out infinite;
}

.recent-qa__thinking-dots span:nth-child(1) { animation-delay: 0s; }
.recent-qa__thinking-dots span:nth-child(2) { animation-delay: 0.2s; }
.recent-qa__thinking-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes recent-qa__bounce {
  0%, 80%, 100% {
    transform: scale(0.6);
    opacity: 0.5;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
}

.recent-qa__thinking-text {
  color: #10b981;
  font-size: 12px;
  font-weight: 500;
}

/* 回答气泡 */
.recent-qa__answer-bubble {
  background: rgba(16, 185, 129, 0.08);
  border: 1px solid rgba(16, 185, 129, 0.2);
  border-radius: 12px 12px 4px 12px;
  padding: 10px 14px;
  position: relative;
}

.recent-qa__answer-bubble--streaming {
  border-color: rgba(16, 185, 129, 0.4);
  background: rgba(16, 185, 129, 0.12);
}

.recent-qa__cursor {
  display: inline-block;
  width: 2px;
  height: 14px;
  background: #10b981;
  margin-right: 2px;
  vertical-align: middle;
  animation: recent-qa__blink 0.8s ease-in-out infinite;
}

@keyframes recent-qa__blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

.recent-qa__answer-text {
  margin: 0;
  color: #f8fafc;
  line-height: 1.6;
  font-size: 13px;
}

/* 操作按钮 */
.recent-qa__actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.recent-qa__item:hover .recent-qa__actions {
  opacity: 1;
}

.recent-qa__action-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border: none;
  border-radius: 6px;
  background: rgba(30, 41, 59, 0.88);
  color: #94a3b8;
  cursor: pointer;
  transition: all 0.15s ease;
}

.recent-qa__action-button:hover {
  background: rgba(51, 65, 85, 0.96);
  color: #f8fafc;
}

.recent-qa__action-button--accent:hover {
  background: rgba(99, 102, 241, 0.22);
  color: #a5b4fc;
}

.recent-qa__action-button--danger:hover {
  background: rgba(239, 68, 68, 0.16);
  color: #fca5a5;
}

.recent-qa__empty {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 22px 20px;
  color: #94a3b8;
}

.recent-qa__empty strong {
  display: block;
  color: #f8fafc;
  margin-bottom: 6px;
}
</style>
