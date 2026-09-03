import { useEffect, useMemo, useState } from "react";
import { Alert, Button, Checkbox, Empty, Space, Switch, Typography, message } from "antd";
import { Save } from "lucide-react";
import { api } from "../api";

type MenuNode = { key: string; label: string; children?: MenuNode[] };
const MENU_TREE: MenuNode[] = [
  { key: "/users", label: "用户管理", children: [{ key: "/users/accounts", label: "视频号管理" }, { key: "/users/local", label: "本地用户" }] },
  { key: "/ai-chat-menu", label: "AI 速问", children: [{ key: "/ai-chat/config", label: "AI 配置" }, { key: "/ai-chat", label: "AI 聊天" }] },
  { key: "/analysis", label: "数据分析", children: [{ key: "/analysis/dashboard", label: "数据概览" }, { key: "/analysis/videos", label: "视频贡献" }, { key: "/analysis/imports", label: "数据导入" }, { key: "/analysis/ai", label: "AI 建议" }] },
  { key: "/download", label: "视频下载", children: [{ key: "/download/config", label: "下载配置" }, { key: "/download/content", label: "下载内容" }] },
  { key: "/settings", label: "系统设置" },
  { key: "/backups", label: "加密备份" },
  { key: "/updates", label: "在线更新" },
  { key: "/usage", label: "使用说明", children: [{ key: "/usage/levels", label: "等级说明" }] },
  { key: "/about", label: "关于开发", children: [{ key: "/about/architecture", label: "项目架构" }, { key: "/about/technology", label: "开发技术" }, { key: "/about/team", label: "关于我们" }] },
];

export default function MenuVisibilityPage() {
  const [values, setValues] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const descendants = (node: MenuNode): string[] => node.children?.flatMap(descendants) || [node.key];
  useEffect(() => { void api<Record<string, boolean>>("/api/settings/menu-visibility").then(setValues).catch((cause) => message.error(cause instanceof Error ? cause.message : "加载菜单配置失败")).finally(() => setLoading(false)); }, []);
  const setNode = (node: MenuNode, visible: boolean) => setValues((current) => ({ ...current, ...Object.fromEntries(descendants(node).map((key) => [key, visible])) }));
  const allKeys = useMemo(() => MENU_TREE.flatMap(descendants), []);
  const incomplete = allKeys.length > 0 && Object.keys(values).length > 0 && !allKeys.every((key) => values[key] !== undefined);
  return <div className="page">
    <div className="page-heading"><div><Typography.Title level={2}>菜单显示管理</Typography.Title><Typography.Text type="secondary">控制普通用户侧边栏菜单的显示与隐藏，管理员始终可以看到完整菜单。</Typography.Text></div><Button type="primary" icon={<Save size={16} />} loading={saving} disabled={loading || incomplete} onClick={() => { setSaving(true); void api<Record<string, boolean>>("/api/settings/menu-visibility", { method: "PUT", body: JSON.stringify(values) }).then(setValues).then(() => message.success("菜单显示配置已保存")).catch((cause) => message.error(cause instanceof Error ? cause.message : "保存菜单配置失败")).finally(() => setSaving(false)); }}>保存配置</Button></div>
    <section className="section-band menu-visibility-panel"><Alert type="info" showIcon message="绿色开关表示禁止显示" description="一级菜单下的全部子菜单被禁止时，普通用户侧边栏会自动隐藏该一级菜单；部分禁止时显示半选状态。" />
      {loading ? <div className="page-loading"><span>正在加载</span></div> : <div className="menu-visibility-tree">{MENU_TREE.map((node) => { const keys = descendants(node); const hidden = keys.filter((key) => values[key] === false); const checked = hidden.length === keys.length; const indeterminate = hidden.length > 0 && hidden.length < keys.length; return <div className="menu-visibility-group" key={node.key}>{node.children ? <><div className="menu-visibility-row menu-visibility-parent"><Checkbox checked={checked} indeterminate={indeterminate} onChange={(event) => setNode(node, event.target.checked)}>{node.label}</Checkbox><Typography.Text type="secondary">{indeterminate ? "部分隐藏" : checked ? "全部隐藏" : "全部显示"}</Typography.Text></div>{node.children.map((child) => <div className="menu-visibility-row menu-visibility-child" key={child.key}><span>{child.label}</span><Switch checked={values[child.key] === false} checkedChildren="禁止显示" unCheckedChildren="显示" onChange={(hiddenState) => setValues((current) => ({ ...current, [child.key]: !hiddenState }))} /></div>)}</> : <div className="menu-visibility-row menu-visibility-parent"><span>{node.label}</span><Switch checked={values[node.key] === false} checkedChildren="禁止显示" unCheckedChildren="显示" onChange={(hiddenState) => setValues((current) => ({ ...current, [node.key]: !hiddenState }))} /></div>}</div>})}</div>}
      {!loading && !MENU_TREE.length && <Empty description="暂无菜单" />}
    </section>
  </div>;
}
