import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react'
import { Button, Layout, Menu, Select, Spin, Typography } from 'antd'
import { BarChart3, Bot, DatabaseBackup, FileUp, LogOut, PanelLeftClose, PanelLeftOpen, RefreshCw, Settings, Video } from 'lucide-react'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { api } from './api'
import { AccountContext } from './account'
import { useAuth } from './auth'
import type { Account } from './types'

const AIPage = lazy(() => import('./pages/AIPage'))
const BackupPage = lazy(() => import('./pages/BackupPage'))
const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const ImportsPage = lazy(() => import('./pages/ImportsPage'))
const SettingsPage = lazy(() => import('./pages/SettingsPage'))
const UpdatesPage = lazy(() => import('./pages/UpdatesPage'))
const VideosPage = lazy(() => import('./pages/VideosPage'))

const items = [
  { key: '/dashboard', icon: <BarChart3 size={19} />, label: '数据概览' },
  { key: '/videos', icon: <Video size={19} />, label: '视频贡献' },
  { key: '/imports', icon: <FileUp size={19} />, label: '数据导入' },
  { key: '/ai', icon: <Bot size={19} />, label: 'AI 建议' },
  { key: '/backups', icon: <DatabaseBackup size={19} />, label: '加密备份' },
  { key: '/settings', icon: <Settings size={19} />, label: '系统设置' },
  { key: '/updates', icon: <RefreshCw size={19} />, label: '在线更新' },
]

export default function App() {
  const { user, logout } = useAuth()
  const [accounts, setAccounts] = useState<Account[]>([])
  const [accountId, setAccountIdState] = useState<number>(() => Number(localStorage.getItem('vx_account_id')) || 0)
  const [siderCollapsed, setSiderCollapsed] = useState(() => localStorage.getItem('vx_sider_collapsed') === 'true')
  const location = useLocation()
  const navigate = useNavigate()

  const reloadAccounts = useCallback(async () => {
    const rows = await api<Account[]>('/api/accounts')
    setAccounts(rows)
    setAccountIdState((current) => {
      const next = rows.some((row) => row.id === current) ? current : (rows[0]?.id || 0)
      if (next) localStorage.setItem('vx_account_id', String(next))
      return next
    })
  }, [])
  useEffect(() => { void reloadAccounts() }, [reloadAccounts])

  const setAccountId = (id: number) => {
    setAccountIdState(id)
    localStorage.setItem('vx_account_id', String(id))
  }
  const account = accounts.find((row) => row.id === accountId) || null
  const context = useMemo(() => ({ accounts, account, setAccountId, reloadAccounts }), [accounts, account, reloadAccounts])

  return (
    <AccountContext.Provider value={context}>
      <Layout className={`app-shell ${siderCollapsed ? 'sider-collapsed' : ''}`}>
        <Layout.Sider className="desktop-sider" width={224} collapsedWidth={72} collapsed={siderCollapsed} theme="light">
          <div className="brand"><span className="brand-mark small">VX</span>{!siderCollapsed && <span>视频号数据</span>}</div>
          <Button className="sider-toggle" type="text" icon={siderCollapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />} title={siderCollapsed ? '展开侧边栏' : '收起侧边栏'} aria-label={siderCollapsed ? '展开侧边栏' : '收起侧边栏'} onClick={() => setSiderCollapsed((value) => { localStorage.setItem('vx_sider_collapsed', String(!value)); return !value })} />
          <Menu selectedKeys={[location.pathname]} items={items} onClick={({ key }) => navigate(key)} />
          <div className="sider-user">
            {!siderCollapsed && <div><Typography.Text strong>{user.username}</Typography.Text><br /><Typography.Text type="secondary">{user.role}</Typography.Text></div>}
            <Button type="text" icon={<LogOut size={18} />} title="退出登录" aria-label="退出登录" onClick={() => void logout()} />
          </div>
        </Layout.Sider>
        <Layout>
          <header className="topbar">
            <div className="mobile-brand"><span className="brand-mark small">VX</span><strong>视频号数据</strong></div>
            <Select
              aria-label="当前视频号"
              className="account-select"
              placeholder="请先创建视频号"
              value={accountId || undefined}
              onChange={setAccountId}
              options={accounts.map((row) => ({ value: row.id, label: row.name }))}
            />
            <Button className="mobile-logout" type="text" icon={<LogOut size={18} />} title="退出登录" aria-label="退出登录" onClick={() => void logout()} />
          </header>
          <Layout.Content className="content">
            <Suspense fallback={<div className="page-loading"><Spin size="large" /></div>}>
              <Routes>
                <Route path="/dashboard" element={<DashboardPage />} />
                <Route path="/videos" element={<VideosPage />} />
                <Route path="/imports" element={<ImportsPage />} />
                <Route path="/ai" element={<AIPage />} />
                <Route path="/backups" element={<BackupPage />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="/updates" element={<UpdatesPage />} />
                <Route path="*" element={<Navigate to="/dashboard" replace />} />
              </Routes>
            </Suspense>
          </Layout.Content>
          <nav className="mobile-nav" aria-label="主导航">
            {items.map((item) => (
              <button key={item.key} className={location.pathname === item.key ? 'active' : ''} onClick={() => navigate(item.key)}>
                {item.icon}<span>{item.label.replace('数据', '')}</span>
              </button>
            ))}
          </nav>
        </Layout>
      </Layout>
    </AccountContext.Provider>
  )
}
