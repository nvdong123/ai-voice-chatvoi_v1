# Backend Bất Động Sản — AI Voice Chatbot

FastAPI backend tích hợp Gemini Live AI cho tư vấn bất động sản với tham quan nhà mẫu VR 360°.

Clone và điều chỉnh từ backend du lịch Lâm Đồng. Toàn bộ logic WebSocket / Gemini Live giữ nguyên, chỉ thay đổi domain (du lịch → bất động sản).

## Điểm khác biệt so với backend du lịch

| Hạng mục | Du lịch Lâm Đồng | Bất Động Sản |
|---|---|---|
| Vai trò AI | Hướng dẫn viên du lịch | Chuyên gia tư vấn BĐS |
| Tool điều hướng | `navigate_vr_scene` | `navigate_property_scene` |
| Tool thông tin | `get_weather_for_scene` | `get_property_info` |
| Tool bộ nhớ | `add_to_memory` | `add_to_memory` (giữ nguyên) |
| Dữ liệu | Địa danh du lịch | Dự án, căn hộ, biệt thự |
| CORS | Domain cố định | Cấu hình qua `CORS_ORIGINS` env |

## Cấu trúc thư mục

```
backend-realestate/
├── main.py              # FastAPI app (WebSocket + Admin API)
├── gemini_live.py       # Gemini Live client (không đổi)
├── tools.py             # Tools BĐS: navigate, get_property_info, memory
├── prompt.txt           # System prompt cho AI tư vấn BĐS
├── requirements.txt
├── Dockerfile
├── .env.example
└── data/
    ├── scenes.json      # Danh sách cảnh VR (sản phẩm BĐS)
    └── nodes.json       # Mapping nodeId ↔ sceneId
```

## Cài đặt & chạy

```bash
# 1. Copy file env
cp .env.example .env

# 2. Điền GEMINI_API_KEY vào .env

# 3. Cài dependencies
pip install -r requirements.txt

# 4. Chạy server
uvicorn main:app --reload --port 8000
```

## Cấu hình scenes.json

Mỗi sản phẩm BĐS là một object JSON với các trường:

```json
{
  "id": "can-ho-2pn-toa-a",          // ID duy nhất (dùng trong tool)
  "panoNodeId": "node001",            // Node ID trong Pano2VR
  "name": "Căn hộ 2PN - Tòa A",
  "project": "Tên dự án",
  "type": "Căn hộ chung cư",
  "area": 68,                         // m²
  "bedrooms": 2,
  "bathrooms": 2,
  "floor": 5,
  "direction": "Đông Nam",
  "price": 3200000000,                // VNĐ
  "status": "available",              // available | reserved | sold
  "legal": "Sổ hồng lâu dài",
  "handover": "Q3/2026",
  "desc": "Mô tả ngắn hiện thị trong VR"
}
```

## WebSocket API

Giống hệt backend du lịch. Frontend gửi/nhận:

- **Gửi audio**: bytes thô PCM 16kHz
- **Gửi vị trí VR**: `{"type": "node_changed", "nodeId": "node001", "sceneId": "can-ho-2pn-toa-a"}`
- **Nhận điều hướng**: `{"type": "vr_navigate", "nodeId": "node001", "sceneId": "..."}`
- **Nhận memory**: `{"type": "memory_update", "memories": [...]}`

## Admin UI

Truy cập `/admin` để quản lý prompt, cấu hình model/voice, và CRUD scenes/nodes.
