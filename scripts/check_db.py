"""
DB Connection Health Check
Run: python check_db.py
"""
import asyncio
import asyncpg
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")

async def check():
    url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    
    try:
        conn = await asyncpg.connect(url)
        
        # 1. Check PostgreSQL version
        version = await conn.fetchval("SELECT version();")
        print(f"[OK] Connected successfully!")
        print(f"     PostgreSQL: {version.split(',')[0]}")
        
        # 2. List all databases
        databases = await conn.fetch("SELECT datname FROM pg_database WHERE datistemplate = false;")
        print(f"\n[DB] Databases: {[r['datname'] for r in databases]}")
        
        # 3. List tables in current DB
        tables = await conn.fetch("""
            SELECT tablename FROM pg_tables 
            WHERE schemaname = 'public'
            ORDER BY tablename;
        """)
        if tables:
            print(f"\n[TABLES] Tables in current DB:")
            for t in tables:
                print(f"   - {t['tablename']}")
        else:
            print(f"\n[WARN] No tables found in the database yet.")
        
        await conn.close()
        
    except Exception as e:
        print(f"[ERROR] Connection failed: {type(e).__name__}: {e}")

asyncio.run(check())
