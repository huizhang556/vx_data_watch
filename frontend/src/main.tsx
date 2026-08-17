import '@ant-design/v5-patch-for-react-19'
import React from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { AuthGate } from './auth'
import './styles.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN} theme={{ token: { colorPrimary: '#137a63', borderRadius: 6, fontFamily: 'Inter, "Microsoft YaHei", sans-serif' } }}>
      <BrowserRouter><AuthGate><App /></AuthGate></BrowserRouter>
    </ConfigProvider>
  </React.StrictMode>,
)
