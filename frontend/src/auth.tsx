/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Alert, Button, Form, Input, Spin, Tabs, Typography, message } from 'antd'
import { LockKeyhole, Mail, UserRound } from 'lucide-react'
import { api, setCsrfToken } from './api'
import type { User } from './types'

interface AuthContextValue { user: User; logout: () => Promise<void> }
const AuthContext = createContext<AuthContextValue | null>(null)
export function useAuth() { const value = useContext(AuthContext); if (!value) throw new Error('AuthContext is missing'); return value }

declare global { interface Window { turnstile?: { render: (el: HTMLElement, opts: Record<string, unknown>) => void } } }
function Captcha({ enabled, siteKey, onChange }: { enabled: boolean; siteKey?: string; onChange: (value?: string) => void }) {
  const [element, setElement] = useState<HTMLDivElement | null>(null)
  useEffect(() => {
    if (!enabled || !siteKey || !element) return
    let timer: number | undefined
    const render = () => {
      if (window.turnstile) window.turnstile.render(element, { sitekey: siteKey, callback: onChange, 'expired-callback': () => onChange(undefined), 'error-callback': () => onChange(undefined) })
      else timer = window.setTimeout(render, 250)
    }
    render()
    return () => { if (timer) window.clearTimeout(timer) }
  }, [enabled, siteKey, element, onChange])
  return enabled ? <div ref={setElement} className="captcha-widget" /> : null
}

export function AuthGate({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true); const [initialized, setInitialized] = useState(false); const [user, setUser] = useState<User | null>(null); const [error, setError] = useState('')
  const [config, setConfig] = useState({ registration_enabled: false, captcha_enabled: false, captcha_site_key: '' }); const [mode, setMode] = useState<'login' | 'register' | 'reset'>('login'); const [captcha, setCaptcha] = useState<string>(); const [email, setEmail] = useState(''); const [busy, setBusy] = useState(false)
  useEffect(() => { void (async () => { try { const [status, authConfig] = await Promise.all([api<{ initialized: boolean }>('/api/setup/status'), api<typeof config>('/api/auth/config')]); setInitialized(status.initialized); setConfig(authConfig); if (status.initialized) { try { const me = await api<User>('/api/auth/me'); setCsrfToken(me.csrf_token); setUser(me) } catch { setUser(null) } } } catch (cause) { setError(cause instanceof Error ? cause.message : '无法连接后端') } finally { setLoading(false) } })() }, [])
  useEffect(() => { const onUnauthorized = () => { setCsrfToken(); setUser(null); localStorage.removeItem('vx_account_id') }; window.addEventListener('vx:unauthorized', onUnauthorized); return () => window.removeEventListener('vx:unauthorized', onUnauthorized) }, [])
  const finishLogin = (next: User) => { setCsrfToken(next.csrf_token); setUser(next); setInitialized(true); message.success('登录成功') }
  const submit = async (values: { username?: string; password: string; email?: string; code?: string }) => { setBusy(true); setError(''); try { if (mode === 'login') finishLogin(await api<User>(initialized ? '/api/auth/login' : '/api/setup', { method: 'POST', body: JSON.stringify({ ...values, captcha_token: captcha }) })); else if (mode === 'register') finishLogin(await api<User>('/api/auth/register', { method: 'POST', body: JSON.stringify({ ...values, captcha_token: captcha }) })); else finishLogin(await api<User>('/api/auth/password-reset', { method: 'POST', body: JSON.stringify({ email: values.email, code: values.code, new_password: values.password, captcha_token: captcha }) })) } catch (cause) { setError(cause instanceof Error ? cause.message : '操作失败') } finally { setBusy(false) } }
  const sendCode = async (email: string) => { setBusy(true); try { await api(mode === 'register' ? '/api/auth/register/request-code' : '/api/auth/password-reset/request-code', { method: 'POST', body: JSON.stringify({ email, captcha_token: captcha }) }); message.success('验证码已发送，请检查邮箱') } catch (cause) { message.error(cause instanceof Error ? cause.message : '发送失败') } finally { setBusy(false) } }
  const logout = async () => { try { await api('/api/auth/logout', { method: 'POST' }) } catch { /* clear local state even if server is unavailable */ } finally { setCsrfToken(); setUser(null); localStorage.removeItem('vx_account_id'); window.history.replaceState({}, '', '/') } }
  const value = useMemo(() => user ? { user, logout } : null, [user])
  if (loading) return <div className="center-screen"><Spin size="large" /></div>
  if (!user) return <main className="auth-page"><section className="auth-panel"><div className="brand-mark">VX</div><Typography.Title level={2}>视频号数据分析</Typography.Title><Typography.Paragraph type="secondary">{initialized ? '使用账号进入数据工作台' : '创建首个本地管理员账号'}</Typography.Paragraph>{error && <Alert type="error" showIcon message={error} />}{initialized && <Tabs activeKey={mode} onChange={(key) => { setMode(key as typeof mode); setError(''); setCaptcha(undefined) }} items={[{ key: 'login', label: '登录' }, ...(config.registration_enabled ? [{ key: 'register', label: '注册' }] : []), { key: 'reset', label: '重置密码' }]} />}
    <Form layout="vertical" onFinish={submit} requiredMark={false} key={mode}>{mode !== 'reset' && <Form.Item name="username" label="用户名" rules={[{ required: true }, { min: 3 }]}><Input prefix={<UserRound size={17} />} autoComplete="username" /> </Form.Item>}{(mode === 'register' || mode === 'reset') && <Form.Item name="email" label="注册邮箱" rules={[{ required: true }, { type: 'email' }]}><Input prefix={<Mail size={17} />} autoComplete="email" onChange={(event) => setEmail(event.target.value)} /></Form.Item>}{mode !== 'login' && <Form.Item name="code" label="邮箱验证码" rules={[{ required: true }, { len: 6 }]}><Input.Search enterButton="发送验证码" onSearch={() => { void sendCode(email) }} /></Form.Item>}<Form.Item name="password" label={mode === 'login' ? '密码' : '新密码'} rules={[{ required: true }, { min: initialized ? 1 : 10 }]}><Input.Password prefix={<LockKeyhole size={17} />} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} /></Form.Item><Captcha enabled={config.captcha_enabled} siteKey={config.captcha_site_key} onChange={setCaptcha} /><Button block type="primary" htmlType="submit" size="large" loading={busy}>{mode === 'login' ? (initialized ? '登录' : '初始化系统') : mode === 'register' ? '注册并登录' : '重置密码并登录'}</Button></Form>
  </section></main>
  return <AuthContext.Provider value={value!}>{children}</AuthContext.Provider>
}
