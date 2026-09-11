import { useEffect, useState } from "react";
import { Alert, Button, Descriptions, Form, Input, InputNumber, Select, Tag, Typography, message } from "antd";
import { Database, RefreshCw } from "lucide-react";
import { api } from "../api";

type DatabaseInfo = { engine: string; database_url: string; data_dir: string; active: boolean; sqlite_path: string; postgresql: { configured: boolean; endpoint: string } };

export default function DatabaseSettingsPage() {
  const [info, setInfo] = useState<DatabaseInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [testing, setTesting] = useState(false);
  const [form] = Form.useForm();
  const load = async () => { setLoading(true); try { setInfo(await api<DatabaseInfo>("/api/settings/database")); } catch (cause) { message.error(cause instanceof Error ? cause.message : "数据库信息加载失败"); } finally { setLoading(false); } };
  useEffect(() => { void load(); }, []);
  const test = async () => { setTesting(true); try { const result = await api<{ message: string }>("/api/settings/database/test", { method: "POST" }); message.success(result.message); } catch (cause) { message.error(cause instanceof Error ? cause.message : "数据库连接测试失败"); } finally { setTesting(false); } };
  return <div className="page"><div className="page-heading"><div><Typography.Title level={2}>数据库设置</Typography.Title><Typography.Text type="secondary">查看当前数据库、数据目录和连接状态。切换数据库前必须先完成备份和迁移验证。</Typography.Text></div><Button icon={<RefreshCw size={16} />} loading={loading} onClick={() => void load()}>刷新状态</Button></div>
    <section className="section-band database-settings-page"><div className="section-heading"><div><Typography.Title level={3}>当前数据库</Typography.Title><Typography.Text type="secondary">当前运行中的数据库配置为实际生效配置。</Typography.Text></div><Tag color={info?.active ? "green" : "default"}>{info?.active ? "正在使用" : "未知"}</Tag></div>
      {info && <Descriptions bordered column={1} items={[{ key: "engine", label: "数据库类型", children: info.engine }, { key: "url", label: "连接信息", children: info.database_url }, { key: "data", label: "数据目录", children: info.data_dir }, { key: "sqlite", label: "SQLite 文件", children: info.sqlite_path }, { key: "pg", label: "PostgreSQL 配置", children: info.postgresql.configured ? `已配置：${info.postgresql.endpoint}` : "未启用" }]} />}
      <Button type="primary" icon={<Database size={16} />} loading={testing} onClick={() => void test()}>测试当前数据库连接</Button>
    </section>
    <section className="section-band"><Typography.Title level={3}>数据库切换准备</Typography.Title><Alert type="info" showIcon message="数据库切换不是普通参数修改" description="当前版本先提供连接状态检查。正式切换 SQLite 与 PostgreSQL 前，应先创建备份、验证目标数据库连接，再执行数据迁移和切换，避免应用与数据分离。" /><Form form={form} layout="vertical" className="database-connection-form"><Form.Item label="目标数据库类型"><Select disabled options={[{ value: "sqlite", label: "SQLite（单机默认）" }, { value: "postgresql", label: "PostgreSQL（多人/长期运行）" }]} placeholder="当前仅展示，切换流程将在迁移工具完成后开放" /></Form.Item><Form.Item label="PostgreSQL 主机"><Input disabled placeholder="由部署配置 VX_DATABASE_URL 管理" /></Form.Item><Form.Item label="PostgreSQL 端口"><InputNumber disabled style={{ width: 190 }} placeholder="5432" /></Form.Item></Form></section>
  </div>;
}
