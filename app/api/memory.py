from fastapi import APIRouter

router = APIRouter(prefix="/api/ai")


@router.post("/memory/clear")
def memory_clear(body: dict):
    from app.core.conversation_memory import clear_context, new_session_id
    sid = body.get("sessionId") or new_session_id()
    clear_context(sid)
    return {"success": True, "message": "上下文已清空", "sessionId": sid}
