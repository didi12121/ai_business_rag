from pydantic import BaseModel


class AskRequest(BaseModel):
    question: str
    sessionId: str | None = None
    userId: str | None = None
    showSql: bool = True


class ModelSaveRequest(BaseModel):
    name: str
    base_url: str
    api_key: str
    model: str
    timeout: int = 120
    sort_order: int = 0
