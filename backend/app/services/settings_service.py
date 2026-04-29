from app.repositories.base import AgentPreferenceRepository
from app.schemas.domain import AgentPreferenceRecord


class SettingsService:
    def __init__(self, preference_repository: AgentPreferenceRepository):
        self.preference_repository = preference_repository

    async def get_agent_preferences(self, user_id: str) -> AgentPreferenceRecord:
        record = await self.preference_repository.get_by_user_id(user_id)
        if record is None:
            record = AgentPreferenceRecord(user_id=user_id)
            record = await self.preference_repository.save(record)
        return record

    async def update_agent_preferences(
        self,
        user_id: str,
        *,
        script_style: str | None,
        custom_sensitive_terms: list[str],
    ) -> AgentPreferenceRecord:
        record = await self.get_agent_preferences(user_id)
        record.script_style = script_style
        record.custom_sensitive_terms = [item.strip() for item in custom_sensitive_terms if item.strip()]
        return await self.preference_repository.save(record)
