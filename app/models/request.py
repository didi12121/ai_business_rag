from pydantic import BaseModel


class AskRequest(BaseModel):
    question: str
    sessionId: str | None = None
    userId: str | None = None
    showSql: bool = True
