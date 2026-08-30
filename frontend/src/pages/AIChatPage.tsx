import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  Button,
  Empty,
  Input,
  Modal,
  Select,
  Space,
  Tabs,
  Typography,
  Upload,
  message,
} from "antd";
import {
  Download,
  Edit3,
  FileText,
  ImagePlus,
  MessageSquarePlus,
  Pin,
  Search,
  Send,
  Settings2,
  Trash2,
  X,
  ChevronDown,
  ChevronRight,
  Copy,
  Plus,
} from "lucide-react";
import { api, query } from "../api";
import { useAuth } from "../auth";
import { useAccount } from "../account";
import AIPage from "./AIPage";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Category = { id: number; name: string; sort_order?: number; pinned?: boolean; provider_id?: number | null };
type Session = {
  id: number;
  category_id?: number | null;
  title: string;
  pinned: boolean;
  provider_id?: number | null;
};
type ChatMessage = {
  id: number;
  role: "user" | "assistant";
  content: string;
  attachments?: { id: number; filename: string; content_type: string }[];
};
type Provider = {
  id: number;
  name: string;
  model: string;
  base_url: string;
  protocol: string;
  timeout_seconds: number;
  api_key_configured: boolean;
};
function MarkdownCode({ children, className }: { children?: ReactNode; className?: string }) {
  const source = String(children ?? "").replace(/\n$/, "");
  return <span className="ai-chat-code-block"><code className={className}>{source}</code><Button type="text" size="small" icon={<Copy size={14} />} onClick={() => void navigator.clipboard.writeText(source).then(() => message.success("代码已复制"), () => message.error("代码复制失败"))}>复制</Button></span>;
}
const timestampName = (prefix: string) => {
  const now = new Date();
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${prefix}${pad(now.getMonth() + 1)}${pad(now.getDate())}${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
};
type ChatAttachment = { id: string; file: File; preview?: string };
const fileAsDataUrl = (file: File) =>
  new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error(`无法读取附件：${file.name}`));
    reader.readAsDataURL(file);
  });

export default function AIChatPage() {
  const { user } = useAuth();
  const { account } = useAccount();
  const [tab, setTab] = useState("chat");
  const [categories, setCategories] = useState<Category[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [activeSession, setActiveSession] = useState<Session | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [categoryId, setCategoryId] = useState<number | undefined>();
  const [expandedCategoryId, setExpandedCategoryId] = useState<number | undefined>();
  const [providerId, setProviderId] = useState<number | undefined>();
  const [busy, setBusy] = useState(false);
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const [previewImage, setPreviewImage] = useState<string>();
  const [search, setSearch] = useState("");
  const [selectedSessions, setSelectedSessions] = useState<number[]>([]);
  const [dragCategoryId, setDragCategoryId] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const load = async () => {
    const [cats, chats, configs] = await Promise.all([
      api<Category[]>("/api/ai-chat/categories"),
      api<Session[]>("/api/ai-chat/sessions"),
      account
        ? api<Provider[]>(
            `/api/ai/providers?${query({ account_id: account.id })}`,
          )
        : Promise.resolve([]),
    ]);
    setCategories(cats);
    setExpandedCategoryId((current) => current && cats.some((item) => item.id === current) ? current : cats[0]?.id);
    setSessions(chats);
    setProviders(configs);
    const first = chats[0];
    if (first) await openSession(first);
  };
  const openSession = async (session: Session) => {
    setActiveSession(session);
    setProviderId(session.provider_id || undefined);
    setMessages(
      await api<ChatMessage[]>(`/api/ai-chat/sessions/${session.id}/messages`),
    );
  };
  useEffect(() => {
    void load().catch((cause) =>
      message.error(
        cause instanceof Error ? cause.message : "加载 AI 速问失败",
      ),
    );
  }, [account]); // eslint-disable-line react-hooks/exhaustive-deps
  const createCategory = () => {
    let name = timestampName("新分类");
    Modal.confirm({
      title: "新建分类",
      content: (
        <Input
          autoFocus
          defaultValue={name}
          onChange={(event) => {
            name = event.target.value;
          }}
          placeholder="分类名称"
        />
      ),
      onOk: async () => {
        if (!name.trim()) return;
        const row = await api<Category>("/api/ai-chat/categories", {
          method: "POST",
          body: JSON.stringify({ name, provider_id: providerId }),
        });
        setCategories((items) => [...items, row]);
      },
    });
  };
  const editCategory = () => {
    const category = categories.find((item) => item.id === categoryId);
    if (!category) return;
    let name = category.name;
    Modal.confirm({
      title: "重命名分类",
      content: (
        <Input
          autoFocus
          defaultValue={name}
          onChange={(event) => {
            name = event.target.value;
          }}
        />
      ),
      onOk: async () => {
        if (!name.trim()) return;
        const row = await api<Category>(
          `/api/ai-chat/categories/${category.id}`,
          { method: "PATCH", body: JSON.stringify({ name }) },
        );
        setCategories((items) =>
          items.map((item) => (item.id === row.id ? row : item)),
        );
      },
    });
  };
  const deleteCategory = () => {
    const category = categories.find((item) => item.id === categoryId);
    if (!category) return;
    Modal.confirm({
      title: "删除分类",
      content: `确认删除“${category.name}”？分类下的对话不会被删除。`,
      okButtonProps: { danger: true },
      onOk: async () => {
        await api(`/api/ai-chat/categories/${category.id}`, {
          method: "DELETE",
        });
        setCategories((items) =>
          items.filter((item) => item.id !== category.id),
        );
        setCategoryId(undefined);
      },
    });
  };
  const editCategoryProvider = (category: Category) => {
    let selected = category.provider_id;
    Modal.confirm({ title: "分类默认模型", content: <Select style={{ width: "100%" }} defaultValue={selected} allowClear options={providers.map((item) => ({ value: item.id, label: `${item.name} · ${item.model}` }))} onChange={(value) => { selected = value; }} />, onOk: async () => {
      const row = await api<Category>(`/api/ai-chat/categories/${category.id}`, { method: "PATCH", body: JSON.stringify({ name: category.name, provider_id: selected }) });
      setCategories((items) => items.map((item) => item.id === row.id ? row : item));
    } });
  };
  const reorderCategory = async (targetId: number) => {
    if (dragCategoryId === null || dragCategoryId === targetId) return;
    const from = categories.findIndex((item) => item.id === dragCategoryId);
    const to = categories.findIndex((item) => item.id === targetId);
    if (from < 0 || to < 0) return;
    const next = [...categories];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    setCategories(next);
    await Promise.all(
      next.map((item, index) =>
        api<Category>(`/api/ai-chat/categories/${item.id}`, {
          method: "PATCH",
          body: JSON.stringify({ name: item.name, sort_order: index }),
        }),
      ),
    );
    setDragCategoryId(null);
  };
  const renameSession = (session: Session) => {
    let title = session.title;
    Modal.confirm({
      title: "重命名对话",
      content: (
        <Input
          defaultValue={title}
          onChange={(event) => {
            title = event.target.value;
          }}
        />
      ),
      onOk: async () => {
        if (title.trim()) await updateSession(session, { title });
      },
    });
  };
  const createSession = async () => {
    if (!categoryId) {
      message.warning("请先创建或选择一个分类");
      return;
    }
    const row = await api<Session>("/api/ai-chat/sessions", {
      method: "POST",
      body: JSON.stringify({
        title: timestampName("新对话"),
        category_id: categoryId,
        provider_id: providerId,
      }),
    });
    setSessions((items) => [row, ...items]);
    await openSession(row);
  };
  const updateSession = async (
    session: Session,
    patch: Record<string, unknown>,
  ) => {
    const row = await api<Session>(`/api/ai-chat/sessions/${session.id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    });
    setSessions((items) =>
      items.map((item) => (item.id === row.id ? row : item)),
    );
    if (activeSession?.id === row.id) setActiveSession(row);
  };
  const removeSession = async (session: Session) => {
    await api(`/api/ai-chat/sessions/${session.id}`, { method: "DELETE" });
    const remaining = sessions.filter((item) => item.id !== session.id);
    setSessions(remaining);
    if (activeSession?.id === session.id) {
      setActiveSession(null);
      setMessages([]);
    }
  };
  const exportSession = async (format: "markdown" | "json") => {
    if (!activeSession) return;
    const response = await fetch(
      `/api/ai-chat/sessions/${activeSession.id}/export?format=${format}`,
      { credentials: "same-origin" },
    );
    if (!response.ok) {
      message.error("导出失败");
      return;
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `ai-chat-${activeSession.id}.${format === "json" ? "json" : "md"}`;
    link.click();
    URL.revokeObjectURL(url);
  };
  const deleteSelected = async () => {
    if (!selectedSessions.length) return;
    await Promise.all(
      selectedSessions.map((id) =>
        api(`/api/ai-chat/sessions/${id}`, { method: "DELETE" }),
      ),
    );
    setSessions((items) =>
      items.filter((item) => !selectedSessions.includes(item.id)),
    );
    if (activeSession && selectedSessions.includes(activeSession.id)) {
      setActiveSession(null);
      setMessages([]);
    }
    setSelectedSessions([]);
    message.success("已删除选中的对话");
  };
  const send = async () => {
    if (!activeSession || (!input.trim() && !attachments.length) || busy)
      return;
    const files = attachments.slice();
    const content = input.trim();
    setInput("");
    setAttachments([]);
    setBusy(true);
    setMessages((items) => [
      ...items,
      { id: Date.now(), role: "user", content: content || "（附件）" },
      { id: Date.now() + 1, role: "assistant", content: "" },
    ]);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const attachmentPayload = await Promise.all(
        files.map(async ({ file }) => ({
          filename: file.name,
          content_type: file.type || "application/octet-stream",
          data: await fileAsDataUrl(file),
        })),
      );
      const response = await fetch(
        `/api/ai-chat/sessions/${activeSession.id}/messages`,
        {
          method: "POST",
          credentials: "same-origin",
          signal: controller.signal,
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": user.csrf_token || "",
          },
          body: JSON.stringify({
            content,
            provider_id: providerId,
            attachments: attachmentPayload,
          }),
        },
      );
      if (!response.ok || !response.body) throw new Error("AI 请求失败");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const result = await reader.read();
        if (result.done) break;
        buffer += decoder.decode(result.value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() || "";
        for (const chunk of chunks) {
          const line = chunk
            .split("\n")
            .find((item) => item.startsWith("data:"));
          if (!line) continue;
          const event = JSON.parse(line.slice(5));
          if (event.type === "delta")
            setMessages((items) =>
              items.map((item, index) =>
                index === items.length - 1
                  ? { ...item, content: item.content + event.content }
                  : item,
              ),
            );
          if (event.type === "error") throw new Error(event.message);
        }
      }
      setSessions((items) =>
        items.map((item) =>
          item.id === activeSession.id ? { ...item } : item,
        ),
      );
    } catch (cause) {
      if ((cause as DOMException)?.name !== "AbortError") {
        setMessages((items) => items.slice(0, -1));
        message.error(cause instanceof Error ? cause.message : "AI 请求失败");
      }
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  };
  const addFiles = (files: File[]) => {
    setAttachments((items) => {
      const remaining = Math.max(0, 8 - items.length);
      const accepted = files.filter(
        (file) =>
          file.type.startsWith("image/") ||
          file.type.startsWith("text/") ||
          /.(txt|md|csv|json)$/i.test(file.name),
      );
      if (accepted.length > remaining) message.warning("最多同时添加 8 个附件");
      const selected = accepted.slice(0, remaining);
      const tooLarge = selected.filter((file) => file.size > 10 * 1024 * 1024);
      if (tooLarge.length)
        message.warning(
          `单个附件不能超过 10 MB：${tooLarge.map((file) => file.name).join("、")}`,
        );
      const total =
        items.reduce((sum, item) => sum + item.file.size, 0) +
        selected.reduce((sum, file) => sum + file.size, 0);
      if (total > 32 * 1024 * 1024) {
        message.warning("附件总大小不能超过 32 MB");
        return items;
      }
      return [
        ...items,
        ...selected
          .filter((file) => file.size <= 10 * 1024 * 1024)
          .map((file) => ({
            id: `${file.name}-${file.lastModified}-${Math.random()}`,
            file,
            preview: file.type.startsWith("image/")
              ? URL.createObjectURL(file)
              : undefined,
          })),
      ];
    });
  };
  const visibleSessions = sessions.filter(
    (item) =>
      item.title.toLowerCase().includes(search.trim().toLowerCase()),
  );
  const chatView = (
    <div className="ai-chat-layout">
      <aside className="ai-chat-sidebar">
        <div className="ai-chat-sidebar-actions">
          <Button
            type="primary"
            icon={<MessageSquarePlus size={16} />}
            onClick={() => void createSession()}
          >
            新建对话
          </Button>
          <Button
            icon={<Settings2 size={16} />}
            onClick={() => setTab("config")}
          >
            配置
          </Button>
        </div>
        <Input
          prefix={<Search size={15} />}
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="搜索对话"
          allowClear
        />
        <div className="ai-chat-category-bar">
          <Select
            allowClear
            value={categoryId}
            onChange={setCategoryId}
            placeholder="全部分类"
            options={categories.map((item) => ({
              value: item.id,
              label: item.name,
            }))}
          />
          <Button
            type="text"
            icon={<Edit3 size={15} />}
            onClick={createCategory}
          />
          <Button
            type="text"
            disabled={!categoryId}
            icon={<Edit3 size={14} />}
            onClick={editCategory}
          />
          <Button
            type="text"
            danger
            disabled={!categoryId}
            icon={<Trash2 size={14} />}
            onClick={deleteCategory}
          />
        </div>
        <Space size={4} style={{ marginBottom: 8 }}>
          <Button
            size="small"
            disabled={!visibleSessions.length}
            onClick={() =>
              setSelectedSessions(visibleSessions.map((item) => item.id))
            }
          >
            全选
          </Button>
          <Button
            size="small"
            danger
            disabled={!selectedSessions.length}
            onClick={() => void deleteSelected()}
          >
            删除选中
          </Button>
        </Space>
        <div className="ai-chat-sessions">
          {categories.map((category) => {
            const categorySessions = visibleSessions.filter((item) => item.category_id === category.id);
            const expanded = expandedCategoryId === category.id;
            return <div className="ai-chat-tree-group" key={category.id}>
              <div className={`ai-chat-category-node ${categoryId === category.id ? "active" : ""}`} onClick={() => { setCategoryId(category.id); setExpandedCategoryId(expanded ? undefined : category.id); }}>
                <Button type="text" size="small" icon={expanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />} aria-label={expanded ? "收起分类" : "展开分类"} />
                <span className="ai-chat-tree-name">{category.name}</span>
                <Space size={0} className="ai-chat-tree-actions">
                  <Button type="text" size="small" icon={<Plus size={14} />} aria-label="添加对话" title="添加对话" onClick={(event) => { event.stopPropagation(); setCategoryId(category.id); void createSession(); }} />
                  <Button type="text" size="small" icon={<Edit3 size={14} />} aria-label="编辑分类" title="编辑分类" onClick={(event) => { event.stopPropagation(); setCategoryId(category.id); editCategory(); }} />
                  <Button type="text" size="small" icon={<Settings2 size={14} />} aria-label="设置分类模型" title="设置分类模型" onClick={(event) => { event.stopPropagation(); editCategoryProvider(category); }} />
                  <Button type="text" size="small" icon={<Pin size={14} />} aria-label="置顶分类" title="置顶分类" onClick={(event) => { event.stopPropagation(); void api<Category>(`/api/ai-chat/categories/${category.id}`, { method: "PATCH", body: JSON.stringify({ name: category.name, pinned: !category.pinned }) }).then((row) => setCategories((items) => items.map((item) => item.id === row.id ? row : item))) }} />
                  <Button type="text" danger size="small" icon={<Trash2 size={14} />} aria-label="删除分类" title="删除分类" onClick={(event) => { event.stopPropagation(); setCategoryId(category.id); deleteCategory(); }} />
                </Space>
              </div>
              {expanded && categorySessions.map((session) => <div key={session.id} className={`ai-chat-session ai-chat-tree-session ${activeSession?.id === session.id ? "active" : ""}`} onClick={() => void openSession(session)}>
                <input type="checkbox" checked={selectedSessions.includes(session.id)} onChange={(event) => { event.stopPropagation(); setSelectedSessions((items) => event.target.checked ? [...items, session.id] : items.filter((id) => id !== session.id)); }} onClick={(event) => event.stopPropagation()} />
                <span className="ai-chat-tree-name">{session.pinned && <Pin size={13} />} {session.title}</span>
                <Space size={0} className="ai-chat-tree-actions"><Button type="text" size="small" icon={<Edit3 size={13} />} aria-label="编辑对话" title="编辑对话" onClick={(event) => { event.stopPropagation(); renameSession(session); }} /><Button type="text" size="small" icon={<Pin size={13} />} aria-label="置顶对话" title="置顶对话" onClick={(event) => { event.stopPropagation(); void updateSession(session, { pinned: !session.pinned }); }} /><Button type="text" danger size="small" icon={<Trash2 size={13} />} aria-label="删除对话" title="删除对话" onClick={(event) => { event.stopPropagation(); void removeSession(session); }} /></Space>
              </div>)}
            </div>;
          })}
        </div>
      </aside>
      <main className="ai-chat-main">
        <div className="ai-chat-toolbar">
          <Select
            value={providerId}
            allowClear
            placeholder="选择 AI 模型"
            onChange={setProviderId}
            options={providers.map((item) => ({
              value: item.id,
              label: `${item.name} · ${item.model}`,
            }))}
          />
          <Button
            onClick={() =>
              activeSession &&
              void updateSession(activeSession, { provider_id: providerId })
            }
          >
            应用模型
          </Button>
          <Button
            icon={<Download size={15} />}
            disabled={!activeSession}
            onClick={() => void exportSession("markdown")}
          >
            导出 Markdown
          </Button>
          <Button
            icon={<Download size={15} />}
            disabled={!activeSession}
            onClick={() => void exportSession("json")}
          >
            导出 JSON
          </Button>
        </div>
        {!activeSession ? (
          <Empty description="请选择或新建一个对话" />
        ) : (
          <>
            <div className="ai-chat-messages">
              {messages.map((item) => (
                <div key={item.id} className={`ai-chat-message ${item.role}`}>
                  <div className="ai-chat-message-role">
                    {item.role === "user" ? "你" : "AI"}
                  </div>
                  <div className="ai-chat-message-content">
                    {item.content ? (
                      item.role === "assistant" ? (
                        <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ code: MarkdownCode }}>
                          {item.content}
                        </ReactMarkdown>
                      ) : (
                        item.content
                      )
                    ) : busy && item.role === "assistant" ? (
                      "正在生成…"
                    ) : (
                      ""
                    )}
                    {item.attachments?.map((attachment) =>
                      attachment.content_type.startsWith("image/") ? (
                        <button
                          type="button"
                          key={attachment.id}
                          className="ai-chat-history-image"
                          onClick={() => setPreviewImage(`/api/ai-chat/attachments/${attachment.id}`)}
                        >
                          <img src={`/api/ai-chat/attachments/${attachment.id}`} alt={attachment.filename} />
                        </button>
                      ) : (
                        <a
                          key={attachment.id}
                          href={`/api/ai-chat/attachments/${attachment.id}`}
                          target="_blank"
                          rel="noreferrer"
                          className="ai-chat-history-attachment"
                        >
                          {attachment.filename}
                        </a>
                      ),
                    )}
                  </div>
                </div>
              ))}
            </div>
            <div className="ai-chat-composer">
              <div className="ai-chat-attachments">
                {attachments.map((item, index) => (
                  <div className="ai-chat-attachment" key={item.id}>
                    {item.preview ? (
                      <button
                        type="button"
                        onClick={() => setPreviewImage(item.preview)}
                      >
                        <img src={item.preview} alt={item.file.name} />
                      </button>
                    ) : (
                      <FileText size={22} />
                    )}
                    <span title={item.file.name}>{item.file.name}</span>
                    <Button
                      type="text"
                      danger
                      icon={<X size={14} />}
                      onClick={() =>
                        setAttachments((items) =>
                          items.filter((row) => row.id !== item.id),
                        )
                      }
                    />
                    <Button
                      type="text"
                      disabled={index === 0}
                      onClick={() =>
                        setAttachments((items) => {
                          const next = [...items];
                          [next[index - 1], next[index]] = [
                            next[index],
                            next[index - 1],
                          ];
                          return next;
                        })
                      }
                    >
                      ↑
                    </Button>
                    <Button
                      type="text"
                      disabled={index === attachments.length - 1}
                      onClick={() =>
                        setAttachments((items) => {
                          const next = [...items];
                          [next[index], next[index + 1]] = [
                            next[index + 1],
                            next[index],
                          ];
                          return next;
                        })
                      }
                    >
                      ↓
                    </Button>
                  </div>
                ))}
              </div>
              <Input.TextArea
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onPaste={(event) => {
                  const files = Array.from(event.clipboardData.files);
                  if (files.length) {
                    event.preventDefault();
                    addFiles(files);
                  }
                }}
                onPressEnter={(event) => {
                  if (!event.shiftKey) {
                    event.preventDefault();
                    void send();
                  }
                }}
                autoSize={{ minRows: 2, maxRows: 6 }}
                placeholder="输入消息，Enter 发送，Shift+Enter 换行"
              />
              <Space>
                <Upload
                  accept="image/*,.txt,.md,.csv,.json"
                  multiple
                  showUploadList={false}
                  beforeUpload={(file) => {
                    addFiles([file]);
                    return false;
                  }}
                >
                  <Button icon={<ImagePlus size={16} />}>附件</Button>
                </Upload>
                <Button
                  disabled={!busy}
                  onClick={() => abortRef.current?.abort()}
                >
                  停止
                </Button>
                <Button
                  type="primary"
                  icon={<Send size={16} />}
                  loading={busy}
                  disabled={
                    (!input.trim() && !attachments.length) || !providerId
                  }
                  onClick={() => void send()}
                >
                  发送
                </Button>
              </Space>
            </div>
          </>
        )}
      </main>
      <Modal
        open={Boolean(previewImage)}
        footer={null}
        onCancel={() => setPreviewImage(undefined)}
      >
        <img src={previewImage} alt="附件预览" style={{ width: "100%" }} />
      </Modal>
    </div>
  );
  return (
    <div className="page ai-chat-page">
      <div className="page-heading">
        <div>
          <Typography.Title level={2}>AI 速问</Typography.Title>
          <Typography.Text type="secondary">
            在线对话、历史记录和多模型配置
          </Typography.Text>
        </div>
      </div>
      <div className="ai-chat-category-order" aria-label="拖动分类调整顺序">
        {categories.map((category) => (
          <span
            key={category.id}
            draggable
            onDragStart={() => setDragCategoryId(category.id)}
            onDragOver={(event) => event.preventDefault()}
            onDrop={() => void reorderCategory(category.id)}
          >
            {category.name}
          </span>
        ))}
      </div>
      <Tabs
        activeKey={tab}
        onChange={setTab}
        items={[
          { key: "config", label: "AI 配置", children: <AIPage configOnly /> },
          { key: "chat", label: "AI 聊天", children: chatView },
        ].filter((item) => user.role === "admin" || item.key !== "config")}
      />
    </div>
  );
}
