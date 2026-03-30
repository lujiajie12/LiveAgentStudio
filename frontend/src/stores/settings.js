import { defineStore } from 'pinia'

import { fetchAgentPreferences, updateAgentPreferences } from '@/api/settings'
import { fetchSystemHealth, fetchSystemMetrics } from '@/api/system'

export const useSettingsStore = defineStore('settings', {
  state: () => ({
    health: null,
    metrics: null,
    preferences: {
      script_style: '',
      custom_sensitive_terms: []
    },
    loading: false,
    error: ''
  }),
  actions: {
    async loadDashboard() {
      this.loading = true
      this.error = ''
      try {
        const [health, metrics, preferences] = await Promise.all([
          fetchSystemHealth(),
          fetchSystemMetrics(),
          fetchAgentPreferences()
        ])
        this.health = health
        this.metrics = metrics
        this.preferences = {
          script_style: preferences.script_style || '',
          custom_sensitive_terms: preferences.custom_sensitive_terms || []
        }
      } catch (error) {
        this.error = error.response?.data?.message || error.message
      } finally {
        this.loading = false
      }
    },
    async savePreferences() {
      this.loading = true
      this.error = ''
      try {
        const record = await updateAgentPreferences({
          script_style: this.preferences.script_style || null,
          custom_sensitive_terms: this.preferences.custom_sensitive_terms
        })
        this.preferences = {
          script_style: record.script_style || '',
          custom_sensitive_terms: record.custom_sensitive_terms || []
        }
      } catch (error) {
        this.error = error.response?.data?.message || error.message
        throw error
      } finally {
        this.loading = false
      }
    }
  }
})
