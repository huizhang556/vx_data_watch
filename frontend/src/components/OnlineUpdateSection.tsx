import { useEffect, useRef, useState } from 'react'
import { Alert, Button, Modal, Select, Space, Typography } from 'antd'
import { CloudDownload, RefreshCw } from 'lucide-react'
import { api } from '../api'
import type { SystemUpdateStatus, SystemVersionInfo } from '../types'

const compareVersions = (left: string, right: string) => {
  const a = left.split('.').map(Number); const b = right.split('.').map(Number)
  for (let index = 0; index < 3; index += 1) if ((a[index] || 0) !== (b[index] || 0)) return (a[index] || 0) - (b[index] || 0)
  return 0
}

export default function OnlineUpdateSection() {
  const [versionInfo, setVersionInfo] = useState<SystemVersionInfo | null>(null)
  const [versionError, setVersionError] = useState('')
  const [versionLoading, setVersionLoading] = useState(false)
  const [targetVersion, setTargetVersion] = useState<string>()
  const [registry, setRegistry] = useState('docker.io')
  const [updateStatus, setUpdateStatus] = useState<SystemUpdateStatus | null>(null)
  const [updateStarting, setUpdateStarting] = useState(false)
  const initialLoadRef = useRef(false)

  const loadVersions = async (selectedRegistry = registry) => {
    setVersionLoading(true); setVersionError('')
    try {
      const result = await api<SystemVersionInfo>(`/api/system/versions?registry=${encodeURIComponent(selectedRegistry)}`)
      setVersionInfo(result)
      setRegistry(result.registry || selectedRegistry)
      setTargetVersion((current) => result.versions.some((row) => row.version === current) ? current : result.versions[0]?.version)
    } catch (cause) { setVersionError(cause instanceof Error ? cause.message : '无法获取版本信息') }
    finally { setVersionLoading(false) }
  }
  const loadUpdateStatus = async () => {
    try { setUpdateStatus(await api<SystemUpdateStatus>('/api/system/update-status')) } catch { /* App may restart during an update. */ }
  }
  useEffect(() => {
    if (initialLoadRef.current) return
    initialLoadRef.current = true
    void loadVersions()
    void loadUpdateStatus()
  }, [])
  useEffect(() => {
    if (!updateStatus || !['queued', 'pulling', 'restarting', 'verifying', 'rolling_back'].includes(updateStatus.state)) return
    const timer = window.setInterval(() => void loadUpdateStatus(), 2000)
    return () => window.clearInterval(timer)
  }, [updateStatus?.state]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const pendingId = window.sessionStorage.getItem('vx_update_id')
    if (updateStatus?.state !== 'success' || !pendingId || pendingId !== updateStatus.id) return
    const timer = window.setTimeout(() => { window.sessionStorage.removeItem('vx_update_id'); window.location.reload() }, 1500)
    return () => window.clearTimeout(timer)
  }, [updateStatus?.id, updateStatus?.state])

  const startUpdate = () => {
    if (!targetVersion) return
    Modal.confirm({
      title: `切换到 ${targetVersion}？`,
      content: '系统会先创建加密备份，再拉取镜像并重启应用。目标版本可以是升级版本，也可以是历史版本。重启期间页面可能短暂断开，请不要关闭 Docker。',
      okText: '备份并更新', cancelText: '取消',
      onOk: async () => {
        setUpdateStarting(true)
        try {
          const result = await api<SystemUpdateStatus>('/api/system/update', { method: 'POST', body: JSON.stringify({ version: targetVersion, registry }) })
          if (result.id) window.sessionStorage.setItem('vx_update_id', result.id)
          setUpdateStatus(result)
        } catch (cause) { setVersionError(cause instanceof Error ? cause.message : '更新任务提交失败') }
        finally { setUpdateStarting(false) }
      },
    })
  }
  const updateActive = !!updateStatus && ['queued', 'pulling', 'restarting', 'verifying', 'rolling_back'].includes(updateStatus.state)
  const statusType = updateStatus?.state === 'failed' ? 'error' : updateStatus?.state === 'success' ? 'success' : 'info'
  const registryOptions = versionInfo?.registries?.map((item) => ({ value: item.registry, label: item.label })) || [{ value: 'docker.io', label: 'Docker Hub' }]
  return <section className="section-band">
    <div className="section-heading"><div><Typography.Title level={3}>在线更新</Typography.Title><Typography.Text type="secondary">选择受信任镜像源，检测正式版本并重启应用</Typography.Text></div><Button icon={<RefreshCw size={18} />} loading={versionLoading} onClick={() => void loadVersions()}>检测更新</Button></div>
    {versionError && <Alert type="error" showIcon message="版本检测失败" description={versionError} />}
    {versionInfo && <div className="update-panel">
      <div className="version-summary"><div><span>当前版本</span><strong>v{versionInfo.current_version}</strong></div><div><span>最新版本</span><strong>{versionInfo.latest_version ? `v${versionInfo.latest_version}` : '暂未发布'}</strong></div><div><span>镜像仓库</span><strong>{versionInfo.repository}</strong></div></div>
      {!versionInfo.update_supported ? <Alert type="warning" showIcon message="当前为源码部署" description="可以在线检测版本，但自动拉取和重启只在 Docker Compose 部署中启用。源码部署请在终端执行 git pull 后重新启动。" /> : versionInfo.versions.length ? <div className="update-actions"><div className="registry-picker"><Select aria-label="镜像源" value={registry} onChange={(value) => { setRegistry(value); void loadVersions(value) }} options={registryOptions} /><small>{versionInfo.registries?.find((item) => item.registry === registry)?.repository || versionInfo.repository}</small></div><Select aria-label="目标版本" value={targetVersion} onChange={setTargetVersion} options={versionInfo.versions.map((row) => ({ value: row.version, label: `v${row.version}${row.version === versionInfo.latest_version ? '（最新）' : ''}${compareVersions(row.version, versionInfo.current_version) < 0 ? '（回退）' : '（升级）'}` }))} /><Button type="primary" icon={<CloudDownload size={18} />} loading={updateStarting || updateActive} disabled={!targetVersion} onClick={startUpdate}>切换并重启</Button></div> : <Alert type="success" showIcon message={versionInfo.latest_version ? '镜像库中没有其他可切换版本' : '镜像仓库暂时没有正式版本标签'} />}
      {updateStatus && updateStatus.state !== 'idle' && <Alert className="update-status" type={statusType} showIcon message={updateStatus.state === 'success' && updateStatus.target_version === versionInfo?.current_version ? `当前已是 v${versionInfo.current_version}` : (updateStatus.message || '正在处理更新')} description={<Space wrap><span>{updateStatus.target_version ? `目标版本：v${updateStatus.target_version}` : ''}</span>{updateStatus.state === 'success' && updateStatus.target_version !== versionInfo?.current_version && <span>页面即将刷新</span>}</Space>} />}
    </div>}
  </section>
}
