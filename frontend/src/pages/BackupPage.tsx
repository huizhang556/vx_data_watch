import { useEffect, useState } from 'react'
import { Alert, Button, Empty, Table, Typography, message } from 'antd'
import { DatabaseBackup, Download, ShieldCheck } from 'lucide-react'
import dayjs from 'dayjs'
import { api } from '../api'
import { useAuth } from '../auth'

interface Backup { filename: string; size: number; modified_at: string }

export default function BackupPage() {
  const { user } = useAuth()
  const [backups, setBackups] = useState<Backup[]>([])
  const [loading, setLoading] = useState(false)
  const loadBackups = () => api<Backup[]>('/api/backups').then(setBackups)
  useEffect(() => { void loadBackups() }, [])
  const backup = async () => {
    setLoading(true)
    try { await api('/api/backups', { method: 'POST' }); await loadBackups(); message.success('加密备份已创建并完成完整性检查') }
    catch (cause) { message.error(cause instanceof Error ? cause.message : '备份失败') }
    finally { setLoading(false) }
  }
  return (
    <div className="page">
      <div className="page-heading"><div><Typography.Title level={2}>加密备份</Typography.Title><Typography.Text type="secondary">保护用户、账号和分析数据，支持下载后异地保存</Typography.Text></div>{user.role === 'admin' && <Button icon={<DatabaseBackup size={18} />} loading={loading} onClick={() => void backup()}>创建备份</Button>}</div>
      <section className="section-band backup-section">
        {!backups.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无备份" /> : <Table size="small" rowKey="filename" pagination={false} dataSource={backups} columns={[
          { title: '文件', dataIndex: 'filename', ellipsis: true },
          { title: '大小', dataIndex: 'size', render: (value) => `${(value / 1024).toFixed(1)} KB` },
          { title: '时间', dataIndex: 'modified_at', render: (value) => dayjs(value).format('YYYY-MM-DD HH:mm') },
          { title: '操作', render: (_, row) => <Button type="text" icon={<Download size={18} />} title="下载备份" href={`/api/backups/${encodeURIComponent(row.filename)}`} /> },
        ]} />}
      </section>
      <section className="security-note"><ShieldCheck size={24} /><div><strong>本地安全模式</strong><p>密码使用 Argon2id，AI Key 使用 AES-256-GCM。主密钥保存在数据目录的独立受限文件中，请与备份一同妥善保管。</p></div></section>
      <Alert type="warning" showIcon message="恢复备份需要停止应用" description="使用项目 README 中的命令行恢复步骤，避免覆盖正在使用的数据库。" />
    </div>
  )
}
