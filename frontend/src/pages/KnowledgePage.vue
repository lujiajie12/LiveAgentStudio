<template>
  <section class="feature-page">
    <header class="feature-page__header">
      <div>
        <p class="panel__eyebrow">Knowledge</p>
        <h1>知识文档录入</h1>
      </div>
      <p class="muted">MVP 阶段先接 JSON 文档录入，后续再扩成文件上传和解析任务。</p>
    </header>

    <form class="editor-card" @submit.prevent="submit">
      <input v-model="form.title" type="text" placeholder="文档标题" />
      <input v-model="form.source_type" type="text" placeholder="source_type，例如 faq" />
      <input v-model="form.product_id" type="text" placeholder="product_id，可选" />
      <textarea v-model="form.content" rows="8" placeholder="文档正文" />
      <button class="primary-button" type="submit">提交文档</button>
      <p v-if="status" class="muted">{{ status }}</p>
    </form>
  </section>
</template>

<script setup>
import { reactive, ref } from 'vue'

import { createDocument } from '@/api/documents'

const status = ref('')
const form = reactive({
  title: '直播 FAQ',
  source_type: 'faq',
  product_id: 'SKU-001',
  content: '支持 7 天无理由，敏感肌可先局部试用。',
  metadata: {}
})

async function submit() {
  const document = await createDocument(form)
  status.value = `已创建文档 ${document.title}`
}
</script>
