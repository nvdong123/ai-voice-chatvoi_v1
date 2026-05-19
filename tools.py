"""
tools.py — VR property navigation and real-estate assistant tools.

Property scene map is auto-loaded from data/scenes.json (single source of truth).
SCENE_MAP_JSON env var is only used as a fallback override.
"""

import json
import os
import time
from pathlib import Path

from google.genai import types


def _find_scenes_json() -> Path | None:
    """Locate scenes.json.
      1. backend-realestate/data/scenes.json  (Docker container / self-contained)
    """
    local = Path(__file__).parent / "data" / "scenes.json"
    if local.exists():
        return local
    return None


def _load_scene_map() -> dict:
    """Build {scene_id: panoNodeId} map.

    Priority:
      1. data/scenes.json
      2. SCENE_MAP_JSON env var  — override / fallback
    """
    scenes_path = _find_scenes_json()
    if scenes_path:
        try:
            data = json.loads(scenes_path.read_text(encoding="utf-8"))
            return {
                item["id"]: item["panoNodeId"]
                for item in data
                if "id" in item and "panoNodeId" in item
            }
        except Exception:
            pass
    # Fallback: env var
    scene_map_json = os.getenv("SCENE_MAP_JSON", "{}")
    try:
        return json.loads(scene_map_json)
    except json.JSONDecodeError:
        return {}


def _load_scenes_data() -> list:
    """Load full scenes data array for property info lookup."""
    scenes_path = _find_scenes_json()
    if scenes_path:
        try:
            return json.loads(scenes_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


# ══════════════════════════════════════════════════════════════════════════════
#  navigate_property_scene
# ══════════════════════════════════════════════════════════════════════════════

def navigate_property_scene(scene_id: str) -> dict:
    """Navigate to a VR property scene by scene_id."""
    scene_map = _load_scene_map()
    node_id = scene_map.get(scene_id)
    if node_id is None:
        available = list(scene_map.keys())
        return {"error": f"Unknown scene_id '{scene_id}'. Available: {available}"}
    return {"result": "navigated", "node_id": node_id}


def build_navigate_tool() -> types.Tool:
    """Build the Gemini tool declaration for navigate_property_scene."""
    scene_map = _load_scene_map()
    scene_ids = list(scene_map.keys())

    scene_id_schema = types.Schema(
        type=types.Type.STRING,
        description="ID của cảnh VR bất động sản muốn chuyển tới",
    )
    if scene_ids:
        scene_id_schema = types.Schema(
            type=types.Type.STRING,
            description="ID của cảnh VR bất động sản muốn chuyển tới",
            enum=scene_ids,
        )

    return types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="navigate_property_scene",
                description=(
                    "Chuyển camera panorama đến một cảnh VR bất động sản cụ thể. "
                    "Gọi hàm này khi khách hàng yêu cầu xem hoặc tham quan một căn hộ, "
                    "biệt thự, khu vực tiện ích, hoặc khu vực cụ thể trong dự án."
                ),
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={"scene_id": scene_id_schema},
                    required=["scene_id"],
                ),
            )
        ]
    )


# ══════════════════════════════════════════════════════════════════════════════
#  get_property_info
# ══════════════════════════════════════════════════════════════════════════════

def get_property_info(scene_id: str) -> dict:
    """Return detailed property information for a given scene_id."""
    scenes = _load_scenes_data()
    scene = next((s for s in scenes if s.get("id") == scene_id), None)
    if scene is None:
        all_ids = [s.get("id") for s in scenes if s.get("id")]
        return {
            "error": f"Không tìm thấy thông tin cho scene_id '{scene_id}'. "
                     f"Có sẵn: {all_ids}"
        }

    # Return all extra fields beyond id and panoNodeId
    info = {k: v for k, v in scene.items() if k not in ("panoNodeId",)}
    return info


def build_get_property_info_tool() -> types.Tool:
    """Build the Gemini tool declaration for get_property_info."""
    scene_ids = list(_load_scene_map().keys())
    return types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="get_property_info",
                description=(
                    "Lấy thông tin chi tiết về một căn hộ, biệt thự hoặc sản phẩm bất động sản: "
                    "giá bán, diện tích, số phòng ngủ, loại sản phẩm, tình trạng (còn hàng/đã bán/giữ chỗ), "
                    "tầng, hướng, tiện ích, tình trạng pháp lý. "
                    "Gọi khi khách hàng hỏi về giá, diện tích, tình trạng hoặc thông tin cụ thể của một sản phẩm."
                ),
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "scene_id": types.Schema(
                            type=types.Type.STRING,
                            description=f"ID của sản phẩm bất động sản. Một trong: {', '.join(scene_ids)}.",
                            enum=scene_ids if scene_ids else None,
                        )
                    },
                    required=["scene_id"],
                ),
            )
        ]
    )


# ══════════════════════════════════════════════════════════════════════════════
#  get_pano_nodeid  (stub — backend cannot query browser VR state)
# ══════════════════════════════════════════════════════════════════════════════

def get_pano_nodeid() -> dict:
    """Backend stub: browser VR state is unavailable in a voice-only session."""
    return {
        "error": (
            "Không thể xác định vị trí VR trong phiên thoại không có trình duyệt. "
            "Tính năng này chỉ khả dụng khi sử dụng ứng dụng web VR360."
        )
    }


def build_get_pano_nodeid_tool() -> types.Tool:
    """Build the Gemini tool declaration for get_pano_nodeid."""
    return types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="get_pano_nodeid",
                description=(
                    "Lấy node ID và scene ID của cảnh VR mà khách hàng đang xem. "
                    "Gọi khi cần biết chính xác khách hàng đang xem căn nào trong không gian VR."
                ),
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={},
                ),
            )
        ]
    )


# ══════════════════════════════════════════════════════════════════════════════
#  add_to_memory  (session-scoped — instantiate SessionMemory per WebSocket)
# ══════════════════════════════════════════════════════════════════════════════

class SessionMemory:
    """Stores memory items added by the add_to_memory tool during a session."""

    def __init__(self):
        self._items: list[dict] = []

    def add_to_memory(self, memory: str, emoji: str = "📝") -> dict:
        self._items.append({"memory": memory, "emoji": emoji})
        return {"success": True, "total": len(self._items)}

    def get_all(self) -> list[dict]:
        return list(self._items)


def build_add_memory_tool() -> types.Tool:
    """Build the Gemini tool declaration for add_to_memory."""
    return types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="add_to_memory",
                description=(
                    "Lưu một ghi chú về nhu cầu hoặc thông tin quan trọng của khách hàng "
                    "trong phiên tư vấn này. Gọi bất cứ khi nào khách hàng tiết lộ thông tin "
                    "hữu ích (ví dụ: ngân sách, mục đích mua, số phòng ngủ cần thiết, "
                    "khu vực ưu tiên, thời gian dự kiến mua, phương thức thanh toán)."
                ),
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "memory": types.Schema(
                            type=types.Type.STRING,
                            description="Nội dung ghi chú ngắn gọn (1-2 câu).",
                        ),
                        "emoji": types.Schema(
                            type=types.Type.STRING,
                            description="Emoji đại diện (ví dụ: 💰, 🏠, 📅, 📍).",
                        ),
                    },
                    required=["memory"],
                ),
            )
        ]
    )
