const btnSend = document.getElementById("btn-send"); // Capturamos el botón de enviar
const userInput = document.getElementById("user-input"); // Capturamos la caja de texto del usuario
const chatBox = document.getElementById("chat-box"); // Capturamos el contenedor de mensajes
const btnAnki = document.getElementById("btn-anki"); // Capturamos el botón de extraer a Anki
const chatList = document.getElementById("chat-list"); // Capturamos la lista de chats
const btnNewChat = document.getElementById("btn-new-chat"); // Capturamos el botón de nuevo chat
const chatTitle = document.getElementById("chat-title"); // Capturamos el título del chat

// Variable para saber en qué conversación estamos
let currentChatId = null;

const newChatForm = document.getElementById("new-chat-form"); // Capturamos el mini-formulario de nuevo chat
const newChatInput = document.getElementById("new-chat-input"); // Capturamos la caja de texto del mini-formulario
const btnConfirmChat = document.getElementById("btn-confirm-chat"); // Capturamos el botón de confirmar del mini-formulario
const btnCancelChat = document.getElementById("btn-cancel-chat"); // Capturamos el botón de cancelar del mini-formulario

// Capturamos los nuevos elementos del modal
const modalRevision = document.getElementById("modal-revision"); // Capturamos el modal de revisión
const listaRevision = document.getElementById("lista-revision"); // Capturamos la lista de revisiones
const btnConfirmarTodo = document.getElementById("btn-confirmar-todo"); // Capturamos el botón de confirmar todo
const btnCerrarModal = document.getElementById("btn-cerrar-modal"); // Capturamos el botón de cerrar modal

// Pasar de markdown a HTML
function formatearMarkdown(texto) {
  let html = texto
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
    
  // Titulos (H1 hasta H6)
  html = html.replace(/^###### (.*$)/gim, "<h6>$1</h6>");
  html = html.replace(/^##### (.*$)/gim, "<h5>$1</h5>");
  html = html.replace(/^#### (.*$)/gim, "<h4>$1</h4>");
  html = html.replace(/^### (.*$)/gim, "<h3>$1</h3>");
  html = html.replace(/^## (.*$)/gim, "<h2>$1</h2>");
  html = html.replace(/^# (.*$)/gim, "<h1>$1</h1>");

  html = html.replace(/(^|\n)\s*[\*-]\s+/g, "$1• "); // listas con viñetas
  html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>"); // negrita
  html = html.replace(/\*(.*?)\*/g, "<em>$1</em>"); // cursiva
  html = html.replace(/\n/g, "<br>"); // cambio \n por <br>
  
  // Limpieza visual: Quita los saltos de línea extra debajo de los títulos
  html = html.replace(/<\/h6><br>/g, "</h6>");
  html = html.replace(/<\/h5><br>/g, "</h5>");
  html = html.replace(/<\/h4><br>/g, "</h4>");
  html = html.replace(/<\/h3><br>/g, "</h3>");
  html = html.replace(/<\/h2><br>/g, "</h2>");
  html = html.replace(/<\/h1><br>/g, "</h1>");
  
  return html;
}

// 🗂️ 1. Cargar la lista de chats en la barra lateral con botones de eliminar y editar
async function cargarChats() {

  // llamada a la API para obtener la lista de chats
  // llega algo asi: # [{"id": 1, "titulo": "Chat 1"}, {"id": 2, "titulo": "Chat 2"}]
  const res = await fetch("/chats");

  // Convertimos la respuesta a JSON
  // ejemplo: [{"id": 1, "titulo": "Chat 1"}, {"id": 2, "titulo": "Chat 2"}]
  const chats = await res.json();

  // inicio con la lista vacia
  chatList.innerHTML = "";

  // chat es un objeto con id y titulo, ejemplo: {id: 1, titulo: "Chat 1"}
  chats.forEach((chat) => {
    const div = document.createElement("div");
    div.className = "chat-item";

    // le pongo la clase "active"
    if (chat.id === currentChatId) div.classList.add("active");

    // Contenedor del título (Al hacer clic aquí, abre el chat)
    const titleSpan = document.createElement("span");
    titleSpan.className = "chat-item-title";
    titleSpan.textContent = chat.titulo;

    // abrirChat se define más abajo, y se encarga de cargar el historial del chat seleccionado
    titleSpan.onclick = () => abrirChat(chat.id, chat.titulo);

    // Contenedor de las herramientas (Lápiz y Basurero)
    const actionsDiv = document.createElement("div");
    actionsDiv.className = "chat-item-actions";

    // Botón Editar
    const btnEdit = document.createElement("button");
    btnEdit.className = "action-btn";
    btnEdit.textContent = "✏️";
    btnEdit.title = "Renombrar";
    btnEdit.onclick = (e) => {
      e.stopPropagation(); // Evita que se abra el chat al hacer clic en el botón

      // Convertimos el texto en una cajita de texto (input)
      titleSpan.innerHTML = `<input type="text" id="edit-input-${chat.id}" value="${chat.titulo}" style="width: 100%; padding: 2px; color: black; border-radius: 3px; border: none; font-size: 13px;">`;
      const input = document.getElementById(`edit-input-${chat.id}`);
      
      // pone el cursor dentro para poder escribir directamente sin otro clic
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
            chatTitle.textContent = nuevoTitulo;
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
        chatTitle.textContent = "Tutor IA";
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
  currentChatId = id; // actualizar el chat actual
  chatTitle.textContent = titulo; // Titulo superior del chat
  chatBox.innerHTML = "";
  await cargarChats(); // Refrescar para marcar en azul el chat activo

   // pido a la api el historial de mensajes de ese chat
  const res = await fetch(`/chats/${id}/mensajes`);
  const mensajes = await res.json();

  if (mensajes.length === 0) {
    const sysMsg = document.createElement("div");
    sysMsg.className = "message bot";
    sysMsg.textContent =
      "¡Hello! Soy tu tutor de inglés. ¿De qué hablaremos en esta sesión? 🚀";
    chatBox.appendChild(sysMsg);
  } else {
    // css y formato de mensaje segun si es el usuario o el bot
    mensajes.forEach((msg) => { 
      const msgDiv = document.createElement("div");
      msgDiv.className = msg.rol === "user" ? "message user" : "message bot";
      if (msg.rol === "bot") {
        msgDiv.innerHTML = formatearMarkdown(msg.texto);
      } else {
        msgDiv.textContent = msg.texto; // evitar xss
      }
      chatBox.appendChild(msgDiv);
    });
  }
  // poner el scroll al final para ver el último mensaje
  chatBox.scrollTop = chatBox.scrollHeight; 
}

// ➕ 3. Lógica para crear nuevo chat
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
  userInput.style.height = "auto";
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
//btnCerrarModal.onclick = () => {
//    modalRevision.style.display = "none";
//};

// Cerrar modal con confirmación de seguridad
btnCerrarModal.onclick = () => {
    // 1. Contamos cuántas cartas hay actualmente en la pantalla
    const numeroDeCartas = document.querySelectorAll(".card-revision").length;
    
    // 2. Si hay cartas, lanzamos la advertencia
    if (numeroDeCartas > 0) {
        const confirmarCierre = confirm("⚠️ ¿Estás seguro de cerrar? Se perderán las cartas no guardadas.");
        
        // Si el usuario hace clic en "Cancelar" en la alerta, detenemos el cierre
        if (!confirmarCierre) {
            return; 
        }
    }
    
    // 3. Si no había cartas (porque las eliminó todas a mano) o si el usuario dijo "Aceptar", cerramos
    modalRevision.style.display = "none";
};

// 🚀 AL INICIAR: Cargar la lista de chats automáticamente
cargarChats();
