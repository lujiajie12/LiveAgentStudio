import { http } from '@/api/http'
import { consumeSSEStream } from '@/utils/sse'

export async function listMessages(sessionId) {
  const response = await http.get(`/sessions/${sessionId}/messages`)
  return response.data.data
}

export async function streamChat({ token, payload, onEvent }) {
  return consumeSSEStream({
    url: '/api/v1/chat/stream',
    token,
    body: payload,
    onEvent
  })
}
