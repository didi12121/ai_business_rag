from fastapi import APIRouter, Path
from sqlalchemy import text

from app.database import SessionLocal
from app.models.request import ModelSaveRequest
from app.llm.openai_compatible import refresh_llm_config

router = APIRouter(prefix="/api/ai")


@router.get("/models")
def list_models():
    """List all LLM model configs."""
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                "SELECT id, name, base_url, api_key, model, timeout, "
                "is_active, sort_order, create_time, update_time "
                "FROM ai_llm_model ORDER BY sort_order, id"
            )
        ).fetchall()
        models = []
        for r in rows:
            models.append({
                "id": r[0], "name": r[1], "base_url": r[2],
                "api_key": r[3], "model": r[4], "timeout": r[5],
                "is_active": bool(r[6]), "sort_order": r[7],
                "create_time": str(r[8]) if r[8] else None,
                "update_time": str(r[9]) if r[9] else None,
            })
        return {"success": True, "models": models}
    except Exception as e:
        return {"success": False, "errorCode": "LIST_ERROR", "errorMsg": str(e)}
    finally:
        db.close()


@router.post("/models")
def create_model(req: ModelSaveRequest):
    """Add a new LLM model config."""
    db = SessionLocal()
    try:
        result = db.execute(
            text(
                "INSERT INTO ai_llm_model (name, base_url, api_key, model, timeout, sort_order, is_active) "
                "VALUES (:name, :base_url, :api_key, :model, :timeout, :sort_order, 0)"
            ),
            {
                "name": req.name, "base_url": req.base_url,
                "api_key": req.api_key, "model": req.model,
                "timeout": req.timeout, "sort_order": req.sort_order,
            },
        )
        db.commit()
        return {"success": True, "id": result.lastrowid, "message": "模型已添加"}
    except Exception as e:
        db.rollback()
        return {"success": False, "errorCode": "CREATE_ERROR", "errorMsg": str(e)}
    finally:
        db.close()


@router.put("/models/{model_id}")
def update_model(model_id: int, req: ModelSaveRequest):
    """Update an existing LLM model config."""
    db = SessionLocal()
    try:
        db.execute(
            text(
                "UPDATE ai_llm_model SET name=:name, base_url=:base_url, api_key=:api_key, "
                "model=:model, timeout=:timeout, sort_order=:sort_order "
                "WHERE id=:id"
            ),
            {
                "name": req.name, "base_url": req.base_url,
                "api_key": req.api_key, "model": req.model,
                "timeout": req.timeout, "sort_order": req.sort_order,
                "id": model_id,
            },
        )
        db.commit()
        refresh_llm_config()
        return {"success": True, "message": "模型已更新"}
    except Exception as e:
        db.rollback()
        return {"success": False, "errorCode": "UPDATE_ERROR", "errorMsg": str(e)}
    finally:
        db.close()


@router.delete("/models/{model_id}")
def delete_model(model_id: int):
    """Delete a model config. Cannot delete the only active model."""
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT is_active FROM ai_llm_model WHERE id = :id"),
            {"id": model_id},
        ).fetchone()
        if not row:
            return {"success": False, "errorCode": "NOT_FOUND", "errorMsg": "模型不存在"}
        if row[0]:
            count = db.execute(
                text("SELECT COUNT(*) FROM ai_llm_model")
            ).fetchone()[0]
            if count <= 1:
                return {"success": False, "errorCode": "LAST_ACTIVE",
                        "errorMsg": "不能删除唯一激活的模型，请先添加新模型并激活"}
        db.execute(text("DELETE FROM ai_llm_model WHERE id = :id"), {"id": model_id})
        db.commit()
        refresh_llm_config()
        return {"success": True, "message": "模型已删除"}
    except Exception as e:
        db.rollback()
        return {"success": False, "errorCode": "DELETE_ERROR", "errorMsg": str(e)}
    finally:
        db.close()


@router.post("/models/{model_id}/activate")
def activate_model(model_id: int):
    """Set a model as the active one."""
    db = SessionLocal()
    try:
        exists = db.execute(
            text("SELECT id FROM ai_llm_model WHERE id = :id"),
            {"id": model_id},
        ).fetchone()
        if not exists:
            return {"success": False, "errorCode": "NOT_FOUND", "errorMsg": "模型不存在"}
        db.execute(text("UPDATE ai_llm_model SET is_active = 0"))
        db.execute(text("UPDATE ai_llm_model SET is_active = 1 WHERE id = :id"), {"id": model_id})
        db.commit()
        refresh_llm_config()
        return {"success": True, "message": "模型已切换"}
    except Exception as e:
        db.rollback()
        return {"success": False, "errorCode": "ACTIVATE_ERROR", "errorMsg": str(e)}
    finally:
        db.close()
