const btnSend = document.getElementById('btn-send');
const userInput = document.getElementById('user-input');
const chatBox = document.getElementById('chat-box');

// Cambiamos a async para poder "esperar" la respuesta del servidor
async function sendMessage() {
    const text = userInput.value.trim();
    if (text === '') return;

    // 1. Dibuja el mensaje del usuario
    const userMsg = document.createElement('div');
    userMsg.className = 'message user';
    userMsg.textContent = text;
    chatBox.appendChild(userMsg);

    // Limpia la caja y baja el scroll
    userInput.value = '';
    chatBox.scrollTop = chatBox.scrollHeight;

    // 2. Dibuja un mensaje temporal de "Escribiendo..."
    const botMsg = document.createElement('div');
    botMsg.className = 'message bot';
    botMsg.innerHTML = '<i>Escribiendo...</i>';
    chatBox.appendChild(botMsg);
    chatBox.scrollTop = chatBox.scrollHeight;

    // 3. Envía el texto a Python (FastAPI)
    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ texto: text }) // Esto coincide con la clase Mensaje de Python
        });

        // 4. Recibe la respuesta de Gemini y actualiza la burbuja
        const data = await response.json();
        
        // El pre-wrap respeta los saltos de línea sin desconfigurar el CSS
        botMsg.style.whiteSpace = 'pre-wrap'; 
        botMsg.textContent = data.respuesta;
        chatBox.scrollTop = chatBox.scrollHeight;

    } catch (error) {
        botMsg.textContent = "Error de red. Asegúrate de que el servidor FastAPI esté encendido.";
    }
}

// Escuchadores de eventos
btnSend.addEventListener('click', sendMessage);
userInput.addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        sendMessage();
    }
});