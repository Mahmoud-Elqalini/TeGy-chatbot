from __future__ import annotations

import uuid

from app.models.chatbot.model_settings import ModelSettings
from app.repositories.base_repo import BaseRepository


class ModelSettingsRepository(BaseRepository[ModelSettings]):
    def __init__(self, db_session):
        super().__init__(ModelSettings, db_session, id_field="model_setting_id")
