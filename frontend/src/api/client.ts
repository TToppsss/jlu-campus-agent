import axios from 'axios'

const apiClient = axios.create()

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

export interface Source {
  title: string
  content: string
}

export interface AgentChatRequest {
  message: string
  conversation_id?: string | null
}

export interface AgentChatResponse {
  intent: string
  answer: string
  sources: Source[]
  conversation_id: string | null
  needs_edu_login?: boolean
}

export interface AuthRequest {
  username: string
  password: string
}

export interface AuthResponse {
  access_token: string
  token_type: string
  username: string
}

export interface Conversation {
  id: string
  title: string
  created_at: number
  updated_at: number
}

export interface ConversationMessage {
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
}

export interface ConversationDetail {
  summary: string
  messages: ConversationMessage[]
}

export async function checkHealth() {
  const { data } = await apiClient.get('/api/health')
  return data
}

export async function chatWithAgent(payload: AgentChatRequest) {
  const { data } = await apiClient.post<AgentChatResponse>('/api/agent/chat', payload)
  return data
}

export async function register(payload: AuthRequest) {
  const { data } = await apiClient.post<AuthResponse>('/api/auth/register', payload)
  return data
}

export async function login(payload: AuthRequest) {
  const { data } = await apiClient.post<AuthResponse>('/api/auth/login', payload)
  return data
}

export async function listConversations() {
  const { data } = await apiClient.get<Conversation[]>('/api/conversations')
  return data
}

export async function createConversation(title?: string) {
  const { data } = await apiClient.post<Conversation>('/api/conversations', { title })
  return data
}

export async function getConversationMessages(id: string) {
  const { data } = await apiClient.get<ConversationDetail>(`/api/conversations/${id}/messages`)
  return data
}

export async function renameConversation(id: string, title: string) {
  const { data } = await apiClient.patch(`/api/conversations/${id}`, { title })
  return data
}

export async function deleteConversation(id: string) {
  const { data } = await apiClient.delete(`/api/conversations/${id}`)
  return data
}

export interface EduStatus {
  logged_in: boolean
  userid?: string
  logged_in_at?: number
  last_refreshed_at?: number
}

export async function eduStatus() {
  const { data } = await apiClient.get<EduStatus>('/api/edu/status')
  return data
}

export async function eduLoginInit(payload: { username: string; password: string }) {
  const { data } = await apiClient.post<{ captcha_image: string }>('/api/edu/login_init', payload)
  return data
}

export async function eduLoginRefreshCaptcha() {
  const { data } = await apiClient.post<{ captcha_image: string }>('/api/edu/login_refresh_captcha')
  return data
}

export async function eduLoginSendWechat(payload: { captcha_text: string }) {
  const { data } = await apiClient.post<{ status: string }>('/api/edu/login_send_wechat', payload)
  return data
}

export async function eduLoginConfirm(payload: { wechat_code: string }) {
  const { data } = await apiClient.post('/api/edu/login_confirm', payload)
  return data as { logged_in: boolean; userid: string }
}

export async function eduLogout() {
  const { data } = await apiClient.post('/api/edu/logout')
  return data
}
