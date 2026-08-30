import {
  Alert,
  Button,
  Card,
  Checkbox,
  Input,
  Progress,
  Select,
  Space,
  Spin,
  Table,
  Typography,
  message,
} from "antd";
import {
  CheckCircle2,
  Download,
  Eraser,
  ListPlus,
  Pause,
  Play,
  Settings2,
  ShieldCheck,
  Trash2,
  XCircle,
} from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";

type LocalDirectoryHandle = { name: string; getFileHandle: (name: string, options?: { create?: boolean }) => Promise<{ createWritable: () => Promise<{ write: (data: Blob) => Promise<void>; close: () => Promise<void> }> }> };
let selectedDownloadDirectory: LocalDirectoryHandle | null = null;

type Settings = {
  quality: string;
  download_type: string;
  save_thumbnail: boolean;
  transcode_enabled: boolean;
  transcode_quality: string;
  keep_original: boolean;
  cookies_enabled: boolean;
  cookies_set: boolean;
  proxy_enabled: boolean;
  proxy_url?: string | null;
  proxy_auto_check: boolean;
  output_dir: string;
};
type Task = {
  id: number;
  url: string;
  title: string;
  duration: string;
  estimated_size: string;
  status: string;
  progress: number;
  error?: string | null;
};
type ProxyStatus = {
  ip: string;
  country: string;
  country_code: string;
  youtube_supported: boolean;
  message: string;
};
type CookieStatus = { configured: boolean; valid: boolean; message: string };
const defaults: Settings = {
  quality: "1080",
  download_type: "video_audio",
  save_thumbnail: true,
  transcode_enabled: false,
  transcode_quality: "balanced",
  keep_original: true,
  cookies_enabled: true,
  cookies_set: false,
  proxy_enabled: false,
  proxy_url: "",
  proxy_auto_check: true,
  output_dir: "downloads",
};

export default function DownloadPage({
  mode = "content",
}: {
  mode?: "config" | "content";
}) {
  const isConfig = mode === "config";
  const [settings, setSettings] = useState<Settings>(defaults);
  const [cookies, setCookies] = useState("");
  const [loading, setLoading] = useState(isConfig);
  const [saving, setSaving] = useState(false);
  const [cookieTesting, setCookieTesting] = useState(false);
  const [links, setLinks] = useState("");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [taskLoading, setTaskLoading] = useState(false);
  const [proxyStatus, setProxyStatus] = useState<ProxyStatus | null>(null);
  const [proxyChecking, setProxyChecking] = useState(false);
  const [proxyError, setProxyError] = useState("");
  const [proxyVerified, setProxyVerified] = useState(false);
  const [cookieStatus, setCookieStatus] = useState<CookieStatus | null>(null);
  const [cookiesValid, setCookiesValid] = useState(false);
  const [localDirectoryName, setLocalDirectoryName] = useState("");
  useEffect(() => {
    if (!isConfig) return;
    void api<Settings>("/api/download/settings")
      .then((value) => {
        setSettings(value);
        void api<CookieStatus>("/api/download/cookies/status").then(setCookieStatus).catch(() => setCookieStatus(null));
      })
      .catch((cause) =>
        message.error(
          cause instanceof Error ? cause.message : "无法读取下载配置",
        ),
      )
      .finally(() => setLoading(false));
  }, [isConfig]);
  useEffect(() => {
    if (!isConfig) return;
    setProxyChecking(true);
    setProxyError("");
    void api<ProxyStatus>("/api/download/proxy/status")
      .then((value) => { setProxyStatus(value); setProxyError(""); })
      .catch((cause) => { setProxyStatus(null); setProxyError(cause instanceof Error ? cause.message : "无法完成服务器出口检测"); })
      .finally(() => setProxyChecking(false));
  }, [isConfig]);
  useEffect(() => {
    if (isConfig) return;
    const load = () =>
      void api<Task[]>("/api/download/tasks")
        .then(setTasks)
        .catch((cause) =>
          message.error(
            cause instanceof Error ? cause.message : "无法读取下载队列",
          ),
        );
    load();
    const timer = window.setInterval(load, 2500);
    return () => window.clearInterval(timer);
  }, [isConfig]);
  const update = <K extends keyof Settings>(key: K, value: Settings[K]) =>
    setSettings((current) => ({ ...current, [key]: value }));
  const save = async () => {
    if (settings.proxy_enabled && !proxyStatus?.youtube_supported && !proxyVerified) {
      message.warning("当前地区可能无法访问 YouTube，请先测试代理成功后再保存");
      return;
    }
    setSaving(true);
    try {
      const result = await api<Settings>("/api/download/settings", {
        method: "PUT",
        body: JSON.stringify({ ...settings, cookies: cookies.trim() || null }),
      });
      setSettings(result);
      setCookies("");
      message.success("下载配置已保存");
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };
  const testCookies = async () => {
    setCookieTesting(true);
    try {
      const result = await api<{ message: string }>(
        "/api/download/cookies/test",
        { method: "POST", body: JSON.stringify({ cookies }) },
      );
      message.success(result.message);
      setCookiesValid(true);
      setCookieStatus({ configured: true, valid: true, message: result.message });
    } catch (cause) {
      message.error(
        cause instanceof Error ? cause.message : "Cookies 测试失败",
      );
    } finally {
      setCookieTesting(false);
    }
  };
  const saveCookies = async () => {
    if (!cookiesValid || !cookies.trim()) return;
    setSaving(true);
    try {
      const result = await api<Settings>("/api/download/settings", { method: "PUT", body: JSON.stringify({ ...settings, cookies: cookies.trim() }) });
      setSettings(result);
      setCookies("");
      setCookiesValid(false);
      setCookieStatus({ configured: true, valid: true, message: "Cookies 已保存并加密存储" });
      message.success("Cookies 已保存");
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : "Cookies 保存失败");
    } finally { setSaving(false); }
  };
  const testProxy = async () => {
    if (!settings.proxy_url?.trim()) {
      message.warning("请先填写代理地址");
      return;
    }
    setCookieTesting(true);
    try {
      const result = await api<{ message: string }>(
        "/api/download/proxy/test",
        {
          method: "POST",
          body: JSON.stringify({ proxy_url: settings.proxy_url.trim() }),
        },
      );
      message.success(result.message);
      setProxyVerified(true);
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : "代理测试失败");
    } finally {
      setCookieTesting(false);
    }
  };
  const clearCookies = async () => {
    setSaving(true);
    try {
      const result = await api<Settings>("/api/download/settings", {
        method: "PUT",
        body: JSON.stringify({ ...settings, cookies: "" }),
      });
      setSettings(result);
      setCookies("");
      message.success("Cookies 已清除");
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : "清除失败");
    } finally {
      setSaving(false);
    }
  };
  const addTasks = async () => {
    const urls = links
      .split(/\r?\n/)
      .map((url) => url.trim())
      .filter(Boolean);
    if (!urls.length) return;
    setTaskLoading(true);
    try {
      const result = await api<Task[]>("/api/download/tasks", {
        method: "POST",
        body: JSON.stringify({ urls }),
      });
      setTasks((current) => [...result, ...current]);
      setLinks("");
      message.success(`已添加 ${result.length} 个下载任务`);
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : "添加任务失败");
    } finally {
      setTaskLoading(false);
    }
  };
  const chooseLocalDirectory = async () => {
    const picker = (window as Window & { showDirectoryPicker?: () => Promise<LocalDirectoryHandle> }).showDirectoryPicker;
    if (!picker) { message.info("当前浏览器不支持选择文件夹，将使用浏览器默认下载目录"); return; }
    try {
      selectedDownloadDirectory = await picker();
      setLocalDirectoryName(selectedDownloadDirectory.name);
      message.success(`已选择本地保存位置：${selectedDownloadDirectory.name}`);
    } catch (cause) { if ((cause as DOMException)?.name !== "AbortError") message.error("无法访问所选本地文件夹"); }
  };
  const downloadTaskFile = async (task: Task) => {
    try {
      const response = await fetch(`/api/download/tasks/${task.id}/file`, { credentials: "same-origin" });
      if (!response.ok) throw new Error("下载文件获取失败");
      const blob = await response.blob();
      const filename = `vx-download-${task.id}.zip`;
      if (selectedDownloadDirectory) {
        const file = await selectedDownloadDirectory.getFileHandle(filename, { create: true });
        const writable = await file.createWritable(); await writable.write(blob); await writable.close();
        message.success("文件已保存到选择的本地文件夹");
      } else {
        const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename; anchor.click(); URL.revokeObjectURL(url);
      }
    } catch (cause) { message.error(cause instanceof Error ? cause.message : "下载文件失败"); }
  };
  const taskAction = async (
    task: Task,
    action: "start" | "pause" | "resume" | "cancel" | "delete",
  ) => {
    try {
      if (action === "delete") {
        await api<void>(`/api/download/tasks/${task.id}`, { method: "DELETE" });
        setTasks((current) => current.filter((item) => item.id !== task.id));
        setSelected((current) => current.filter((id) => id !== task.id));
      } else {
        const result = await api<Task>(
          `/api/download/tasks/${task.id}/${action}`,
          { method: "POST" },
        );
        setTasks((current) =>
          current.map((item) => (item.id === task.id ? result : item)),
        );
      }
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : "操作失败");
    }
  };
  const selectedTasks = tasks.filter((task) => selected.includes(task.id));
  const runSelected = (
    allowed: string[],
    action: "start" | "pause" | "resume" | "cancel" | "delete",
  ) =>
    selectedTasks
      .filter((task) => allowed.includes(task.status))
      .forEach((task) => void taskAction(task, action));
  const statusLabel: Record<string, string> = {
    queued: "排队中",
    downloading: "下载中",
    completed: "已完成",
    failed: "失败",
    cancelled: "已取消",
    paused: "已暂停",
  };
  const columns = [
    { title: "序号", dataIndex: "id", width: 70 },
    { title: "链接", dataIndex: "url", ellipsis: true },
    { title: "标题", dataIndex: "title", ellipsis: true },
    { title: "时长", dataIndex: "duration", width: 90 },
    { title: "预计大小", dataIndex: "estimated_size", width: 100 },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (status: string, task: Task) => (
        <span className={`download-status ${status}`}>
          {statusLabel[status] || status}
          {task.error && (
            <Typography.Text type="danger" title={task.error}>
              {" "}
              *
            </Typography.Text>
          )}
        </span>
      ),
    },
    {
      title: "进度",
      dataIndex: "progress",
      width: 150,
      render: (progress: number) => (
        <Progress percent={Math.round(progress)} size="small" />
      ),
    },
  ];
  if (isConfig && loading)
    return (
      <div className="page-loading">
        <Spin size="large" />
      </div>
    );
  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <Typography.Title level={2}>
            {isConfig ? "下载配置" : "下载内容"}
          </Typography.Title>
          <Typography.Text type="secondary">
            {isConfig
              ? "配置视频下载质量、兼容性、Cookies 和代理"
              : "探索、添加和管理视频下载任务"}
          </Typography.Text>
        </div>
      </div>
      {!isConfig ? (
        <div className="download-content">
          <Card className="download-content-group" title="探索与下载">
            <Button
              className="browser-launch"
              type="primary"
              icon={<Download size={17} />}
              onClick={() =>
                window.open(
                  "https://www.youtube.com/",
                  "_blank",
                  "noopener,noreferrer",
                )
              }
            >
              启动 YouTube 内容浏览器
            </Button>
            <div className="download-link-row">
              <Typography.Text>手动/批量输入链接</Typography.Text>
              <Input.TextArea
                value={links}
                onChange={(event) => setLinks(event.target.value)}
                rows={4}
                placeholder="每行输入一个 YouTube 视频或播放列表链接"
              />
              <Button
                icon={<ListPlus size={16} />}
                loading={taskLoading}
                onClick={() => void addTasks()}
              >
                添加
              </Button>
            </div>
          </Card>
          <Card className="download-content-group" title="下载队列">
            {tasks.length ? (
              <Table
                rowKey="id"
                size="small"
                pagination={false}
                rowSelection={{
                  selectedRowKeys: selected,
                  onChange: (keys) => setSelected(keys as number[]),
                }}
                columns={columns}
                dataSource={tasks}
                scroll={{ x: 900 }}
              />
            ) : (
              <div className="download-empty">
                <Download size={40} strokeWidth={1.5} />
                <Typography.Text>暂无下载任务</Typography.Text>
              </div>
            )}
          </Card>
          <Card className="download-content-group" title="下载操作">
            <div className="download-path-row">
              <Typography.Text>下载路径</Typography.Text>
              <Input value={`/app/data/${settings.output_dir}`} readOnly />
              <Typography.Text type="secondary">
                在下载配置中修改
              </Typography.Text>
            </div>
            <Space wrap>
              <Button
                type="primary"
                icon={<Play size={16} />}
                disabled={!selected.length}
                onClick={() => runSelected(["queued", "failed"], "start")}
              >
                开始下载
              </Button>
              <Button
                icon={<Pause size={16} />}
                disabled={
                  !selectedTasks.some((task) => task.status === "downloading")
                }
                onClick={() => runSelected(["downloading"], "pause")}
              >
                暂停
              </Button>
              <Button
                icon={<Play size={16} />}
                disabled={
                  !selectedTasks.some((task) => task.status === "paused")
                }
                onClick={() => runSelected(["paused"], "resume")}
              >
                继续
              </Button>
              <Button
                icon={<XCircle size={16} />}
                disabled={!selected.length}
                onClick={() => runSelected(["queued", "downloading"], "cancel")}
              >
                取消
              </Button>
              <Button
                icon={<Trash2 size={16} />}
                disabled={!selected.length}
                onClick={() =>
                  runSelected(["completed", "failed", "cancelled"], "delete")
                }
              >
                删除选中
              </Button>
              <Button
                icon={<Eraser size={16} />}
                onClick={() =>
                  tasks
                    .filter((task) =>
                      ["completed", "failed", "cancelled"].includes(
                        task.status,
                      ),
                    )
                    .forEach((task) => void taskAction(task, "delete"))
                }
              >
                清空列表
              </Button>
              {selectedTasks.filter((task) => task.status === "completed").map((task) => <Button key={`download-${task.id}`} icon={<Download size={16} />} onClick={() => void downloadTaskFile(task)}>下载 {task.title || `任务 ${task.id}`}</Button>)}
            </Space>
          </Card>
        </div>
      ) : (
        <div className="download-config">
          <Card
            className="download-config-group"
            title={
              <span>
                <Settings2 size={18} /> 下载选项
              </span>
            }
          >
            <div className="download-settings-grid">
              <label>
                视频质量
                <Select
                  value={settings.quality}
                  onChange={(value) => update("quality", value)}
                  options={[
                    ["best", "最高质量"],
                    ["2160", "2160p (4K)"],
                    ["1440", "1440p"],
                    ["1080", "1080p"],
                    ["720", "720p"],
                    ["480", "480p"],
                    ["360", "360p"],
                  ].map(([value, label]) => ({ value, label }))}
                />
              </label>
              <label>
                下载类型
                <Select
                  value={settings.download_type}
                  onChange={(value) => update("download_type", value)}
                  options={[
                    ["video_audio", "视频+音频"],
                    ["video", "仅视频"],
                    ["audio", "仅音频"],
                  ].map(([value, label]) => ({ value, label }))}
                />
              </label>
              <Checkbox
                checked={settings.save_thumbnail}
                onChange={(event) =>
                  update("save_thumbnail", event.target.checked)
                }
              >
                同时保存高清封面图
              </Checkbox>
            </div>
          </Card>
          <Card className="download-config-group" title="视频兼容性转码">
            <Checkbox
              checked={settings.transcode_enabled}
              onChange={(event) =>
                update("transcode_enabled", event.target.checked)
              }
            >
              下载完成后转为高兼容 MP4（H.264 + AAC）
            </Checkbox>
            <label className="download-inline-field">
              转码质量
              <Select
                disabled={!settings.transcode_enabled}
                value={settings.transcode_quality}
                onChange={(value) => update("transcode_quality", value)}
                options={[
                  ["fast", "快速"],
                  ["balanced", "平衡（推荐）"],
                  ["high", "高质量"],
                ].map(([value, label]) => ({ value, label }))}
              />
            </label>
            <Checkbox
              disabled={!settings.transcode_enabled}
              checked={settings.keep_original}
              onChange={(event) =>
                update("keep_original", event.target.checked)
              }
            >
              转码成功后保留原文件
            </Checkbox>
            <Typography.Paragraph type="secondary">
              需要系统安装 ffmpeg，转码只在下载完成后执行。
            </Typography.Paragraph>
          </Card>
          <Card
            className="download-config-group"
            title={
              <span>
                <ShieldCheck size={18} /> Cookies 设置
              </span>
            }
          >
            <Checkbox
              checked={settings.cookies_enabled}
              onChange={(event) =>
                update("cookies_enabled", event.target.checked)
              }
            >
              使用 Cookies（解决验证问题）
            </Checkbox>
            {settings.cookies_set && (
              <Alert type="success" showIcon message="已保存一份加密 Cookies" />
            )}
            {cookieStatus && (
              <Alert type={cookieStatus.valid ? "success" : "warning"} showIcon message={cookieStatus.message} style={{ marginBottom: 12 }} />
            )}
            <Input.TextArea
              value={cookies}
              onChange={(event) => { setCookies(event.target.value); setCookiesValid(false); }}
              disabled={!settings.cookies_enabled}
              rows={7}
              placeholder="请粘贴 Netscape 格式 Cookies 文本。Cookies 仅保存在本地并加密存储。"
            />
            <Space wrap>
              <Button
                icon={<CheckCircle2 size={16} />}
                loading={cookieTesting}
                disabled={!cookies.trim()}
                onClick={() => void testCookies()}
              >
                测试 Cookies
              </Button>
              <Button type="primary" disabled={!cookiesValid} loading={saving} onClick={() => void saveCookies()}>
                保存 Cookies
              </Button>
              <Button
                icon={<Eraser size={16} />}
                disabled={!settings.cookies_set && !cookies}
                onClick={() => void clearCookies()}
              >
                清除 Cookies
              </Button>
            </Space>
          </Card>
          <Card className="download-config-group" title="代理设置">
            {proxyChecking && <Alert showIcon type="info" message="正在检测服务器出口 IP 和地区，请稍候..." style={{ marginBottom: 12 }} />}
            {proxyError && <Alert showIcon type="error" message="服务器出口检测失败" description={`${proxyError}。你仍可以填写代理地址并点击“测试代理”，测试成功后再保存。`} style={{ marginBottom: 12 }} />}
            {proxyStatus && (
              <Alert
                showIcon
                type={proxyStatus.youtube_supported ? "success" : "warning"}
                message={`${proxyStatus.message}（${proxyStatus.country}，${proxyStatus.ip}）`}
                style={{ marginBottom: 12 }}
              />
            )}
            <Checkbox
              checked={settings.proxy_enabled}
              onChange={(event) =>
                update("proxy_enabled", event.target.checked)
              }
            >
              启用代理
            </Checkbox>
            <Input
              value={settings.proxy_url || ""}
              disabled={!settings.proxy_enabled}
              onChange={(event) => update("proxy_url", event.target.value)}
              placeholder="例如 http://127.0.0.1:7890"
            />
            <Button
              icon={<CheckCircle2 size={16} />}
              loading={cookieTesting}
              disabled={!settings.proxy_enabled || !settings.proxy_url?.trim()}
              onClick={() => void testProxy()}
            >
              测试代理
            </Button>
            <Checkbox
              checked={settings.proxy_auto_check}
              onChange={(event) =>
                update("proxy_auto_check", event.target.checked)
              }
            >
              启动时自动检测代理
            </Checkbox>
          </Card>
          <Card className="download-config-group" title="保存位置">
            <div className="local-save-picker"><Button type="primary" icon={<Download size={16} />} onClick={() => void chooseLocalDirectory()}>选择本地文件夹</Button><Typography.Text type="secondary">{localDirectoryName ? `已选择：${localDirectoryName}` : "尚未选择，将使用浏览器默认下载目录"}</Typography.Text></div>
            <Alert type="info" showIcon message="下载任务在服务器端执行。任务完成后，在“下载内容”中点击“下载”即可保存到这里选择的本地文件夹；不支持目录选择的浏览器会使用其默认下载目录。" style={{ marginTop: 12 }} />
          </Card>
          <div className="download-config-actions">
            <Button type="primary" loading={saving} onClick={() => void save()}>
              保存下载配置
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
