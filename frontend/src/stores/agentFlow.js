import { defineStore } from 'pinia'

import { streamChat } from '@/api/chat'
import { fetchTrace, listTraces } from '@/api/ops'
import { readToken } from '@/utils/auth'

function buildDefaultPayload() {
  return {
    session_id: `agent-flow-${Date.now()}`,
    user_input: '帮我生成一段促单话术，强调库存紧张和当前优惠节奏。',
    current_product_id: '',
    live_stage: 'closing',
    hot_keywords: ['库存', '优惠', '限时'],
    live_offer_snapshot: {
      display_stock: 92,
      display_unit: '套',
      current_price: 89,
      original_price: 149,
      countdown_seconds: 180,
      coupon_summary: '下单立减20元',
      gift_summary: '赠清洁布1份',
      stock_label: '库存紧张'
    }
  }
}

export const useAgentFlowStore = defineStore('agentFlow', {
  state: () => ({
    traces: [],
    activeTrace: null,
    debugPayload: buildDefaultPayload(),
    debugStream: '',
    debugMeta: null,
    loading: false,
    error: ''
  }),
  actions: {
    async loadTraces(limit = 20) {
      this.loading = true
      this.error = ''
      try {
        this.traces = await listTraces(limit)
      } catch (error) {
        this.error = error.response?.data?.message || error.message
      } finally {
        this.loading = false
      }
    },
    async loadTraceDetail(traceId) {
      this.loading = true
      this.error = ''
      try {
        this.activeTrace = await fetchTrace(traceId)
      } catch (error) {
        this.error = error.response?.data?.message || error.message
      } finally {
        this.loading = false
      }
    },
    async runDebugChat() {
      this.loading = true
      this.error = ''
      this.debugStream = ''
      this.debugMeta = null
      try {
        await streamChat({
          token: readToken(),
          payload: this.debugPayload,
          onEvent: async (event) => {
            if (event.event === 'meta') {
              this.debugMeta = event.data
              if (event.data.trace_id) {
                await this.loadTraceDetail(event.data.trace_id)
              }
            }
            if (event.event === 'token') {
              this.debugStream += event.data.content
            }
            if (event.event === 'final') {
              this.debugStream = event.data.message?.content || this.debugStream
              if (this.debugMeta?.trace_id) {
                await this.loadTraceDetail(this.debugMeta.trace_id)
                await this.loadTraces()
              }
            }
            if (event.event === 'error') {
              this.error = event.data.message
            }
          }
        })
      } catch (error) {
        this.error = error.message
      } finally {
        this.loading = false
      }
    }
  }
})
