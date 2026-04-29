import { http } from '@/api/http'

export async function fetchAgentPreferences() {
  const response = await http.get('/settings/agent-preferences')
  return response.data.data
}

export async function updateAgentPreferences(payload) {
  const response = await http.put('/settings/agent-preferences', payload)
  return response.data.data
}
