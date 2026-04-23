import os
import uuid
import shutil
from fastapi import FastAPI, Request, UploadFile, File, Form, Response, Cookie, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse,JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from urllib.parse import quote, unquote
from passlib.context import CryptContext
# Импортируем базу
from database import db, verify_password
# Импортируем утилиты
from utils import format_time, get_safe_name, write_to_history, get_project_path, save_chat_file,check_file_size
# Импортируем админку
from admin import router as admin_router

# Базовое хранилище
UPLOAD_DIR = "C:/CorpStorage/Uploads"
# Папка чата внутри хранилища
CHAT_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "Global_Chat")
os.makedirs(CHAT_UPLOAD_DIR, exist_ok=True)

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Сохраняем шаблоны в state приложения, чтобы admin.py мог их достать
app.state.templates = templates

# Подключаем роутер админки
app.include_router(admin_router)

# Монтирование статики
# 1. Находим папку проекта, где лежит этот main.py
current_dir = os.path.dirname(os.path.abspath(__file__))
# 2. Соединяем её с папкой static
static_dir = os.path.join(current_dir, "static")

# 3. Печатаем в консоль при запуске (чтобы ты увидел реальный путь)
print(f"DEBUG: Пытаюсь подключить статику из: {static_dir}")

if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
else:
    print("!!! ОШИБКА: Папка static не найдена по указанному пути !!!")

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
                INSERT INTO public."Users" ("Username", "Email", "HashedPassword", "GroupId")
                VALUES (:u, :e, :p, 0)
            ''', u=username, e=email.strip().lower(), p=hashed)
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
        SELECT "Username", "HashedPassword", "GroupId"
        FROM public."Users" 
        WHERE "Email" = :e
        LIMIT 1
    ''', e=login_field.strip().lower())  # Приводим к нижнему регистру для надежности

    if not user_row:
        return RedirectResponse(url="/login?error=UserNotFound", status_code=303)

    db_username = user_row[0][0]
    hashed_pass = user_row[0][1]
    db_group_id = user_row[0][2]  # Получаем ID группы из БД

    if not verify_password(password, hashed_pass):
        return RedirectResponse(url="/login?error=WrongPassword", status_code=303)

    # Успешный вход
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(key="user_name", value=quote(db_username), httponly=True)
    response.set_cookie(key="group_id", value=str(db_group_id), httponly=True)
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    # Удаляем основные куки
    response.delete_cookie("user_name")
    response.delete_cookie("group_id")
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


# 1. Страница подтверждения входа (простая форма с паролем)
@app.get("/admin/auth", response_class=HTMLResponse)
async def admin_auth_page(request: Request):
    return templates.TemplateResponse("admin_login.html", {"request": request})

app.include_router(admin_router)


# --- ГЛАВНАЯ СТРАНИЦА ---
@app.get("/", response_class=HTMLResponse)
async def index(request: Request, user_name: str = Cookie(None), group_id: str = Cookie(None), q: str = ""):
    if not user_name:
        return templates.TemplateResponse("login.html", {"request": request})

    decoded_name = unquote(user_name)

    # 1. Получаем данные пользователя (ID и GroupId)
    user_row = db.run('SELECT "Id", "GroupId" FROM public."Users" WHERE "Username" = :u', u=decoded_name)

    # Если юзера нет в базе (удалили), кидаем на выход
    if not user_row:
        return RedirectResponse(url="/logout", status_code=303)

    u_id = int(user_row[0][0])
    actual_g_id = int(user_row[0][1])

    # 2. ЕСЛИ ГРУППА 0 — СРАЗУ ПОКАЗЫВАЕМ ЗАГЛУШКУ
    if actual_g_id == 0:
        return templates.TemplateResponse("waiting_room.html", {
            "request": request,
            "user_name": decoded_name
        })

    # 3. Синхронизация куки группы
    needs_cookie_update = str(group_id) != str(actual_g_id)
    g_id = actual_g_id

    # 4. Получаем название группы
    group_row = db.run('SELECT "Name" FROM public."Groups" WHERE "Id" = :g', g=g_id)
    group_name = group_row[0][0] if group_row else f"Отдел №{g_id}"

    # 5. ПОЛУЧАЕМ ИЗБРАННЫЕ ПРОЕКТЫ ПОЛЬЗОВАТЕЛЯ
    fav_projects = db.run('''
        SELECT p."Id", p."Name" 
        FROM public."Projects" p
        JOIN public."UserFavorites" f ON p."Id" = f."ProjectId"
        WHERE f."UserId" = :uid AND p."Status" = 'Active'
        ORDER BY p."Name" ASC
    ''', uid=u_id)

    # Список ID избранных проектов для отрисовки закрашенных звезд в общем списке
    my_fav_ids = [p[0] for p in fav_projects]

    # 6. Поиск или основной список проектов группы
    if q:
        projects = db.run('''
                SELECT "Id", "Name", "Description" FROM public."Projects" 
                WHERE "Status" = 'Active' AND "GroupId" = :g AND "Name" ILIKE :s 
                ORDER BY "Id" DESC''', g=g_id, s=f"%{q}%")
    else:
        projects = db.run('''
                SELECT "Id", "Name", "Description" FROM public."Projects" 
                WHERE "Status" = 'Active' AND "GroupId" = :g 
                ORDER BY "Id" DESC''', g=g_id)

    # 7. Последние комментарии в этой группе
    last_comments = db.run('''
        SELECT c."Text", c."AuthorName", p."Name", c."ProjectId" 
        FROM public."Comments" c
        JOIN public."Projects" p ON c."ProjectId" = p."Id"
        WHERE p."GroupId" = :g
        ORDER BY c."CreatedAt" DESC LIMIT 5
    ''', g=g_id)

    # 8. Чат группы
    raw_chat_messages = db.run('''
                SELECT c."Id", c."AuthorName", c."Message", c."CreatedAt", a."Id", a."FileName"
                FROM public."GlobalChat" c
                LEFT JOIN public."ChatAttachments" a ON c."Id" = a."MessageId"
                WHERE c."GroupId" = :g
                ORDER BY c."Id" DESC LIMIT 50
            ''', g=g_id)

    chat_messages = [(r[0], r[1], r[2], format_time(r[3]), r[4], r[5]) for r in raw_chat_messages]

    # 9. Список пользователей группы (для меншенов)
    user_list = [row[0] for row in db.run('''
            SELECT "Username" FROM public."Users" WHERE "GroupId" = :g''', g=g_id)]

    # 10. Формируем ответ
    response = templates.TemplateResponse("index.html", {
        "request": request,
        "projects": projects,
        "user_name": decoded_name,
        "group_name": group_name,
        "search_query": q,
        "last_comments": last_comments,
        "chat_messages": chat_messages,
        "user_list": user_list,
        "fav_projects": fav_projects,  # Передаем в правую колонку чата
        "my_fav_ids": my_fav_ids  # Передаем для проверки звезд в списке
    })

    # Если группа в базе сменилась, обновляем куку
    if needs_cookie_update:
        response.set_cookie(key="group_id", value=str(g_id), httponly=True)

    return response

# --- API ЖИВОГО ЧАТА ---
@app.post("/api/chat/send")
async def api_send_message(
        message: str = Form(...),
        file: UploadFile = File(None),
        user_name: str = Cookie(None),
        group_id: str = Cookie(None)
):
    if not user_name: return {"success": False}
    # ПРОВЕРКА РАЗМЕРА
    if file and file.filename:
        if not check_file_size(file):
            return {"success": False, "error": "Файл слишком велик (макс. 50 МБ)"}


    author = unquote(user_name)
    g_id = int(group_id) if group_id and group_id != "None" else 1

    # Сохраняем сообщение с привязкой к группе
    res = db.run('''
        INSERT INTO public."GlobalChat" ("AuthorName", "Message", "GroupId") 
        VALUES (:a, :m, :g) RETURNING "Id"''',
                 a=author, m=message, g=g_id)

    msg_id = res[0][0]

    # 3. Сохраняем файл через utils.py
    if file and file.filename:
        # Вызываем функцию из utils
        original_name, saved_path = save_chat_file(file, CHAT_UPLOAD_DIR)

        if saved_path:
            db.run('''
                    INSERT INTO public."ChatAttachments" ("MessageId", "FileName", "InternalPath") 
                    VALUES (:m_id, :f_n, :i_p)''',
                   m_id=msg_id, f_n=original_name, i_p=saved_path)

    return {"success": True}


@app.get("/api/chat/messages")
async def api_get_messages(last_id: int = 0, group_id: str = Cookie(None)):
    # 1. Безопасно определяем ID группы, чтобы не видеть чужую переписку
    g_id = int(group_id) if group_id and group_id != "None" else 1

    # 2. Добавляем AND c."GroupId" = :g в SQL-запрос
    rows = db.run('''
        SELECT c."Id", c."AuthorName", c."Message", c."CreatedAt", a."Id" as attach_id, a."FileName"
        FROM public."GlobalChat" c
        LEFT JOIN public."ChatAttachments" a ON c."Id" = a."MessageId"
        WHERE c."Id" > :last_id AND c."GroupId" = :g
        ORDER BY c."Id" ASC
    ''', last_id=last_id, g=g_id)

    return {"messages": [
        {
            "id": r[0],
            "author": r[1],
            "text": r[2],
            "time": format_time(r[3]),
            "file_id": r[4],
            "file_name": r[5]
        } for r in rows
    ]}


@app.post("/chat/message/{msg_id}/edit")
async def edit_chat_message(msg_id: int, text: str = Form(...), user_name: str = Cookie(None)):
    if not user_name:
        return JSONResponse({"status": "error"}, status_code=401)

    author = unquote(user_name)

    # Обновляем только если ID и Автор совпадают (защита от подмены)
    db.run("""
        UPDATE public."GlobalChat"
        SET "Message" = :t 
        WHERE "Id" = :m_id AND "AuthorName" = :auth
    """, t=text, m_id=msg_id, auth=author)

    return {"status": "ok"}

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


@app.post("/create_project")
async def create_project(
        name: str = Form(...),
        description: str = Form(None),
        group_id: str = Cookie(None),
        user_name: str = Cookie(None)
):
    # 1. Проверка авторизации
    if not user_name:
        return RedirectResponse(url="/login", status_code=303)
    try:
        g_id = int(group_id) if group_id and group_id != "None" else 1
    except (ValueError, TypeError):
        g_id = 1

    # 3. Подготовка данных
    author = unquote(user_name)
    desc = description.strip() if description else ""
    # 4. Сохраняем проект в БД с привязкой к GroupId
    res = db.run('''
            INSERT INTO public."Projects" ("Name", "Description", "Status", "GroupId") 
            VALUES (:n, :d, 'Active', :g) 
            RETURNING "Id"
        ''', n=name.strip(), d=desc, g=g_id)

    new_project_id = res[0][0]

    return RedirectResponse(url="/?success=project_created", status_code=303)


@app.post("/project/{p_id}/comment")
async def add_comment(p_id: int, text: str = Form(...), file: UploadFile = File(None), user_name: str = Cookie(None)):
    if not user_name: return RedirectResponse(url="/")

    if file and file.filename:
        if not check_file_size(file):
            # Перенаправляем обратно с ошибкой в URL
            return RedirectResponse(url=f"/project/{p_id}?error=file_too_large", status_code=303)

    author = unquote(user_name)

    p_path = get_project_path(p_id, db, UPLOAD_DIR)

    # Запись в историю через утилиту
    write_to_history(p_path, author, text, file.filename if file and file.filename else None)

    c_id = \
        db.run(
            'INSERT INTO public."Comments" ("ProjectId", "AuthorName", "Text") VALUES (:p_id, :a, :t) RETURNING "Id"',
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

    p_path = get_project_path(p_id, db, UPLOAD_DIR)

    write_to_history(p_path, author, text, action="ИЗМЕНЕНО")

    db.run('UPDATE public."Comments" SET "Text" = :t WHERE "Id" = :c_id AND "AuthorName" = :cur', t=text, c_id=c_id,
           cur=author)
    return RedirectResponse(url=f"/project/{p_id}", status_code=303)


@app.post("/api/projects/{p_id}/favorite")
async def toggle_project_favorite(p_id: int, user_name: str = Cookie(None)):
    if not user_name:
        return {"success": False, "error": "Нужна авторизация"}

    decoded_name = unquote(user_name)

    # 1. Достаем ID пользователя.
    user_data = db.run('SELECT "Id" FROM public."Users" WHERE "Username" = :u', u=decoded_name)

    if not user_data or len(user_data) == 0:
        return {"success": False, "error": "Пользователь не найден"}

    # ИСПРАВЛЕНИЕ ТУТ: берем первый элемент первого списка
    # user_data выглядит как [[1]], поэтому берем [0][0]
    u_id = int(user_data[0][0])

    # 2. Проверяем наличие в избранном
    # Обрати внимание, здесь u_id и p_id теперь чистые числа
    exists = db.run('''
        SELECT 1 FROM public."UserFavorites" 
        WHERE "UserId" = :uid AND "ProjectId" = :pid
    ''', uid=u_id, pid=p_id)

    if exists and len(exists) > 0:
        db.run('DELETE FROM public."UserFavorites" WHERE "UserId" = :uid AND "ProjectId" = :pid',
               uid=u_id, pid=p_id)
        status = "removed"
    else:
        db.run('INSERT INTO public."UserFavorites" ("UserId", "ProjectId") VALUES (:uid, :pid)',
               uid=u_id, pid=p_id)
        status = "added"

    return {"success": True, "status": status}

@app.get("/archive", response_class=HTMLResponse)
async def archive_index(request: Request, user_name: str = Cookie(None), group_id: str = Cookie(None), q: str = ""):
    if not user_name:
        return RedirectResponse(url="/login", status_code=303)

    # 1. Безопасное определение группы
    try:
        g_id = int(group_id) if group_id and group_id != "None" else 1
    except (ValueError, TypeError):
        g_id = 1

    # 2. Логика поиска с учетом GroupId
    if q:
        query = '''
            SELECT "Id", "Name", "Description", "CreatedAt" 
            FROM public."Projects" 
            WHERE "Status" = 'Archived' AND "GroupId" = :g AND "Name" ILIKE :q 
            ORDER BY "Id" DESC
        '''
        projects_raw = db.run(query, g=g_id, q=f"%{q}%")
    else:
        query = '''
            SELECT "Id", "Name", "Description", "CreatedAt" 
            FROM public."Projects" 
            WHERE "Status" = 'Archived' AND "GroupId" = :g 
            ORDER BY "Id" DESC
        '''
        projects_raw = db.run(query, g=g_id)

    # 3. Форматируем данные
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
async def archive_project(
    project_id: int,
    user_name: str = Cookie(None),
    group_id: str = Cookie(None)
):
    # 1. Проверяем авторизацию
    if not user_name:
        return RedirectResponse(url="/login", status_code=303)

    # Определяем ID группы из куки (защита)
    g_id = int(group_id) if group_id and group_id != "None" else 1
    author = unquote(user_name)

    # 2. Меняем статус ТОЛЬКО если проект принадлежит группе пользователя
    # Это защита, чтобы никто не мог через адресную строку закрыть чужой проект
    db.run('''
        UPDATE public."Projects" 
        SET "Status" = 'Archived' 
        WHERE "Id" = :id AND "GroupId" = :g
    ''', id=project_id, g=g_id)

    # 3. Фиксируем завершение в текстовой истории проекта
    try:
        from utils import get_project_path, write_to_history
        # Получаем путь через нашу новую функцию
        p_path = get_project_path(project_id, db, UPLOAD_DIR)
        if p_path:
            write_to_history(p_path, author, "Проект успешно завершён и перемещён в архив.", action="АРХИВАЦИЯ")
    except Exception as e:
        print(f"Ошибка записи в историю при архивации: {e}")

    # 4. Возвращаемся на главную
    return RedirectResponse(url="/?success=project_archived", status_code=303)


@app.post("/project/{project_id}/restore")
async def restore_project(
    project_id: int,
    user_name: str = Cookie(None),
    group_id: str = Cookie(None)
):
    if not user_name:
        return RedirectResponse(url="/login", status_code=303)

    g_id = int(group_id) if group_id and group_id != "None" else 1
    author = unquote(user_name)

    # 1. Возвращаем статус Active только для своей группы
    db.run('''
        UPDATE public."Projects" 
        SET "Status" = 'Active' 
        WHERE "Id" = :id AND "GroupId" = :g
    ''', id=project_id, g=g_id)

    # 2. Фиксируем восстановление в истории
    try:
        from utils import get_project_path, write_to_history
        p_path = get_project_path(project_id, db, UPLOAD_DIR)
        if p_path:
            write_to_history(p_path, author, "Проект возвращён из архива в работу.", action="ВОССТАНОВЛЕНИЕ")
    except Exception as e:
        print(f"Ошибка записи в историю: {e}")

    return RedirectResponse(url="/archive?success=project_restored", status_code=303)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
