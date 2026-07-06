import jwt
import datetime


SECRET_KEY = "id6ATMgbrH7myxeylAtfLHwbbX5RpWTqHSRmBp-sh6M"
user_id = "3fa85f64-5717-4562-b3fc-2c963f66afa6"

def create_token(user_id: str):
    payload = {
        "sub": user_id,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=1)
    }

    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    return token

if __name__ == "__main__":
    token = create_token(user_id)
    print(f"Generated JWT Token: {token}")