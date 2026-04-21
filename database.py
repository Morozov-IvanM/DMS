import pg8000.native
import hashlib
import os

# _p = base64.b64decode("MjdQa3NJZW4=").decode()
def get_db_connection():
    return pg8000.native.Connection(
        user="postgres",
        # password=_p
        password="27PksIen",
        host="127.0.0.1",
        port=5432,
        database="dms_db"
    )

# Создаем глобальный объект базы (как и было)
db = get_db_connection()

# Функции безопасности (hash_password и verify_password)
def hash_password(password: str):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(plain_password, hashed_password):
    return hash_password(plain_password) == hashed_password