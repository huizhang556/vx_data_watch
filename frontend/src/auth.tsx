/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Alert, Button, Form, Input, Spin, Typography, message } from 'antd'
import { LockKeyhole, UserRound } from 'lucide-react'
import { api, setCsrfToken } from './api'
import type { User } from './types'

interface AuthContextValue {
  user: User
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('AuthContext is missing')
  return context
}

export function AuthGate({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true)
  const [initialized, setInitialized] = useState(false)
  const [user, setUser] = useState<User | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    void (async () => {
      try {
        const status = await api<{ initialized: boolean }>('/api/setup/status')
        setInitialized(status.initialized)
        if (status.initialized) {
          try {
            const me = await api<User>('/api/auth/me')
            setCsrfToken(me.csrf_token)
            setUser(me)
          } catch {
            setUser(null)
          }
        }
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : '无法连接后端')
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  const submit = async (values: { username: string; password: string }) => {
    setError('')
    try {
      const next = await api<User>(initialized ? '/api/auth/login' : '/api/setup', {
        method: 'POST', body: JSON.stringify(values),
      })
      // Confirm the browser accepted the session cookie before entering the app.
      const verified = await api<User>('/api/auth/me')
      setCsrfToken(verified.csrf_token || next.csrf_token)
      setUser(verified)
      setInitialized(true)
      message.success(initialized ? '已登录' : '管理员已创建')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '操作失败')
    }
  }

  const logout = async () => {
    let failed = false
    try {
      await api('/api/auth/logout', { method: 'POST' })
    } catch {
      failed = true
    } finally {
      setCsrfToken()
      setUser(null)
      localStorage.removeItem('vx_account_id')
    }
    if (failed) message.warning('页面已退出；服务端会话清理失败，请稍后重试')
    else message.success('已退出登录')
  }

  const value = useMemo(() => user ? { user, logout } : null, [user])
  if (loading) return <div className="center-screen"><Spin size="large" /></div>
  if (!user) {
    return (
      <main className="auth-page">
        <section className="auth-panel">
          <div className="brand-mark">VX</div>
          <Typography.Title level={2}>视频号数据分析</Typography.Title>
          <Typography.Paragraph type="secondary">
            {initialized ? '使用本地账号进入数据工作台' : '创建首个本地管理员账号'}
          </Typography.Paragraph>
          {error && <Alert type="error" showIcon message={error} />}
          <Form layout="vertical" onFinish={submit} requiredMark={false}>
            <Form.Item name="username" label="用户名" rules={[{ required: true }, { min: 3 }]}>
              <Input prefix={<UserRound size={17} />} autoComplete="username" />
            </Form.Item>
            <Form.Item name="password" label="密码" rules={[{ required: true }, { min: initialized ? 1 : 10 }]}>
              <Input.Password prefix={<LockKeyhole size={17} />} autoComplete={initialized ? 'current-password' : 'new-password'} />
            </Form.Item>
            <Button block type="primary" htmlType="submit" size="large">
              {initialized ? '登录' : '初始化系统'}
            </Button>
          </Form>
        </section>
      </main>
    )
  }
  return <AuthContext.Provider value={value!}>{children}</AuthContext.Provider>
}
