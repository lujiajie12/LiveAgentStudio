import { defineStore } from 'pinia'

import { login, logout } from '@/api/auth'
import { fetchStudioCurrentUser } from '@/api/studio'
import {
  clearStudioToken,
  clearStudioUser,
  readStudioToken,
  readStudioUser,
  writeStudioToken,
  writeStudioUser
} from '@/utils/studioAuth'

export const useStudioAuthStore = defineStore('studioAuth', {
  state: () => ({
    token: readStudioToken(),
    user: readStudioUser(),
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
        writeStudioToken(tokenResponse.access_token)
        this.token = tokenResponse.access_token
        const user = await fetchStudioCurrentUser()
        writeStudioUser(user)
        this.user = user
      } catch (error) {
        this.error = error.response?.data?.message || error.message
        throw error
      } finally {
        this.loading = false
      }
    },
    async logout() {
      try {
        await logout()
      } catch (_) {
        // 即使后端调用失败也清除本地状态
      }
      clearStudioToken()
      clearStudioUser()
      this.token = ''
      this.user = null
    }
  }
})
