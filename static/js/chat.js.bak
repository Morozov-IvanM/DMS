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

    if (chatWindow) { chatWindow.scrollTop = chatWindow.scrollHeight; }

    // --- УВЕДОМЛЕНИЯ ---
    if (Notification.permission !== "granted" && Notification.permission !== "denied") {
        Notification.requestPermission();
    }

    function showNotification(author, text) {
        if (localStorage.getItem('notifications_enabled') !== 'false' && author !== currentUser) {
            new Notification("Новое сообщение", { body: `${author}: ${text}` });
        }
    }

    // --- ОТРИСОВКА ---
    function appendMessage(msg) {
        if (!chatWindow) return;
        const emptyHint = document.getElementById('chat-empty');
        if (emptyHint) emptyHint.remove();

        const isMe = msg.author === currentUser;
        let fileHtml = msg.file_id ? `
            <div class="chat-file-attachment mt-2 pt-1 border-top border-light-subtle" style="opacity: 0.9;">
                <a href="/download_chat/${msg.file_id}" target="_blank" class="${isMe ? 'text-white' : 'text-primary'} text-decoration-none small">
                    <i class="fas fa-paperclip"></i> ${msg.file_name}
                </a>
            </div>` : "";

        const html = `
            <div class="chat-msg ${isMe ? 'msg-me' : 'msg-other'}">
                <span class="chat-author">${msg.author}</span>
                <div class="chat-text">${msg.text}</div>
                ${fileHtml}
                <span class="chat-time">${msg.time}</span>
            </div>`;
        
        chatWindow.insertAdjacentHTML('beforeend', html);
        chatWindow.scrollTop = chatWindow.scrollHeight;
    }

    // --- ОТПРАВКА ---
    chatForm.onsubmit = async (e) => {
        e.preventDefault();
        const formData = new FormData();
        formData.append('message', chatInput.value);
        if (chatFile.files[0]) formData.append('file', chatFile.files[0]);

        const response = await fetch('/api/chat/send', { method: 'POST', body: formData });
        if (response.ok) {
            chatInput.value = '';
            chatFile.value = '';
            document.getElementById('file-preview').style.display = 'none';
            await pollMessages();
        }
    };

    // --- ПОЛЛИНГ ---
    async function pollMessages() {
        try {
            const res = await fetch(`/api/chat/messages?last_id=${lastMsgId}`);
            if (!res.ok) return;
            const data = await res.json();
            if (data.messages && data.messages.length > 0) {
                data.messages.forEach(m => {
                    if (m.id > lastMsgId) {
                        if (m.author !== currentUser) showNotification(m.author, m.text);
                        appendMessage(m);
                        lastMsgId = m.id;
                    }
                });
            }
        } catch (err) { console.error("Ошибка обновления:", err); }
    }

    setInterval(pollMessages, 3000);

    // --- УПОМИНАНИЯ И ФАЙЛЫ ---
    chatFile.onchange = function() {
        const preview = document.getElementById('file-preview');
        if(this.files[0]) {
            preview.innerText = "📎 " + this.files[0].name;
            preview.style.display = 'block';
        }
    };

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

    function renderMentionList(users, atPos) {
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

// Функции вне инициализации (глобальные)
function toggleNotifications(status) {
    localStorage.setItem('notifications_enabled', status);
}

window.addEventListener('load', () => {
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('success') === 'password_changed') alert("Пароль обновлен!");
    if (urlParams.get('error') === 'wrong_old_password') alert("Старый пароль неверен!");
});