import axios from 'axios'

// 生产环境挂载在 /web 下，API 路径为 /web/api
// 开发环境通过 vite proxy 转发 /web/api → localhost:8080/web/api
const http = axios.create({ baseURL: '/web/api', timeout: 15000 })

// ── 统计 ──────────────────────────────────────────────
export const getStats = () => http.get('/stats')

// ── 记忆 ──────────────────────────────────────────────
export const getMemories = (params: {
  page?: number
  page_size?: number
  user_id?: string
  keyword?: string
}) => http.get('/memories', { params })

export const deleteMemory = (id: number) => http.delete(`/memories/${id}`)

export const getMemoryUsers = () => http.get('/memories/users')

// ── 图谱 ──────────────────────────────────────────────
export const getEntities = (params: {
  page?: number
  page_size?: number
  user_id?: string
  keyword?: string
}) => http.get('/graph/entities', { params })

export const getRelations = (params: {
  page?: number
  page_size?: number
  user_id?: string
}) => http.get('/graph/relations', { params })

// ── 配置 ──────────────────────────────────────────────
export const listConfigs = () => http.get('/config')
export const getConfig = (name: string) => http.get(`/config/${name}`)
export const updateConfig = (name: string, content: string) =>
  http.put(`/config/${name}`, { content })

// ── 日志 ──────────────────────────────────────────────
export const getLogs = (name: string, params: { lines?: number; filter?: string }) =>
  http.get(`/logs/${name}`, { params })

// ── XN_Core ──────────────────────────────────────────
export const getXnCoreStatus = () => http.get('/xn_core/status')

export const getXnCoreReflections = (params: {
  page?: number
  page_size?: number
  user_id?: string
}) => http.get('/xn_core/reflections', { params })

export const getXnCoreHeartbeatLogs = (params: {
  page?: number
  page_size?: number
  user_id?: string
}) => http.get('/xn_core/heartbeat_logs', { params })

// ── 音乐 ──────────────────────────────────────────────
export const getMusicList = () => http.get('/music/list')
export const getMusicFileUrl = (filename: string) => `/web/api/music/file/${encodeURIComponent(filename)}`
