import re
import os
from datetime import datetime
import uuid
import shutil


"""Сохраняет файл на диск с уникальным именем и возвращает (имя_файла, путь)"""
def save_chat_file(upload_file, storage_dir):


    if not upload_file or not upload_file.filename:
        return None, None

    f_ext = os.path.splitext(upload_file.filename)[1]
    internal_name = f"{uuid.uuid4()}{f_ext}"
    f_path = os.path.join(storage_dir, internal_name)

    with open(f_path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)

    return upload_file.filename, f_path

"""Автоматически получает имя проекта по ID, очищает его и возвращает полный путь к папке."""
    # Выполняем запрос к БД
def get_project_path(p_id: int, db_instance, base_dir: str):
    p_data = db_instance.run('SELECT "Name" FROM public."Projects" WHERE "Id" = :id', id=p_id)

    if not p_data:
        return None

    # Извлекаем имя из результата запроса [0][0]
    project_name = p_data[0][0]
    safe_folder = get_safe_name(project_name)

    # Собираем путь
    p_path = os.path.join(base_dir, safe_folder)

    # Создаем папку, если её нет
    os.makedirs(p_path, exist_ok=True)

    return p_path

"""Очистка имени папки от запрещенных символов"""
def get_safe_name(name: str):
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()


"""Безопасное форматирование: возвращает ЧЧ:ММ"""
def format_time(dt):

    if not dt:
        return ""
    if hasattr(dt, 'strftime'):
        return dt.strftime('%H:%M')

    # Если пришла строка "2026-04-15 13:47:19.473026"
    dt_str = str(dt)
    if ' ' in dt_str:
        # Берем часть после пробела и отрезаем секунды
        return dt_str.split(' ')[1][:5]
    return dt_str[:5]

"""Запись в историю проекта (history.txt)"""
def write_to_history(folder_path: str, author: str, text: str, file_name: str = None, action=""):
    history_path = os.path.join(folder_path, "history.txt")
    timestamp = datetime.now().strftime("%d.%m.%Y %H:%M")

    file_info = f"\n[Файл: {file_name}]" if file_name else ""
    action_info = f" ({action})" if action else ""

    with open(history_path, "a", encoding="utf-16") as f:
        f.write(f"[{timestamp}] {author}{action_info}:\n{text}{file_info}\n")
        f.write("-" * 30 + "\n")
