const btnSend = document.getElementById('btn-send');
const userInput = document.getElementById('user-input');
const chatBox = document.getElementById('chat-box');
const btnAnki = document.getElementById('btn-anki');

// 🌟 FUNCIÓN TRADUCTORA BLINDADA
function formatearMarkdown(texto) {
    let html = texto
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");

    // 1. VIÑETAS PRIMERO: Busca un inicio de línea o un salto (\n), posibles espacios, y un asterisco o guion
    html = html.replace(/(^|\n)\s*[\*-]\s+/g, '$1• ');

    // 2. NEGRITAS: **texto** -> <strong>texto</strong>
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

    // 3. CURSIVAS: *texto* -> <em>texto</em> (Ya no chocará con las viñetas porque ahora son puntitos)
    html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');

    // 4. SALTOS DE LÍNEA: \n -> <br>
    html = html.replace(/\n/g, '<br>');

    return html;
}

// ==========================================
// 💬 LÓGICA DE LA CONVERSACIÓN (CHAT)
// ==========================================
async function sendMessage() {
    const text = userInput.value.trim();
    if (text === '') return;

    // Dibuja el mensaje del usuario
    const userMsg = document.createElement('div');
    userMsg.className = 'message user';
    userMsg.textContent = text;
    chatBox.appendChild(userMsg);

    userInput.value = '';
    chatBox.scrollTop = chatBox.scrollHeight;

    // Mensaje temporal de "Escribiendo..."
    const botMsg = document.createElement('div');
    botMsg.className = 'message bot';
    botMsg.innerHTML = '<i>Escribiendo...</i>';
    chatBox.appendChild(botMsg);
    chatBox.scrollTop = chatBox.scrollHeight;

    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ texto: text })
        });

        const data = await response.json();
        
        // Aplicamos el formato con la nueva regla de viñetas
        botMsg.innerHTML = formatearMarkdown(data.respuesta);
        chatBox.scrollTop = chatBox.scrollHeight;

    } catch (error) {
        botMsg.textContent = "Error de red. Asegúrate de que el servidor FastAPI esté encendido.";
    }
}

// Escuchadores del chat
btnSend.addEventListener('click', sendMessage);
userInput.addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        sendMessage();
    }
});

// ==========================================
// 🗂️ LÓGICA DEL BOTÓN EXTRAER A ANKI
// ==========================================
btnAnki.addEventListener('click', async () => {
    const textoOriginal = btnAnki.textContent;
    btnAnki.disabled = true;
    btnAnki.textContent = "⏳ Extrayendo y generando medios...";
    btnAnki.style.backgroundColor = "#e67e22";

    try {
        const response = await fetch('/extraer', { method: 'POST' });
        const data = await response.json();
        
        const sysMsg = document.createElement('div');
        sysMsg.className = 'message bot';
        sysMsg.style.backgroundColor = '#e8f5e9';
        sysMsg.style.color = '#2e7d32';
        sysMsg.style.fontWeight = 'bold';
        sysMsg.textContent = data.mensaje;
        
        chatBox.appendChild(sysMsg);
        chatBox.scrollTop = chatBox.scrollHeight;
        
    } catch (err) {
        alert("Hubo un error de red al intentar extraer las cartas.");
    } finally {
        btnAnki.disabled = false;
        btnAnki.textContent = textoOriginal;
        btnAnki.style.backgroundColor = "#27ae60";
    }
});