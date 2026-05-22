import { useEffect, useRef, useState } from 'react';
import { Upload, Trash2, FileText, AlertCircle } from 'lucide-react';
import toast from 'react-hot-toast';
import { adminApi, type RagDocument } from '../api/client';
import PageHeader from '../components/PageHeader';

function fmtSize(bytes?: number): string {
  if (!bytes) return '';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1024 / 1024).toFixed(1) + ' MB';
}

export default function RAGPage() {
  const [docs, setDocs] = useState<RagDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  async function load() {
    try {
      const data = await adminApi.getRagDocuments();
      setDocs(data.documents ?? []);
    } catch {
      toast.error('Không tải được danh sách tài liệu');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function handleUpload(files: FileList | null) {
    if (!files?.length) return;
    setUploading(true);
    let success = 0;
    for (const file of Array.from(files)) {
      try {
        const res = await adminApi.uploadRagDocument(file);
        toast.success(`"${res.filename}" — ${res.chunks} chunks`);
        success++;
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : 'Lỗi không xác định';
        toast.error(`"${file.name}": ${msg}`);
      }
    }
    setUploading(false);
    if (success > 0) await load();
    // reset input so same file can be re-uploaded
    if (inputRef.current) inputRef.current.value = '';
  }

  async function handleDelete(filename: string) {
    if (!confirm(`Xoá "${filename}" khỏi RAG?`)) return;
    try {
      await adminApi.deleteRagDocument(filename);
      toast.success('Đã xoá');
      setDocs((prev) => prev.filter((d) => d.filename !== filename));
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Lỗi không xác định';
      toast.error(msg);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Tài liệu RAG"
        description="Upload tài liệu để AI có thêm ngữ cảnh bất động sản khi trả lời khách"
      />

      {/* Upload zone */}
      <div
        className={`card flex cursor-pointer flex-col items-center justify-center gap-3 border-2 border-dashed p-10 text-center transition-colors ${
          dragOver
            ? 'border-teal-400/60 bg-teal-400/5'
            : 'border-white/[0.12] hover:border-teal-400/40'
        }`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          handleUpload(e.dataTransfer.files);
        }}
      >
        <Upload size={32} className={uploading ? 'animate-bounce text-teal-400' : 'text-teal-400'} />
        <p className="text-sm font-medium text-gray-200">
          {uploading ? 'Đang tải lên...' : 'Kéo thả hoặc click để upload'}
        </p>
        <p className="text-xs text-gray-500">.txt · .pdf · .docx · .md</p>
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          multiple
          accept=".txt,.pdf,.docx,.md"
          onChange={(e) => handleUpload(e.target.files)}
        />
      </div>

      {/* Document list */}
      {loading ? (
        <p className="text-sm text-gray-500">Đang tải...</p>
      ) : docs.length === 0 ? (
        <div className="card flex items-center gap-3 p-4 text-sm text-gray-500">
          <AlertCircle size={16} className="flex-shrink-0" />
          Chưa có tài liệu nào. Upload tài liệu để RAG hoạt động.
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          <p className="text-xs text-gray-500">{docs.length} tài liệu</p>
          {docs.map((doc) => (
            <div
              key={doc.filename}
              className="card flex items-center justify-between gap-4 p-4"
            >
              <div className="flex min-w-0 flex-1 items-center gap-3">
                <FileText size={18} className="flex-shrink-0 text-teal-400" />
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-gray-100">
                    {doc.filename}
                  </p>
                  <p className="text-xs text-gray-500">
                    {doc.chunks} chunk{doc.chunks !== 1 ? 's' : ''}
                    {doc.size_bytes ? ` · ${fmtSize(doc.size_bytes)}` : ''}
                  </p>
                </div>
              </div>
              <button
                onClick={() => handleDelete(doc.filename)}
                className="flex-shrink-0 rounded-lg p-1.5 text-gray-500 transition-colors hover:bg-red-500/10 hover:text-red-400"
                title="Xoá tài liệu"
              >
                <Trash2 size={15} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
