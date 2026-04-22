from fastapi import APIRouter, Request, Form, Cookie
from fastapi.responses import RedirectResponse, HTMLResponse
from urllib.parse import unquote
from database import db, hash_password  # Импортируем из нашего нового файла

# Создаем роутер. В main.py мы укажем, где лежат шаблоны
router = APIRouter(prefix="/admin", tags=["admin"])


@router.api_route("/panel", methods=["GET", "POST"]) # Должно быть так!
async def admin_panel_page(request: Request, user_name: str = Cookie(None)):
    if not user_name or unquote(user_name) != "Администратор":
        return RedirectResponse(url="/?error=no_admin_rights", status_code=303)

    users = db.run('SELECT "Username", "Email" FROM public."Users" ORDER BY "Username"')
    all_groups = db.run('SELECT "Id", "Name" FROM public."Groups" ORDER BY "Id"')

    # Шаблоны мы возьмем из request.app.state (настроим это в main.py)
    return request.app.state.templates.TemplateResponse("admin_panel.html", {
        "request": request,
        "users": users,
        "all_groups": all_groups
    })


@router.post("/reset-user-password")
async def admin_reset_password(user_email: str = Form(...), new_password: str = Form(...),
                               user_name: str = Cookie(None)):
    if not user_name or unquote(user_name) != "Администратор": return RedirectResponse(url="/")

    new_hashed = hash_password(new_password)
    db.run('UPDATE public."Users" SET "HashedPassword" = :p WHERE "Email" = :e',
           p=new_hashed, e=user_email.strip().lower())
    return RedirectResponse(url="/admin/panel?success=admin_reset_done", status_code=303)


@router.post("/change-user-group")
async def admin_change_user_group(target_email: str = Form(...), new_group_id: int = Form(...),
                                  user_name: str = Cookie(None)):
    if not user_name or unquote(user_name) != "Администратор": return RedirectResponse(url="/")

    db.run('UPDATE public."Users" SET "GroupId" = :g WHERE "Email" = :e',
           g=new_group_id, e=target_email.strip().lower())
    return RedirectResponse(url="/admin/panel?success=group_changed", status_code=303)

"""Удаление сообщений из глобального чата"""
@router.post("/delete-chat-message/{msg_id}")
async def delete_chat_message(msg_id: int, user_name: str = Cookie(None)):
    # Проверка прав администратора
    if not user_name or unquote(user_name) != "Администратор":
        return {"success": False, "error": "Отказ в доступе"}

    # Удаляем сообщение
    db.run('DELETE FROM public."GlobalChat" WHERE "Id" = :id', id=msg_id)

    # Файлы вложений (ChatAttachments) удалятся сами,
    # если в БД настроено ON DELETE CASCADE

    return {"success": True}