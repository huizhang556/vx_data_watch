/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Alert, Button, Form, Input, Spin, Typography, message } from 'antd'
import { LockKeyhole, Mail, UserRound } from 'lucide-react'
import { api, setCsrfToken } from './api'
import type { User } from './types'

interface AuthContextValue { user: User; logout: () => Promise<void>; updateUser: (user: User) => void }
const AuthContext = createContext<AuthContextValue | null>(null)
export function useAuth() { const value = useContext(AuthContext); if (!value) throw new Error('AuthContext is missing'); return value }

declare global { interface Window { turnstile?: { render: (el: HTMLElement, opts: Record<string, unknown>) => void } } }
function Captcha({ enabled, siteKey, onChange }: { enabled: boolean; siteKey?: string; onChange: (value?: string) => void }) {
  const [element, setElement] = useState<HTMLDivElement | null>(null)
  useEffect(() => {
    if (!enabled || !siteKey || !element) return
    let timer: number | undefined
    const render = () => { if (window.turnstile) window.turnstile.render(element, { sitekey: siteKey, callback: onChange, 'expired-callback': () => onChange(undefined), 'error-callback': () => onChange(undefined) }); else timer = window.setTimeout(render, 250) }
    render()
    return () => { if (timer) window.clearTimeout(timer) }
  }, [enabled, siteKey, element, onChange])
  return enabled ? <div ref={setElement} className="captcha-widget" /> : null
}

type Mode = 'login' | 'register' | 'reset'
const usernameRule = { pattern: /^[A-Za-z0-9_.-]+$/, message: '用户名只能包含英文、数字、下划线、点和短横线' }
const passwordRule = { pattern: /^(?=.*[A-Za-z])(?=.*\d).+$/, message: '密码至少 10 位，并同时包含字母和数字' }
export function AuthGate({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true); const [initialized, setInitialized] = useState(false); const [user, setUser] = useState<User | null>(null); const [error, setError] = useState('')
  const [config, setConfig] = useState({ registration_enabled: false, captcha_enabled: false, captcha_site_key: '' }); const [mode, setMode] = useState<Mode>('login'); const [captcha, setCaptcha] = useState<string>(); const [email, setEmail] = useState(''); const [busy, setBusy] = useState(false)
  const [form] = Form.useForm()
  const captchaReady = !config.captcha_enabled || Boolean(captcha)
  useEffect(() => {
    const button = document.querySelector<HTMLButtonElement>('.auth-panel form button[type="submit"]')
    if (!button) return
    button.disabled = !captchaReady || busy
    button.setAttribute('aria-disabled', String(!captchaReady || busy))
  }, [captchaReady, busy, mode])
  useEffect(() => { void (async () => { try { const [status, authConfig] = await Promise.all([api<{ initialized: boolean }>('/api/setup/status'), api<typeof config>('/api/auth/config')]); setInitialized(status.initialized); setConfig(authConfig); if (status.initialized) { try { const me = await api<User>('/api/auth/me'); setCsrfToken(me.csrf_token); setUser(me) } catch { setUser(null) } } } catch (cause) { setError(cause instanceof Error ? cause.message : '无法连接后端') } finally { setLoading(false) } })() }, [])
  useEffect(() => {
    if (user !== null || !initialized) return
    void api<typeof config>('/api/auth/config').then(setConfig).catch(() => undefined)
  }, [user, initialized])
  useEffect(() => { const onUnauthorized = () => { setCsrfToken(); setUser(null); localStorage.removeItem('vx_account_id') }; window.addEventListener('vx:unauthorized', onUnauthorized); return () => window.removeEventListener('vx:unauthorized', onUnauthorized) }, [])
  const switchMode = (next: Mode) => { setMode(next); setError(''); setCaptcha(undefined); form.resetFields(); setEmail('') }
  const finishLogin = (next: User) => { setCsrfToken(next.csrf_token); setUser(next); setInitialized(true); message.success('登录成功') }
  const submit = async (values: { username?: string; password: string; email?: string; code?: string }) => { setBusy(true); setError(''); try { if (mode === 'login') finishLogin(await api<User>(initialized ? '/api/auth/login' : '/api/setup', { method: 'POST', body: JSON.stringify({ ...values, captcha_token: captcha }) })); else if (mode === 'register') finishLogin(await api<User>('/api/auth/register', { method: 'POST', body: JSON.stringify({ ...values, captcha_token: captcha }) })); else finishLogin(await api<User>('/api/auth/password-reset', { method: 'POST', body: JSON.stringify({ email: values.email, code: values.code, new_password: values.password, captcha_token: captcha }) })) } catch (cause) { setError(cause instanceof Error ? cause.message : '操作失败') } finally { setBusy(false) } }
  const syncField = (name: string, value: string) => { form.setFieldValue(name, value); if (name === 'email') setEmail(value) }
  const sendCode = async (value?: string) => { const targetEmail = value || form.getFieldValue('email') || email; setBusy(true); try { await api(mode === 'register' ? '/api/auth/register/request-code' : '/api/auth/password-reset/request-code', { method: 'POST', body: JSON.stringify({ email: targetEmail, captcha_token: captcha }) }); message.success('验证码已发送，请检查邮箱') } catch (cause) { message.error(cause instanceof Error ? cause.message : '发送失败') } finally { setBusy(false) } }
  const logout = async () => { try { await api('/api/auth/logout', { method: 'POST' }) } catch { /* clear local state even if server is unavailable */ } finally { setCsrfToken(); setUser(null); setMode('login'); setCaptcha(undefined); form.resetFields(); localStorage.removeItem('vx_account_id'); window.history.replaceState({}, '', '/') } }
  const updateUser = (next: User) => { setUser(next); if (next.csrf_token) setCsrfToken(next.csrf_token) }
  const value = useMemo(() => user ? { user, logout, updateUser } : null, [user])
  if (loading) return <div className="center-screen"><Spin size="large" /></div>
  if (user) return <AuthContext.Provider value={value!}>{children}</AuthContext.Provider>
  const isSetup = !initialized
  return <main className="auth-page"><section className="auth-panel"><div className="brand-mark">VX</div><Typography.Title level={2}>视频号数据分析</Typography.Title><Typography.Paragraph type="secondary">{isSetup ? '创建首个本地管理员账号' : mode === 'login' ? '使用账号进入数据工作台' : mode === 'register' ? '使用邮箱验证码创建账号' : '使用注册邮箱重置密码'}</Typography.Paragraph>{error && <Alert type="error" showIcon message={error} />}
    <Form form={form} layout="vertical" onFinish={submit} requiredMark={false} key={mode}>{(mode === 'login' || mode === 'register') && <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }, { min: 3, message: '用户名至少需要 3 个字符' }, usernameRule]}><Input prefix={<UserRound size={17} />} autoComplete="username" onChange={(event) => syncField('username', event.currentTarget.value)} onInput={(event) => syncField('username', event.currentTarget.value)} onBlur={(event) => syncField('username', event.currentTarget.value)} /></Form.Item>}{(mode === 'register' || mode === 'reset') && <Form.Item name="email" label="注册邮箱" rules={[{ required: true, type: 'email', message: '请输入有效邮箱' }]}><Input prefix={<Mail size={17} />} autoComplete="email" onChange={(event) => syncField('email', event.target.value)} onBlur={(event) => syncField('email', event.target.value)} /></Form.Item>}{mode !== 'login' && <Form.Item name="code" label="邮箱验证码" rules={[{ required: true, message: '请输入 6 位数字验证码' }, { len: 6, pattern: /^\d{6}$/, message: '验证码必须是 6 位数字' }]}><Input.Search enterButton="发送验证码" onSearch={() => { void sendCode(form.getFieldValue('email')) }} /></Form.Item>}<Form.Item name="password" label={mode === 'login' ? '密码' : '新密码'} rules={[{ required: true, message: '请输入密码' }, ...(mode === 'login' ? [] : [{ min: 10, message: '密码至少需要 10 个字符' }, passwordRule])]}><Input.Password prefix={<LockKeyhole size={17} />} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} onChange={(event) => syncField('password', event.currentTarget.value)} onInput={(event) => syncField('password', event.currentTarget.value)} onBlur={(event) => syncField('password', event.currentTarget.value)} /></Form.Item><Captcha enabled={config.captcha_enabled} siteKey={config.captcha_site_key} onChange={setCaptcha} /><Button block type="primary" htmlType="submit" size="large" loading={busy}>{isSetup ? '初始化系统' : mode === 'login' ? '登录' : mode === 'register' ? '注册并登录' : '重置密码并登录'}</Button></Form>
    {!isSetup && <div className="auth-links"><button type="button" onClick={() => switchMode('reset')}>重置密码</button>{config.registration_enabled && <button type="button" onClick={() => switchMode('register')}>注册账号</button>}{mode !== 'login' && <button type="button" onClick={() => switchMode('login')}>返回登录</button>}</div>}
  </section></main>
}
