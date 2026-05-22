"""
main.py — FastAPI backend for Real Estate AI Voice Chatbot.

Cloned and adapted from the Lâm Đồng tourism backend.
Adapted for real estate property tours with VR 360° integration.
"""

import asyncio
import base64
import hashlib
import hmac as _hmac
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from gemini_live import GeminiLive
from rag import RAGEngine
from chat_history import ChatHistory
from tools import (
    build_navigate_tool, navigate_property_scene,
    build_get_property_info_tool, get_property_info,
    build_get_pano_nodeid_tool, get_pano_nodeid,
    build_add_memory_tool, SessionMemory,
)

# ─── Load environment variables ───────────────────────────────────────────────
load_dotenv()

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logging.getLogger("gemini_live").setLevel(logging.DEBUG)
logging.getLogger(__name__).setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)

# ─── Config (all from .env, no hardcoded values) ──────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-live-preview")
GEMINI_VOICE = os.getenv("GEMINI_VOICE", "Aoede")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

# ─── Mutable runtime config (overridable via POST /admin/config) ──────────────
_CURRENT_MODEL: str = GEMINI_MODEL
_CURRENT_VOICE: str = GEMINI_VOICE
AVAILABLE_VOICES = ["Aoede", "Charon", "Fenrir", "Kore", "Puck"]

BASE_DIR = Path(__file__).parent
PROMPT_FILE = BASE_DIR / "prompt.txt"

# admin-dist: React admin UI build output
ADMIN_DIST_DIR = BASE_DIR / "admin-dist"
if not ADMIN_DIST_DIR.exists():
    ADMIN_DIST_DIR = None
    logger.warning("admin-dist not found — admin UI will fall back to static/admin.html")

# ─── Data directory (scenes.json + nodes.json) ────────────────────────────────
_data_dir_env = os.getenv("DATA_DIR", "").strip()
if _data_dir_env:
    DATA_DIR = Path(_data_dir_env)
elif (BASE_DIR / "data").exists():
    DATA_DIR = BASE_DIR / "data"
else:
    DATA_DIR = BASE_DIR / "data"
    DATA_DIR.mkdir(exist_ok=True)
SCENES_FILE = DATA_DIR / "scenes.json"
NODES_FILE  = DATA_DIR / "nodes.json"
logger.info("Data directory: %s", DATA_DIR)

# ─── System prompt (hot-reloadable) ───────────────────────────────────────────
def load_prompt() -> str:
    try:
        return PROMPT_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        logger.warning("prompt.txt not found, using default system prompt.")
        return "Bạn là chuyên viên tư vấn bất động sản chuyên nghiệp và tận tâm."


SYSTEM_PROMPT = load_prompt()
_INITIAL_PROMPT = SYSTEM_PROMPT
logger.info("System prompt loaded (%d chars)", len(SYSTEM_PROMPT))

# ─── RAG engine + Chat history (module-level singletons) ─────────────────────
rag_engine   = RAGEngine()
chat_history = ChatHistory()

# ─── Tool setup ───────────────────────────────────────────────────────────────
NAVIGATE_TOOL          = build_navigate_tool()
GET_PROPERTY_INFO_TOOL = build_get_property_info_tool()
GET_PANO_NODEID_TOOL   = build_get_pano_nodeid_tool()
ADD_MEMORY_TOOL        = build_add_memory_tool()

_GLOBAL_TOOL_MAPPING: dict = {
    "navigate_property_scene": navigate_property_scene,
    "get_property_info":       get_property_info,
    "get_pano_nodeid":         get_pano_nodeid,
}
ALL_TOOLS = [NAVIGATE_TOOL, GET_PROPERTY_INFO_TOOL, GET_PANO_NODEID_TOOL, ADD_MEMORY_TOOL]

# ─── Token-based auth (HMAC stateless, survives restarts) ─────────────────────

def _gen_admin_token() -> str:
    expiry = str(int(time.time() * 1000) + 24 * 3600 * 1000)
    sig = _hmac.new(ADMIN_PASSWORD.encode("utf-8"), expiry.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{expiry}.{sig}"


def _check_admin_token(token: str) -> bool:
    if not ADMIN_PASSWORD:
        return True  # auth disabled
    if not token or "." not in token:
        return False
    dot = token.rfind(".")
    expiry, sig = token[:dot], token[dot + 1:]
    expected = _hmac.new(ADMIN_PASSWORD.encode("utf-8"), expiry.encode("utf-8"), hashlib.sha256).hexdigest()
    try:
        if not _hmac.compare_digest(sig, expected):
            return False
        return int(time.time() * 1000) <= int(expiry)
    except Exception:
        return False


# ─── FastAPI app ──────────────────────────────────────────────────────────────
app = FastAPI(title="Real Estate AI Chatbot Backend")

# Update CORS origins with your actual deployment domains
_CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
if not _CORS_ORIGINS:
    _CORS_ORIGINS = ["http://localhost:3000", "http://localhost:5173", "http://localhost:8080"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Static files ─────────────────────────────────────────────────────────────
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
if ADMIN_DIST_DIR and (ADMIN_DIST_DIR / "assets").exists():
    app.mount("/admin/assets", StaticFiles(directory=ADMIN_DIST_DIR / "assets"), name="admin_assets")
    logger.info("admin-dist assets mounted from %s", ADMIN_DIST_DIR)

security = HTTPBasic(auto_error=False)

_NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate",
    "Pragma": "no-cache",
}


def _spa_response():
    if ADMIN_DIST_DIR and (ADMIN_DIST_DIR / "index.html").exists():
        return FileResponse(ADMIN_DIST_DIR / "index.html", headers=_NO_CACHE_HEADERS)
    fallback = STATIC_DIR / "admin.html"
    if fallback.exists():
        return FileResponse(fallback, headers=_NO_CACHE_HEADERS)
    return HTMLResponse("<h1>Admin UI not built yet.</h1>", status_code=503)


def _is_api_request(request: Request) -> bool:
    if "x-admin-token" in request.headers:
        return True
    accept = request.headers.get("accept", "")
    if "application/json" in accept and "text/html" not in accept:
        return True
    return False


def verify_admin(
    request: Request,
    credentials: Optional[HTTPBasicCredentials] = Depends(security),
) -> None:
    if not ADMIN_PASSWORD:
        return
    token = request.headers.get("X-Admin-Token", "").strip()
    if not token and not credentials:
        if _is_api_request(request):
            raise HTTPException(
                status_code=401,
                detail="Unauthorized",
                headers={"WWW-Authenticate": 'Bearer, Basic realm="Admin"'},
            )
        return
    if token and _check_admin_token(token):
        return
    if credentials and secrets.compare_digest(
        credentials.password.encode("utf-8"), ADMIN_PASSWORD.encode("utf-8")
    ):
        return
    raise HTTPException(
        status_code=401,
        detail="Unauthorized",
        headers={"WWW-Authenticate": 'Bearer, Basic realm="Admin"'},
    )


# ─── Landing page ─────────────────────────────────────────────────────────────
_LANDING_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>AI Voice Chatbot — BĐS</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{min-height:100vh;background:#0d1117;color:#e2e8f0;font-family:'Segoe UI',system-ui,sans-serif;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:24px}
  .card{background:#161b22;border:1px solid rgba(255,255,255,.08);border-radius:16px;padding:48px 40px;max-width:480px;width:100%;text-align:center;box-shadow:0 24px 64px rgba(0,0,0,.5)}
  .icon{width:64px;height:64px;border-radius:18px;background:linear-gradient(135deg,#2dd4bf,#06b6d4);display:flex;align-items:center;justify-content:center;margin:0 auto 24px;font-size:28px}
  h1{font-size:1.75rem;font-weight:700;letter-spacing:-.02em;color:#f1f5f9;margin-bottom:8px}
  .sub{color:#64748b;font-size:.9rem;line-height:1.6;margin-bottom:32px}
  .btn{display:inline-flex;align-items:center;gap:8px;background:linear-gradient(135deg,#2dd4bf,#06b6d4);color:#0d1117;font-weight:600;font-size:.9rem;padding:12px 28px;border-radius:10px;text-decoration:none;transition:opacity .2s}
  .btn:hover{opacity:.88}
  .divider{border:none;border-top:1px solid rgba(255,255,255,.06);margin:32px 0}
  .info{display:grid;grid-template-columns:1fr 1fr;gap:12px;text-align:left}
  .info-item{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.06);border-radius:10px;padding:14px 16px}
  .info-label{font-size:.7rem;text-transform:uppercase;letter-spacing:.06em;color:#475569;margin-bottom:4px}
  .info-value{font-size:.82rem;color:#94a3b8;font-family:monospace;word-break:break-all}
  .dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#34d399;margin-right:6px;box-shadow:0 0 6px #34d399}
  .status{font-size:.78rem;color:#34d399;margin-bottom:32px}
  footer{margin-top:40px;font-size:.75rem;color:#334155}
</style>
</head>
<body>
<div class="card">
  <div class="icon">🏠</div>
  <h1>AI Voice Chatbot</h1>
  <p class="sub">Trợ lý giọng nói thông minh cho dự án bất động sản.<br/>Tích hợp VR 360° &amp; Gemini Live AI.</p>
  <p class="status"><span class="dot"></span>Backend đang hoạt động</p>
  <a href="/admin/" class="btn">
    <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
    Vào Admin Panel
  </a>
  <hr class="divider"/>
  <div class="info">
    <div class="info-item">
      <div class="info-label">WebSocket</div>
      <div class="info-value">wss://[host]/ws</div>
    </div>
    <div class="info-item">
      <div class="info-label">API Docs</div>
      <div class="info-value">/docs</div>
    </div>
    <div class="info-item">
      <div class="info-label">Health</div>
      <div class="info-value">/admin/api/health</div>
    </div>
    <div class="info-item">
      <div class="info-label">Admin</div>
      <div class="info-value">/admin/</div>
    </div>
  </div>
</div>
<footer>Powered by Gemini Live · FastAPI · ChromaDB</footer>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def landing_page():
    return HTMLResponse(_LANDING_HTML)


# ─── Admin auth endpoints ──────────────────────────────────────────────────────
@app.post("/admin/login")
async def admin_login(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    password = (body.get("password") or "").strip()
    if ADMIN_PASSWORD and not secrets.compare_digest(
        password.encode("utf-8"), ADMIN_PASSWORD.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="Sai mật khẩu")
    return JSONResponse({"token": _gen_admin_token(), "message": "Đăng nhập thành công"})


@app.post("/admin/logout")
async def admin_logout():
    return JSONResponse({"ok": True})


@app.get("/admin/api/me")
async def admin_me(request: Request):
    token = request.headers.get("X-Admin-Token", "").strip()
    if not _check_admin_token(token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return JSONResponse({"ok": True})


@app.get("/admin/models")
async def admin_models(request: Request, _: None = Depends(verify_admin)):
    if not _is_api_request(request):
        return _spa_response()
    return JSONResponse({"models": [
        {"name": "gemini-3.1-flash-live-preview",                    "displayName": "Gemini 3.1 Flash Live Preview"},
        {"name": "gemini-2.5-flash-native-audio-latest",             "displayName": "Gemini 2.5 Flash Native Audio (Latest)"},
        {"name": "gemini-2.5-flash-native-audio-preview-09-2025",    "displayName": "Gemini 2.5 Flash Native Audio (Sep 2025)"},
        {"name": "gemini-2.5-flash-native-audio-preview-12-2025",    "displayName": "Gemini 2.5 Flash Native Audio (Dec 2025)"},
    ]})


@app.get("/admin")
@app.get("/admin/")
async def admin_page(request: Request):
    return _spa_response()


# ─── Admin: prompt ────────────────────────────────────────────────────────────
@app.get("/admin/prompt")
async def get_prompt(request: Request, _: None = Depends(verify_admin)):
    if not _is_api_request(request):
        return _spa_response()
    current = PROMPT_FILE.read_text(encoding="utf-8") if PROMPT_FILE.exists() else SYSTEM_PROMPT
    return JSONResponse({"prompt": current})


@app.post("/admin/prompt")
async def save_prompt(request: Request, _: None = Depends(verify_admin)):
    global SYSTEM_PROMPT
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    new_prompt = body.get("prompt", "").strip()
    if not new_prompt:
        raise HTTPException(status_code=400, detail="Prompt không được để trống")
    PROMPT_FILE.write_text(new_prompt, encoding="utf-8")
    SYSTEM_PROMPT = new_prompt
    logger.info("System prompt hot-reloaded via admin UI (%d chars)", len(SYSTEM_PROMPT))
    return JSONResponse({"message": "Đã lưu và áp dụng prompt mới thành công"})


# ─── Admin: config ────────────────────────────────────────────────────────────
@app.get("/admin/config")
async def admin_config(request: Request, _: None = Depends(verify_admin)):
    if not _is_api_request(request):
        return _spa_response()
    scene_map_json = os.getenv("SCENE_MAP_JSON", "{}")
    try:
        scene_map = json.loads(scene_map_json)
    except json.JSONDecodeError:
        scene_map = {}
    platform = (
        "Vertex AI"
        if os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").upper() == "TRUE"
        else "AI Studio"
    )
    current_prompt = PROMPT_FILE.read_text(encoding="utf-8") if PROMPT_FILE.exists() else SYSTEM_PROMPT
    return JSONResponse({
        "model": _CURRENT_MODEL,
        "voice": _CURRENT_VOICE,
        "availableVoices": AVAILABLE_VOICES,
        "prompt": current_prompt,
        "platform": platform,
        "scene_ids": list(scene_map.keys()),
    })


@app.post("/admin/config")
async def save_config(request: Request, _: None = Depends(verify_admin)):
    global _CURRENT_MODEL, _CURRENT_VOICE
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    model = (body.get("model") or "").strip()
    voice = (body.get("voice") or "").strip()
    if not model:
        raise HTTPException(status_code=400, detail="model không được để trống")
    if voice and voice not in AVAILABLE_VOICES:
        raise HTTPException(
            status_code=400,
            detail=f"voice không hợp lệ. Chọn một trong: {', '.join(AVAILABLE_VOICES)}",
        )
    _CURRENT_MODEL = model
    if voice:
        _CURRENT_VOICE = voice
    logger.info("Config hot-reloaded: model=%s voice=%s", _CURRENT_MODEL, _CURRENT_VOICE)
    return JSONResponse({
        "message": "Đã lưu cấu hình. Phiên WebSocket tiếp theo sẽ dùng model và voice mới.",
        "model": _CURRENT_MODEL,
        "voice": _CURRENT_VOICE,
    })


@app.post("/admin/reset")
async def reset_prompt_to_default(_: None = Depends(verify_admin)):
    global SYSTEM_PROMPT
    SYSTEM_PROMPT = _INITIAL_PROMPT
    PROMPT_FILE.write_text(_INITIAL_PROMPT, encoding="utf-8")
    logger.info("System prompt reset to initial value (%d chars)", len(SYSTEM_PROMPT))
    return JSONResponse({"message": "Đã reset về mặc định"})


# ─── Helpers: read/write JSON ──────────────────────────────────────────────────
def _read_json(path: Path, default=None):
    if default is None:
        default = []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ─── Public API ───────────────────────────────────────────────────────────────
@app.get("/api/scenes")
async def public_scenes():
    """Public — list all property scenes (used by VR frontend)."""
    return JSONResponse(_read_json(SCENES_FILE))


@app.get("/api/nodes")
async def public_nodes():
    """Public — list all VR nodes."""
    return JSONResponse(_read_json(NODES_FILE))


# ─── Admin CRUD: scenes ───────────────────────────────────────────────────────
@app.get("/admin/scenes")
async def list_scenes(request: Request, _: None = Depends(verify_admin)):
    if not _is_api_request(request):
        return _spa_response()
    return JSONResponse(_read_json(SCENES_FILE))


@app.post("/admin/scenes")
async def create_scene(request: Request, _: None = Depends(verify_admin)):
    try:
        scene = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    if not scene.get("id") or not scene.get("panoNodeId"):
        raise HTTPException(status_code=400, detail="id và panoNodeId là bắt buộc")
    scenes = _read_json(SCENES_FILE)
    if any(s["id"] == scene["id"] for s in scenes):
        raise HTTPException(status_code=409, detail=f"Scene id '{scene['id']}' đã tồn tại")
    scenes.append(scene)
    _write_json(SCENES_FILE, scenes)
    logger.info("Scene created: %s", scene["id"])
    return JSONResponse(scene, status_code=201)


@app.put("/admin/scenes/{scene_id}")
async def update_scene(scene_id: str, request: Request, _: None = Depends(verify_admin)):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    scenes = _read_json(SCENES_FILE)
    idx = next((i for i, s in enumerate(scenes) if s["id"] == scene_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy scene")
    scenes[idx] = {**scenes[idx], **body, "id": scene_id}
    _write_json(SCENES_FILE, scenes)
    logger.info("Scene updated: %s", scene_id)
    return JSONResponse(scenes[idx])


@app.delete("/admin/scenes/{scene_id}")
async def delete_scene(scene_id: str, _: None = Depends(verify_admin)):
    scenes = [s for s in _read_json(SCENES_FILE) if s["id"] != scene_id]
    _write_json(SCENES_FILE, scenes)
    logger.info("Scene deleted: %s", scene_id)
    return JSONResponse({"ok": True})


# ─── Admin CRUD: nodes ────────────────────────────────────────────────────────
@app.get("/admin/nodes")
async def list_nodes(request: Request, _: None = Depends(verify_admin)):
    if not _is_api_request(request):
        return _spa_response()
    return JSONResponse(_read_json(NODES_FILE))


@app.post("/admin/nodes")
async def create_node(request: Request, _: None = Depends(verify_admin)):
    try:
        node = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    if not node.get("nodeId"):
        raise HTTPException(status_code=400, detail="nodeId là bắt buộc")
    nodes = _read_json(NODES_FILE)
    if any(n["nodeId"] == node["nodeId"] for n in nodes):
        raise HTTPException(status_code=409, detail=f"nodeId '{node['nodeId']}' đã tồn tại")
    nodes.append(node)
    _write_json(NODES_FILE, nodes)
    logger.info("Node created: %s", node["nodeId"])
    return JSONResponse(node, status_code=201)


@app.put("/admin/nodes/{node_id}")
async def update_node(node_id: str, request: Request, _: None = Depends(verify_admin)):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    nodes = _read_json(NODES_FILE)
    idx = next((i for i, n in enumerate(nodes) if n["nodeId"] == node_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy node")
    nodes[idx] = {**nodes[idx], **body, "nodeId": node_id}
    _write_json(NODES_FILE, nodes)
    logger.info("Node updated: %s", node_id)
    return JSONResponse(nodes[idx])


@app.delete("/admin/nodes/{node_id}")
async def delete_node(node_id: str, _: None = Depends(verify_admin)):
    nodes = [n for n in _read_json(NODES_FILE) if n["nodeId"] != node_id]
    _write_json(NODES_FILE, nodes)
    logger.info("Node deleted: %s", node_id)
    return JSONResponse({"ok": True})


# ─── Admin: RAG documents ─────────────────────────────────────────────────────
@app.get("/admin/rag/documents")
async def rag_list_documents(request: Request, _: None = Depends(verify_admin)):
    if not _is_api_request(request):
        return _spa_response()
    return JSONResponse({"documents": rag_engine.list_documents()})


@app.post("/admin/rag/upload")
async def rag_upload(
    request: Request,
    _: None = Depends(verify_admin),
):
    from fastapi import UploadFile
    import shutil

    MAX_BYTES = 20 * 1024 * 1024  # 20 MB
    ALLOWED_EXTS = {".pdf", ".docx", ".csv", ".xlsx", ".xls", ".txt"}

    form = await request.form()
    file: UploadFile = form.get("file")  # type: ignore
    if file is None:
        raise HTTPException(status_code=400, detail="No file field in form")

    from pathlib import Path as _Path
    ext = _Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTS))}",
        )

    dest_dir = _Path(os.getenv("RAG_DOCS_DIR", "./data/rag_docs"))
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / (file.filename or "upload")

    size = 0
    with dest.open("wb") as out:
        while True:
            chunk = await file.read(64 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_BYTES:
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="File exceeds 20 MB limit")
            out.write(chunk)

    result = rag_engine.ingest_file(dest, file.filename or dest.name)
    return JSONResponse(result, status_code=201)


@app.delete("/admin/rag/documents/{filename:path}")
async def rag_delete_document(
    filename: str,
    request: Request,
    _: None = Depends(verify_admin),
):
    from pathlib import Path as _Path
    result = rag_engine.delete_file(filename)
    # Also remove physical file if it exists
    dest_dir = _Path(os.getenv("RAG_DOCS_DIR", "./data/rag_docs"))
    phys = dest_dir / filename
    if phys.exists():
        phys.unlink()
    return JSONResponse({"ok": True, **result})


# ─── Admin: chat history ──────────────────────────────────────────────────────
@app.get("/admin/history")
async def history_list(
    request: Request,
    limit: int = 50,
    project: str = "",
    _: None = Depends(verify_admin),
):
    if not _is_api_request(request):
        return _spa_response()
    sessions = await chat_history.list_sessions(
        limit=limit,
        project=project or None,
    )
    return JSONResponse({"sessions": sessions})


@app.get("/admin/history/{session_id}")
async def history_get(
    session_id: str,
    _: None = Depends(verify_admin),
):
    messages = await chat_history.get_history(session_id)
    return JSONResponse({"session_id": session_id, "messages": messages})


@app.delete("/admin/history/{session_id}")
async def history_delete(
    session_id: str,
    _: None = Depends(verify_admin),
):
    ok = await chat_history.delete_session(session_id)
    return JSONResponse({"ok": ok})


# ─── SPA catch-all: must be the LAST GET route under /admin/ ─────────────────
@app.get("/admin/{full_path:path}")
async def admin_spa_fallback(full_path: str, request: Request):
    return _spa_response()


# ─── WebSocket endpoint ────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for Gemini Live AI voice chat."""
    # Resolve or create session ID
    session_id: str = (
        websocket.query_params.get("session_id") or secrets.token_urlsafe(16)
    )

    await websocket.accept()
    logger.info("WebSocket connection accepted (session=%s)", session_id)

    # Inform client of their session ID immediately
    await websocket.send_json({"type": "session_info", "session_id": session_id})

    audio_input_queue: asyncio.Queue = asyncio.Queue()
    video_input_queue: asyncio.Queue = asyncio.Queue()
    text_input_queue: asyncio.Queue = asyncio.Queue()

    async def audio_output_callback(data: bytes):
        await websocket.send_bytes(data)

    async def audio_interrupt_callback():
        pass

    _session_mem = SessionMemory()
    _current_node: dict = {"nodeId": None, "sceneId": None}

    def _get_pano_nodeid_session() -> dict:
        if _current_node["nodeId"]:
            return {
                "nodeId":  _current_node["nodeId"],
                "sceneId": _current_node["sceneId"],
            }
        return {
            "error": (
                "Chưa nhận được vị trí VR từ trình duyệt. "
                "Hãy mở ứng dụng VR360 và xem một cảnh panorama trước."
            )
        }

    _session_tool_mapping = {
        **_GLOBAL_TOOL_MAPPING,
        "add_to_memory":   _session_mem.add_to_memory,
        "get_pano_nodeid": _get_pano_nodeid_session,
    }

    # Inject RAG context into system prompt for this session
    effective_prompt = SYSTEM_PROMPT
    try:
        if rag_engine.has_documents():
            rag_ctx = rag_engine.get_all_context()
            if rag_ctx:
                effective_prompt = SYSTEM_PROMPT + "\n\n" + rag_ctx
    except Exception as _rag_exc:
        logger.warning("RAG context injection failed: %s", _rag_exc)

    gemini_client = GeminiLive(
        api_key=GEMINI_API_KEY,
        model=_CURRENT_MODEL,
        input_sample_rate=16000,
        system_instruction=effective_prompt,
        voice_name=_CURRENT_VOICE,
        tools=ALL_TOOLS,
        tool_mapping=_session_tool_mapping,
    )

    async def receive_from_client():
        try:
            while True:
                message = await websocket.receive()

                if message.get("bytes"):
                    await audio_input_queue.put(message["bytes"])
                elif message.get("text"):
                    text = message["text"]
                    try:
                        payload = json.loads(text)

                        if isinstance(payload, dict) and "realtimeInput" in payload:
                            rt = payload["realtimeInput"]
                            audio_obj = rt.get("audio") if isinstance(rt, dict) else None
                            if isinstance(audio_obj, dict):
                                b64 = audio_obj.get("data", "")
                                if b64:
                                    await audio_input_queue.put(base64.b64decode(b64))
                            continue

                        if isinstance(payload, dict) and payload.get("type") == "node_changed":
                            _current_node["nodeId"]  = payload.get("nodeId")
                            _current_node["sceneId"] = payload.get("sceneId")
                            logger.debug("VR node updated: %s / %s",
                                         _current_node["nodeId"], _current_node["sceneId"])
                            continue

                        if isinstance(payload, dict) and payload.get("type") == "image":
                            logger.debug(
                                "Received image chunk: %d base64 chars",
                                len(payload.get("data", "")),
                            )
                            image_data = base64.b64decode(payload["data"])
                            await video_input_queue.put(image_data)
                            continue

                        if isinstance(payload, dict) and "clientContent" in payload:
                            cc = payload["clientContent"]
                            for turn in cc.get("turns") or []:
                                for part in turn.get("parts") or []:
                                    actual = (part.get("text") or "").strip()
                                    if actual:
                                        await text_input_queue.put(actual)
                            continue

                    except (json.JSONDecodeError, Exception):
                        pass

                    await text_input_queue.put(text)

        except WebSocketDisconnect:
            logger.info("WebSocket disconnected")
        except Exception as e:
            logger.error("Error receiving from client: %s", e)

    receive_task = asyncio.create_task(receive_from_client())

    async def run_session():
        async for event in gemini_client.start_session(
            audio_input_queue=audio_input_queue,
            video_input_queue=video_input_queue,
            text_input_queue=text_input_queue,
            audio_output_callback=audio_output_callback,
            audio_interrupt_callback=audio_interrupt_callback,
        ):
            if not event:
                continue

            # Save transcription events to chat history
            evt_type = event.get("type", "")
            if evt_type == "user" and event.get("text"):
                try:
                    await chat_history.save_message(session_id, "user", event["text"])
                except Exception as _ce:
                    logger.warning("ChatHistory save user msg failed: %s", _ce)
            elif evt_type == "gemini" and event.get("text"):
                try:
                    await chat_history.save_message(session_id, "assistant", event["text"])
                except Exception as _ce:
                    logger.warning("ChatHistory save assistant msg failed: %s", _ce)

            if event.get("type") == "tool_call":
                name = event.get("name")

                # navigate_property_scene → push vr_navigate to client
                if name == "navigate_property_scene":
                    result = event.get("result", {})
                    node_id = result.get("node_id") if isinstance(result, dict) else None
                    scene_id = (event.get("args") or {}).get("scene_id")
                    if node_id:
                        logger.info("Sending vr_navigate: nodeId=%s sceneId=%s", node_id, scene_id)
                        await websocket.send_json({
                            "type": "vr_navigate",
                            "nodeId": node_id,
                            "sceneId": scene_id,
                        })

                # add_to_memory → push memory_update to client
                elif name == "add_to_memory":
                    await websocket.send_json({
                        "type": "memory_update",
                        "memories": _session_mem.get_all(),
                    })

                await websocket.send_json(event)
            else:
                await websocket.send_json(event)

    try:
        await run_session()
    except asyncio.CancelledError:
        # Normal shutdown (server stopping or client disconnecting) — not an error
        pass
    except Exception as e:
        import traceback

        logger.error(
            "Error in Gemini session: %s: %s\n%s",
            type(e).__name__,
            e,
            traceback.format_exc(),
        )
    finally:
        receive_task.cancel()
        try:
            await websocket.close()
        except Exception:
            pass


# ─── Health check ──────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok"}
