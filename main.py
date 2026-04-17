import os
import uuid
import shutil
from fastapi import FastAPI, Request, UploadFile, File, Form, Response, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from urllib.parse import quote, unquote
from passlib.context import CryptContext

# Импортируем наши новые модули
from database import db
from utils import get_safe_name, format_time, write_to_history

# Настройки путей
UPLOAD_DIR = "C:/CorpStorage/Uploads"
CHAT_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "Global_Chat")
os.makedirs(CHAT_UPLOAD_DIR, exist_ok=True)

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Монтирование статики
current_dir = os.path.dirname(os.path.abspath(__file__))
static_path = os.path.join(current_dir, "static")
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")

# Создаем объект для работы с хешированием
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str):
    """Превращает пароль в хеш для хранения в базе"""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str):
    """Сравнивает введенный пароль с хешем из базы"""
    return pwd_context.verify(plain_password, hashed_password)

# --- РЕГИСТРАЦИЯ ---
@app.post("/register")
async def register(username: str = Form(...), email: str = Form(...), password: str = Form(...)):
    try:
        hashed = hash_password(password)
        db.run('''
            INSERT INTO public."Users" ("Username", "Email", "HashedPassword") 
            VALUES (:u, :e, :p)
        ''', u=username, e=email, p=hashed)
        return RedirectResponse(url="/login?success=registered", status_code=303)
    except Exception as e:
        return RedirectResponse(url="/login?error=UserExists", status_code=303)


# --- АВТОРИЗАЦИЯ ---
# 1. ПОКАЗ СТРАНИЦЫ (ОБЯЗАТЕЛЬНО ДОЛЖЕН БЫТЬ)
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None, success: str = None):
    success_msg = "Регистрация прошла успешно! Войдите." if success == "registered" else None
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": error,
        "success_msg": success_msg
    })

# 2. ОБРАБОТКА ВХОДА
@app.post("/login")
async def login(response: Response, login_field: str = Form(...), password: str = Form(...)):
    user_row = db.run('''
        SELECT "Username", "HashedPassword" 
        FROM public."Users" 
        WHERE "Email" = :e
        LIMIT 1
    ''', e=login_field.strip().lower()) # Приводим к нижнему регистру для надежности

    if not user_row:
        return RedirectResponse(url="/login?error=UserNotFound", status_code=303)

    db_username = user_row[0][0]
    hashed_pass = user_row[0][1]

    if not verify_password(password, hashed_pass):
        return RedirectResponse(url="/login?error=WrongPassword", status_code=303)

    # Успешный вход
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(key="user_name", value=quote(db_username), httponly=True)
    return response

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("user_name") # Удаляем куку
    return response

@app.post("/change-password")
async def change_password(
    request: Request,
    old_password: str = Form(...),
    new_password: str = Form(...),
    user_name: str = Cookie(None)
):
    if not user_name:
        return RedirectResponse(url="/login", status_code=303)

    # 1. Получаем текущий хеш пароля из базы
    decoded_name = unquote(user_name)
    user_row = db.run('''
        SELECT "HashedPassword" FROM public."Users" 
        WHERE "Username" = :u LIMIT 1
    ''', u=decoded_name)

    if not user_row:
        return {"error": "Пользователь не найден"}

    current_hashed_pass = user_row[0][0]

    # 2. Проверяем, правильно ли введен старый пароль
    if not verify_password(old_password, current_hashed_pass):
        # Возвращаем на главную или в профиль с ошибкой
        return RedirectResponse(url="/?error=wrong_old_password", status_code=303)

    # 3. Хешируем новый пароль и обновляем базу
    new_hashed = hash_password(new_password)
    db.run('''
        UPDATE public."Users" 
        SET "HashedPassword" = :p 
        WHERE "Username" = :u
    ''', p=new_hashed, u=decoded_name)

    return RedirectResponse(url="/?success=password_changed", status_code=303)


# --- ГЛАВНАЯ СТРАНИЦА ---
@app.get("/", response_class=HTMLResponse)
async def index(request: Request, user_name: str = Cookie(None), q: str = ""):
    if not user_name:
        return templates.TemplateResponse("login.html", {"request": request})

    decoded_name = unquote(user_name)

    # 1. Поиск или список проектов
    if q:
        projects = db.run(
            'SELECT "Id", "Name", "Description" FROM public."Projects" WHERE "Status" = \'Active\' AND "Name" ILIKE :s ORDER BY "Id" DESC',
            s=f"%{q}%")
    else:
        projects = db.run(
            'SELECT "Id", "Name", "Description" FROM public."Projects" WHERE "Status" = \'Active\' ORDER BY "Id" DESC')

    # 2. Последние комментарии
    last_comments = db.run('''
        SELECT c."Text", c."AuthorName", p."Name", c."ProjectId" 
        FROM public."Comments" c
        JOIN public."Projects" p ON c."ProjectId" = p."Id"
        ORDER BY c."CreatedAt" DESC LIMIT 5
    ''')

    # 3. Чат (Добавляем форматирование времени)
    raw_chat_messages = db.run('''
            SELECT c."Id", c."AuthorName", c."Message", c."CreatedAt", a."Id", a."FileName"
            FROM public."GlobalChat" c
            LEFT JOIN public."ChatAttachments" a ON c."Id" = a."MessageId"
            ORDER BY c."Id" DESC LIMIT 50
        ''')

    # Пересобираем список, заменяя r[3] (CreatedAt) на отформатированную строку
    chat_messages = [
        (r[0], r[1], r[2], format_time(r[3]), r[4], r[5])
        for r in raw_chat_messages
    ]

    # 4. Список пользователей
    user_list = [row[0] for row in db.run(
        'SELECT DISTINCT "AuthorName" FROM public."GlobalChat" UNION SELECT DISTINCT "AuthorName" FROM public."Comments"')]

    return templates.TemplateResponse("index.html", {
        "request": request,
        "projects": projects,
        "user_name": decoded_name,
        "search_query": q,
        "last_comments": last_comments,
        "chat_messages": chat_messages,  # Теперь здесь время уже "ЧЧ:ММ"
        "user_list": user_list
    })

# --- API ЖИВОГО ЧАТА ---
@app.post("/api/chat/send")
async def api_send_message(message: str = Form(...), file: UploadFile = File(None), user_name: str = Cookie(None)):
    if not user_name: return {"success": False}
    author = unquote(user_name)

    # 1. Сохраняем текст и получаем ID
    res = db.run('INSERT INTO public."GlobalChat" ("AuthorName", "Message") VALUES (:a, :m) RETURNING "Id"',
                 a=author, m=message)

    # ВАЖНО: берем [0][0], так как возвращается [[ID]]
    msg_id = res[0][0]

    # 2. Если есть файл - сохраняем
    if file and file.filename:
        f_ext = os.path.splitext(file.filename)[1]
        f_path = os.path.join(CHAT_UPLOAD_DIR, f"{uuid.uuid4()}{f_ext}")

        with open(f_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        db.run('''INSERT INTO public."ChatAttachments" ("MessageId", "FileName", "InternalPath") 
                  VALUES (:m_id, :f_n, :i_p)''',
               m_id=msg_id, f_n=file.filename, i_p=f_path)

    return {"success": True}


@app.get("/api/chat/messages")
async def api_get_messages(last_id: int = 0):
    rows = db.run('''
        SELECT c."Id", c."AuthorName", c."Message", c."CreatedAt", a."Id" as attach_id, a."FileName"
        FROM public."GlobalChat" c
        LEFT JOIN public."ChatAttachments" a ON c."Id" = a."MessageId"
        WHERE c."Id" > :last_id ORDER BY c."Id" ASC
    ''', last_id=last_id)
    return {"messages": [
        {"id": r[0], "author": r[1], "text": r[2], "time": format_time(r[3]), "file_id": r[4], "file_name": r[5]} for r
        in rows]}


# --- ПРОЕКТЫ И КОММЕНТАРИИ ---
@app.get("/project/{p_id}", response_class=HTMLResponse)
async def project_detail(request: Request, p_id: int, user_name: str = Cookie(None)):
    if not user_name: return RedirectResponse(url="/")
    project = db.run('SELECT "Id", "Name", "Description", "Status" FROM public."Projects" WHERE "Id" = :id', id=p_id)
    if not project: return HTMLResponse("Проект не найден", status_code=404)

    comments = db.run(
        'SELECT "Id", "AuthorName", "Text", "CreatedAt" FROM public."Comments" WHERE "ProjectId" = :id ORDER BY "CreatedAt" DESC',
        id=p_id)
    attachments = db.run('SELECT "Id", "CommentId", "FileName" FROM public."Attachments" WHERE "ProjectId" = :id',
                         id=p_id)

    return templates.TemplateResponse("project.html", {
        "request": request, "project": project[0], "comments": comments,
        "attachments": attachments, "user_name": unquote(user_name)
    })


@app.post("/project/{p_id}/comment")
async def add_comment(p_id: int, text: str = Form(...), file: UploadFile = File(None), user_name: str = Cookie(None)):
    if not user_name: return RedirectResponse(url="/")
    author = unquote(user_name)

    p_data = db.run('SELECT "Name" FROM public."Projects" WHERE "Id" = :id', id=p_id)
    safe_folder = get_safe_name(p_data[0][0])
    p_path = os.path.join(UPLOAD_DIR, safe_folder)
    os.makedirs(p_path, exist_ok=True)

    # Запись в историю через утилиту
    write_to_history(p_path, author, text, file.filename if file and file.filename else None)

    c_id = \
    db.run('INSERT INTO public."Comments" ("ProjectId", "AuthorName", "Text") VALUES (:p_id, :a, :t) RETURNING "Id"',
           p_id=p_id, a=author, t=text)[0][0]

    if file and file.filename:
        f_path = os.path.join(p_path, f"{uuid.uuid4()}{os.path.splitext(file.filename)[1]}")
        with open(f_path, "wb") as b: shutil.copyfileobj(file.file, b)
        db.run(
            'INSERT INTO public."Attachments" ("ProjectId", "CommentId", "FileName", "InternalPath") VALUES (:p_id, :c_id, :f_n, :i_p)',
            p_id=p_id, c_id=c_id, f_n=file.filename, i_p=f_path)

    return RedirectResponse(url=f"/project/{p_id}", status_code=303)

@app.post("/comment/{c_id}/edit")
async def edit_comment(c_id: int, p_id: int = Form(...), text: str = Form(...), user_name: str = Cookie(None)):
    author = unquote(user_name)
    p_data = db.run('SELECT "Name" FROM public."Projects" WHERE "Id" = :id', id=p_id)
    safe_folder = get_safe_name(p_data[0][0])

    write_to_history(os.path.join(UPLOAD_DIR, safe_folder), author, text, action="ИЗМЕНЕНО")

    db.run('UPDATE public."Comments" SET "Text" = :t WHERE "Id" = :c_id AND "AuthorName" = :cur', t=text, c_id=c_id,
           cur=author)
    return RedirectResponse(url=f"/project/{p_id}", status_code=303)


@app.get("/archive", response_class=HTMLResponse)
async def archive_index(request: Request, user_name: str = Cookie(None), q: str = ""):
    if not user_name:
        return RedirectResponse(url="/login", status_code=303)

    # 1. Логика поиска: добавляем фильтрацию, если q не пустой
    if q:
        query = '''
            SELECT "Id", "Name", "Description", "CreatedAt" 
            FROM public."Projects" 
            WHERE "Status" = 'Archived' AND "Name" ILIKE :q 
            ORDER BY "Id" DESC
        '''
        projects_raw = db.run(query, q=f"%{q}%")
    else:
        query = '''
            SELECT "Id", "Name", "Description", "CreatedAt" 
            FROM public."Projects" 
            WHERE "Status" = 'Archived' 
            ORDER BY "Id" DESC
        '''
        projects_raw = db.run(query)

    # 2. Форматируем дату для каждого проекта через нашу функцию format_time
    projects = [
        (p[0], p[1], p[2], format_time(p[3]))
        for p in projects_raw
    ]

    return templates.TemplateResponse("archive.html", {
        "request": request,
        "projects": projects,
        "user_name": unquote(user_name),
        "search_query": q
    })

@app.get("/download/{attach_id}")
async def download_file(attach_id: int):
    res = db.run('SELECT "InternalPath", "FileName" FROM public."Attachments" WHERE "Id" = :id', id=attach_id)
    if res and os.path.exists(res[0][0]): return FileResponse(path=res[0][0], filename=res[0][1])
    return HTMLResponse("Файл не найден", status_code=404)

@app.get("/download_chat/{attach_id}")
async def download_chat_file(attach_id: int):
    res = db.run('SELECT "InternalPath", "FileName" FROM public."ChatAttachments" WHERE "Id" = :id', id=attach_id)
    if res and os.path.exists(res[0][0]): return FileResponse(path=res[0][0], filename=res[0][1])
    return HTMLResponse("Файл не найден", status_code=404)

@app.post("/archive-project/{project_id}/")
async def archive_project(project_id: int, user_name: str = Cookie(None)):
    # 1. Проверяем авторизацию
    if not user_name:
        return RedirectResponse(url="/login", status_code=303)

    # 2. Меняем статус проекта в базе данных
    # Предполагаем, что у тебя есть колонка Status в таблице Projects
    db.run('''
        UPDATE public."Projects" 
        SET "Status" = 'Archived' 
        WHERE "Id" = :id
    ''', id=project_id)

    # 3. Возвращаемся на главную
    return RedirectResponse(url="/", status_code=303)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
    # try commen