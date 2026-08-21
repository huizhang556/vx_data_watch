import { Card, Descriptions, Typography } from 'antd'

const details = {
  architecture: { title: '项目架构', subtitle: '了解系统的组成与数据流转方式', rows: [['前端', 'React + TypeScript + Vite'], ['后端', 'FastAPI + SQLAlchemy'], ['部署', 'Docker Compose 或 Ubuntu/Debian 源码部署'], ['数据存储', 'SQLite（可通过环境变量切换数据库配置）']] },
  technology: { title: '开发技术', subtitle: '项目使用的主要技术栈', rows: [['界面组件', 'Ant Design、Lucide Icons、ECharts'], ['数据处理', 'CSV/Excel 导入、OCR 识别、时间段统计'], ['AI 接口', 'OpenAI 兼容 API'], ['安全机制', '加密配置、CSRF、防暴力登录、Cloudflare Turnstile']] },
  team: { title: '关于我们', subtitle: 'VX Data Watch 项目信息', rows: [['项目名称', 'VX Data Watch'], ['项目定位', '微信视频号数据分析工具'], ['许可证', 'MIT License'], ['版本', '以当前部署镜像和 VERSIONS.md 为准']] },
} as const

export default function AboutPage({ section = 'architecture' }: { section?: keyof typeof details }) {
  const detail = details[section]
  return <div className="page">
    <div className="page-heading"><div><Typography.Title level={2}>{detail.title}</Typography.Title><Typography.Text type="secondary">{detail.subtitle}</Typography.Text></div></div>
    <Card className="tool-section" bordered><Descriptions bordered column={1} items={detail.rows.map(([label, children]) => ({ key: label, label, children }))} /></Card>
  </div>
}
