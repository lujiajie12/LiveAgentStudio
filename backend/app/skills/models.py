from pydantic import BaseModel, Field


class SkillMatch(BaseModel):
    mode: str = "keyword_any"  # keyword_any | regex
    keywords: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)


class SkillResponse(BaseModel):
    text: str
    agent_name: str = "skill"
    intent: str = "direct"


class SkillDefinition(BaseModel):
    id: str
    name: str
    enabled: bool = True
    priority: int = 10
    match: SkillMatch
    response: SkillResponse
