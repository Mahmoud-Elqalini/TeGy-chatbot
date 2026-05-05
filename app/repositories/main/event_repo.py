import json
from decimal import Decimal
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

class MainEventRepository:
    """
    Repository for interacting with the Main (MSSQL) database for event data.
    Uses SQLAlchemy AsyncSession.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        return value

    @staticmethod
    def _normalize_row(row: Any) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
            
        # row._mapping is available in SQLAlchemy 2.0 Row objects when fetched via execute
        return {
            key: MainEventRepository._json_safe(value)
            for key, value in dict(row._mapping).items()
        }

    @staticmethod
    def _normalize_rows(rows: List[Any]) -> List[Dict[str, Any]]:
        return [
            MainEventRepository._normalize_row(row)
            for row in rows
            if row is not None
        ]

    async def fetch_features_by_event_ids(self, event_ids: List[int]) -> Dict[int, List[Dict[str, Any]]]:
        """
        Fetches live event add-ons/features from MSSQL Features.
        """
        if not event_ids:
            return {}

        # Safe parameterization for IN clause
        placeholders = ", ".join([f":id_{i}" for i in range(len(event_ids))])
        params = {f"id_{i}": eid for i, eid in enumerate(event_ids)}

        sql = f"""
            SELECT
                Id AS source_id,
                EventId AS event_source_id,
                Name AS name,
                Description AS description,
                Price AS price,
                ParticipantsNumber AS capacity,
                [Limit] AS limit_per_user,
                CreatedAt AS created_at
            FROM dbo.Features
            WHERE EventId IN ({placeholders})
            ORDER BY EventId ASC, Id ASC
        """

        result = await self.db.execute(text(sql), params)
        rows = result.fetchall()

        features_by_event: Dict[int, List[Dict[str, Any]]] = {}

        for row in self._normalize_rows(rows):
            event_id = int(row["event_source_id"])
            features_by_event.setdefault(event_id, []).append(row)

        return features_by_event

    async def get_events_by_ids(self, source_ids: List[int]) -> List[Dict[str, Any]]:
        """
        Fetches live event data directly from MSSQL Events.
        Maintains order based on the provided source_ids.
        """
        if not source_ids:
            return []

        clean_ids = []
        for value in source_ids:
            try:
                clean_ids.append(int(value))
            except Exception:
                continue

        if not clean_ids:
            return []

        # Parameter binding for IN clause and ORDER BY CASE
        in_placeholders = ", ".join([f":id_{i}" for i in range(len(clean_ids))])
        order_cases = " ".join([f"WHEN :id_{i} THEN {idx}" for idx, i in enumerate(range(len(clean_ids)))])
        
        params = {f"id_{i}": cid for i, cid in enumerate(clean_ids)}

        sql = f"""
            SELECT
                Id AS source_id,
                Name AS name,
                Description AS description,
                Category AS category,
                Tags AS tags,
                StartDate AS start_date,
                EndDate AS end_date,
                RegistrationDeadLine AS registration_deadline,
                Place AS place,
                City AS city,
                Street AS street,
                IsOnline AS is_online,
                Url AS url,
                Price AS price,
                TotalTicketsCount AS total_tickets,
                TicketCount AS ticket_count,
                status AS status,
                Visibility AS visibility,
                CoverImageUrl AS cover_image_url,
                CreatedByUserId AS organizer_source_id,
                CreatedAt AS created_at,
                IsChatActive AS is_chat_active,
                SoldOutTime AS sold_out_time
            FROM dbo.Events
            WHERE Id IN ({in_placeholders})
            ORDER BY
                CASE Id
                    {order_cases}
                END
        """

        result = await self.db.execute(text(sql), params)
        rows = result.fetchall()

        events = self._normalize_rows(rows)
        features_by_event = await self.fetch_features_by_event_ids(clean_ids)

        for event in events:
            event_id = int(event["source_id"])

            raw_tags = event.get("tags")
            if isinstance(raw_tags, str):
                try:
                    event["tags"] = json.loads(raw_tags)
                except Exception:
                    event["tags"] = raw_tags

            event["features"] = features_by_event.get(event_id, [])

        return events
