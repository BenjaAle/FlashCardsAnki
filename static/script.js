const btnSend = document.getElementById("btn-send");
const userInput = document.getElementById("user-input");
const chatBox = document.getElementById("chat-box");
const btnAnki = document.getElementById("btn-anki");
const chatList = document.getElementById("chat-list");
const btnNewChat = document.getElementById("btn-new-chat");
const chatTitle = document.getElementById("chat-title");

// Variable vital para saber en qué conversación estamos
let currentChatId = null;

function formatearMarkdown(texto) {
  let html = texto
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  html = html.replace(/(^|\n)\s*[\*-]\s+/g, "$1• ");
  html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*(.*?)\*/g, "<em>$1</em>");
  html = html.replace(/\n/g, "<br>");
  return html;
}

// 🗂️ 1. Cargar la lista de chats en la barra lateral
async function cargarChats() {
  const res = await fetch("/chats");
  const chats = await res.json();
  chatList.innerHTML = "";

  chats.forEach((chat) => {
    const div = document.createElement("div");
    div.className = "chat-item";
    div.textContent = chat.titulo;
    if (chat.id === currentChatId) div.classList.add("active");

    div.onclick = () => abrirChat(chat.id, chat.titulo);
    chatList.appendChild(div);
  });
}

// 📖 2. Abrir un chat específico y cargar su historial
async function abrirChat(id, titulo) {
  currentChatId = id;
  chatTitle.textContent = "🇬🇧 " + titulo;
  chatBox.innerHTML = "";
  await cargarChats(); // Refrescar para marcar en azul el chat activo

  const res = await fetch(`/chats/${id}/mensajes`);
  const mensajes = await res.json();

  if (mensajes.length === 0) {
    const sysMsg = document.createElement("div");
    sysMsg.className = "message bot";
    sysMsg.textContent =
      "¡Hello! Soy tu tutor de inglés. ¿De qué hablaremos en esta sesión? 🚀";
    chatBox.appendChild(sysMsg);
  } else {
    mensajes.forEach((msg) => {
      const msgDiv = document.createElement("div");
      msgDiv.className = msg.rol === "user" ? "message user" : "message bot";
      if (msg.rol === "bot") {
        msgDiv.innerHTML = formatearMarkdown(msg.texto);
      } else {
        msgDiv.textContent = msg.texto;
      }
      chatBox.appendChild(msgDiv);
    });
  }
  chatBox.scrollTop = chatBox.scrollHeight;
}

// Capturamos los nuevos elementos visuales
const newChatForm = document.getElementById('new-chat-form');
const newChatInput = document.getElementById('new-chat-input');
const btnConfirmChat = document.getElementById('btn-confirm-chat');
const btnCancelChat = document.getElementById('btn-cancel-chat');

// ➕ 3. Lógica moderna para crear nuevo chat
btnNewChat.addEventListener('click', () => {
    btnNewChat.style.display = 'none'; // Ocultamos el botón
    newChatForm.style.display = 'flex'; // Mostramos el mini-formulario
    newChatInput.focus(); // Ponemos el cursor ahí automáticamente
});

btnCancelChat.addEventListener('click', () => {
    newChatForm.style.display = 'none';
    btnNewChat.style.display = 'block';
    newChatInput.value = ''; // Limpiamos la caja
});

async function crearNuevoChat() {
    const titulo = newChatInput.value.trim();
    if (!titulo) return;

    // Restauramos la interfaz a la normalidad
    newChatForm.style.display = 'none';
    btnNewChat.style.display = 'block';
    newChatInput.value = '';

    const res = await fetch('/crear_chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ titulo: titulo })
    });
    const data = await res.json();
    await abrirChat(data.chat_id, data.titulo);
}

btnConfirmChat.addEventListener('click', crearNuevoChat);
newChatInput.addEventListener('keypress', e => { 
    if (e.key === 'Enter') crearNuevoChat(); 
});

// 💬 4. Enviar un mensaje (ahora incluye el currentChatId)
async function sendMessage() {
  if (!currentChatId) {
    alert(
      "Por favor, selecciona o crea un chat primero usando la barra lateral.",
    );
    return;
  }

  const text = userInput.value.trim();
  if (text === "") return;

  const userMsg = document.createElement("div");
  userMsg.className = "message user";
  userMsg.textContent = text;
  chatBox.appendChild(userMsg);

  userInput.value = "";
  chatBox.scrollTop = chatBox.scrollHeight;

  const botMsg = document.createElement("div");
  botMsg.className = "message bot";
  botMsg.innerHTML = "<i>Escribiendo...</i>";
  chatBox.appendChild(botMsg);
  chatBox.scrollTop = chatBox.scrollHeight;

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ texto: text, chat_id: currentChatId }),
    });

    const data = await response.json();
    botMsg.innerHTML = formatearMarkdown(data.respuesta);
    chatBox.scrollTop = chatBox.scrollHeight;
  } catch (error) {
    botMsg.textContent = "Error de red.";
  }
}

btnSend.addEventListener("click", sendMessage);
userInput.addEventListener("keypress", (e) => {
  if (e.key === "Enter") sendMessage();
});

// 📥 5. Extraer a Anki (ahora incluye el currentChatId)
btnAnki.addEventListener("click", async () => {
  if (!currentChatId) {
    alert("Selecciona un chat primero.");
    return;
  }

  const textoOriginal = btnAnki.textContent;
  btnAnki.disabled = true;
  btnAnki.textContent = "⏳ Procesando...";
  btnAnki.style.backgroundColor = "#e67e22";

  try {
    const response = await fetch("/extraer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: currentChatId }),
    });
    const data = await response.json();

    const sysMsg = document.createElement("div");
    sysMsg.className = "message bot";
    sysMsg.style.backgroundColor = "#e8f5e9";
    sysMsg.style.color = "#2e7d32";
    sysMsg.style.fontWeight = "bold";
    sysMsg.textContent = data.mensaje;

    chatBox.appendChild(sysMsg);
    chatBox.scrollTop = chatBox.scrollHeight;
  } catch (err) {
    alert("Hubo un error de red al intentar extraer.");
  } finally {
    btnAnki.disabled = false;
    btnAnki.textContent = textoOriginal;
    btnAnki.style.backgroundColor = "#27ae60";
  }
});

// 🚀 AL INICIAR: Cargar la lista de chats automáticamente
cargarChats();
