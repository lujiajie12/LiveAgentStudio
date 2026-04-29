<template>
  <section class="admin-overview">
    <div class="admin-overview__stats">
      <RouterLink
        v-for="card in overviewCards"
        :key="card.label"
        :to="card.to || ''"
        custom
        v-slot="{ navigate }"
      >
        <article
          class="admin-stat-card"
          :class="[`admin-stat-card--${card.tone}`, { 'admin-stat-card--clickable': card.to }]"
          @click="card.to && navigate()"
        >
          <div class="admin-stat-card__top">
            <span>{{ card.label }}</span>
            <span class="admin-stat-card__icon">
              <AppIcon :name="card.icon" :size="17" />
            </span>
          </div>
          <strong>{{ card.title }}</strong>
          <p v-if="card.desc">{{ card.desc }}</p>
          <div v-if="card.chips" class="admin-stat-card__chips">
            <span v-for="chip in card.chips" :key="chip">{{ chip }}</span>
          </div>
        </article>
      </RouterLink>
    </div>

    <div class="admin-overview__workspace">
      <section class="admin-overview__modules">
        <div class="admin-overview__section-title">
          <AppIcon name="sparkles" :size="20" />
          <h3>管理模块</h3>
        </div>

        <div class="admin-module-list">
          <RouterLink
            v-for="module in modules"
            :key="module.title"
            :to="module.to"
            class="admin-module-card"
          >
            <span class="admin-module-card__icon" :class="`admin-module-card__icon--${module.tone}`">
              <AppIcon :name="module.icon" :size="20" />
            </span>
            <span class="admin-module-card__copy">
              <strong>{{ module.title }}</strong>
              <small>{{ module.desc }}</small>
            </span>
            <span class="admin-module-card__tag">{{ module.tag }}</span>
            <AppIcon class="admin-module-card__arrow" name="chevron-right" :size="18" />
          </RouterLink>
        </div>
      </section>

      <aside class="admin-studio-card">
        <div class="admin-studio-card__orb" aria-hidden="true"></div>

        <div class="admin-studio-card__body">
          <span class="admin-studio-card__badge">
            <AppIcon name="monitor-play" :size="14" />
            Platform
          </span>

          <h3>直播操作中台</h3>

          <div class="admin-studio-card__section">
            <span>面向群体</span>
            <p>
              为 <strong>主播、场控及客服</strong> 打造的实时生产力工具。
            </p>
          </div>

          <div class="admin-studio-card__section">
            <span>核心价值</span>
            <p>
              实现了 <mark>管理</mark> 与 <mark>执行</mark> 的物理分离，确保直播高压环境下角色边界清晰。
            </p>
          </div>

          <RouterLink class="admin-studio-card__action" :to="{ name: 'studio-login', query: { next: '/studio-v2' } }">
            立即进入 Studio 工作台
            <AppIcon name="chevron-right" :size="18" />
          </RouterLink>

          <footer class="admin-studio-card__footer">
            <div>
              <strong>Live Agent</strong>
              <span>Intelligence Hub</span>
            </div>
            <span class="admin-studio-card__footer-icon">
              <AppIcon name="cpu" :size="24" />
            </span>
          </footer>
        </div>
      </aside>
    </div>
  </section>
</template>

<script setup>
import { RouterLink } from 'vue-router'

import AppIcon from '@/components/AppIcon.vue'

const overviewCards = [
  {
    label: '系统定位',
    title: '后台管理系统',
    desc: '负责索引、检索、观测及配置',
    icon: 'activity',
    tone: 'indigo'
  },
  {
    label: '适用角色',
    title: 'Admin',
    chips: ['RAG-Full', 'Ops-Full'],
    icon: 'shield-check',
    tone: 'emerald'
  },
  {
    label: 'Studio 快捷入口',
    title: '/studio-login',
    desc: '点击复制链接并访问 →',
    icon: 'external-link',
    tone: 'orange',
    to: { name: 'studio-login', query: { next: '/studio-v2' } }
  }
]

const modules = [
  {
    title: '离线索引管理',
    desc: '触发全量或增量索引，监控任务队列与索引健康度。',
    tag: 'RAG',
    icon: 'database',
    tone: 'blue',
    to: '/rag/offline'
  },
  {
    title: '在线检索调试',
    desc: '深度分析查询重写、向量相似度及重排序全过程。',
    tag: 'Debug',
    icon: 'search',
    tone: 'purple',
    to: '/rag/online'
  },
  {
    title: 'Agent Flow',
    desc: '全链路追踪 Router 及 Analyst 决策路径，定位瓶颈。',
    tag: 'Trace',
    icon: 'workflow',
    tone: 'indigo',
    to: '/agent-flow'
  },
  {
    title: '复盘报告',
    desc: '基于 AI 的直播洞察，提供自动化的问题修复建议。',
    tag: 'Analysis',
    icon: 'bar-chart-3',
    tone: 'emerald',
    to: '/reports'
  },
  {
    title: '系统设置',
    desc: 'Agent 行为偏好调整、安全网关及降级策略配置。',
    tag: 'Core',
    icon: 'settings',
    tone: 'amber',
    to: '/system'
  }
]
</script>
