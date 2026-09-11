import '@ant-design/v5-patch-for-react-19'
import React, { useEffect, type PropsWithChildren } from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { AuthGate } from './auth'
import { ThemeProvider } from './theme'
import './styles.css'

function InteractionPolicy({ children }: PropsWithChildren) {
  useEffect(() => {
    const blockUnexpectedContextMenu = (event: MouseEvent) => {
      const target = event.target
      if (!(target instanceof Element)) return
      if (target.closest('[data-allow-context-menu="true"]')) return
      if (target.closest('button, [role="button"], [role="combobox"], [role="menuitem"], [role="option"], .ant-select, .ant-select-item, .ant-dropdown-trigger, .ant-dropdown-menu-item, .ant-picker, .ant-picker-cell, .ant-tree-node-content-wrapper, .ant-tabs-tab')) event.preventDefault()
    }
    document.addEventListener('contextmenu', blockUnexpectedContextMenu)
    return () => document.removeEventListener('contextmenu', blockUnexpectedContextMenu)
  }, [])
  return <>{children}</>
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN} theme={{ token: { colorPrimary: '#137a63', borderRadius: 8, fontFamily: 'var(--vx-font-family, "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif)' } }}>
      <InteractionPolicy><ThemeProvider><BrowserRouter><AuthGate><App /></AuthGate></BrowserRouter></ThemeProvider></InteractionPolicy>
    </ConfigProvider>
  </React.StrictMode>,
)
