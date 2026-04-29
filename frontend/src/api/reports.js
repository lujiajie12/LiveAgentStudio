import { http } from '@/api/http'

export async function listReports() {
  const response = await http.get('/reports')
  return response.data.data
}

export async function fetchReport(reportId) {
  const response = await http.get(`/reports/${reportId}`)
  return response.data.data
}
