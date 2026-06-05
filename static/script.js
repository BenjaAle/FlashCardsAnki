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
    
  // 🌟 Enseñar a leer TODOS los títulos de Markdown (H1 hasta H6)
  // Es importante ir del más grande (######) al más chico (#)
  html = html.replace(/^###### (.*$)/gim, "<h6>$1</h6>");
  html = html.replace(/^##### (.*$)/gim, "<h5>$1</h5>");
  html = html.replace(/^#### (.*$)/gim, "<h4>$1</h4>");
  html = html.replace(/^### (.*$)/gim, "<h3>$1</h3>");
  html = html.replace(/^## (.*$)/gim, "<h2>$1</h2>");
  html = html.replace(/^# (.*$)/gim, "<h1>$1</h1>");

  html = html.replace(/(^|\n)\s*[\*-]\s+/g, "$1• ");
  html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*(.*?)\*/g, "<em>$1</em>");
  html = html.replace(/\n/g, "<br>");
  
  // Limpieza visual: Quita los saltos de línea extra debajo de los títulos
  html = html.replace(/<\/h6><br>/g, "</h6>");
  html = html.replace(/<\/h5><br>/g, "</h5>");
  html = html.replace(/<\/h4><br>/g, "</h4>");
  html = html.replace(/<\/h3><br>/g, "</h3>");
  html = html.replace(/<\/h2><br>/g, "</h2>");
  html = html.replace(/<\/h1><br>/g, "</h1>");
  
  return html;
}

// 🗂️ 1. Cargar la lista de chats en la barra lateral
// 🗂️ 1. Cargar la lista de chats (AHORA CON BOTONES DE EDITAR Y BORRAR)
async function cargarChats() {
  const res = await fetch("/chats");
  const chats = await res.json();
  chatList.innerHTML = "";

  chats.forEach((chat) => {
    const div = document.createElement("div");
    div.className = "chat-item";
    if (chat.id === currentChatId) div.classList.add("active");

    // Contenedor del título (Al hacer clic aquí, abre el chat)
    const titleSpan = document.createElement("span");
    titleSpan.className = "chat-item-title";
    titleSpan.textContent = chat.titulo;
    titleSpan.onclick = () => abrirChat(chat.id, chat.titulo);

    // Contenedor de las herramientas (Lápiz y Basurero)
    const actionsDiv = document.createElement("div");
    actionsDiv.className = "chat-item-actions";

    // Botón Editar (Renombrado elegante sin alertas)
    const btnEdit = document.createElement("button");
    btnEdit.className = "action-btn";
    btnEdit.textContent = "✏️";
    btnEdit.title = "Renombrar";
    btnEdit.onclick = (e) => {
      e.stopPropagation(); // Evita que se abra el chat al hacer clic en el botón

      // Convertimos el texto en una cajita de texto (input)
      titleSpan.innerHTML = `<input type="text" id="edit-input-${chat.id}" value="${chat.titulo}" style="width: 100%; padding: 2px; color: black; border-radius: 3px; border: none; font-size: 13px;">`;
      const input = document.getElementById(`edit-input-${chat.id}`);
      input.focus();

      // Función para guardar cuando el usuario termine
      const guardarCambio = async () => {
        const nuevoTitulo = input.value.trim();
        // Si escribió algo nuevo, lo guardamos en la base de datos
        if (nuevoTitulo && nuevoTitulo !== chat.titulo) {
          await fetch(`/chats/${chat.id}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ titulo: nuevoTitulo }),
          });
          if (currentChatId === chat.id)
            chatTitle.textContent = "🇬🇧 " + nuevoTitulo;
        }
        cargarChats(); // Refrescamos la lista
      };

      input.addEventListener("blur", guardarCambio); // Guarda si hace clic afuera
      input.addEventListener("keypress", (e) => {
        if (e.key === "Enter") guardarCambio();
      }); // Guarda si presiona Enter
    };

    // Botón Eliminar
    const btnDelete = document.createElement("button");
    btnDelete.className = "action-btn";
    btnDelete.textContent = "🗑️";
    btnDelete.title = "Eliminar";
    btnDelete.onclick = async (e) => {
      e.stopPropagation();

      // Borrado instantáneo a la base de datos
      await fetch(`/chats/${chat.id}`, { method: "DELETE" });

      // Si eliminaste el chat que tenías abierto, limpiamos la pantalla principal
      if (currentChatId === chat.id) {
        currentChatId = null;
        chatBox.innerHTML = "";
        chatTitle.textContent = "🇬🇧 Tutor IA";
      }

      cargarChats(); // Refrescamos la lista automáticamente
    };

    // Ensamblamos las piezas
    actionsDiv.appendChild(btnEdit);
    actionsDiv.appendChild(btnDelete);
    div.appendChild(titleSpan);
    div.appendChild(actionsDiv);
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
const newChatForm = document.getElementById("new-chat-form");
const newChatInput = document.getElementById("new-chat-input");
const btnConfirmChat = document.getElementById("btn-confirm-chat");
const btnCancelChat = document.getElementById("btn-cancel-chat");

// ➕ 3. Lógica moderna para crear nuevo chat
btnNewChat.addEventListener("click", () => {
  btnNewChat.style.display = "none"; // Ocultamos el botón
  newChatForm.style.display = "flex"; // Mostramos el mini-formulario
  newChatInput.focus(); // Ponemos el cursor ahí automáticamente
});

btnCancelChat.addEventListener("click", () => {
  newChatForm.style.display = "none";
  btnNewChat.style.display = "block";
  newChatInput.value = ""; // Limpiamos la caja
});

async function crearNuevoChat() {
  const titulo = newChatInput.value.trim();
  if (!titulo) return;

  // Restauramos la interfaz a la normalidad
  newChatForm.style.display = "none";
  btnNewChat.style.display = "block";
  newChatInput.value = "";

  const res = await fetch("/crear_chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ titulo: titulo }),
  });
  const data = await res.json();
  await abrirChat(data.chat_id, data.titulo);
}

btnConfirmChat.addEventListener("click", crearNuevoChat);
newChatInput.addEventListener("keypress", (e) => {
  if (e.key === "Enter") crearNuevoChat();
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
  userInput.style.height = "auto"; // 👈 ¡LÍNEA NUEVA! Restaura el tamaño de la caja
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

// Enviar con Enter, salto de línea con Shift + Enter
userInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault(); // Evita que se dibuje un salto de línea accidental
    sendMessage();
  }
});

// Autoajustar la altura de la caja mientras el usuario escribe o pega texto
userInput.addEventListener("input", function () {
  this.style.height = "auto"; // Resetea la altura para calcular bien
  this.style.height = this.scrollHeight + "px"; // Expande según el contenido
});

// Capturamos los nuevos elementos del modal
const modalRevision = document.getElementById("modal-revision");
const listaRevision = document.getElementById("lista-revision");
const btnConfirmarTodo = document.getElementById("btn-confirmar-todo");
const btnCerrarModal = document.getElementById("btn-cerrar-modal");

// 📥 5. NUEVA LÓGICA: Extraer -> Revisar -> Inyectar
btnAnki.addEventListener("click", async () => {
  if (!currentChatId) return alert("Selecciona un chat primero.");

  const textoOriginal = btnAnki.textContent;
  btnAnki.disabled = true;
  btnAnki.textContent = "⏳ Analizando chat...";

  try {
    const res = await fetch("/proponer_cartas", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: currentChatId }),
    });
    const data = await res.json();

    if (data.error) {
      alert(data.error);
    } else if (data.cartas.length === 0) {
      alert("🤷‍♂️ Gemini no encontró vocabulario nuevo para extraer.");
    } else {
      abrirModalRevision(data.cartas);
    }
  } catch (err) {
    alert("Error al conectar con el servidor.");
  } finally {
    btnAnki.disabled = false;
    btnAnki.textContent = textoOriginal;
  }
});

// Función para dibujar las cartas en el modal
function abrirModalRevision(cartas) {
  listaRevision.innerHTML = ""; // Limpiamos

  cartas.forEach((carta, index) => {
    const cardDiv = document.createElement("div");
    cardDiv.className = "card-revision";
    cardDiv.dataset.index = index;

    cardDiv.innerHTML = `
            <span class="delete-card" onclick="this.parentElement.remove()">✕ Eliminar</span>
            <div class="grid-edit">
                <div class="field-group">
                    <label>Frente (Concepto)</label>
                    <input type="text" class="edit-frente" value="${carta.frente}">
                </div>
                <div class="field-group">
                    <label>Categoría</label>
                    <select class="edit-categoria">
                        <option value="Vocabulario" ${carta.categoria === "Vocabulario" ? "selected" : ""}>Vocabulario</option>
                        <option value="Phrasal Verbs" ${carta.categoria === "Phrasal Verbs" ? "selected" : ""}>Phrasal Verbs</option>
                        <option value="Falsos Amigos" ${carta.categoria === "Falsos Amigos" ? "selected" : ""}>Falsos Amigos</option>
                        <option value="Verbos Irregulares" ${carta.categoria === "Verbos Irregulares" ? "selected" : ""}>Verbos Irregulares</option>
                        <option value="Gramatica y Teoria" ${carta.categoria === "Gramatica y Teoria" ? "selected" : ""}>Gramatica y Teoria</option>
                        <option value="Expresiones Nativas" ${carta.categoria === "Expresiones Nativas" ? "selected" : ""}>Expresiones Nativas</option>
                        <option value="Colocaciones" ${carta.categoria === "Colocaciones" ? "selected" : ""}>Colocaciones</option>
                        <option value="Otros" ${carta.categoria === "Otros" ? "selected" : ""}>Otros</option>
                    </select>
                </div>
                <div class="field-group" style="grid-column: span 2;">
                    <label>Reverso (Significado/Definición)</label>
                    <textarea class="edit-reverso" rows="2">${carta.reverso}</textarea>
                </div>
                
                <div class="field-group">
                    <label>Oración Ejemplo (Inglés)</label>
                    <input type="text" class="edit-ejemplo" value="${carta.ejemplo_ingles}">
                    
                    <input type="hidden" class="edit-traduccion" value="${carta.ejemplo_espanol || ""}">
                </div>
                
                <div class="field-group">
                    <label>Término para Imagen (Pexels)</label>
                    <input type="text" class="edit-imagen" value="${carta.termino_imagen}">
                </div>
            </div>
        `;
    listaRevision.appendChild(cardDiv);
  });

  modalRevision.style.display = "block";
}

// Botón Final: Confirmar e Inyectar
btnConfirmarTodo.onclick = async () => {
  const cardElements = document.querySelectorAll(".card-revision");
  const cartasFinales = [];

  cardElements.forEach((el) => {
    cartasFinales.push({
      frente: el.querySelector(".edit-frente").value,
      reverso: el.querySelector(".edit-reverso").value,
      ejemplo_ingles: el.querySelector(".edit-ejemplo").value,
      ejemplo_espanol: el.querySelector(".edit-traduccion").value, // 👈 ¡Nueva línea!
      termino_imagen: el.querySelector(".edit-imagen").value,
      categoria: el.querySelector(".edit-categoria").value,
    });
  });

  if (cartasFinales.length === 0) return alert("No hay cartas para enviar.");

  btnConfirmarTodo.disabled = true;
  btnConfirmarTodo.textContent = "🚀 Inyectando a Anki...";

  try {
    const res = await fetch("/inyectar_cartas", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: currentChatId, cartas: cartasFinales }),
    });
    const data = await res.json();

    alert(data.mensaje);
    modalRevision.style.display = "none";
  } catch (err) {
    alert("Error al inyectar las cartas.");
  } finally {
    btnConfirmarTodo.disabled = false;
    btnConfirmarTodo.textContent = "Confirmar e Inyectar a Anki";
  }
};

// Cerrar modal
btnCerrarModal.onclick = () => (modalRevision.style.display = "none");
window.onclick = (e) => {
  if (e.target == modalRevision) modalRevision.style.display = "none";
};

// 🚀 AL INICIAR: Cargar la lista de chats automáticamente
cargarChats();
