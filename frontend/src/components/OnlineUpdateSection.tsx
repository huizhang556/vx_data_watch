import { useEffect, useRef, useState } from 'react'
import { Alert, Button, Collapse, Descriptions, Modal, Select, Space, Tooltip, Typography, message } from 'antd'
import { CloudDownload, Copy, FileText, RefreshCw } from 'lucide-react'
import { api } from '../api'
import type { ConfigMigrationPlan, DeploymentInfo, SystemUpdateStatus, SystemVersionInfo, UpdateHealthInfo, UpdateHistoryRecord } from '../types'

const compareVersions = (left: string, right: string) => {
  const a = left.split('.').map(Number); const b = right.split('.').map(Number)
  for (let i = 0; i < 3; i += 1) if ((a[i] || 0) !== (b[i] || 0)) return (a[i] || 0) - (b[i] || 0)
  return 0
}
const repositoryFor = (registry: string, info?: SystemVersionInfo | null) => info?.registries?.find((item) => item.registry === registry)?.repository || (registry === 'docker.io' ? 'docker.io/litehub/vx-data-watch:latest' : `${registry}/zhang_spaces/vx-data-watch:latest`)
const registryFromError = (message: string) => message.match(/镜像仓库\s+([^（\s]+)/)?.[1]
const formatImageSize = (bytes?: number | null) => {
  if (!Number.isFinite(bytes) || !bytes || bytes <= 0) return '大小未知'
  const units = ['B', 'KB', 'MB', 'GB']
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit += 1 }
  return `${value >= 100 || unit === 0 ? value.toFixed(0) : value.toFixed(2)} ${units[unit]}`
}

export default function OnlineUpdateSection({ autoStart = false }: { autoStart?: boolean }) {
  const [versionInfo, setVersionInfo] = useState<SystemVersionInfo | null>(null)
  const [healthInfo, setHealthInfo] = useState<UpdateHealthInfo | null>(null)
  const [versionError, setVersionError] = useState('')
  const [versionLoading, setVersionLoading] = useState(false)
  const [targetVersion, setTargetVersion] = useState<string>()
  const [registry, setRegistry] = useState('')
  const [configuredRegistry, setConfiguredRegistry] = useState('')
  const [registrySaving, setRegistrySaving] = useState(false)
  const [updateStatus, setUpdateStatus] = useState<SystemUpdateStatus | null>(null)
  const [updateStarting, setUpdateStarting] = useState(false)
  const [deploymentInfo, setDeploymentInfo] = useState<DeploymentInfo | null>(null)
  const [deploymentLoading, setDeploymentLoading] = useState(false)
  const [history, setHistory] = useState<UpdateHistoryRecord[]>([])
  const [migration, setMigration] = useState<ConfigMigrationPlan | null>(null)
  const [migrationLoading, setMigrationLoading] = useState(false)
  const [migrationApplying, setMigrationApplying] = useState(false)
  const initialLoadRef = useRef(false); const requestIdRef = useRef(0)
  const autoStartRef = useRef(false)
  const registryOptions = versionInfo?.registries?.map((item) => ({ registry: item.registry, label: item.label })) || [{ registry: 'docker.io', label: 'Docker Hub' }, { registry: 'crpi-k1zyo7p3ez2ovrc3.cn-chengdu.personal.cr.aliyuncs.com', label: '阿里云 ACR' }]
  const selectedRepository = repositoryFor(registry || configuredRegistry || 'docker.io', versionInfo)
  const loadVersions = async (selectedRegistry?: string) => {
    const requestId = ++requestIdRef.current
    setVersionLoading(true)
    try {
      const endpoint = selectedRegistry ? `/api/system/versions?registry=${encodeURIComponent(selectedRegistry)}` : '/api/system/versions'
      const result = await api<SystemVersionInfo>(endpoint)
      if (requestId !== requestIdRef.current) return
      const resolvedRegistry = result.registry || selectedRegistry || 'docker.io'
      setVersionError(''); setVersionInfo(result); setRegistry(resolvedRegistry); setConfiguredRegistry(result.configured_registry || resolvedRegistry); setTargetVersion(result.versions[0]?.version)
    } catch (cause) {
      if (requestId === requestIdRef.current) {
        const errorMessage = cause instanceof Error ? cause.message : '无法获取版本信息'
        const failedRegistry = selectedRegistry || registryFromError(errorMessage) || configuredRegistry || 'docker.io'
        setRegistry(failedRegistry)
        setVersionError(`${repositoryFor(failedRegistry)} 不可用：${errorMessage}`)
      }
    } finally { if (requestId === requestIdRef.current) setVersionLoading(false) }
  }
  const loadHealth = async (selectedRegistry?: string) => {
    try {
      const endpoint = selectedRegistry ? `/api/system/update-health?registry=${encodeURIComponent(selectedRegistry)}` : '/api/system/update-health'
      setHealthInfo(await api<UpdateHealthInfo>(endpoint))
    } catch {
      setHealthInfo((current) => current ? { ...current, status: 'warning', message: '无法完成在线更新链路检测' } : null)
    }
  }
  const saveRegistry = async () => {
    setRegistrySaving(true)
    try { await api('/api/system/update-registry', { method: 'PUT', body: JSON.stringify({ registry }) }); setConfiguredRegistry(registry); message.success('镜像源配置已保存') }
    catch (cause) { message.error(cause instanceof Error ? cause.message : '镜像源配置保存失败') }
    finally { setRegistrySaving(false) }
  }
  const loadUpdateStatus = async () => { try { setUpdateStatus(await api<SystemUpdateStatus>('/api/system/update-status')) } catch { /* The app can restart during an update. */ } }
  const loadDeploymentInfo = async () => { setDeploymentLoading(true); try { setDeploymentInfo(await api<DeploymentInfo>('/api/system/deployment-info')) } catch { setDeploymentInfo(null) } finally { setDeploymentLoading(false) } }
  const loadHistory = async () => { try { setHistory(await api<UpdateHistoryRecord[]>('/api/system/update-history')) } catch { setHistory([]) } }
  const loadMigration = async () => { setMigrationLoading(true); try { setMigration(await api<ConfigMigrationPlan>('/api/system/config-migration')) } catch { setMigration(null) } finally { setMigrationLoading(false) } }
  const applyMigration = async () => { setMigrationApplying(true); try { const result = await api<ConfigMigrationPlan>('/api/system/config-migration', { method: 'POST', body: '{}' }); setMigration(result); message.success('配置迁移完成，请按部署方式重启服务') } catch (cause) { message.error(cause instanceof Error ? cause.message : '配置迁移失败') } finally { setMigrationApplying(false) } }
  useEffect(() => { if (initialLoadRef.current) return; initialLoadRef.current = true; void loadVersions(); void loadHealth(); void loadUpdateStatus(); void loadDeploymentInfo(); void loadHistory(); void loadMigration() }, []) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const refresh = () => { if (document.visibilityState === 'visible') { void loadVersions(configuredRegistry || undefined); void loadHealth(configuredRegistry || undefined) } }
    const timer = window.setInterval(refresh, 60_000)
    document.addEventListener('visibilitychange', refresh)
    return () => { window.clearInterval(timer); document.removeEventListener('visibilitychange', refresh) }
  }, [configuredRegistry]) // eslint-disable-line react-hooks/exhaustive-deps
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
  useEffect(() => {
    if (!autoStart || autoStartRef.current || !versionInfo || versionError || !targetVersion || updateActive) return
    autoStartRef.current = true
    startUpdate()
  }, [autoStart, versionInfo, versionError, targetVersion, updateActive]) // eslint-disable-line react-hooks/exhaustive-deps
  const statusType = updateStatus?.state === 'failed' ? 'error' : updateStatus?.state === 'success' ? 'success' : 'info'
  const retryVersionCheck = () => { void loadVersions(configuredRegistry); void loadHealth(configuredRegistry) }
  const copyRepository = async () => {
    try {
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(selectedRepository)
      else {
        const input = document.createElement('textarea'); input.value = selectedRepository; input.style.position = 'fixed'; input.style.opacity = '0'; document.body.appendChild(input); input.select();
        if (!document.execCommand('copy')) throw new Error('copy failed')
        input.remove()
      }
      message.success('镜像仓库地址已复制')
    }
    catch { message.error('复制失败，请检查浏览器权限') }
  }
  const healthBanner = healthInfo ? <>
    <div className="section-heading update-health-heading"><div><Typography.Title level={3}>更新服务状态</Typography.Title><Typography.Text type="secondary">每 60 秒检测更新链路、镜像源和本地更新服务</Typography.Text></div></div>
    <Alert className="update-health-summary" type={healthInfo.status === 'ok' ? 'success' : 'warning'} showIcon message={<span><i className={`update-health-dot ${healthInfo.status}`} />更新链路：{healthInfo.status === 'ok' ? '正常' : '异常'}</span>} description={healthInfo.message} />
    <div className="update-health-panel"><div className="update-health-grid">{healthInfo.checks.map((check) => <Tooltip key={check.key} title={check.message} placement="top"><div className="update-health-check"><span><i className={`update-health-dot ${check.status}`} />{check.label}</span><strong>{check.status === 'ok' ? '正常' : '异常'}</strong></div></Tooltip>)}</div></div>
  </> : null
  const registryOptionLabel = (item: { registry: string; label: string }) => { const health = healthInfo?.registries?.[item.registry]; return <span className="registry-option" title={health?.message}><i className={`update-health-dot ${health?.status || 'warning'}`} />{item.label}<small>{health ? `${health.latency_ms}ms` : '检测中'}</small></span> }
  const registrySelectOptions = registryOptions.map((item) => ({ value: item.registry, label: registryOptionLabel(item) }))
  const browseFile = (file: 'env' | 'compose') => {
    const item = file === 'env' ? deploymentInfo?.service_runtime.env_file : deploymentInfo?.service_runtime.compose_file
    if (!item) return
    Modal.info({ title: file === 'env' ? '.env 文件内容（敏感值已脱敏）' : 'docker-compose 文件内容', width: 820, content: <pre className="deployment-file-preview">{item.readable ? item.content : '文件不存在或不可读取'}</pre> })
  }
  const formatBytes = (value: number | null | undefined) => value == null ? '暂无数据' : value < 1024 ? `${value} B` : value < 1024 ** 2 ? `${(value / 1024).toFixed(1)} KB` : `${(value / (1024 ** 2)).toFixed(1)} MB`
  const formatStorage = (value: unknown) => typeof value === 'string' ? value : (value && typeof value === 'object' && 'path' in value ? `${(value as { path: string }).path}（${(value as unknown as { exists: boolean }).exists ? '存在' : '不存在'}，${formatBytes((value as unknown as { size_bytes?: number | null }).size_bytes)}）` : '暂无数据')
  const deploymentPanel = <section className="deployment-info-panel"><div className="section-heading"><div><Typography.Title level={3}>项目部署基本信息</Typography.Title><Typography.Text type="secondary">只读显示当前部署、配置文件和数据存储位置</Typography.Text></div><Button icon={<RefreshCw size={16} />} loading={deploymentLoading} onClick={() => void loadDeploymentInfo()}>刷新信息</Button></div>{deploymentInfo ? <><Descriptions bordered size="small" column={1}><Descriptions.Item label="部署方式">{deploymentInfo.deployment_method}</Descriptions.Item><Descriptions.Item label="镜像路径">{deploymentInfo.image_path}</Descriptions.Item></Descriptions><Collapse defaultActiveKey={['runtime', 'storage']} items={[{ key: 'runtime', label: '服务运行目录', children: <Descriptions bordered size="small" column={1}><Descriptions.Item label="项目目录">{deploymentInfo.service_runtime.project_dir}</Descriptions.Item><Descriptions.Item label=".env 文件"><Space><Typography.Text code>{deploymentInfo.service_runtime.env_file.path}</Typography.Text><Button size="small" icon={<FileText size={14} />} onClick={() => browseFile('env')}>浏览内容</Button></Space></Descriptions.Item><Descriptions.Item label="docker-compose 文件"><Space><Typography.Text code>{deploymentInfo.service_runtime.compose_file.path}</Typography.Text><Button size="small" icon={<FileText size={14} />} onClick={() => browseFile('compose')}>浏览内容</Button></Space></Descriptions.Item></Descriptions> }, { key: 'storage', label: '数据存储目录', children: <Descriptions bordered size="small" column={1}><Descriptions.Item label="数据库类型">{deploymentInfo.data_storage.database_type}</Descriptions.Item><Descriptions.Item label="数据库文件目录">{formatStorage(deploymentInfo.data_storage.database_file_dir)}</Descriptions.Item><Descriptions.Item label="用户信息数据目录">{formatStorage(deploymentInfo.data_storage.user_data_dir)}</Descriptions.Item><Descriptions.Item label="备份文件存储目录">{formatStorage(deploymentInfo.data_storage.backup_dir)}，备份 {deploymentInfo.data_storage.backup_dir.backup_count} 个，最近备份 {deploymentInfo.data_storage.backup_dir.latest_backup_at || '暂无'}</Descriptions.Item><Descriptions.Item label="可用空间">{formatBytes(deploymentInfo.data_storage.disk_free_bytes)}</Descriptions.Item></Descriptions> }]} /></> : <Alert type="warning" showIcon message="暂时无法读取部署信息" />}</section>
  const migrationPanel = <section className="deployment-info-panel"><div className="section-heading"><div><Typography.Title level={3}>配置迁移更新</Typography.Title><Typography.Text type="secondary">复用上方部署信息，仅补齐缺失的部署字段并保留原有业务配置</Typography.Text></div><Space><Button icon={<RefreshCw size={16} />} loading={migrationLoading} onClick={() => void loadMigration()}>检查配置</Button><Button type="primary" loading={migrationApplying} disabled={!migration?.deployment_method || !migration?.changes.length} onClick={applyMigration}>备份并迁移</Button></Space></div>{migration ? <><Descriptions bordered size="small" column={1}><Descriptions.Item label="识别的部署方式">{migration.deployment_method || '未记录，无法确认'}</Descriptions.Item><Descriptions.Item label="配置文件">{migration.env_path}</Descriptions.Item><Descriptions.Item label="待补齐字段">{migration.changes.length ? migration.changes.join('、') : '无，配置已完整'}</Descriptions.Item><Descriptions.Item label="Compose 挂载检查">{migration.deployment_method === 'source' ? '源码部署不需要 Compose' : migration.compose_mount_ok ? '已发现 /project/.env 挂载' : migration.compose_readable ? '未发现 /project/.env 挂载' : 'Compose 文件不可读取'}</Descriptions.Item></Descriptions><Alert type="info" showIcon message="迁移只修改部署字段，不修改数据库、用户资料、AI 配置、主密钥或数据卷。执行后需要按当前部署方式重启服务。" /></> : <Alert type="warning" showIcon message="暂时无法读取配置迁移信息" />}</section>
  const historyPanel = <section className="update-history-panel"><div className="section-heading"><div><Typography.Title level={3}>更新记录</Typography.Title><Typography.Text type="secondary">查看历史更新、失败和回滚过程</Typography.Text></div><Button icon={<RefreshCw size={16} />} onClick={() => void loadHistory()}>刷新记录</Button></div>{history.length ? <div className="update-history-list">{history.map((item) => <button type="button" className="update-history-row" key={item.id} onClick={() => Modal.info({ title: `更新记录 ${item.target_version ? `v${item.target_version}` : ''}`, width: 760, content: <div><Descriptions size="small" column={1} bordered><Descriptions.Item label="任务 ID">{item.id}</Descriptions.Item><Descriptions.Item label="更新前版本">{item.current_version ? `v${item.current_version}` : '-'}</Descriptions.Item><Descriptions.Item label="目标版本">{item.target_version ? `v${item.target_version}` : '-'}</Descriptions.Item><Descriptions.Item label="实际完成版本">{item.final_version ? `v${item.final_version}` : '-'}</Descriptions.Item><Descriptions.Item label="状态">{item.state}</Descriptions.Item><Descriptions.Item label="镜像源">{item.registry || '-'}</Descriptions.Item><Descriptions.Item label="镜像路径">{item.image || '-'}</Descriptions.Item><Descriptions.Item label="备份文件">{item.backup_filename || '-'}</Descriptions.Item><Descriptions.Item label="是否回滚">{item.rollback ? '是' : '否'}</Descriptions.Item><Descriptions.Item label="耗时">{item.duration_seconds == null ? '-' : `${item.duration_seconds} 秒`}</Descriptions.Item><Descriptions.Item label="开始时间">{item.started_at || '-'}</Descriptions.Item><Descriptions.Item label="最后更新时间">{item.updated_at || '-'}</Descriptions.Item><Descriptions.Item label="结果">{item.message || '-'}</Descriptions.Item></Descriptions><Typography.Title level={5}>阶段日志</Typography.Title>{item.stages?.map((stage) => <div key={`${stage.at}-${stage.state}`}><Typography.Text code>{stage.at}</Typography.Text> {stage.message}</div>)}</div> })}><span><strong>{item.target_version ? `v${item.target_version}` : '未知版本'}</strong><small>{item.message || item.state}</small></span><time>{item.updated_at || item.started_at || '-'}</time></button>)}</div> : <Typography.Text type="secondary">暂无历史更新记录</Typography.Text>}</section>
  return <section className="section-band">
    {deploymentPanel}
    {migrationPanel}
    {healthBanner}
    <div className="section-heading"><div><Typography.Title level={3}>在线更新</Typography.Title><Typography.Text type="secondary">选择镜像源，检测正式版本并重启应用</Typography.Text></div><Button icon={<RefreshCw size={18} />} loading={versionLoading} onClick={() => void loadVersions()}>检测更新</Button></div>
    {versionError && <Alert type="error" showIcon message="版本检测失败" description={versionError} />}
    {versionError && <div className="update-actions update-error-actions"><div className="registry-picker"><Select aria-label="镜像源" value={registry} onChange={(value) => { setRegistry(value); void loadVersions(value) }} options={registrySelectOptions} /><small>{selectedRepository}</small></div><div className="update-action-buttons"><Button icon={<RefreshCw size={18} />} loading={versionLoading} onClick={retryVersionCheck}>重新检测</Button><Button onClick={() => window.location.reload()}>刷新页面</Button></div></div>}
    {versionInfo && <div className="update-panel"><div className="version-summary"><div><span>当前版本</span><strong>v{versionInfo.current_version}</strong></div><div><span>最新版本</span><strong>{versionInfo.latest_version ? `v${versionInfo.latest_version}` : '暂未发布'}</strong></div><div className="repository-summary"><span>镜像仓库</span><div><Tooltip title={selectedRepository}><strong>{selectedRepository}</strong></Tooltip><Button type="text" size="small" icon={<Copy size={15} />} title="复制镜像仓库地址" aria-label="复制镜像仓库地址" onClick={() => void copyRepository()} /></div></div></div>
      {!versionInfo.update_supported ? <Alert type="warning" showIcon message="当前为源码部署" description="可以在线检测版本，但自动拉取和重启只在 Docker Compose 部署中启用。源码部署请在终端执行 git pull 后重新启动。" /> : versionInfo.versions.length ? <div className="update-actions"><div className="registry-picker"><Select aria-label="镜像源" value={registry} onChange={(value) => { setRegistry(value); void loadVersions(value); void loadHealth(value) }} options={registrySelectOptions} /><small>{selectedRepository}</small></div><Select aria-label="目标版本" value={targetVersion} onChange={setTargetVersion} options={versionInfo.versions.map((row) => ({ value: row.version, label: <span className="version-option"><i className={`update-health-dot ${healthInfo?.versions[row.version] || 'warning'}`} /><span>v{row.version}{row.version === versionInfo.latest_version ? '（最新）' : ''}{compareVersions(row.version, versionInfo.current_version) < 0 ? '（回退）' : '（升级）'}</span><small>{formatImageSize(row.size_bytes)}</small></span> }))} /><div className="update-action-buttons"><Button type="primary" icon={<CloudDownload size={18} />} loading={updateStarting || updateActive} disabled={!targetVersion || !!versionError} onClick={startUpdate}>切换并重启</Button>{registry !== configuredRegistry && <Button loading={registrySaving} onClick={() => void saveRegistry()}>保存镜像源</Button>}</div></div> : <Alert type="success" showIcon message={versionInfo.latest_version ? '镜像库中没有其他可切换版本' : '镜像仓库暂时没有正式版本标签'} />}
      {updateStatus && updateStatus.state !== 'idle' && <Alert className="update-status" type={statusType} showIcon message={updateStatus.state === 'success' && updateStatus.target_version === versionInfo.current_version ? `当前已是 v${versionInfo.current_version}` : (updateStatus.message || '正在处理更新')} description={<Space wrap><span>{updateStatus.target_version ? `目标版本：v${updateStatus.target_version}` : ''}</span>{updateStatus.state === 'success' && updateStatus.target_version !== versionInfo.current_version && <span>页面即将刷新</span>}</Space>} />}
    </div>}
    {historyPanel}
  </section>
}
