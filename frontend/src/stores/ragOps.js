import { defineStore } from 'pinia'

import {
  createRagOfflineJob,
  debugRagOnline,
  fetchRagOfflineJob,
  fetchRagOfflineOverview
} from '@/api/rag'

export const useRagOpsStore = defineStore('ragOps', {
  state: () => ({
    offlineOverview: null,
    activeJob: null,
    onlineDebugResult: null,
    loading: false,
    error: ''
  }),
  actions: {
    async loadOfflineOverview() {
      this.loading = true
      this.error = ''
      try {
        this.offlineOverview = await fetchRagOfflineOverview()
      } catch (error) {
        this.error = error.response?.data?.message || error.message
      } finally {
        this.loading = false
      }
    },
    async startOfflineJob(payload) {
      this.loading = true
      this.error = ''
      try {
        this.activeJob = await createRagOfflineJob(payload)
        await this.loadOfflineOverview()
      } catch (error) {
        this.error = error.response?.data?.message || error.message
        throw error
      } finally {
        this.loading = false
      }
    },
    async refreshOfflineJob(jobId) {
      this.loading = true
      this.error = ''
      try {
        this.activeJob = await fetchRagOfflineJob(jobId)
      } catch (error) {
        this.error = error.response?.data?.message || error.message
      } finally {
        this.loading = false
      }
    },
    async runOnlineDebug(payload) {
      this.loading = true
      this.error = ''
      try {
        this.onlineDebugResult = await debugRagOnline(payload)
      } catch (error) {
        this.error = error.response?.data?.message || error.message
        throw error
      } finally {
        this.loading = false
      }
    }
  }
})
