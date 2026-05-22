import { useEffect, useState } from 'react';
import { MessageSquare, Trash2, ChevronDown, ChevronUp, AlertCircle, User, Bot } from 'lucide-react';
import toast from 'react-hot-toast';
import { adminApi, type HistorySession, type HistoryMessage } from '../api/client';
import PageHeader from '../components/PageHeader';

// ─── Single session row (collapsible) ────────────────────────────────────────
function SessionRow({
  session,
  onDelete,
}: {
  session: HistorySession;
  onDelete: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<HistoryMessage[]>([]);
  const [loadingMsgs, setLoadingMsgs] = useState(false);

  async function toggle() {
    if (!open && messages.length === 0) {
      setLoadingMsgs(true);
      try {
        const data = await adminApi.getHistorySession(session.session_id);
        setMessages(data.messages ?? []);
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : 'Lỗi';
        toast.error(msg);
      } finally {
        setLoadingMsgs(false);
      }
    }
    setOpen((v) => !v);
  }

  async function handleDelete() {
    const short = session.session_id.slice(0, 8) + '…';
    if (!confirm(`Xoá session "${short}"?`)) return;
    try {
      await adminApi.deleteHistorySession(session.session_id);
      toast.success('Đã xoá session');
      onDelete(session.session_id);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Lỗi';
      toast.error(msg);
    }
  }

  const timeStr = session.updated_at
    ? new Date(session.updated_at).toLocaleString('vi-VN')
    : '';

  return (
    <div className="card overflow-hidden">
      {/* Header row */}
      <div className="flex items-center gap-3 p-4">
        <button
          className="flex min-w-0 flex-1 items-center gap-3 text-left"
          onClick={toggle}
        >
          <MessageSquare size={15} className="flex-shrink-0 text-teal-400" />
          <div className="min-w-0 flex-1">
            <p className="truncate font-mono text-xs text-teal-400">
              {session.session_id}
            </p>
            <p className="mt-0.5 text-xs text-gray-500">
              {session.message_count} tin nhắn
              {session.project ? ` · ${session.project}` : ''}
              {timeStr ? ` · ${timeStr}` : ''}
            </p>
          </div>
          {open
            ? <ChevronUp size={14} className="flex-shrink-0 text-gray-500" />
            : <ChevronDown size={14} className="flex-shrink-0 text-gray-500" />}
        </button>
        <button
          onClick={handleDelete}
          className="flex-shrink-0 rounded-lg p-1.5 text-gray-500 transition-colors hover:bg-red-500/10 hover:text-red-400"
          title="Xoá session"
        >
          <Trash2 size={15} />
        </button>
      </div>

      {/* Message thread */}
      {open && (
        <div className="border-t border-white/[0.06] px-4 pb-4 pt-3">
          {loadingMsgs ? (
            <p className="text-xs text-gray-500">Đang tải tin nhắn...</p>
          ) : messages.length === 0 ? (
            <p className="text-xs text-gray-500">Không có tin nhắn</p>
          ) : (
            <div className="flex max-h-72 flex-col gap-2 overflow-y-auto pr-1">
              {messages.map((msg, i) => {
                const isUser = msg.role === 'user';
                return (
                  <div
                    key={i}
                    className={`flex items-start gap-2 ${isUser ? '' : 'flex-row-reverse'}`}
                  >
                    <span
                      className={`mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full text-[10px] ${
                        isUser
                          ? 'bg-teal-400/15 text-teal-400'
                          : 'bg-purple-500/15 text-purple-400'
                      }`}
                    >
                      {isUser ? <User size={10} /> : <Bot size={10} />}
                    </span>
                    <div
                      className={`max-w-[85%] rounded-lg px-3 py-1.5 text-xs leading-relaxed ${
                        isUser
                          ? 'bg-white/5 text-gray-200'
                          : 'bg-purple-500/10 text-gray-300'
                      }`}
                    >
                      {msg.text}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────
export default function HistoryPage() {
  const [sessions, setSessions] = useState<HistorySession[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    try {
      const data = await adminApi.getHistorySessions();
      setSessions(data.sessions ?? []);
    } catch {
      toast.error('Không tải được lịch sử trò chuyện');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  function removeSession(id: string) {
    setSessions((prev) => prev.filter((s) => s.session_id !== id));
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Lịch sử trò chuyện"
        description="Các session chat của khách với AI — click để xem nội dung"
      />

      {loading ? (
        <p className="text-sm text-gray-500">Đang tải...</p>
      ) : sessions.length === 0 ? (
        <div className="card flex items-center gap-3 p-4 text-sm text-gray-500">
          <AlertCircle size={16} className="flex-shrink-0" />
          Chưa có lịch sử trò chuyện nào.
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          <p className="text-xs text-gray-500">{sessions.length} session</p>
          {sessions.map((s) => (
            <SessionRow key={s.session_id} session={s} onDelete={removeSession} />
          ))}
        </div>
      )}
    </div>
  );
}
