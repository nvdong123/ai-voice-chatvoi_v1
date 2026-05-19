import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { Pencil, Trash2, Plus, X, Check, ChevronDown, ChevronUp } from 'lucide-react';
import { adminApi, type Scene } from '../api/client';
import PageHeader from '../components/PageHeader';

// ─── Empty scene template ─────────────────────────────────────────────────────
const EMPTY: Omit<Scene, never> = {
  id: '',
  panoNodeId: '',
  name: '',
  desc: '',
  type: '',
  area: undefined,
  bedrooms: undefined,
  floor: undefined,
  direction: '',
  price: undefined,
  status: 'available',
  legal: '',
  handover: '',
  thumbClass: '',
};

// ─── Inline row editor ────────────────────────────────────────────────────────
function SceneRow({
  scene,
  onSave,
  onDelete,
}: {
  scene: Scene;
  onSave: (updated: Scene) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft]     = useState<Scene>(scene);
  const [busy, setBusy]       = useState(false);

  function set(key: keyof Scene, val: string) {
    setDraft((prev) => ({ ...prev, [key]: val }));
  }
  function setNum(key: keyof Scene, val: string) {
    const n = val === '' ? undefined : Number(val);
    setDraft((prev) => ({ ...prev, [key]: n }));
  }

  async function save() {
    setBusy(true);
    try {
      await onSave(draft);
      setEditing(false);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!confirm(`Xoá scene "${scene.name || scene.id}"?`)) return;
    setBusy(true);
    try {
      await onDelete(scene.id);
    } finally {
      setBusy(false);
    }
  }

  if (!editing) {
    const priceStr = scene.price ? (scene.price / 1e9).toFixed(1) + ' tỷ' : null;
    const badge = scene.status === 'available' ? '\ud83d\udfe2' : scene.status === 'reserved' ? '\ud83d\udfe1' : '\ud83d\udd34';
    return (
      <div className="card flex items-start justify-between gap-4 p-4">
        <div className="min-w-0 flex-1">
          <p className="truncate font-semibold text-gray-100">{scene.name || <em className="text-gray-500">chưa đặt tên</em>}</p>
          <p className="mt-0.5 text-xs text-gray-500">
            <span className="mr-3 font-mono text-teal-400">{scene.id}</span>
            <span className="font-mono text-gray-400 text-[11px] break-all">{scene.panoNodeId}</span>
          </p>
          {(scene.type || scene.area || priceStr) && (
            <p className="mt-1 text-xs text-gray-400">
              {badge} {[scene.type, scene.area ? scene.area + 'm²' : null, priceStr].filter(Boolean).join(' · ')}
            </p>
          )}
          {scene.desc && (
            <p className="mt-1 text-xs text-gray-400 line-clamp-2">{scene.desc}</p>
          )}
        </div>
        <div className="flex shrink-0 gap-1">
          <button
            onClick={() => { setDraft(scene); setEditing(true); }}
            className="rounded-lg p-2 text-gray-400 transition-colors hover:bg-white/5 hover:text-gray-100"
            title="Sửa"
          >
            <Pencil size={14} />
          </button>
          <button
            onClick={remove}
            disabled={busy}
            className="rounded-lg p-2 text-gray-400 transition-colors hover:bg-red-500/10 hover:text-red-400 disabled:opacity-40"
            title="Xoá"
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="card space-y-3 p-4">
      <div className="grid grid-cols-2 gap-3">
        <Field label="ID (slug)" value={draft.id} readOnly onChange={(v) => set('id', v)} />
        <Field label="Pano Node ID" value={draft.panoNodeId} onChange={(v) => set('panoNodeId', v)} />
        <Field label="Tên hiển thị" value={draft.name} onChange={(v) => set('name', v)} />
        <Field label="Loại BDS" value={draft.type ?? ''} onChange={(v) => set('type', v)} placeholder="Căn hộ, Biệt thự, Tiện ích…" />
      </div>
      <div className="grid grid-cols-3 gap-3">
        <FieldNum label="Diện tích (m²)" value={draft.area} onChange={(v) => setNum('area', v)} />
        <FieldNum label="Phòng ngủ" value={draft.bedrooms} onChange={(v) => setNum('bedrooms', v)} />
        <FieldNum label="Tầng" value={draft.floor} onChange={(v) => setNum('floor', v)} />
        <Field label="Hướng" value={draft.direction ?? ''} onChange={(v) => set('direction', v)} placeholder="Đông Nam, Tây Bắc…" />
        <FieldNum label="Giá (VNĐ)" value={draft.price} onChange={(v) => setNum('price', v)} />
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-400">Trạng thái</label>
          <select
            value={draft.status ?? 'available'}
            onChange={(e) => set('status', e.target.value)}
            className="w-full rounded-lg border border-white/10 bg-surface px-3 py-1.5 text-sm text-gray-100 focus:border-teal-400/50 focus:outline-none"
          >
            <option value="available">🟢 Còn hàng</option>
            <option value="reserved">🟡 Giữ chỗ</option>
            <option value="sold">🔴 Đã bán</option>
          </select>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Pháp lý" value={draft.legal ?? ''} onChange={(v) => set('legal', v)} placeholder="Sổ hồng lâu dài…" />
        <Field label="Bàn giao" value={draft.handover ?? ''} onChange={(v) => set('handover', v)} placeholder="Q4/2027…" />
      </div>
      <div>
        <label className="mb-1 block text-xs font-medium text-gray-400">Mô tả</label>
        <textarea
          value={draft.desc ?? ''}
          onChange={(e) => set('desc', e.target.value)}
          rows={2}
          className="w-full rounded-lg border border-white/10 bg-surface px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:border-teal-400/50 focus:outline-none"
        />
      </div>
      <div className="flex justify-end gap-2">
        <button
          onClick={() => setEditing(false)}
          className="flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-xs text-gray-400 transition-colors hover:bg-white/5"
        >
          <X size={12} /> Huỷ
        </button>
        <button
          onClick={save}
          disabled={busy || !draft.id || !draft.panoNodeId}
          className="flex items-center gap-1.5 rounded-lg bg-teal-500 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-teal-400 disabled:opacity-40"
        >
          <Check size={12} /> Lưu
        </button>
      </div>
    </div>
  );
}

// ─── Add new scene form ───────────────────────────────────────────────────────
function AddSceneForm({ onAdd }: { onAdd: (s: Scene) => Promise<void> }) {
  const [open, setOpen]   = useState(false);
  const [draft, setDraft] = useState<Scene>({ ...EMPTY });
  const [busy, setBusy]   = useState(false);

  function set(key: keyof Scene, val: string | number | undefined) {
    setDraft((prev) => ({ ...prev, [key]: val }));
  }
  function setNum(key: keyof Scene, val: string) {
    const n = val === '' ? undefined : Number(val);
    setDraft((prev) => ({ ...prev, [key]: n }));
  }

  async function submit() {
    setBusy(true);
    try {
      await onAdd(draft);
      setDraft({ ...EMPTY });
      setOpen(false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-4 py-3 text-sm font-medium text-teal-400 transition-colors hover:bg-white/5"
      >
        <Plus size={15} />
        Thêm scene mới
        {open ? <ChevronUp size={14} className="ml-auto" /> : <ChevronDown size={14} className="ml-auto" />}
      </button>

      {open && (
        <div className="space-y-3 border-t border-white/[0.08] px-4 pb-4 pt-3">
          <div className="grid grid-cols-2 gap-3">
            <Field label="ID *" value={draft.id} onChange={(v) => set('id', v)} placeholder="vd: sky-lounge" />
            <Field label="Pano Node ID *" value={draft.panoNodeId} onChange={(v) => set('panoNodeId', v)} placeholder="vd: panorama_3F…" />
            <Field label="Tên hiển thị" value={draft.name} onChange={(v) => set('name', v)} placeholder="vd: Sky Lounge Tầng 42" />
            <Field label="Loại BDS" value={draft.type ?? ''} onChange={(v) => set('type', v)} placeholder="Căn hộ, Tiện ích…" />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <FieldNum label="Diện tích (m²)" value={draft.area} onChange={(v) => setNum('area', v)} />
            <FieldNum label="Phòng ngủ" value={draft.bedrooms} onChange={(v) => setNum('bedrooms', v)} />
            <FieldNum label="Tầng" value={draft.floor} onChange={(v) => setNum('floor', v)} />
            <Field label="Hướng" value={draft.direction ?? ''} onChange={(v) => set('direction', v)} placeholder="Đông Nam…" />
            <FieldNum label="Giá (VNĐ)" value={draft.price} onChange={(v) => setNum('price', v)} />
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-400">Trạng thái</label>
              <select
                value={draft.status ?? 'available'}
                onChange={(e) => set('status', e.target.value)}
                className="w-full rounded-lg border border-white/10 bg-surface px-3 py-1.5 text-sm text-gray-100 focus:border-teal-400/50 focus:outline-none"
              >
                <option value="available">🟢 Còn hàng</option>
                <option value="reserved">🟡 Giữ chỗ</option>
                <option value="sold">🔴 Đã bán</option>
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Pháp lý" value={draft.legal ?? ''} onChange={(v) => set('legal', v)} placeholder="Sổ hồng lâu dài" />
            <Field label="Bàn giao" value={draft.handover ?? ''} onChange={(v) => set('handover', v)} placeholder="Q4/2027" />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-400">Mô tả</label>
            <textarea
              value={draft.desc ?? ''}
              onChange={(e) => set('desc', e.target.value)}
              rows={2}
              placeholder="Mô tả ngắn về căn hộ/tiện ích..."
              className="w-full rounded-lg border border-white/10 bg-surface px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:border-teal-400/50 focus:outline-none"
            />
          </div>
          <div className="flex justify-end">
            <button
              onClick={submit}
              disabled={busy || !draft.id.trim() || !draft.panoNodeId.trim()}
              className="flex items-center gap-1.5 rounded-lg bg-teal-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-teal-400 disabled:opacity-40"
            >
              <Plus size={14} /> Thêm
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Simple text field ────────────────────────────────────────────────────────
function Field({
  label, value, onChange, readOnly, placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  readOnly?: boolean;
  placeholder?: string;
}) {
  return (
    <div>      <label className="mb-1 block text-xs font-medium text-gray-400">{label}</label>
      <input
        type="text"
        value={value}
        readOnly={readOnly}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={`w-full rounded-lg border border-white/10 bg-surface px-3 py-1.5 text-sm text-gray-100 placeholder-gray-600 focus:border-teal-400/50 focus:outline-none ${readOnly ? 'cursor-not-allowed opacity-50' : ''}`}
      />
    </div>
  );
}

function FieldNum({
  label, value, onChange, placeholder,
}: {
  label: string;
  value: number | undefined;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-gray-400">{label}</label>
      <input
        type="number"
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-lg border border-white/10 bg-surface px-3 py-1.5 text-sm text-gray-100 placeholder-gray-600 focus:border-teal-400/50 focus:outline-none"
      />
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────
export default function ScenesPage() {
  const [scenes, setScenes]   = useState<Scene[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch]   = useState('');

  useEffect(() => {
    adminApi
      .getScenes()
      .then(setScenes)
      .catch(() => toast.error('Không thể tải danh sách scenes'))
      .finally(() => setLoading(false));
  }, []);

  async function handleAdd(scene: Scene) {
    try {
      const created = await adminApi.createScene(scene);
      setScenes((prev) => [...prev, created]);
      toast.success(`Đã thêm: ${created.name || created.id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Lỗi khi thêm scene');
    }
  }

  async function handleSave(updated: Scene) {
    try {
      const saved = await adminApi.updateScene(updated.id, updated);
      setScenes((prev) => prev.map((s) => (s.id === saved.id ? saved : s)));
      toast.success('Đã lưu');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Lỗi khi lưu');
    }
  }

  async function handleDelete(id: string) {
    try {
      await adminApi.deleteScene(id);
      setScenes((prev) => prev.filter((s) => s.id !== id));
      toast.success('Đã xoá');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Lỗi khi xoá');
    }
  }

  const filtered = search.trim()
    ? scenes.filter(
        (s) =>
          s.id.includes(search) ||
          s.name.toLowerCase().includes(search.toLowerCase()) ||
          s.panoNodeId.includes(search),
      )
    : scenes;

  return (
    <>
      <PageHeader
        title="Quản lý Bất động sản / Scenes"
        description={`${scenes.length} panorama scene${scenes.length !== 1 ? 's' : ''} — click Sửa để cập nhật thông tin`}
      />

      {/* Add form */}
      <div className="mb-4">
        <AddSceneForm onAdd={handleAdd} />
      </div>

      {/* Search */}
      <input
        type="text"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Tìm theo id, tên, nodeId..."
        className="mb-4 w-full rounded-lg border border-white/10 bg-surface-card px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:border-teal-400/50 focus:outline-none"
      />

      {/* List */}
      {loading ? (
        <p className="py-12 text-center text-sm text-gray-500">Đang tải...</p>
      ) : filtered.length === 0 ? (
        <p className="py-12 text-center text-sm text-gray-500">
          {search ? 'Không tìm thấy kết quả.' : 'Chưa có scene nào.'}
        </p>
      ) : (
        <div className="space-y-2">
          {filtered.map((scene) => (
            <SceneRow
              key={scene.id}
              scene={scene}
              onSave={handleSave}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}
    </>
  );
}
