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

export function slideImageUrl(videoId: string, slideId: number) {
  const token = localStorage.getItem('videomind_token') || ''
  return `${API_URL}/api/videos/${videoId}/slides/${slideId}/image?token=${encodeURIComponent(token)}`
}

export function slideThumbnailUrl(videoId: string, slideId: number) {
  const token = localStorage.getItem('videomind_token') || ''
  return `${API_URL}/api/videos/${videoId}/slides/${slideId}/thumbnail?token=${encodeURIComponent(token)}`
}

export function slidePdfUrl(videoId: string) {
  const token = localStorage.getItem('videomind_token') || ''
  return `${API_URL}/api/videos/${videoId}/slides/export.pdf?token=${encodeURIComponent(token)}`
}

export function slideZipUrl(videoId: string) {
  const token = localStorage.getItem('videomind_token') || ''
  return `${API_URL}/api/videos/${videoId}/slides/export.zip?token=${encodeURIComponent(token)}`
}

export async function downloadSlidePdf(videoId: string, title = 'slides') {
  const response = await api.get(`/videos/${videoId}/slides/export.pdf`, {
    responseType: 'blob',
  })
  const url = URL.createObjectURL(response.data)
  const a = document.createElement('a')
  a.href = url
  const cleanTitle = title.replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 40) || 'slides'
  a.download = `${cleanTitle}-slides.pdf`
  a.click()
  URL.revokeObjectURL(url)
}

export async function downloadSlideZip(videoId: string, title = 'slides') {
  const response = await api.get(`/videos/${videoId}/slides/export.zip`, {
    responseType: 'blob',
  })
  const url = URL.createObjectURL(response.data)
  const a = document.createElement('a')
  a.href = url
  const cleanTitle = title.replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 40) || 'slides'
  a.download = `${cleanTitle}-slides.zip`
  a.click()
  URL.revokeObjectURL(url)
}

