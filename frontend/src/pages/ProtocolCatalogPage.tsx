import { useEffect, useState } from "react";
import { Alert, Button, Card, Input, Modal, Space, Tag, Typography, message } from "antd";
import { Download, RefreshCw, RotateCcw, Save, Upload } from "lucide-react";
import { api } from "../api";

type CatalogHistory = { filename: string; updated_at: string };
type CatalogResponse = { catalog: Record<string, unknown>; builtin_catalog?: Record<string, unknown>; source: "builtin" | "custom"; updated_at?: string | null; history?: CatalogHistory[] };

const catalogCounts = (catalog: Record<string, unknown> | undefined) => {
  const providers = catalog?.providers && typeof catalog.providers === "object" ? Object.values(catalog.providers as Record<string, Record<string, unknown>>) : [];
  const models = providers.reduce((total: number, provider) => total + Object.values((provider.models as Record<string, unknown>) || {}).reduce((count: number, items) => count + (Array.isArray(items) ? items.length : 0), 0), 0);
  const protocols = providers.reduce((total: number, provider) => total + Object.values((provider.protocols as Record<string, unknown>) || {}).reduce((count: number, items) => count + (Array.isArray(items) ? items.length : 0), 0), 0);
  return { providers: providers.length, models, protocols };
};

export default function ProtocolCatalogPage() {
  const [value, setValue] = useState("");
  const [source, setSource] = useState<CatalogResponse["source"]>("builtin");
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [history, setHistory] = useState<CatalogHistory[]>([]);
  const [builtinCatalog, setBuiltinCatalog] = useState<Record<string, unknown>>();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const response = await api<CatalogResponse>("/api/ai/protocol-catalog");
      setValue(JSON.stringify(response.catalog, null, 2));
      setSource(response.source);
      setUpdatedAt(response.updated_at || null);
      setHistory(response.history || []);
      setBuiltinCatalog(response.builtin_catalog);
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : "协议目录加载失败");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { void load(); }, []);

  const save = async () => {
    setSaving(true);
    try {
      const catalog = JSON.parse(value) as Record<string, unknown>;
      const response = await api<CatalogResponse>("/api/ai/protocol-catalog", { method: "PUT", body: JSON.stringify({ catalog }) });
      setValue(JSON.stringify(response.catalog, null, 2));
      setSource("custom");
      setUpdatedAt(response.updated_at || null);
      setHistory(response.history || []);
      setBuiltinCatalog(response.builtin_catalog);
      message.success("协议目录已保存，后续请求将使用新目录");
    } catch (cause) {
      message.error(cause instanceof SyntaxError ? "JSON 格式无效，请检查括号和逗号" : cause instanceof Error ? cause.message : "协议目录保存失败");
    } finally {
      setSaving(false);
    }
  };

  const importFile = (file: File) => {
    const reader = new FileReader();
    reader.onload = () => setValue(String(reader.result || ""));
    reader.readAsText(file, "utf-8");
  };

  const exportFile = () => {
    const blob = new Blob([value], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "ai_protocols.json";
    link.click();
    URL.revokeObjectURL(url);
  };

  const reset = async () => {
    setSaving(true);
    try {
      await api<void>("/api/ai/protocol-catalog", { method: "DELETE" });
      await load();
      message.success("已恢复内置协议目录");
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : "恢复内置目录失败");
    } finally {
      setSaving(false);
    }
  };

  const restore = async (filename: string) => {
    setSaving(true);
    try {
      const response = await api<CatalogResponse>(`/api/ai/protocol-catalog/history/${encodeURIComponent(filename)}`, { method: "POST" });
      setValue(JSON.stringify(response.catalog, null, 2));
      setSource("custom");
      setUpdatedAt(response.updated_at || null);
      setHistory(response.history || []);
      message.success("历史协议目录已恢复");
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : "历史目录恢复失败");
    } finally {
      setSaving(false);
    }
  };

  return <div className="page protocol-catalog-page">
    <div className="page-heading"><div><Typography.Title level={2}>AI 协议目录管理</Typography.Title><Typography.Text type="secondary">管理员可维护厂商模型和请求协议。协议目录不保存 API Key。{updatedAt ? ` 最后修改：${new Date(updatedAt).toLocaleString()}` : ""}</Typography.Text></div><Tag color={source === "custom" ? "blue" : "default"}>{source === "custom" ? "自定义覆盖" : "内置目录"}</Tag></div>
    <Alert type="info" showIcon message="保存前会执行结构校验；标记为“暂未接入”的协议只作为目录记录，不能用于实际请求。" description={`内置目录：${catalogCounts(builtinCatalog).providers} 个厂商、${catalogCounts(builtinCatalog).models} 个模型、${catalogCounts(builtinCatalog).protocols} 个协议。当前编辑内容：${(() => { try { return JSON.stringify(catalogCounts(JSON.parse(value) as Record<string, unknown>)); } catch { return "JSON 待校验"; } })()}`} />
    <Card style={{ marginTop: 16 }} loading={loading}>
      <Space wrap style={{ marginBottom: 12 }}>
        <Button icon={<RefreshCw size={15} />} onClick={() => void load()}>重新读取</Button>
        <Button icon={<Upload size={15} />} onClick={() => { const input = document.createElement("input"); input.type = "file"; input.accept = ".json,application/json"; input.onchange = () => { const file = input.files?.[0]; if (file) importFile(file); }; input.click(); }}>导入 JSON</Button>
        <Button icon={<Download size={15} />} onClick={exportFile}>导出 JSON</Button>
        <Button icon={<RotateCcw size={15} />} onClick={() => Modal.confirm({ title: "恢复内置协议目录？", content: "当前自定义覆盖将停止生效，但历史版本仍会保留。", okText: "确认恢复", cancelText: "取消", onOk: reset })} loading={saving}>恢复内置目录</Button>
        <Button type="primary" icon={<Save size={15} />} onClick={() => void save()} loading={saving}>校验并保存</Button>
      </Space>
      <Input.TextArea value={value} onChange={(event) => setValue(event.target.value)} autoSize={{ minRows: 24, maxRows: 42 }} spellCheck={false} />
    </Card>
    {history.length > 0 && <Card title="历史版本" style={{ marginTop: 16 }}>
      {history.map((item) => <div className="update-history-row" key={item.filename}><span>{new Date(item.updated_at).toLocaleString()}<small>{item.filename}</small></span><Button size="small" onClick={() => Modal.confirm({ title: "恢复此历史版本？", okText: "恢复", cancelText: "取消", onOk: () => restore(item.filename) })}>恢复</Button></div>)}
    </Card>}
  </div>;
}
