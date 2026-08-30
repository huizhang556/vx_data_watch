export type Role = 'admin' | 'editor' | 'viewer'

export interface User {
  id: number
  username: string
  role: Role
  level: number
  csrf_token?: string
  email?: string
  is_active?: boolean
  created_at?: string
  last_login_at?: string
  avatar?: string
}

export interface Account {
  id: number
  name: string
  description?: string
  created_at: string
}

export interface DailyMetric {
  date: string
  plays: number
  recommendations: number | null
  likes: number | null
  comments: number | null
  shares: number | null
  follows: number | null
  favorites: number | null
}

export interface VideoRow {
  id: number
  title: string
  published_at?: string
  plays: number
  share: number
  cumulative_share: number
  likes?: number
  comments?: number
  shares?: number
}

export interface DayAnalytics {
  date: string
  metric: DailyMetric | null
  videos: VideoRow[]
  reconciliation: null | {
    account_total: number
    video_total: number
    difference: number
    coverage: number | null
    status: string
  }
}

export interface RangeAnalytics {
  account_id: number
  start_date: string
  end_date: string
  days_with_data: number
  trend: DailyMetric[]
  totals: Record<string, number | null>
  averages: Record<string, number | null>
  previous_start_date: string
  previous_end_date: string
  previous_trend: DailyMetric[]
  previous_totals: Record<string, number | null>
}

export interface VideoRangeAnalytics {
  account_id: number
  start_date: string
  end_date: string
  days_with_data: number
  videos: VideoRow[]
  reconciliation: DayAnalytics['reconciliation']
}

export interface SystemVersion {
  version: string
  published_at?: string
  digest?: string
}

export interface SystemVersionInfo {
  current_version: string
  latest_version: string | null
  versions: SystemVersion[]
  repository: string
  registry: string
  configured_registry?: string
  registries: { registry: string; label: string; repository: string }[]
  update_supported: boolean
  deployment: 'docker' | 'source'
}

export interface SystemUpdateStatus {
  id?: string
  state: 'idle' | 'queued' | 'pulling' | 'restarting' | 'verifying' | 'rolling_back' | 'success' | 'failed' | 'unknown'
  current_version?: string
  target_version?: string
  message?: string
  updated_at?: string
}
