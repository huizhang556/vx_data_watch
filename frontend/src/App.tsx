import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  Avatar,
  Button,
  Dropdown,
  Layout,
  Menu,
  Select,
  Space,
  Spin,
  Typography,
  type MenuProps,
} from "antd";
import {
  BarChart3,
  BookOpen,
  Bot,
  Cloud,
  Coffee,
  DatabaseBackup,
  Download,
  FileUp,
  Info,
  LogOut,
  MessageCircle,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Palette,
  RefreshCw,
  Settings,
  Sun,
  Leaf,
  Sparkles,
  UserRound,
  Video,
} from "lucide-react";
import {
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { api } from "./api";
import { AccountContext } from "./account";
import { useAuth } from "./auth";
import { THEME_LABELS, useTheme, type ThemeMode } from "./theme";
import type { Account } from "./types";

type UpdateCheck = { current_version: string; latest_version?: string; has_update: boolean };
const versionCompare = (left: string, right: string) => left.localeCompare(right, undefined, { numeric: true });

const AIPage = lazy(() => import("./pages/AIPage"));
const AIChatPage = lazy(() => import("./pages/AIChatPage"));
const BackupPage = lazy(() => import("./pages/BackupPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const ImportsPage = lazy(() => import("./pages/ImportsPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const UpdatesPage = lazy(() => import("./pages/UpdatesPage"));
const VideosPage = lazy(() => import("./pages/VideosPage"));
const DownloadPage = lazy(() => import("./pages/DownloadPage"));
const AboutPage = lazy(() => import("./pages/AboutPage"));
const ProfilePage = lazy(() => import("./pages/ProfilePage"));
const UsagePage = lazy(() => import("./pages/UsagePage"));

const items = [
  {
    key: "/users",
    icon: <UserRound size={19} />,
    label: "用户管理",
    children: [
      { key: "/users/accounts", label: "视频号账号" },
      { key: "/users/local", label: "本地用户" },
    ],
  },
  { key: "/ai-chat", icon: <Bot size={19} />, label: "AI 速问" },
  { key: "/accounts", icon: <Video size={19} />, label: "视频号账号" },
  {
    key: "/analysis",
    icon: <BarChart3 size={19} />,
    label: "数据分析",
    children: [
      {
        key: "/analysis/dashboard",
        icon: <BarChart3 size={17} />,
        label: "数据概览",
      },
      { key: "/analysis/videos", icon: <Video size={17} />, label: "视频贡献" },
      {
        key: "/analysis/imports",
        icon: <FileUp size={17} />,
        label: "数据导入",
      },
      { key: "/analysis/ai", icon: <Bot size={17} />, label: "AI 建议" },
    ],
  },
  {
    key: "/download",
    icon: <Download size={19} />,
    label: "视频下载",
    children: [
      { key: "/download/config", label: "下载配置" },
      { key: "/download/content", label: "下载内容" },
    ],
  },
  { key: "/settings", icon: <Settings size={19} />, label: "系统设置" },
  { key: "/backups", icon: <DatabaseBackup size={19} />, label: "加密备份" },
  { key: "/updates", icon: <RefreshCw size={19} />, label: "在线更新" },
  {
    key: "/usage",
    icon: <BookOpen size={19} />,
    label: "使用说明",
    children: [{ key: "/usage/levels", label: "等级说明" }],
  },
  {
    key: "/about",
    icon: <Info size={19} />,
    label: "关于开发",
    children: [
      { key: "/about/architecture", label: "项目架构" },
      { key: "/about/technology", label: "开发技术" },
      { key: "/about/team", label: "关于我们" },
    ],
  },
];

export default function App() {
  const { user, logout } = useAuth();
  const { theme, setTheme, toggleTheme } = useTheme();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [accountId, setAccountIdState] = useState<number>(
    () => Number(localStorage.getItem("vx_account_id")) || 0,
  );
  const [siderCollapsed, setSiderCollapsed] = useState(
    () => localStorage.getItem("vx_sider_collapsed") === "true",
  );
  const [openKeys, setOpenKeys] = useState<string[]>([]);
  const [updateCheck, setUpdateCheck] = useState<UpdateCheck | null>(null);
  const location = useLocation();
  const navigate = useNavigate();
  const checkUpdates = useCallback(async () => {
    if (user.role !== "admin") return;
    try {
      const result = await api<{ current_version: string; latest_version?: string; versions?: { version: string }[] }>("/api/system/versions");
      const latest = result.latest_version || result.versions?.[0]?.version;
      setUpdateCheck({ current_version: result.current_version, latest_version: latest, has_update: Boolean(latest && versionCompare(latest, result.current_version) > 0) });
    } catch {
      setUpdateCheck(null);
    }
  }, [user.role]);
  useEffect(() => { void checkUpdates(); }, [checkUpdates]);

  const reloadAccounts = useCallback(async () => {
    const rows = await api<Account[]>("/api/accounts");
    setAccounts(rows);
    setAccountIdState((current) => {
      const next = rows.some((row) => row.id === current)
        ? current
        : rows[0]?.id || 0;
      if (next) localStorage.setItem("vx_account_id", String(next));
      return next;
    });
  }, []);
  useEffect(() => {
    void reloadAccounts();
  }, [reloadAccounts]);

  const setAccountId = (id: number) => {
    setAccountIdState(id);
    localStorage.setItem("vx_account_id", String(id));
  };
  const account = accounts.find((row) => row.id === accountId) || null;
  const visibleItems =
    user.role === "admin"
      ? items
      : items.filter((item) =>
          [
            "/ai-chat",
            "/accounts",
            "/analysis",
            "/download",
            "/about",
            "/usage",
          ].includes(item.key),
        );
  const context = useMemo(
    () => ({ accounts, account, setAccountId, reloadAccounts }),
    [accounts, account, reloadAccounts],
  );
  const profileMenu: MenuProps["items"] = [
    { key: "profile", label: "个人资料" },
    { type: "divider" },
    { key: "logout", label: "退出软件", danger: true },
  ];
  const handleProfileMenu: MenuProps["onClick"] = ({ key }) => {
    if (key === "profile") navigate("/profile");
    if (key === "logout") void logout();
  };
  const themeIcons = {
    system: <Sun size={16} />,
    morning: <Sun size={16} />,
    night: <Moon size={16} />,
    rose: <Palette size={16} />,
    lavender: <Sparkles size={16} />,
    mist: <Cloud size={16} />,
    mint: <Leaf size={16} />,
    cream: <Coffee size={16} />,
  };
  const themeMenu: MenuProps["items"] = (["morning", "night", "rose", "lavender", "mist", "mint", "cream"] as ThemeMode[]).map((mode) => ({
    key: mode,
    icon: themeIcons[mode],
    label: THEME_LABELS[mode],
  }));
  const handleThemeMenu: MenuProps["onClick"] = ({ key }) => setTheme(key as ThemeMode);

  return (
    <AccountContext.Provider value={context}>
      <Layout
        className={`app-shell ${siderCollapsed ? "sider-collapsed" : ""}`}
      >
        <Layout.Sider
          className="desktop-sider"
          width={224}
          collapsedWidth={72}
          collapsed={siderCollapsed}
          theme="light"
        >
          <div className="brand">
            <span className="brand-mark small">VX</span>
            {!siderCollapsed && <span>视频号数据</span>}
          </div>
          <Button
            className="sider-toggle"
            type="text"
            icon={
              siderCollapsed ? (
                <PanelLeftOpen size={18} />
              ) : (
                <PanelLeftClose size={18} />
              )
            }
            title={siderCollapsed ? "展开侧边栏" : "收起侧边栏"}
            aria-label={siderCollapsed ? "展开侧边栏" : "收起侧边栏"}
            onClick={() =>
              setSiderCollapsed((value) => {
                localStorage.setItem("vx_sider_collapsed", String(!value));
                return !value;
              })
            }
          />
          <Menu
            mode="inline"
            inlineCollapsed={siderCollapsed}
            openKeys={siderCollapsed ? [] : openKeys}
            selectedKeys={[location.pathname]}
            items={visibleItems}
            onOpenChange={(keys) => setOpenKeys(keys.slice(-1))}
            onClick={({ key }) => navigate(key)}
          />
          <div className="sider-user">
            {!siderCollapsed && (
              <div>
                <Typography.Text strong>{user.username}</Typography.Text>
                <br />
                <Typography.Text type="secondary">{user.role}</Typography.Text>
              </div>
            )}
            {user.role === "admin" && !siderCollapsed && <div className="sider-admin-actions">
              <Button size="small" icon={<RefreshCw size={14} />} onClick={() => void checkUpdates()}>版本检测</Button>
              {updateCheck && <Typography.Text className={updateCheck.has_update ? "update-ready" : "update-current"}>
                {updateCheck.has_update ? `v${updateCheck.latest_version}（可更新）` : `v${updateCheck.current_version}（最新版）`}
              </Typography.Text>}
              <Button size="small" type="primary" className="sider-update-button" onClick={() => navigate("/updates")} disabled={!updateCheck?.has_update}>一键更新</Button>
            </div>}
            <Button
              type="text"
              icon={<LogOut size={18} />}
              title="退出登录"
              aria-label="退出登录"
              onClick={() => void logout()}
            />
          </div>
        </Layout.Sider>
        <Layout>
          <header className="topbar">
            <div className="mobile-brand">
              <span className="brand-mark small">VX</span>
              <strong>视频号数据</strong>
            </div>
            <Button
              className="theme-toggle"
              type="text"
              icon={
                theme === "night" ? (
                  <Sun size={18} />
                ) : theme === "rose" ? (
                  <Palette size={18} />
                ) : (
                  <Moon size={18} />
                )
              }
              title={
                theme === "morning"
                  ? "切换到黑夜模式"
                  : theme === "night"
                    ? "切换到柔和玫瑰模式"
                    : "切换到白天模式"
              }
              aria-label={
                theme === "morning"
                  ? "切换到黑夜模式"
                  : theme === "night"
                    ? "切换到柔和玫瑰模式"
                    : "切换到白天模式"
              }
              data-theme-mode={theme}
              onClick={toggleTheme}
            />
            <Dropdown className="theme-picker" menu={{ items: themeMenu, selectedKeys: [theme], onClick: handleThemeMenu }} trigger={["click"]} placement="bottomRight">
              <Button className="theme-picker-button" type="text" icon={themeIcons[theme]} aria-label="选择主题" title="选择主题" />
            </Dropdown>
            <Space className="quick-links" size={4}>
              <Button
                type="text"
                icon={<MessageCircle size={17} />}
                onClick={() => navigate("/ai-chat")}
                title="AI 聊天"
              >
                AI 聊天
              </Button>
              <Button
                type="text"
                icon={<Download size={17} />}
                onClick={() => navigate("/download/content")}
                title="下载内容"
              >
                下载内容
              </Button>
            </Space>
            <Select
              aria-label="当前视频号"
              className="account-select"
              placeholder="请先创建视频号"
              value={accountId || undefined}
              onChange={setAccountId}
              options={accounts.map((row) => ({
                value: row.id,
                label: row.name,
              }))}
            />
            <Dropdown
              overlayClassName="profile-dropdown"
              menu={{ items: profileMenu, onClick: handleProfileMenu }}
              trigger={["click"]}
              placement="bottomRight"
            >
              <button
                type="button"
                className="profile-trigger"
                aria-label="打开用户菜单"
              >
                <Avatar
                  size={36}
                  className="profile-avatar"
                  src={
                    user.avatar && user.avatar !== "default"
                      ? user.avatar
                      : undefined
                  }
                >
                  {user.username.slice(0, 1).toUpperCase()}
                </Avatar>
              </button>
            </Dropdown>
            <Button
              className="mobile-logout"
              type="text"
              icon={<LogOut size={18} />}
              title="退出登录"
              aria-label="退出登录"
              onClick={() => void logout()}
            />
          </header>
          <Layout.Content className="content">
            <Suspense
              fallback={
                <div className="page-loading">
                  <Spin size="large" />
                </div>
              }
            >
              <Routes>
                <Route path="/dashboard" element={<DashboardPage />} />
                <Route path="/videos" element={<VideosPage />} />
                <Route path="/imports" element={<ImportsPage />} />
                <Route path="/ai" element={<AIPage />} />
                <Route path="/ai-chat" element={<AIChatPage />} />
                <Route path="/accounts" element={<SettingsPage section="accounts" />} />
                <Route path="/analysis/dashboard" element={<DashboardPage />} />
                <Route path="/analysis/videos" element={<VideosPage />} />
                <Route path="/analysis/imports" element={<ImportsPage />} />
                <Route path="/analysis/ai" element={<AIPage />} />
                <Route
                  path="/analysis"
                  element={<Navigate to="/analysis/dashboard" replace />}
                />
                <Route
                  path="/users"
                  element={<Navigate to="/users/accounts" replace />}
                />
                <Route
                  path="/users/accounts"
                  element={<SettingsPage section="accounts" />}
                />
                <Route
                  path="/users/local"
                  element={<SettingsPage section="local" />}
                />
                <Route
                  path="/download"
                  element={<Navigate to="/download/config" replace />}
                />
                <Route
                  path="/download/config"
                  element={<DownloadPage mode="config" />}
                />
                <Route
                  path="/download/content"
                  element={<DownloadPage mode="content" />}
                />
                <Route
                  path="/about/architecture"
                  element={<AboutPage section="architecture" />}
                />
                <Route
                  path="/about/technology"
                  element={<AboutPage section="technology" />}
                />
                <Route
                  path="/about/team"
                  element={<AboutPage section="team" />}
                />
                <Route
                  path="/about"
                  element={<Navigate to="/about/architecture" replace />}
                />
                <Route path="/backups" element={<BackupPage />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="/updates" element={user.role === "admin" ? <UpdatesPage /> : <Navigate to="/analysis" replace />} />
                <Route path="/profile" element={<ProfilePage />} />
                <Route path="/usage/levels" element={<UsagePage />} />
                <Route
                  path="/usage"
                  element={<Navigate to="/usage/levels" replace />}
                />
                <Route
                  path="*"
                  element={<Navigate to="/dashboard" replace />}
                />
              </Routes>
            </Suspense>
          </Layout.Content>
          <nav className="mobile-nav" aria-label="主导航">
            {visibleItems.map((item) => (
              <button
                key={item.key}
                className={location.pathname === item.key ? "active" : ""}
                onClick={() => navigate(item.key)}
              >
                {item.icon}
                <span>{item.label.replace("数据", "")}</span>
              </button>
            ))}
          </nav>
        </Layout>
      </Layout>
    </AccountContext.Provider>
  );
}
