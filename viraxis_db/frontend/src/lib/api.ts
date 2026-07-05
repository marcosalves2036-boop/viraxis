const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

function getToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('viraxis_token')
}

export function setToken(t: string) { localStorage.setItem('viraxis_token', t) }
export function clearToken()        { localStorage.removeItem('viraxis_token') }
export function isLoggedIn(): boolean { return !!getToken() }

async function req<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  })

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? 'Erro desconhecido')
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export interface TokenResponse { access_token: string; token_type: string }
export interface UserResponse  { id: string; email: string; full_name: string; plan: string }

export interface MessageResponse { message: string }

export const auth = {
  login: (email: string, password: string) =>
    req<TokenResponse>('POST', '/auth/login', { email, password }),
  register: (email: string, password: string, full_name: string) =>
    req<MessageResponse>('POST', '/auth/register', { email, password, full_name }),
  verifyEmail: (token: string) =>
    req<MessageResponse>('POST', '/auth/verify-email', { token }),
  resendVerification: (email: string) =>
    req<MessageResponse>('POST', '/auth/resend-verification', { email }),
  forgotPassword: (email: string) =>
    req<MessageResponse>('POST', '/auth/forgot-password', { email }),
  resetPassword: (token: string, new_password: string) =>
    req<MessageResponse>('POST', '/auth/reset-password', { token, new_password }),
  me: () => req<UserResponse>('GET', '/users/me'),
  // Compat helpers usados por layout/conteudo/login pages
  getToken: () => getToken(),
  clear: () => clearToken(),
  save: (t: TokenResponse) => setToken(t.access_token),
}

// ── Offices ───────────────────────────────────────────────────────────────────

export interface NicheProfile {
  niche_name: string
  content_style: Record<string, string>
  target_audience?: string
  brain_params?: Record<string, unknown>
}
export interface OfficeResponse {
  id: string
  name: string
  status: string
  niche_profile?: NicheProfile
  created_at: string
}
export interface CreateOfficeBody {
  name: string
  niche: string
  platforms?: string[]
  target_audience?: string
  content_style?: string
}

export const offices = {
  list: () => req<OfficeResponse[]>('GET', '/offices'),
  get:  (id: string) => req<OfficeResponse>('GET', `/offices/${id}`),
  create: (body: CreateOfficeBody) => req<OfficeResponse>('POST', '/offices', body),
  runBrain: (id: string, temperature?: number) =>
    req<BrainRunResponse>('POST', `/offices/${id}/brain/run`, temperature ? { temperature } : {}),
  analyzeUrl: (id: string, url: string) =>
    req<TrendResponse>('POST', `/offices/${id}/trends/analyze`, { url }),
  listDecisions: (id: string) =>
    req<DecisionResponse[]>('GET', `/offices/${id}/decisions`),
  getDecision: (officeId: string, decisionId: string) =>
    req<DecisionResponse>('GET', `/offices/${officeId}/decisions/${decisionId}`),
  approveDecision: (officeId: string, decisionId: string) =>
    req<DecisionResponse>('PATCH', `/offices/${officeId}/decisions/${decisionId}/status`, { status: 'approved' }),
  renderDecision: (officeId: string, decisionId: string) =>
    req<RenderResponse>('POST', `/offices/${officeId}/decisions/${decisionId}/render`),
}

// ── Decisions / Content ───────────────────────────────────────────────────────

export interface BrainRunResponse {
  decision_id: string
  decision_type: string
  selected_topic: string
  selected_platform: string
  confidence_score: number
  hypothesis: string
}

export interface TrendResponse {
  snapshot_id: string
  platform: string
  title: string
  view_count: number
  archetype?: string
}

export interface DecisionResponse {
  id: string
  office_id: string
  status: string
  decision_type: string
  selected_topic: string
  selected_archetype: string
  selected_platform: string
  hypothesis: string
  confidence_score: number
  created_at: string
}

export interface ScriptSection {
  section: 'hook' | 'development' | 'climax' | 'cta'
  content: string
  duration_estimate_seconds: number
  visual_notes?: string
}

export interface ContentItemResponse {
  id: string
  office_id: string
  decision_id?: string
  title: string
  script: string
  status: string
  platform?: string
  duration_seconds?: number
  renderer_output?: {
    sections: ScriptSection[]
    total_duration_estimate_seconds: number
    archetype_applied: string
    platform_adaptations: string
    confidence_score: number
  }
  created_at: string
}

export interface RenderResponse {
  content_item_id: string
  title: string
  status: string
  duration_seconds?: number
}

export interface ProcessVideoResponse {
  video_url: string
  storage_path: string
  status: string
  mode: string
}

export const content = {
  get: (id: string) => req<ContentItemResponse>('GET', `/content-items/${id}`),
  list: (officeId: string) =>
    req<ContentItemResponse[]>('GET', `/content-items?office_id=${officeId}`),
  processVideo: (officeId: string, itemId: string) =>
    req<ProcessVideoResponse>('POST', `/offices/${officeId}/content-items/${itemId}/process-video`),
}

// ── Raw Videos ────────────────────────────────────────────────────────────────

export interface RawVideoResponse {
  id: string
  office_id: string
  original_filename: string
  title?: string
  description?: string
  tags?: string[]
  status: string
  r2_url?: string
  duration_seconds?: number
  created_at: string
}

export const rawVideos = {
  list:   (officeId: string) =>
    req<RawVideoResponse[]>('GET', `/raw-videos?office_id=${officeId}`),
  get:    (id: string) => req<RawVideoResponse>('GET', `/raw-videos/${id}`),
  update: (id: string, body: Partial<Pick<RawVideoResponse,'title'|'description'|'tags'>>) =>
    req<RawVideoResponse>('PATCH', `/raw-videos/${id}`, body),
  delete: (id: string) => req<void>('DELETE', `/raw-videos/${id}`),
}

// api = alias de auth (compatibilidade com login/cadastro/verify-email pages)
export const api = auth
