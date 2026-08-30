import { useEffect, useRef, useState } from 'react'
import { Alert, Button, Modal, Select, Space, Typography, message } from 'antd'
import { CloudDownload, RefreshCw } from 'lucide-react'
import { api } from '../api'
import type { SystemUpdateStatus, SystemVersionInfo } from '../types'

const compareVersions = (left: string, right: string) => {
  const a = left.split('.').map(Number); const b = right.split('.').map(Number)
  for (let i = 0; i < 3; i += 1) if ((a[i] || 0) !== (b[i] || 0)) return (a[i] || 0) - (b[i] || 0)
  return 0
}
const repositoryFor = (registry: string, info?: SystemVersionInfo | null) => info?.registries?.find((item) => item.registry === registry)?.repository || (registry === 'docker.io' ? 'docker.io/litehub/vx-data-watch' : `${registry}/zhang_spaces/vx-data-watch`)

export default function OnlineUpdateSection() {
  const [versionInfo, setVersionInfo] = useState<SystemVersionInfo | null>(null)
  const [versionError, setVersionError] = useState('')
  const [versionLoading, setVersionLoading] = useState(false)
  const [targetVersion, setTargetVersion] = useState<string>()
  const [registry, setRegistry] = useState('docker.io')
  const [configuredRegistry, setConfiguredRegistry] = useState('docker.io')
  const [registrySaving, setRegistrySaving] = useState(false)
  const [updateStatus, setUpdateStatus] = useState<SystemUpdateStatus | null>(null)
  const [updateStarting, setUpdateStarting] = useState(false)
  const initialLoadRef = useRef(false); const requestIdRef = useRef(0)
  const registryOptions = versionInfo?.registries?.map((item) => ({ value: item.registry, label: item.label })) || [{ value: 'docker.io', label: 'Docker Hub' }, { value: 'crpi-k1zyo7p3ez2ovrc3.cn-chengdu.personal.cr.aliyuncs.com', label: '阿里云 ACR' }]
  const selectedRepository = repositoryFor(registry, versionInfo)
  const loadVersions = async (selectedRegistry = registry) => {
    const requestId = ++requestIdRef.current
    setVersionLoading(true); setVersionError(''); setTargetVersion(undefined)
    try {
      const result = await api<SystemVersionInfo>(`/api/system/versions?registry=${encodeURIComponent(selectedRegistry)}`)
      if (requestId !== requestIdRef.current) return
      setVersionInfo(result); setRegistry(result.registry || selectedRegistry); setConfiguredRegistry(result.configured_registry || result.registry || selectedRegistry); setTargetVersion(result.versions[0]?.version)
    } catch (cause) {
      if (requestId === requestIdRef.current) setVersionError(`${repositoryFor(selectedRegistry)} 不可用：${cause instanceof Error ? cause.message : '无法获取版本信息'}`)
    } finally { if (requestId === requestIdRef.current) setVersionLoading(false) }
  }
  const saveRegistry = async () => {
    setRegistrySaving(true)
    try { await api('/api/system/update-registry', { method: 'PUT', body: JSON.stringify({ registry }) }); setConfiguredRegistry(registry); message.success('镜像源配置已保存') }
    catch (cause) { message.error(cause instanceof Error ? cause.message : '镜像源配置保存失败') }
    finally { setRegistrySaving(false) }
  }
  const loadUpdateStatus = async () => { try { setUpdateStatus(await api<SystemUpdateStatus>('/api/system/update-status')) } catch { /* The app can restart during an update. */ } }
  useEffect(() => { if (initialLoadRef.current) return; initialLoadRef.current = true; void loadVersions(); void loadUpdateStatus() }, []) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (!updateStatus || !['queued', 'pulling', 'restarting', 'verifying', 'rolling_back'].includes(updateStatus.state)) return; const timer = window.setInterval(() => void loadUpdateStatus(), 2000); return () => window.clearInterval(timer) }, [updateStatus?.state]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { const pendingId = window.sessionStorage.getItem('vx_update_id'); if (updateStatus?.state !== 'success' || !pendingId || pendingId !== updateStatus.id) return; const timer = window.setTimeout(() => { window.sessionStorage.removeItem('vx_update_id'); window.location.reload() }, 1500); return () => window.clearTimeout(timer) }, [updateStatus?.id, updateStatus?.state])
  const startUpdate = () => {
    if (!targetVersion) return
    Modal.confirm({ title: `切换到 v${targetVersion}`, content: '系统会先创建加密备份，再拉取镜像并重启应用。重启期间页面可能短暂断开，请不要关闭 Docker。', okText: '备份并更新', cancelText: '取消', onOk: async () => {
      setUpdateStarting(true)
      try { const result = await api<SystemUpdateStatus>('/api/system/update', { method: 'POST', body: JSON.stringify({ version: targetVersion, registry }) }); if (result.id) window.sessionStorage.setItem('vx_update_id', result.id); setUpdateStatus(result) }
      catch (cause) { message.error(cause instanceof Error ? cause.message : '更新任务提交失败') }
      finally { setUpdateStarting(false) }
    } })
  }
  const updateActive = !!updateStatus && ['queued', 'pulling', 'restarting', 'verifying', 'rolling_back'].includes(updateStatus.state)
  const statusType = updateStatus?.state === 'failed' ? 'error' : updateStatus?.state === 'success' ? 'success' : 'info'
  const retryVersionCheck = () => { void loadVersions(registry) }
  return <section className="section-band">
    <div className="section-heading"><div><Typography.Title level={3}>在线更新</Typography.Title><Typography.Text type="secondary">选择镜像源，检测正式版本并重启应用</Typography.Text></div><Button icon={<RefreshCw size={18} />} loading={versionLoading} onClick={() => void loadVersions()}>检测更新</Button></div>
    {versionError && <Alert type="error" showIcon message="版本检测失败" description={versionError} />}
    {versionError && <div className="update-actions update-error-actions"><div className="registry-picker"><Select aria-label="镜像源" value={registry} onChange={(value) => { setRegistry(value); void loadVersions(value) }} options={registryOptions} /><small>{selectedRepository}</small></div><div className="update-action-buttons"><Button icon={<RefreshCw size={18} />} loading={versionLoading} onClick={retryVersionCheck}>重新检测</Button><Button onClick={() => window.location.reload()}>刷新页面</Button></div></div>}
    {versionInfo && <div className="update-panel"><div className="version-summary"><div><span>当前版本</span><strong>v{versionInfo.current_version}</strong></div><div><span>最新版本</span><strong>{versionInfo.latest_version ? `v${versionInfo.latest_version}` : '暂未发布'}</strong></div><div><span>镜像仓库</span><strong>{selectedRepository}</strong></div></div>
      {!versionInfo.update_supported ? <Alert type="warning" showIcon message="当前为源码部署" description="可以在线检测版本，但自动拉取和重启只在 Docker Compose 部署中启用。源码部署请在终端执行 git pull 后重新启动。" /> : versionInfo.versions.length ? <div className="update-actions"><div className="registry-picker"><Select aria-label="镜像源" value={registry} onChange={(value) => { setRegistry(value); void loadVersions(value) }} options={registryOptions} /><small>{selectedRepository}</small></div><Select aria-label="目标版本" value={targetVersion} onChange={setTargetVersion} options={versionInfo.versions.map((row) => ({ value: row.version, label: `v${row.version}${row.version === versionInfo.latest_version ? '（最新）' : ''}${compareVersions(row.version, versionInfo.current_version) < 0 ? '（回退）' : '（升级）'}` }))} /><div className="update-action-buttons"><Button type="primary" icon={<CloudDownload size={18} />} loading={updateStarting || updateActive} disabled={!targetVersion || !!versionError} onClick={startUpdate}>切换并重启</Button>{registry !== configuredRegistry && <Button loading={registrySaving} onClick={() => void saveRegistry()}>保存镜像源</Button>}</div></div> : <Alert type="success" showIcon message={versionInfo.latest_version ? '镜像库中没有其他可切换版本' : '镜像仓库暂时没有正式版本标签'} />}
      {updateStatus && updateStatus.state !== 'idle' && <Alert className="update-status" type={statusType} showIcon message={updateStatus.state === 'success' && updateStatus.target_version === versionInfo.current_version ? `当前已是 v${versionInfo.current_version}` : (updateStatus.message || '正在处理更新')} description={<Space wrap><span>{updateStatus.target_version ? `目标版本：v${updateStatus.target_version}` : ''}</span>{updateStatus.state === 'success' && updateStatus.target_version !== versionInfo.current_version && <span>页面即将刷新</span>}</Space>} />}
    </div>}
  </section>
}
