<template>
  <section class="recent-qa">
    <div class="recent-qa__header">
      <div class="recent-qa__title">
        <div class="recent-qa__title-icon">
          <AppIcon name="history" :size="16" />
        </div>
        <h3>最近问答</h3>
        <span class="recent-qa__count">{{ filteredItems.length }} 条记录</span>
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
        v-for="(item, index) in visibleItems"
        :key="item.id"
        class="recent-qa__item"
        :class="{ 'recent-qa__item--streaming': item.streaming }"
      >
        <div v-if="index !== visibleItems.length - 1" class="recent-qa__line"></div>

        <div class="recent-qa__question-row">
          <div class="recent-qa__question-icon">Q</div>

          <div class="recent-qa__question-copy">
            <p>{{ item.question || '等待新的提问...' }}</p>
          </div>

          <div class="recent-qa__time">
            <AppIcon name="clock" :size="10" />
            <span>{{ item.timeLabel || '刚刚' }}</span>
          </div>
        </div>

        <div class="recent-qa__answer-row">
          <div class="recent-qa__answer-icon">
            <AppIcon name="bot" :size="12" />
          </div>

          <div class="recent-qa__answer-card">
            <p class="recent-qa__answer-text">
              {{ item.answer || (item.streaming ? '正在流式生成，请稍候...' : '当前暂无回答内容。') }}
            </p>

            <div class="recent-qa__answer-footer">
              <div class="recent-qa__meta">
                <span class="recent-qa__tag" :class="`recent-qa__tag--${resolveTagTone(item)}`">
                  {{ resolveType(item) }}
                </span>
                <span class="recent-qa__citation">{{ resolveCitation(item) }}</span>
              </div>

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
    return `引用 ${item.references.length} 条知识片段`
  }
  if (typeof item.references === 'number' && item.references > 0) {
    return `引用 ${item.references} 条知识片段`
  }
  return item.streaming ? '当前回答正在流式更新' : '引用系统问答记录'
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
  max-height: 420px;
  overflow-y: auto;
  padding: 18px 20px 10px;
}

.recent-qa__item {
  position: relative;
  display: grid;
  gap: 12px;
  padding-bottom: 18px;
}

.recent-qa__line {
  position: absolute;
  left: 15px;
  top: 38px;
  bottom: -6px;
  width: 1px;
  background: linear-gradient(to bottom, rgba(99, 102, 241, 0.4), transparent);
}

.recent-qa__question-row,
.recent-qa__answer-row {
  display: flex;
  gap: 12px;
}

.recent-qa__question-icon,
.recent-qa__answer-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 999px;
  flex: 0 0 30px;
}

.recent-qa__question-icon {
  background: rgba(51, 65, 85, 0.96);
  color: #e2e8f0;
  font-size: 14px;
  font-weight: 700;
}

.recent-qa__answer-icon {
  background: rgba(99, 102, 241, 0.18);
  border: 1px solid rgba(99, 102, 241, 0.28);
  color: #818cf8;
}

.recent-qa__question-copy {
  flex: 1;
  min-width: 0;
  padding-top: 4px;
  color: #cbd5e1;
}

.recent-qa__question-copy p {
  margin: 0;
  line-height: 1.6;
}

.recent-qa__time {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #94a3b8;
  font-size: 12px;
  white-space: nowrap;
  padding-top: 4px;
}

.recent-qa__answer-card {
  flex: 1;
  min-width: 0;
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid rgba(99, 102, 241, 0.18);
  background: rgba(30, 41, 59, 0.28);
}

.recent-qa__answer-text {
  margin: 0;
  color: #f8fafc;
  line-height: 1.7;
}

.recent-qa__answer-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 12px;
}

.recent-qa__meta {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.recent-qa__tag {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 12px;
  border-radius: 10px;
  font-size: 12px;
  border: 1px solid transparent;
}

.recent-qa__tag--rag {
  color: #a5b4fc;
  background: rgba(99, 102, 241, 0.14);
  border-color: rgba(99, 102, 241, 0.26);
}

.recent-qa__tag--product {
  color: #93c5fd;
  background: rgba(59, 130, 246, 0.14);
  border-color: rgba(59, 130, 246, 0.24);
}

.recent-qa__tag--service {
  color: #fcd34d;
  background: rgba(245, 158, 11, 0.14);
  border-color: rgba(245, 158, 11, 0.24);
}

.recent-qa__tag--logistics {
  color: #86efac;
  background: rgba(34, 197, 94, 0.14);
  border-color: rgba(34, 197, 94, 0.24);
}

.recent-qa__tag--stream {
  color: #c4b5fd;
  background: rgba(139, 92, 246, 0.14);
  border-color: rgba(139, 92, 246, 0.24);
}

.recent-qa__citation {
  color: #94a3b8;
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.recent-qa__actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.recent-qa__action-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 10px;
  background: rgba(30, 41, 59, 0.88);
  color: #94a3b8;
  cursor: pointer;
}

.recent-qa__action-button--accent:hover {
  background: rgba(99, 102, 241, 0.22);
  color: #f8fafc;
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
