import asyncio
import uuid
import httpx
import time
import sys

sys.stdout.reconfigure(encoding='utf-8')

API_URL = "http://127.0.0.1:8000/api/v1/chat/message"
HEADERS = {
    "x-api-key": "NIfxW9XJw83M9Y3_X2Bf4qSARsQgdLMT0riE7crmsBk",
    "Content-Type": "application/json"
}

async def main():
    user_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    
    print(f"Testing session: {session_id}")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Request 1: Ask for events
        payload1 = {
            "user_id": user_id,
            "session_id": session_id,
            "message": "انا ببحث عن حفلات في القاهرة",
            "role": "user"
        }
        
        print("\n--- Request 1 ---")
        t0 = time.time()
        res1 = await client.post(API_URL, json=payload1, headers=HEADERS)
        t1 = time.time()
        print(f"Status: {res1.status_code}")
        print(f"Time: {t1-t0:.2f}s")
        print(f"Response: {res1.text[:200]}...")
        
        # IMMEDIATELY send Request 2 to trigger race condition
        # (Before BackgroundTasks commit to DB)
        payload2 = {
            "user_id": user_id,
            "session_id": session_id,
            "message": "كم سعر اول حفلة؟",
            "role": "user"
        }
        
        print("\n--- Request 2 (IMMEDIATE) ---")
        t0 = time.time()
        res2 = await client.post(API_URL, json=payload2, headers=HEADERS)
        t1 = time.time()
        print(f"Status: {res2.status_code}")
        print(f"Time: {t1-t0:.2f}s")
        print(f"Response: {res2.text[:200]}...")

if __name__ == "__main__":
    asyncio.run(main())
