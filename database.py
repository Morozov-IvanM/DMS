import pg8000.native
import base64

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