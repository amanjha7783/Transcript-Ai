import axios from 'axios'

export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
export const api = axios.create({ baseURL: `${API_URL}/api` })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('videomind_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

export function mediaUrl(videoId: string) {
  const token = localStorage.getItem('videomind_token') || ''
  return `${API_URL}/api/videos/${videoId}/media?token=${encodeURIComponent(token)}`
}

export async function downloadExport(videoId: string, kind: string, fmt: string, language = 'original') {
  const response = await api.get(`/videos/${videoId}/export`, {
    params: { kind, fmt, language },
    responseType: 'blob',
  })
  const url = URL.createObjectURL(response.data)
  const a = document.createElement('a')
  a.href = url
  a.download = `videomind-${kind}-${videoId}.${fmt}`
  a.click()
  URL.revokeObjectURL(url)
}
