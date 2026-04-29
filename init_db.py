import asyncio
from app.models.chatbot.base import ChatbotBase
from app.db.chatbot_database import chatbot_engine
from app.models.main.base import MainBase
from app.db.main_database import main_engine

# Import all models so they are registered with Base.metadata
import app.models.chatbot.session
import app.models.chatbot.message
import app.models.main.user
import app.models.main.event

from sqlalchemy import text

async def init_db():
    print("Dropping and recreating Chatbot DB tables...")
    async with chatbot_engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE;"))
        await conn.execute(text("CREATE SCHEMA public;"))
    async with chatbot_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";"))
        await conn.run_sync(ChatbotBase.metadata.create_all)
        
    
    print("Database initialization complete.")

if __name__ == "__main__":
    asyncio.run(init_db())
