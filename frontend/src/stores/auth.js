import { defineStore } from 'pinia'

import { fetchCurrentUser, login } from '@/api/auth'
import { clearToken, clearUser, readToken, readUser, writeToken, writeUser } from '@/utils/auth'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: readToken(),
    user: readUser(),
    loading: false,
    error: ''
  }),
  getters: {
    isAuthenticated: (state) => Boolean(state.token)
  },
  actions: {
    async loginWithCredentials(payload) {
      this.loading = true
      this.error = ''
      try {
        const tokenResponse = await login(payload)
        writeToken(tokenResponse.access_token)
        this.token = tokenResponse.access_token
        const user = await fetchCurrentUser()
        writeUser(user)
        this.user = user
      } catch (error) {
        this.error = error.response?.data?.message || error.message
        throw error
      } finally {
        this.loading = false
      }
    },
    logout() {
      clearToken()
      clearUser()
      this.token = ''
      this.user = null
    }
  }
})
