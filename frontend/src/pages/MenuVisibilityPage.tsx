import { useEffect, useMemo, useState } from "react";
import { Alert, Button, Checkbox, Input, Switch, Tag, Typography, message } from "antd";
import { ArrowDown, ArrowUp, RotateCcw, Save } from "lucide-react";
import { api } from "../api";

type MenuNode = { key: string; label: string; configurable: boolean; children?: MenuNode[] };
const MENU_TREE: MenuNode[] = [
  { key: "/users", label: "用户管理", configurable: true, children: [{ key: "/users/accounts", label: "视频号管理", configurable: true }, { key: "/users/local", label: "注册用户管理（管理员专用）", configurable: false }] },
  { key: "/ai-chat-menu", label: "AI 速问", configurable: true, children: [{ key: "/ai-chat/config", label: "AI 配置（管理员专用）", configurable: false }, { key: "/ai-chat", label: "AI 聊天", configurable: true }] },
  { key: "/analysis", label: "数据分析", configurable: true, children: [{ key: "/analysis/dashboard", label: "数据概览", configurable: true }, { key: "/analysis/videos", label: "视频贡献", configurable: true }, { key: "/analysis/imports", label: "数据导入", configurable: true }, { key: "/analysis/ai", label: "AI 建议", configurable: true }] },
  { key: "/download", label: "视频下载", configurable: true, children: [{ key: "/download/config", label: "下载配置", configurable: true }, { key: "/download/content", label: "下载内容", configurable: true }] },
  { key: "/settings", label: "系统设置（管理员专用）", configurable: false, children: [{ key: "/settings/auth", label: "基础系统设置（管理员专用）", configurable: false }, { key: "/settings/database", label: "数据库设置（管理员专用）", configurable: false }, { key: "/settings/menu", label: "菜单显示管理（管理员专用）", configurable: false }] },
  { key: "/backups", label: "加密备份（管理员专用）", configurable: false },
  { key: "/updates", label: "在线更新（管理员专用）", configurable: false },
  { key: "/usage", label: "使用说明", configurable: true, children: [{ key: "/usage/levels", label: "等级说明", configurable: true }] },
  { key: "/about", label: "关于开发", configurable: true, children: [{ key: "/about/architecture", label: "项目架构", configurable: true }, { key: "/about/technology", label: "开发技术", configurable: true }, { key: "/about/team", label: "关于我们", configurable: true }] },
];
const descendants = (node: MenuNode): MenuNode[] => node.children?.flatMap(descendants) || [node];
const configurableDescendants = (node: MenuNode) => descendants(node).filter((item) => item.configurable);
const DEFAULT_ORDER: Record<string, string[]> = {
  "/users": ["/users/accounts", "/users/local"], "/ai-chat-menu": ["/ai-chat/config", "/ai-chat"], "/settings": ["/settings/auth", "/settings/database", "/settings/menu"], "/analysis": ["/analysis/dashboard", "/analysis/videos", "/analysis/imports", "/analysis/ai"], "/download": ["/download/config", "/download/content"], "/usage": ["/usage/levels"], "/about": ["/about/architecture", "/about/technology", "/about/team"],
};

export default function MenuVisibilityPage() {
  const [values, setValues] = useState<Record<string, boolean>>({});
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [order, setOrder] = useState<Record<string, string[]>>(DEFAULT_ORDER);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const configurableKeys = useMemo(() => MENU_TREE.flatMap(configurableDescendants).map((node) => node.key), []);
  useEffect(() => {
    void Promise.all([api<Record<string, boolean>>("/api/settings/menu-visibility"), api<Record<string, string>>("/api/settings/menu-labels"), api<Record<string, string[]>>("/api/settings/menu-order")]).then(([visibility, names, ordering]) => { setValues(visibility); setLabels(names); setOrder(ordering); }).catch((cause) => message.error(cause instanceof Error ? cause.message : "加载菜单配置失败")).finally(() => setLoading(false));
  }, []);
  const setNode = (node: MenuNode, visible: boolean) => setValues((current) => ({ ...current, ...Object.fromEntries(configurableDescendants(node).map((item) => [item.key, visible])) }));
  const save = async () => {
    setSaving(true);
    try {
      const payload = Object.fromEntries(configurableKeys.map((key) => [key, values[key] !== false]));
      const [visibility, names, ordering] = await Promise.all([
        api<Record<string, boolean>>("/api/settings/menu-visibility", { method: "PUT", body: JSON.stringify(payload) }),
        api<Record<string, string>>("/api/settings/menu-labels", { method: "PUT", body: JSON.stringify(labels) }),
        api<Record<string, string[]>>("/api/settings/menu-order", { method: "PUT", body: JSON.stringify(order) }),
      ]);
      setValues(visibility); setLabels(names); setOrder(ordering); window.dispatchEvent(new Event("vx:menu-config-updated")); message.success("菜单显示、名称和顺序配置已保存");
    } catch (cause) { message.error(cause instanceof Error ? cause.message : "保存菜单配置失败"); }
    finally { setSaving(false); }
  };
  const labelEditor = (node: MenuNode) => <><Input className="menu-visibility-label-input" size="small" value={labels[node.key] || ""} maxLength={20} placeholder="留空使用默认名称" onChange={(event) => setLabels((current) => ({ ...current, [node.key]: event.target.value }))} /><Button className="menu-visibility-label-reset" type="text" size="small" icon={<RotateCcw size={14} />} title="恢复默认名称" aria-label={`恢复${node.label}默认名称`} disabled={!labels[node.key]} onClick={() => setLabels((current) => ({ ...current, [node.key]: "" }))} /></>;
  const moveChild = (parent: string, child: string, offset: number) => setOrder((current) => { const next = [...(current[parent] || [])]; const index = next.indexOf(child); const target = index + offset; if (index < 0 || target < 0 || target >= next.length) return current; [next[index], next[target]] = [next[target], next[index]]; return { ...current, [parent]: next }; });
  const renderNode = (node: MenuNode) => {
    const configurable = configurableDescendants(node);
    const hidden = configurable.filter((item) => values[item.key] === false).length;
    const checked = configurable.length > 0 && hidden === configurable.length;
    const indeterminate = hidden > 0 && hidden < configurable.length;
    return <div className="menu-visibility-group" key={node.key}>
      <div className="menu-visibility-row menu-visibility-parent">
        <Checkbox className={checked ? "menu-visibility-hidden-checkbox" : undefined} disabled={!configurable.length} checked={checked} indeterminate={indeterminate} onChange={(event) => setNode(node, event.target.checked)}>{node.label}</Checkbox>
        <span className="menu-visibility-status"><Tag color={node.configurable ? "blue" : "default"}>{node.configurable ? "可配置" : "不可配置"}</Tag>{configurable.length > 0 && (indeterminate ? "部分隐藏" : checked ? "全部隐藏" : "全部显示")}</span>
        {labelEditor(node)}
        <span className="menu-visibility-order-placeholder" aria-hidden="true" />
        <span className="menu-visibility-switch-placeholder" aria-hidden="true" />
      </div>
      {(node.children ? [...node.children].sort((left, right) => (order[node.key] || []).indexOf(left.key) - (order[node.key] || []).indexOf(right.key)) : []).map((child, index, children) => <div className="menu-visibility-row menu-visibility-child" key={child.key}>
        <span>{child.label}</span>
        <span className="menu-visibility-status"><Tag color={child.configurable ? "blue" : "default"}>{child.configurable ? "可配置" : "不可配置"}</Tag></span>
        {labelEditor(child)}<span className="menu-order-actions"><Button type="text" size="small" icon={<ArrowUp size={14} />} disabled={index === 0} title="上移" aria-label={`${child.label}上移`} onClick={() => moveChild(node.key, child.key, -1)} /><Button type="text" size="small" icon={<ArrowDown size={14} />} disabled={index === children.length - 1} title="下移" aria-label={`${child.label}下移`} onClick={() => moveChild(node.key, child.key, 1)} /></span><span className="menu-visibility-switch-cell">{child.configurable && <Switch className="menu-visibility-switch" checked={values[child.key] === false} checkedChildren="禁止显示" unCheckedChildren="显示" onChange={(hiddenValue) => setValues((current) => ({ ...current, [child.key]: !hiddenValue }))} />}</span>
      </div>)}
    </div>;
  };
  return <div className="page"><div className="page-heading"><div><Typography.Title level={2}>菜单显示管理</Typography.Title><Typography.Text type="secondary">仅管理员可配置普通用户侧边栏；管理员始终看到完整菜单。</Typography.Text></div><Button type="primary" icon={<Save size={16} />} loading={saving} disabled={loading} onClick={() => void save()}>保存配置</Button></div><section className="section-band menu-visibility-panel"><Alert type="info" showIcon message="绿色开关表示禁止显示" description="可配置项目会影响普通用户；标记为不可配置的菜单仅用于说明，不能被隐藏。名称留空时使用系统默认名称。" />{loading ? <div className="page-loading"><span>正在加载</span></div> : <div className="menu-visibility-tree">{MENU_TREE.map(renderNode)}</div>}</section></div>;
}
