# Deploy backend-realestate lên Coolify

## Yêu cầu

- VPS có **Coolify** đã cài
- Domain/subdomain trỏ về VPS (vd: `api-realestate.yourdomain.com`)
- Repo đã push lên GitHub/GitLab (hoặc dùng Coolify Git integration)

---

## 1. Tạo Resource trên Coolify

1. Mở Coolify → **New Resource** → **Application**
2. Chọn source: **Git Repository** (hoặc **Dockerfile** nếu dùng local)
3. Trỏ tới repo, **Root Directory** = `/backend-realestate`
4. Coolify tự detect `Dockerfile` → chọn **Dockerfile** build mode
5. **Port**: `8000`

> **Lưu ý:** Dockerfile đã có multi-stage build — stage 1 build React admin UI,
> stage 2 chạy Python backend. Không cần làm gì thêm.

---

## 2. Cấu hình Environment Variables

Vào tab **Environment Variables** và thêm:

| Biến | Giá trị | Bắt buộc |
|---|---|---|
| `GEMINI_API_KEY` | API key từ [Google AI Studio](https://aistudio.google.com/apikey) | ✅ |
| `GEMINI_MODEL` | `gemini-2.0-flash-live-001` | ✅ |
| `GEMINI_VOICE` | `Aoede` | ✅ |
| `ADMIN_PASSWORD` | Mật khẩu bất kỳ (tự đặt) | ✅ |
| `CORS_ORIGINS` | Domain frontend (xem bên dưới) | ✅ |
| `DATA_DIR` | (để trống — dùng mặc định `/app/data`) | ❌ |

### Giá trị CORS_ORIGINS

```
https://your-frontend-domain.com,https://www.your-frontend-domain.com
```

Nếu test local thêm: `,http://localhost:5500`

---

## 3. Cấu hình Domain & HTTPS

- **Domain**: `api-realestate.yourdomain.com`
- **Port**: `8000`
- **HTTPS**: bật (Coolify + Let's Encrypt tự động)

Sau khi deploy xong, cập nhật `CORS_ORIGINS` với domain thật.

---

## 4. Cấu hình frontend (demo-realestate)

Sau khi backend đã có URL production, sửa `index.html` trong frontend:

```html
<!-- Thay dòng này: -->
<script>window.AI_BACKEND_WS = (location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + location.hostname + ':8000/ws';</script>

<!-- Thành: -->
<script>window.AI_BACKEND_WS = 'wss://api-realestate.yourdomain.com/ws';</script>
```

---

## 5. Endpoints sau khi deploy

| URL | Mô tả |
|---|---|
| `https://api-realestate.yourdomain.com/` | Health check |
| `https://api-realestate.yourdomain.com/admin/` | Admin panel (React UI) |
| `wss://api-realestate.yourdomain.com/ws` | WebSocket Gemini Live |
| `https://api-realestate.yourdomain.com/admin/api/scenes` | API scenes |

---

## 6. Persistent Data (tuỳ chọn)

`scenes.json` và `nodes.json` nằm trong `/app/data/` bên trong container.
Để giữ data khi redeploy, mount volume trong Coolify:

- **Volume**: `/app/data` → persistent volume

Nếu không mount, data sẽ reset về file gốc trong repo mỗi lần deploy.
