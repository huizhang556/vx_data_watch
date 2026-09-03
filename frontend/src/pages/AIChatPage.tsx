import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import {
  Button,
  Empty,
  Input,
  Modal,
  Select,
  Space,
  Upload,
  message,
} from "antd";
import {
  Download,
  Edit3,
  FileText,
  ImagePlus,
  Pin,
  PinOff,
  Search,
  Send,
  Trash2,
  X,
  ChevronDown,
  ChevronRight,
  Copy,
  Plus,
  ArrowDownToLine,
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
  generation_status?: "idle" | "running" | "completed" | "failed";
  generation_type?: "image" | "video" | null;
  generation_error?: string | null;
};
type ChatMessage = {
  id: number;
  role: "user" | "assistant";
  content: string;
  created_at?: string;
  attachments?: { id: number | string; filename: string; content_type: string; preview?: string }[];
};
type ContextInfo = { used_tokens: number; max_tokens: number; compressed: boolean };
type Provider = {
  id: number;
  name: string;
  model: string;
  base_url: string;
  protocol: string;
  timeout_seconds: number;
  api_key_configured: boolean;
  models?: string[];
  model_categories?: Record<string, string[]>;
  is_enabled: boolean;
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

export default function AIChatPage({ configOnly = false }: { configOnly?: boolean }) {
  const { user } = useAuth();
  const { account } = useAccount();
  const [categories, setCategories] = useState<Category[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [activeSession, setActiveSession] = useState<Session | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [categoryId, setCategoryId] = useState<number | undefined>();
  const [expandedCategoryId, setExpandedCategoryId] = useState<number | undefined>();
  const [providerId, setProviderId] = useState<number | undefined>();
  const [model, setModel] = useState("");
  const [modelCategory, setModelCategory] = useState("chat");
  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const categoryModels = (provider: Provider | undefined, category: string) => {
    if (!provider) return [];
    const categorized = provider.model_categories?.[category];
    if (categorized?.length) return categorized;
    return provider.models?.length ? provider.models : provider.model ? [provider.model] : [];
  };
  const [busy, setBusy] = useState(false);
  const [applyingModel, setApplyingModel] = useState(false);
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const [previewImage, setPreviewImage] = useState<string>();
  const [search, setSearch] = useState("");
  const [messageSearch, setMessageSearch] = useState("");
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const [highlightedMessageId, setHighlightedMessageId] = useState<number | null>(null);
  const [selectedSessions, setSelectedSessions] = useState<number[]>([]);
  const [dragCategoryId, setDragCategoryId] = useState<number | null>(null);
  const [chatSidebarWidth, setChatSidebarWidth] = useState(320);
  const [contextInfo, setContextInfo] = useState<ContextInfo | null>(null);
  const chatLayoutRef = useRef<HTMLDivElement>(null);
  const resizingChatRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  const messageRequestRef = useRef(0);
  const creatingCategoryRef = useRef(false);
  const creatingSessionRef = useRef(false);
  const lastNodeClickRef = useRef<{ key: string; at: number } | null>(null);
  const messagesRef = useRef<HTMLDivElement>(null);
  const messageRefs = useRef<Record<number, HTMLDivElement | null>>({});

  useEffect(() => {
    const container = messagesRef.current;
    if (!container) return;
    const updateScrollState = () => {
      const distance = container.scrollHeight - container.scrollTop - container.clientHeight;
      setShowScrollToBottom(distance > 8);
    };
    updateScrollState();
    container.addEventListener("scroll", updateScrollState, { passive: true });
    return () => container.removeEventListener("scroll", updateScrollState);
  }, [messages, activeSession]);

  useEffect(() => {
    const move = (event: PointerEvent) => {
      if (!resizingChatRef.current || !chatLayoutRef.current) return;
      const bounds = chatLayoutRef.current.getBoundingClientRect();
      setChatSidebarWidth(Math.max(280, Math.min(520, event.clientX - bounds.left)));
    };
    const stop = () => { resizingChatRef.current = false; };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
  }, []);

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
    if (first) {
      setProviderId(first.provider_id || undefined);
      const firstProvider = configs.find((item) => item.id === first.provider_id);
      setModel(firstProvider?.model || "");
      setModelOptions(categoryModels(firstProvider, "chat"));
      await openSession(first, configs);
    }
  };
  const refreshProviderChoices = async () => {
    if (!account) return;
    const rows = await api<Provider[]>(`/api/ai/providers?${query({ account_id: account.id })}`);
    setProviders(rows.filter((item) => item.is_enabled));
    if (providerId && !rows.some((item) => item.id === providerId && item.is_enabled)) {
      setProviderId(undefined);
      setModel("");
      setModelOptions([]);
    }
  };
  const openSession = async (session: Session, providerList = providers) => {
    const requestId = ++messageRequestRef.current;
    setActiveSession(session);
    setContextInfo(null);
    setProviderId(session.provider_id || undefined);
    const sessionProvider = providerList.find((item) => item.id === session.provider_id);
    const savedModel = localStorage.getItem(`vx-ai-chat-model:${session.id}`);
    setModel(savedModel || sessionProvider?.model || "");
    setModelOptions(categoryModels(sessionProvider, modelCategory));
    setMessages([]);
    try {
      const history = await api<ChatMessage[]>(`/api/ai-chat/sessions/${session.id}/messages`);
      if (requestId === messageRequestRef.current) {
        setMessages(history);
        const used = history.reduce((total, item) => total + Math.max(1, Math.ceil(item.content.length / 3)), 0);
        setContextInfo({ used_tokens: used, max_tokens: 12000, compressed: false });
      }
    } catch (cause) {
      if (requestId === messageRequestRef.current) {
        message.error(cause instanceof Error ? cause.message : "加载聊天历史失败");
      }
    }
  };
  useEffect(() => {
    void load().catch((cause) =>
      message.error(
        cause instanceof Error ? cause.message : "加载 AI 速问失败",
      ),
    );
  }, [account]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!providerId || !account) {
      setModelOptions([]);
      return;
    }
    const provider = providers.find((item) => item.id === providerId);
    setModelOptions(categoryModels(provider, modelCategory));
  }, [providerId, account, providers, modelCategory]);
  const changeModelCategory = (value: string) => {
    if (value !== "chat" && activeSession && messages.length > 0) {
      const provider = providers.find((item) => item.id === providerId);
      const options = categoryModels(provider, "chat");
      setModelCategory("chat");
      setModelOptions(options);
      setModel(options.includes(model) ? model : options[0] || "");
      message.warning("当前对话已有历史消息，生图或生视频需要新建聊天窗口");
      return;
    }
    setModelCategory(value);
    const provider = providers.find((item) => item.id === providerId);
    const options = categoryModels(provider, value);
    setModelOptions(options);
    setModel(options.includes(model) ? model : options[0] || "");
  };
  const applyModel = async () => {
    if (!activeSession || !providerId || !model || applyingModel) return;
    const selectedProvider = providers.find((item) => item.id === providerId);
    if (!selectedProvider) return;
    setApplyingModel(true);
    try {
      const response = await api<{ result: string }>("/api/ai/provider/test-selected", {
        method: "POST",
        body: JSON.stringify({ account_id: account?.id ?? null, provider_id: providerId, model }),
      });
      localStorage.setItem(`vx-ai-chat-model:${activeSession.id}`, model);
      await updateSession(activeSession, { provider_id: providerId });
      message.success(response.result?.slice(0, 100) || "模型配置可用，已应用");
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : "模型配置测试失败，未应用");
    } finally {
      setApplyingModel(false);
    }
  };
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
        if (!name.trim() || creatingCategoryRef.current) return;
        creatingCategoryRef.current = true;
        try {
          const row = await api<Category>("/api/ai-chat/categories", {
            method: "POST",
            body: JSON.stringify({ name, provider_id: providerId }),
          });
          setCategories((items) => [...items, row]);
        } finally {
          creatingCategoryRef.current = false;
        }
      },
    });
  };
  const editCategory = (targetCategoryId = categoryId) => {
    const category = categories.find((item) => item.id === targetCategoryId);
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
  const reorderCategory = async (targetId: number) => {
    if (dragCategoryId === null || dragCategoryId === targetId) return;
    const from = categories.findIndex((item) => item.id === dragCategoryId);
    const to = categories.findIndex((item) => item.id === targetId);
    if (from < 0 || to < 0) return;
    const next = [...categories];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    setCategories(next);
    await Promise.all(next.map((item, index) => api<Category>(`/api/ai-chat/categories/${item.id}`, {
      method: "PATCH",
      body: JSON.stringify({ name: item.name, sort_order: index }),
    })));
    setDragCategoryId(null);
  };
  const deleteCategory = (targetCategoryId = categoryId) => {
    const category = categories.find((item) => item.id === targetCategoryId);
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
  const createSession = async (targetCategoryId = categoryId) => {
    if (creatingSessionRef.current) return;
    if (!targetCategoryId) {
      message.warning("请先创建或选择一个分类");
      return;
    }
    creatingSessionRef.current = true;
    try {
      const row = await api<Session>("/api/ai-chat/sessions", {
      method: "POST",
      body: JSON.stringify({
        title: timestampName("新对话"),
        category_id: targetCategoryId,
        provider_id: providerId,
      }),
      });
      setSessions((items) => [row, ...items]);
      await openSession(row);
    } finally {
      creatingSessionRef.current = false;
    }
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
      items.map((item) => (item.id === row.id ? row : item)).sort((a, b) => Number(b.pinned) - Number(a.pinned) || b.id - a.id),
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
  const editMessage = (item: ChatMessage) => {
    let content = item.content;
    Modal.confirm({
      title: "编辑消息",
      content: <Input.TextArea autoFocus defaultValue={content} autoSize={{ minRows: 3, maxRows: 8 }} onChange={(event) => { content = event.target.value; }} />,
      onOk: async () => {
        const row = await api<{ id: number; content: string }>(`/api/ai-chat/messages/${item.id}`, {
          method: "PATCH",
          body: JSON.stringify({ content }),
        });
        setMessages((items) => items.map((messageItem) => messageItem.id === row.id ? { ...messageItem, content: row.content } : messageItem));
      },
    });
  };
  const deleteMessage = (item: ChatMessage) => {
    Modal.confirm({
      title: "删除消息",
      content: "确认删除这条用户消息吗？",
      okButtonProps: { danger: true },
      onOk: async () => {
        await api(`/api/ai-chat/messages/${item.id}`, { method: "DELETE" });
        setMessages((items) => items.filter((messageItem) => messageItem.id !== item.id));
      },
    });
  };
  const clearMessages = async () => {
    if (!activeSession || !messages.length) return;
    await api(`/api/ai-chat/sessions/${activeSession.id}/messages`, { method: "DELETE" });
    setMessages([]);
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
    if (modelCategory !== "chat" && messages.length > 0) {
      message.warning("当前对话已有历史消息，生图或生视频需要新建聊天窗口");
      setModelCategory("chat");
      return;
    }
    const files = attachments.slice();
    const content = input.trim();
    setInput("");
    setAttachments([]);
    setBusy(true);
    if (modelCategory !== "chat") message.info(modelCategory === "image" ? "生图任务正在进行中，完成后会通知您" : "生视频任务正在进行中，完成后会通知您");
    const temporaryMessageId = -Date.now();
    setMessages((items) => [
      ...items,
      { id: temporaryMessageId, role: "user", content, attachments: files.map(({ file, preview }) => ({ id: `${temporaryMessageId}-${file.name}`, filename: file.name, content_type: file.type || "application/octet-stream", preview })) },
      { id: temporaryMessageId - 1, role: "assistant", content: "" },
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
            mode: modelCategory,
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
          if (event.type === "context") setContextInfo({ used_tokens: event.used_tokens, max_tokens: event.max_tokens, compressed: Boolean(event.compressed) });
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
        setMessages((items) => items.filter((item) => item.id !== temporaryMessageId && item.id !== temporaryMessageId - 1));
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
  const searchActive = search.trim().length > 0;
  const messageSearchTerm = messageSearch.trim().toLowerCase();
  const messageMatches = messageSearchTerm
    ? messages.filter((item) => item.content.toLowerCase().includes(messageSearchTerm))
    : [];
  const formatMessageTime = (value?: string) => value ? new Date(value).toLocaleString() : "时间未知";
  const jumpToMessage = (item: ChatMessage) => {
    messageRefs.current[item.id]?.scrollIntoView({ behavior: "smooth", block: "center" });
    setHighlightedMessageId(item.id);
    window.setTimeout(() => setHighlightedMessageId((current) => current === item.id ? null : current), 1800);
  };
  const categoryNames = new Map(categories.map((item) => [item.id, item.name]));
  const acceptNodeClick = (key: string) => {
    const now = Date.now();
    const previous = lastNodeClickRef.current;
    if (previous?.key === key && now - previous.at < 350) {
      lastNodeClickRef.current = null;
      return false;
    }
    lastNodeClickRef.current = { key, at: now };
    return true;
  };
  const chatView = (
    <div className="ai-chat-layout" ref={chatLayoutRef} style={{ "--ai-chat-sidebar-width": `${chatSidebarWidth}px` } as CSSProperties}>
      <aside className="ai-chat-sidebar">
        <Input
          prefix={<Search size={15} />}
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="搜索对话"
          allowClear
        />
        {!searchActive && <Space className="ai-chat-bulk-actions" size={4} style={{ marginBottom: 8 }}>
          <Button
            size="small"
            disabled={!visibleSessions.length}
            onClick={() =>
              setSelectedSessions(visibleSessions.map((item) => item.id))
            }
          >
            全选
          </Button>
          <div className="ai-chat-message-search">
            <Input
              prefix={<Search size={15} />}
              value={messageSearch}
              onChange={(event) => setMessageSearch(event.target.value)}
              placeholder="搜索对话内容"
              allowClear
            />
            {messageSearchTerm && (
              <div className="ai-chat-message-search-results" role="listbox" aria-label="消息搜索结果">
                {messageMatches.length ? messageMatches.map((item) => (
                  <button key={item.id} type="button" role="option" className="ai-chat-message-search-result" onClick={() => jumpToMessage(item)}>
                    <span>{item.content.replace(/\s+/g, " ").slice(0, 100)}</span>
                    <time>{formatMessageTime(item.created_at)}</time>
                  </button>
                )) : <span className="ai-chat-message-search-empty">未找到匹配消息</span>}
              </div>
            )}
          </div>
          <Button
            size="small"
            danger
            disabled={!selectedSessions.length}
            onClick={() => void deleteSelected()}
          >
            删除选中
          </Button>
          <Button
            type="text"
            aria-label="添加分类"
            title="添加分类"
            icon={<Plus size={16} />}
            onClick={createCategory}
          />
        </Space>}
        {searchActive ? (
          <div className="ai-chat-search-results" role="list" aria-label="对话筛选结果">
            {visibleSessions.length ? visibleSessions.map((session) => <div
              key={session.id}
              className={`ai-chat-session ai-chat-search-result ${activeSession?.id === session.id ? "active" : ""}`}
              role="listitem"
              onContextMenu={(event) => { event.preventDefault(); event.stopPropagation(); }}
              onDoubleClick={(event) => { event.preventDefault(); event.stopPropagation(); }}
              onClick={() => { if (acceptNodeClick(`search-${session.id}`)) void openSession(session); }}
            >
              <span className="ai-chat-tree-name">{session.title}</span>
              <Space size={0} className="ai-chat-tree-actions">
                <Button type="text" size="small" icon={<Edit3 size={13} />} aria-label="编辑对话" title="编辑对话" onClick={(event) => { event.stopPropagation(); renameSession(session); }} />
                <Button type="text" size="small" icon={session.pinned ? <PinOff size={13} /> : <Pin size={13} />} aria-label={session.pinned ? "取消置顶对话" : "置顶对话"} title={session.pinned ? "取消置顶对话" : "置顶对话"} onClick={(event) => { event.stopPropagation(); void updateSession(session, { pinned: !session.pinned }); }} />
                <Button type="text" danger size="small" icon={<Trash2 size={13} />} aria-label="删除对话" title="删除对话" onMouseDown={(event) => event.preventDefault()} onClick={(event) => { event.stopPropagation(); void removeSession(session); }} />
              </Space>
              <span className="ai-chat-search-category">{categoryNames.get(session.category_id ?? -1) || "未分类"}</span>
            </div>) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="未找到匹配的对话" />}
          </div>
        ) : <div className="ai-chat-sessions">
          {categories.map((category) => {
            const categorySessions = visibleSessions.filter((item) => item.category_id === category.id);
            const expanded = expandedCategoryId === category.id;
            return <div className="ai-chat-tree-group" key={category.id}>
              <div className={`ai-chat-category-node ${categoryId === category.id ? "active" : ""}`} draggable onDragStart={() => setDragCategoryId(category.id)} onDragOver={(event) => event.preventDefault()} onDrop={() => void reorderCategory(category.id)} onContextMenu={(event) => { event.preventDefault(); event.stopPropagation(); }} onDoubleClick={(event) => { event.preventDefault(); event.stopPropagation(); }} onClick={() => { if (!acceptNodeClick(`category-${category.id}`)) return; setCategoryId(category.id); setExpandedCategoryId(expanded ? undefined : category.id); }}>
                <Button type="text" size="small" icon={expanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />} aria-label={expanded ? "收起分类" : "展开分类"} />
                <span className="ai-chat-tree-name">{category.name}</span>
                <Space size={0} className="ai-chat-tree-actions">
                  <Button type="text" size="small" icon={<Plus size={14} />} aria-label="添加对话" title="添加对话" onClick={(event) => { event.stopPropagation(); setCategoryId(category.id); void createSession(category.id); }} />
                  <Button type="text" size="small" icon={<Edit3 size={14} />} aria-label="编辑分类" title="编辑分类" onClick={(event) => { event.stopPropagation(); setCategoryId(category.id); editCategory(category.id); }} />
                  <Button type="text" size="small" icon={category.pinned ? <PinOff size={14} /> : <Pin size={14} />} aria-label={category.pinned ? "取消置顶分类" : "置顶分类"} title={category.pinned ? "取消置顶分类" : "置顶分类"} onClick={(event) => { event.stopPropagation(); void api<Category>(`/api/ai-chat/categories/${category.id}`, { method: "PATCH", body: JSON.stringify({ name: category.name, pinned: !category.pinned }) }).then((row) => setCategories((items) => items.map((item) => item.id === row.id ? row : item).sort((a, b) => Number(b.pinned) - Number(a.pinned) || (b.pinned ? b.id - a.id : (a.sort_order ?? 0) - (b.sort_order ?? 0))))) }} />
                  <Button type="text" danger size="small" icon={<Trash2 size={14} />} aria-label="删除分类" title="删除分类" onMouseDown={(event) => event.preventDefault()} onClick={(event) => { event.stopPropagation(); setCategoryId(category.id); deleteCategory(category.id); }} />
                </Space>
              </div>
              {expanded && categorySessions.map((session) => <div key={session.id} className={`ai-chat-session ai-chat-tree-session ${activeSession?.id === session.id ? "active" : ""}`} onContextMenu={(event) => { event.preventDefault(); event.stopPropagation(); }} onDoubleClick={(event) => { event.preventDefault(); event.stopPropagation(); }} onClick={() => { if (acceptNodeClick(`session-${session.id}`)) void openSession(session); }}>
                <input type="checkbox" checked={selectedSessions.includes(session.id)} onChange={(event) => { event.stopPropagation(); setSelectedSessions((items) => event.target.checked ? [...items, session.id] : items.filter((id) => id !== session.id)); }} onClick={(event) => event.stopPropagation()} />
                <span className="ai-chat-tree-name">{session.title}</span>
                <Space size={0} className="ai-chat-tree-actions"><Button type="text" size="small" icon={<Edit3 size={13} />} aria-label="编辑对话" title="编辑对话" onClick={(event) => { event.stopPropagation(); renameSession(session); }} /><Button type="text" size="small" icon={session.pinned ? <PinOff size={13} /> : <Pin size={13} />} aria-label={session.pinned ? "取消置顶对话" : "置顶对话"} title={session.pinned ? "取消置顶对话" : "置顶对话"} onClick={(event) => { event.stopPropagation(); void updateSession(session, { pinned: !session.pinned }); }} /><Button type="text" danger size="small" icon={<Trash2 size={13} />} aria-label="删除对话" title="删除对话" onMouseDown={(event) => event.preventDefault()} onClick={(event) => { event.stopPropagation(); void removeSession(session); }} /></Space>
              </div>)}
            </div>;
          })}
        </div>}
      </aside>
      <div
        className="ai-chat-resizer"
        role="separator"
        aria-label="调整会话栏宽度"
        aria-orientation="vertical"
        onPointerDown={(event) => {
          event.preventDefault();
          resizingChatRef.current = true;
        }}
      />
      <main className="ai-chat-main">
        <div className="ai-chat-toolbar">
          <Select
            value={providerId}
            placeholder="选择模型厂商"
            onOpenChange={(open) => { if (open) void refreshProviderChoices(); }}
            onChange={(value) => {
              setProviderId(value);
              const provider = providers.find((item) => item.id === value);
              setModel(provider?.model || "");
              setModelCategory("chat");
              setModelOptions(categoryModels(provider, "chat"));
            }}
            options={providers.filter((item) => item.is_enabled).map((item) => ({
              value: item.id,
              label: item.name,
            }))}
          />
          <Select
            value={modelCategory}
            disabled={!providerId}
            onChange={changeModelCategory}
            options={[{ value: "chat", label: "聊天模型" }, { value: "image", label: "生图模型" }, { value: "video", label: "视频模型" }]}
          />
          <Select
            value={model || undefined}
            placeholder="选择具体模型"
            disabled={!providerId}
            onChange={setModel}
            options={modelOptions.map((item) => ({ value: item, label: item }))}
          />
          <Button
            loading={applyingModel}
            disabled={!activeSession || !providerId || !model}
            onClick={() => void applyModel()}
          >
            应用模型
          </Button>
          <Space className="ai-chat-export-actions" size={8}>
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
          </Space>
        </div>
        {!activeSession ? (
          <Empty description="请选择或新建一个对话" />
        ) : (
          <>
            <div className="ai-chat-messages" ref={messagesRef}>
              {messages.map((item) => (
                <div key={item.id} ref={(element) => { messageRefs.current[item.id] = element; }} className={`ai-chat-message ${item.role} ${highlightedMessageId === item.id ? "search-highlight" : ""}`}>
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
                          onClick={() => setPreviewImage(attachment.preview || `/api/ai-chat/attachments/${attachment.id}`)}
                        >
                          <img src={attachment.preview || `/api/ai-chat/attachments/${attachment.id}`} alt={attachment.filename} />
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
                    {item.role === "user" && (
                      <div className="ai-chat-message-actions">
                        <Button type="text" size="small" icon={<Edit3 size={12} />} aria-label="编辑消息" title="编辑消息" onClick={() => editMessage(item)} />
                        <Button type="text" size="small" icon={<Copy size={12} />} aria-label="复制消息" title="复制消息" onClick={() => void navigator.clipboard.writeText(item.content).then(() => message.success("消息已复制"), () => message.error("消息复制失败"))} />
                        <Button type="text" danger size="small" icon={<Trash2 size={12} />} aria-label="删除消息" title="删除消息" onClick={() => deleteMessage(item)} />
                      </div>
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
              {contextInfo && <div className="ai-chat-context-info" role="status">
                <span>背景信息窗口：</span>
                <strong>{Math.min(100, Math.round((contextInfo.used_tokens / contextInfo.max_tokens) * 100))}% 已用</strong>
                <span>（剩余 {Math.max(0, 100 - Math.min(100, Math.round((contextInfo.used_tokens / contextInfo.max_tokens) * 100)))}%）</span>
                {contextInfo.compressed && <span>已自动压缩较早消息</span>}
              </div>}
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
                {showScrollToBottom && <Button type="text" icon={<ArrowDownToLine size={16} />} aria-label="置底" title="置底" onClick={() => messagesRef.current?.scrollTo({ top: messagesRef.current.scrollHeight, behavior: "smooth" })} />}
                <Button
                  type="text"
                  danger
                  icon={<Trash2 size={16} />}
                  aria-label="清空对话"
                  title="清空对话"
                  disabled={!messages.length || busy}
                  onClick={() => void clearMessages()}
                />
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
  if (configOnly) return <div className="page ai-chat-page"><AIPage configOnly /></div>;
  return <div className="page ai-chat-page">{chatView}</div>;
}
