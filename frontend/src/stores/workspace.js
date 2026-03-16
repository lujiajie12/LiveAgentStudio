import { defineStore } from 'pinia'

import { listMessages, streamChat } from '@/api/chat'
import { readToken } from '@/utils/auth'

function createDefaultSession() {
  return {
    id: `session-${Date.now()}`,
    title: '当前直播会话',
    current_product_id: 'SKU-001',
    live_stage: 'intro'
  }
}

export const useWorkspaceStore = defineStore('workspace', {
  state: () => ({
    sessions: [createDefaultSession()],
    activeSessionId: '',
    messagesBySession: {},
    streamBuffer: '',
    isStreaming: false,
    error: '',
    liveContext: {
      current_product_id: 'SKU-001',
      live_stage: 'intro'
    }
  }),
  getters: {
    activeSession(state) {
      return (
        state.sessions.find((session) => session.id === state.activeSessionId) ||
        state.sessions[0] ||
        null
      )
    },
    activeMessages(state) {
      return state.messagesBySession[state.activeSessionId] || []
    }
  },
  actions: {
    bootstrap() {
      if (!this.activeSessionId && this.sessions.length) {
        this.activeSessionId = this.sessions[0].id
      }
    },
    async loadMessages(sessionId) {
      this.activeSessionId = sessionId
      try {
        const items = await listMessages(sessionId)
        this.messagesBySession[sessionId] = items
      } catch {
        this.messagesBySession[sessionId] = this.messagesBySession[sessionId] || []
      }
    },
    async sendMessage(userInput) {
      const session = this.activeSession
      if (!session) {
        return
      }

      const sessionId = session.id
      const existing = this.messagesBySession[sessionId] || []
      this.messagesBySession[sessionId] = [
        ...existing,
        {
          id: `local-${Date.now()}`,
          role: 'user',
          content: userInput,
          created_at: new Date().toISOString()
        }
      ]
      this.streamBuffer = ''
      this.error = ''
      this.isStreaming = true

      try {
        await streamChat({
          token: readToken(),
          payload: {
            session_id: sessionId,
            user_input: userInput,
            current_product_id: this.liveContext.current_product_id,
            live_stage: this.liveContext.live_stage
          },
          onEvent: (event) => {
            if (event.event === 'token') {
              this.streamBuffer += event.data.content
            }
            if (event.event === 'final') {
              this.messagesBySession[sessionId] = [
                ...(this.messagesBySession[sessionId] || []),
                event.data.message
              ]
              this.streamBuffer = ''
            }
            if (event.event === 'error') {
              this.error = event.data.message
            }
          }
        })
      } catch (error) {
        this.error = error.message
      } finally {
        this.isStreaming = false
      }
    }
  }
})
