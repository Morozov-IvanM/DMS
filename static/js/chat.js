// static/js/chat.js

function initChat(config) {
    let lastMsgId = config.initialLastMsgId;
    const currentUser = config.userName;
    const allUsers = config.userList;

    const chatWindow = document.getElementById('chat-window');
    const chatForm = document.getElementById('chat-form-js');
    const chatInput = document.getElementById('chat-input-js');
    const chatFile = document.getElementById('chat-file');
    const mentionList = document.getElementById('mention-list');
    
    // Новые элементы превью из обновленной верстки
    const filePreviewContainer = document.getElementById('file-preview-container');
    const filePreviewName = document.getElementById('file-preview-name');

    if (chatWindow) { chatWindow.scrollTop = chatWindow.scrollHeight; }

    // --- УВЕДОМЛЕНИЯ ---
    // Используем функцию showNotification из родительского шаблона, если она есть
    function notifyUser(author, text) {
        if (author === currentUser) return; // Сами себе не шлем
        
        if (typeof window.showNotification === 'function') {
            window.showNotification(author, text);
        } else {
            // Резервный вариант, если основная функция не подгрузилась
            if (Notification.permission === "granted") {
                new Notification(`Чат: ${author}`, { body: text });
            }
        }
    }

    // --- ОТРИСОВКА ---
    function appendMessage(msg) {
        if (!chatWindow) return;
        const emptyHint = document.getElementById('chat-empty');
        if (emptyHint) emptyHint.remove();

        // Проверяем, нет ли уже такого сообщения на экране (защита от дублей)
        if (document.getElementById(`msg-item-${msg.id}`)) return;

        const isMe = msg.author === currentUser;
        let fileHtml = msg.file_id ? `
            <div class="chat-file-attachment mt-2 pt-1 border-top border-light-subtle">
                <a href="/download_chat/${msg.file_id}" target="_blank" class="text-decoration-none small">
                    <i class="fas fa-paperclip"></i> ${msg.file_name}
                </a>
            </div>` : "";

        // Добавили ID для блока сообщения
        const html = `
            <div class="chat-msg ${isMe ? 'msg-me' : 'msg-other'} shadow-sm" id="msg-item-${msg.id}">
                <span class="chat-author">${msg.author}</span>
                <div class="chat-text">${msg.text}</div>
                ${fileHtml}
                <span class="chat-time text-muted">${msg.time}</span>
            </div>`;
        
        chatWindow.insertAdjacentHTML('beforeend', html);
        chatWindow.scrollTop = chatWindow.scrollHeight;
    }

    // --- ОТПРАВКА ---
    if (chatForm) {
        chatForm.onsubmit = async (e) => {
            e.preventDefault();
            if (!chatInput.value.trim() && !chatFile.files[0]) return;

            const formData = new FormData();
            formData.append('message', chatInput.value);
            if (chatFile.files[0]) formData.append('file', chatFile.files[0]);

            const response = await fetch('/api/chat/send', { method: 'POST', body: formData });
            if (response.ok) {
                chatInput.value = '';
                chatFile.value = '';
                // БЕЗОПАСНО очищаем превью
                if (filePreviewContainer) filePreviewContainer.style.display = 'none';
                await pollMessages();
            }
        };
    }

    // --- ПОЛЛИНГ ---
    async function pollMessages() {
        try {
            const res = await fetch(`/api/chat/messages?last_id=${lastMsgId}`);
            if (!res.ok) return;
            const data = await res.json();
            if (data.messages && data.messages.length > 0) {
                data.messages.forEach(m => {
                    if (m.id > lastMsgId) {
                        appendMessage(m);
                        notifyUser(m.author, m.text);
                        lastMsgId = m.id;
                    }
                });
            }
        } catch (err) { console.error("Ошибка обновления чата:", err); }
    }

    setInterval(pollMessages, 3000);

    // --- ФАЙЛЫ (ПРЕВЬЮ) ---
    if (chatFile) {
        chatFile.onchange = function() {
            if(this.files[0]) {
                if (filePreviewName) filePreviewName.innerText = "📎 " + this.files[0].name;
                if (filePreviewContainer) filePreviewContainer.style.display = 'flex';
            }
        };
    }

    // --- МЕНШЕНЫ (@) ---
    if (chatInput && mentionList) {
        chatInput.addEventListener('input', function() {
            const value = this.value;
            const lastAtPos = value.lastIndexOf('@');
            if (lastAtPos !== -1 && (lastAtPos === 0 || value[lastAtPos - 1] === ' ')) {
                const query = value.substring(lastAtPos + 1).toLowerCase();
                const matches = allUsers.filter(u => u.toLowerCase().startsWith(query));
                if (matches.length > 0) renderMentionList(matches, lastAtPos);
                else mentionList.style.display = 'none';
            } else { mentionList.style.display = 'none'; }
        });
    }

    function renderMentionList(users, atPos) {
        if (!mentionList) return;
        mentionList.innerHTML = '';
        users.forEach(user => {
            const item = document.createElement('div');
            item.className = 'list-group-item';
            item.textContent = user;
            item.onclick = () => {
                const before = chatInput.value.substring(0, atPos);
                const after = chatInput.value.substring(chatInput.selectionStart);
                chatInput.value = before + '@' + user + ' ' + after;
                mentionList.style.display = 'none';
                chatInput.focus();
            };
            mentionList.appendChild(item);
        });
        const rect = chatInput.getBoundingClientRect();
        mentionList.style.left = rect.left + 'px';
        mentionList.style.bottom = (window.innerHeight - rect.top + 10) + 'px';
        mentionList.style.display = 'block';
    }
}

// Удаление сообщений (админ)
function confirmDeleteMessage(msgId, btn) {
    if (!confirm("Удалить это сообщение?")) return;
    fetch(`/admin/delete-chat-message/${msgId}`, { method: 'POST' })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            const msgElement = btn.closest('.chat-msg');
            if (msgElement) {
                msgElement.style.opacity = '0';
                setTimeout(() => msgElement.remove(), 300);
            }
        }
    });
}