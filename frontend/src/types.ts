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
  is_enabled: boolean
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
  size_bytes?: number | null
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

export interface DeploymentInfo {
  deployment_method: string
  image_path: string
  service_runtime: { project_dir: string; env_file: { path: string; exists: boolean; readable: boolean; content: string }; compose_file: { path: string; exists: boolean; readable: boolean; content: string } }
  data_storage: {
    database_type: string
    database_file_dir: string | { path: string; exists: boolean; readable: boolean; writable: boolean; size_bytes: number | null }
    user_data_dir: { path: string; exists: boolean; readable: boolean; writable: boolean; size_bytes: number | null }
    backup_dir: { path: string; exists: boolean; readable: boolean; writable: boolean; size_bytes: number | null; backup_count: number; latest_backup_at: string | null }
    disk_free_bytes: number | null
  }
}

export interface ConfigMigrationPlan {
  env_path: string
  compose_path: string
  deployment_method: 'script' | 'compose' | 'source' | null
  changes: string[]
  compose_mount_ok: boolean
  compose_readable: boolean
  compose_validation?: string
  ready: boolean
  applied?: boolean
  backup_path?: string
  compose_backup_path?: string | null
  restart_required?: boolean
}

export interface UpdateHistoryRecord {
  id: string
  state: string
  target_version?: string
  current_version?: string
  message?: string
  started_at?: string
  updated_at?: string
  requested_at?: string
  registry?: string
  repository?: string
  image?: string
  deployment_method?: string
  backup_filename?: string
  duration_seconds?: number
  rollback?: boolean
  final_version?: string
  target_digest?: string | null
  latest_digest?: string | null
  app_updater_digest_match?: boolean
  stages?: { state: string; message: string; at: string }[]
}

export interface UpdateHealthInfo {
  registry: string
  repository: string
  status: 'ok' | 'warning'
  registry_status: 'ok' | 'warning'
  manifest_status: 'ok' | 'warning'
  updater_status: 'ok' | 'warning'
  config_status: 'ok' | 'warning'
  message: string
  versions: Record<string, 'ok' | 'warning'>
  registries: Record<string, { status: 'ok' | 'warning'; latency_ms: number; message: string }>
  checks: Array<{ key: string; label: string; status: 'ok' | 'warning'; message: string }>
}

export interface SystemUpdateStatus {
  id?: string
  state: 'idle' | 'queued' | 'pulling' | 'restarting' | 'verifying' | 'rolling_back' | 'success' | 'failed' | 'unknown'
  current_version?: string
  target_version?: string
  message?: string
  updated_at?: string
}
