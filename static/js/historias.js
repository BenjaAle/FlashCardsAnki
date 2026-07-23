const btnGenerar = document.getElementById("btn-generar");
const temaInput = document.getElementById("tema-input");
const btnPlayAll = document.getElementById("btn-play-all");
const storyBoard = document.getElementById("story-board");
const historiaTitulo = document.getElementById("historia-titulo");
const modeBtns = document.querySelectorAll(".mode-btn");
const listaHistoriasContainer = document.getElementById("lista-historias");

// Capturamos los elementos del modal (ya existen en el HTML)
const modalRevision = document.getElementById("modal-revision");
const listaRevision = document.getElementById("lista-revision");
const btnConfirmarTodo = document.getElementById("btn-confirmar-todo");
const btnCerrarModal = document.getElementById("btn-cerrar-modal");

const selectorVelocidad = document.getElementById("velocidad-audio");
// Cambiar la velocidad en tiempo real si el audio ya está sonando
selectorVelocidad.addEventListener("change", (e) => {
    audioPlayer.playbackRate = parseFloat(e.target.value);
});

// Memoria global de palabras guardadas
let palabrasEnAnki = [];

// Cargar las palabras desde la base de datos apenas abre la página
async function cargarVocabulario() {
    try {
        const res = await fetch("/api/vocabulario");
        palabrasEnAnki = await res.json();
    } catch (err) {
        console.error("Error cargando vocabulario:", err);
    }
}
cargarVocabulario();

// El motor de pintado (filtro visual)
function resaltarPalabras(textoIngles) {
    if (palabrasEnAnki.length === 0) return textoIngles;

    let textoResaltado = textoIngles;
    
    // Ordenamos de más larga a más corta (para que "give up" se pinte antes que "give")
    const palabrasOrdenadas = [...palabrasEnAnki].sort((a, b) => b.length - a.length);

    palabrasOrdenadas.forEach(palabra => {
        // Escapamos símbolos especiales y usamos \b para pintar solo palabras enteras
        const palabraLimpia = palabra.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const regex = new RegExp(`\\b(${palabraLimpia})\\b`, 'gi');
        
        textoResaltado = textoResaltado.replace(regex, '<span class="anki-highlight">$1</span>');
    });

    return textoResaltado;
}

let lineasActuales = [];
let audioObjects = [];
let reproduciendo = false;
let indiceAudioActual = 0;

// 1. Lógica para cambiar de Modo (Ocultar/Mostrar texto)
modeBtns.forEach(btn => {
    btn.addEventListener("click", () => {
        modeBtns.forEach(b => b.classList.remove("active"));
        btn.classList.add("active");

        const modo = btn.dataset.mode;
        
        // Limpiamos todas las clases de estado del tablero
        storyBoard.classList.remove("hide-es", "hide-en", "show-ipa");

        if (modo === "lectura") {
            // MODO 2 (Adquisición): Oculta español, muestra IPA
            storyBoard.classList.add("hide-es", "show-ipa"); 
        } else if (modo === "escucha") {
            // MODO 3 (Inmersión): Oculta todo
            storyBoard.classList.add("hide-en", "hide-es"); 
        }
    });
});

// 2. Generar la historia llamando al Backend
btnGenerar.addEventListener("click", async () => {
  const tema = temaInput.value.trim();
  if (!tema) return alert("Escribe un tema para la historia.");

  btnGenerar.disabled = true;
  btnGenerar.textContent = "⏳ Escribiendo y grabando...";
  storyBoard.innerHTML =
    "<div style='text-align:center;'>Generando contenido con IA... Esto puede tomar unos segundos.</div>";

  try {
    const res = await fetch("/generar_historia", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tematica: tema, nivel: "Intermedio" }),
    });
    const data = await res.json();

    if (data.error) throw new Error(data.error);

    historiaTitulo.textContent = `📚 ${data.titulo}`;
    cargarHistoria(data.historia_id); // Llamamos a la función que renderiza

    cargarListaHistorias(); // 👈 NUEVO: Refresca la barra lateral
    temaInput.value = ""; // 👈 NUEVO: Limpia la caja de texto
  } catch (err) {
    alert("Error: " + err.message);
    storyBoard.innerHTML = "";
  } finally {
    btnGenerar.disabled = false;
    btnGenerar.textContent = "✨ Generar y Crear Audios";
  }
});

// Capturamos el nuevo reproductor visible
const audioPlayer = document.getElementById("audio-player");

// 3. Cargar la historia en el HTML
async function cargarHistoria(historia_id) {
    audioPlayer.pause();
    audioPlayer.src = "";
    audioPlayer.style.display = "none"; // Ocultamos el reproductor nativo
    
    // Mostramos el botón de inicio al cargar una historia nueva
    btnPlayAll.style.display = "block"; 
    btnPlayAll.textContent = "▶ Reproducir Historia";
    
    indiceAudioActual = -1; // Reseteamos el índice

    const res = await fetch(`/api/historias/${historia_id}`);
    const data = await res.json();
    
    lineasActuales = data.lineas;
    storyBoard.innerHTML = "";

    lineasActuales.forEach((linea, index) => {
        const div = document.createElement("div");
        div.className = "story-line";
        div.id = `linea-${index}`;
        div.style.cursor = "pointer";
        
        // ✨ FIX 2 y FIX 3: Lógica inteligente al hacer clic en la fila
        div.onclick = () => {
            // FIX 3: Si el usuario seleccionó texto, cancelamos el clic para no interrumpir
            if (window.getSelection().toString().trim().length > 0) return;

            // FIX 2: Si hacemos clic en la fila que YA está sonando, pausamos o reanudamos
            if (indiceAudioActual === index) {
                if (audioPlayer.paused) {
                    audioPlayer.play();
                } else {
                    audioPlayer.pause();
                }
            } else {
                // Si es una fila diferente, la reproducimos desde cero
                reproducirDesde(index);
            }
        };
        
        div.innerHTML = `
            <!-- Pasamos la línea en inglés por nuestro filtro de resaltado -->
            <div class="text-en">${resaltarPalabras(linea.en)}</div>
            <div class="text-ipa">${linea.ipa}</div>
            <div class="text-es">${linea.es}</div>
        `;
        storyBoard.appendChild(div);
    });
}

// 4. Lógica del Reproductor Único y Visible
function reproducirDesde(index) {
    if (index >= lineasActuales.length) {
        // Terminó la historia: Volvemos a mostrar el botón inicial
        btnPlayAll.style.display = "block";
        btnPlayAll.textContent = "▶ Reproducir Historia";
        audioPlayer.style.display = "none"; // Ocultamos el reproductor nativo
        document.querySelectorAll(".story-line").forEach(el => el.classList.remove("playing"));
        indiceAudioActual = -1;
        return;
    }

    indiceAudioActual = index;
    
    // ✨ FIX 1: Ocultamos el botón verde porque el reproductor nativo toma el control
    btnPlayAll.style.display = "none";

    // Cargamos el archivo en el reproductor visible y lo hacemos aparecer
    audioPlayer.style.display = "block";
    audioPlayer.src = lineasActuales[index].audio;

    // ✨ EL TRUCO INFALIBLE: Le decimos a este audio específico que cambie su velocidad 
    // justo en el milisegundo en que termina de cargar su información (metadata)
    audioPlayer.onloadedmetadata = () => {
        audioPlayer.playbackRate = parseFloat(selectorVelocidad.value);
    };
    
    audioPlayer.play();

    // Limpiar resaltados anteriores y resaltar el actual
    document.querySelectorAll(".story-line").forEach(el => el.classList.remove("playing"));
    document.getElementById(`linea-${index}`).classList.add("playing");
    
    // Auto-scroll para que la línea siempre se vea
    document.getElementById(`linea-${index}`).scrollIntoView({ behavior: "smooth", block: "center" });
}

// Escuchamos el evento nativo del reproductor
audioPlayer.onended = () => {
    reproducirDesde(indiceAudioActual + 1);
};

// Control maestro inicial (Solo sirve para arrancar desde cero)
btnPlayAll.addEventListener("click", () => {
    if (lineasActuales.length === 0) return;
    reproducirDesde(0);
});

// 5. Cargar la lista de historias en la barra lateral
async function cargarListaHistorias() {
    try {
        const res = await fetch("/api/lista_historias");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        const historias = await res.json();
        const listaHistorias = document.getElementById("lista-historias");
        listaHistorias.innerHTML = "";

        historias.forEach((h) => {
            const item = document.createElement("div");
            item.className = "story-list-item";

            const titleSpan = document.createElement("span");
            titleSpan.textContent = h.titulo;
            titleSpan.className = "story-list-title";
            titleSpan.onclick = () => cargarHistoria(h.id);

            const deleteBtn = document.createElement("button");
            deleteBtn.innerHTML = "🗑️";
            deleteBtn.className = "story-delete-btn";

            deleteBtn.onclick = async (e) => {
                e.stopPropagation();
                if (confirm("¿Estás seguro de que deseas eliminar esta historia?")) {
                    await fetch(`/api/historias/${h.id}`, { method: "DELETE" });
                    cargarListaHistorias();

                    const tituloPantalla = document.getElementById("historia-titulo").textContent;
                    if (tituloPantalla === h.titulo) {
                        document.getElementById("story-board").innerHTML = "<p class='story-empty-state'>Selecciona o genera una historia.</p>";
                        document.getElementById("historia-titulo").textContent = "📚 Reproductor de Historias";
                        audioPlayer.style.display = "none";
                    }
                }
            };

            item.appendChild(titleSpan);
            item.appendChild(deleteBtn);
            listaHistorias.appendChild(item);
        });
    } catch (err) {
        console.error("No se pudo cargar la lista de historias:", err);
    }
}

// 🚀 AL INICIAR: Cargar la lista automáticamente
cargarListaHistorias();

// ==========================================
// 🪄 LÓGICA DE SELECCIÓN "ESTILO KINDLE"
// ==========================================
const floatingBtn = document.getElementById("floating-anki-btn");
let seleccionActual = { palabra: "", contexto: "" };

// 1. Detectar cuando el usuario suelta el clic (termina de seleccionar)
document.addEventListener("mouseup", (e) => {
    // Si hicimos clic en el propio botón flotante, no hacemos nada aquí
    if (e.target.id === "floating-anki-btn") return;

    const selection = window.getSelection();
    const textoSeleccionado = selection.toString().trim();

    // Verificamos si hay texto seleccionado y si estamos dentro de una línea de la historia
    const lineaCercana = e.target.closest('.story-line');

    if (textoSeleccionado.length > 0 && lineaCercana) {
        // Capturamos el texto y la oración completa (para dársela a Gemini como contexto)
        seleccionActual.palabra = textoSeleccionado;
        seleccionActual.contexto = lineaCercana.querySelector('.text-en').textContent;
        // 👇 NUEVO: Guardamos el contenedor HTML exacto donde está la oración en inglés
        seleccionActual.nodoIngles = lineaCercana.querySelector('.text-en');

        // Calculamos dónde dibujar el botón flotante (justo arriba al centro de la selección)
        const range = selection.getRangeAt(0);
        const rect = range.getBoundingClientRect();
        
        // window.scrollY y window.scrollX corrigen la posición si la página está scrolleada
        floatingBtn.style.top = `${rect.top + window.scrollY - 35}px`;
        floatingBtn.style.left = `${rect.left + window.scrollX + (rect.width / 2) - 40}px`;
        floatingBtn.style.display = "block";
    } else {
        // Si hizo clic en el vacío, ocultamos el botón
        floatingBtn.style.display = "none";
    }
});

// Ocultar el botón si la página hace scroll o se cambia el tamaño
window.addEventListener("scroll", () => { floatingBtn.style.display = "none"; });
window.addEventListener("resize", () => { floatingBtn.style.display = "none"; });

// 2. Acción al hacer clic en el botón flotante
// 2. Acción al hacer clic en el botón flotante
floatingBtn.addEventListener("click", async () => {
    floatingBtn.style.display = "none";
    
    // Cambiamos el cursor para mostrar que está cargando
    document.body.style.cursor = "wait";

    try {
        const res = await fetch("/proponer_carta_unica", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ 
                palabra: seleccionActual.palabra, 
                contexto: seleccionActual.contexto 
            })
        });
        const data = await res.json();

        if (data.error) {
            alert(data.error);
        } else if (data.cartas.length === 0) {
            alert("No se pudo generar la carta.");
        } else {
            abrirModalRevision(data.cartas);
        }
    } catch (err) {
        alert("Error al conectar con el servidor.");
    } finally {
        document.body.style.cursor = "default";
        window.getSelection().removeAllRanges(); // Limpiamos la selección
    }
});

// 3. Dibujar las cartas en el modal (Idéntico a script.js)
function abrirModalRevision(cartas) {
    listaRevision.innerHTML = ""; 

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

// 4. Confirmar e Inyectar a Anki
btnConfirmarTodo.onclick = async () => {
    const cardElements = document.querySelectorAll(".card-revision");
    const cartasFinales = [];

    cardElements.forEach((el) => {
        cartasFinales.push({
            frente: el.querySelector(".edit-frente").value,
            reverso: el.querySelector(".edit-reverso").value,
            ejemplo_ingles: el.querySelector(".edit-ejemplo").value,
            ejemplo_espanol: el.querySelector(".edit-traduccion").value,
            termino_imagen: el.querySelector(".edit-imagen").value,
            categoria: el.querySelector(".edit-categoria").value,
        });
    });

    if (cartasFinales.length === 0) return alert("No hay cartas para enviar.");

    btnConfirmarTodo.disabled = true;
    btnConfirmarTodo.textContent = "🚀 Inyectando a Anki...";

    try {
        // Usamos tu mismo endpoint maestro de inyección.
        // Le pasamos chat_id: 0 porque esta carta viene de una historia, no de un chat.
        const res = await fetch("/inyectar_cartas", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ chat_id: 0, cartas: cartasFinales }),
        });
        const data = await res.json();

        alert(data.mensaje);
        modalRevision.style.display = "none";

        if (seleccionActual.palabra) {
            // 1. Guardamos en la base de datos permanente
            await fetch("/api/vocabulario", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ palabra: seleccionActual.palabra })
            });

            // 2. Añadimos a la memoria local
            if (!palabrasEnAnki.includes(seleccionActual.palabra)) {
                palabrasEnAnki.push(seleccionActual.palabra);
            }

            // 3. Pintamos la palabra instantáneamente en la pantalla sin recargar
            if (seleccionActual.nodoIngles) {
                const htmlOriginal = seleccionActual.nodoIngles.innerHTML;
                const palabraLimpia = seleccionActual.palabra.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                const regex = new RegExp(`\\b(${palabraLimpia})\\b`, 'gi');
                seleccionActual.nodoIngles.innerHTML = htmlOriginal.replace(regex, '<span class="anki-highlight">$1</span>');
            }
        }

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

// ==========================================
// ⌨️ ATAJOS DE TECLADO (Espacio, Modos 1-3, W, C)
// ==========================================
document.addEventListener("keydown", function(event) {
    // 1. Protegemos los campos de texto
    const etiquetasIgnoradas = ["INPUT", "TEXTAREA", "SELECT"];
    if (etiquetasIgnoradas.includes(event.target.tagName)) {
        return; 
    }

    // 2. Barra espaciadora para Play / Pausa
    if (event.code === "Space") {
        event.preventDefault();
        if (audioPlayer && audioPlayer.src) {
            if (audioPlayer.paused) {
                audioPlayer.play();
            } else {
                audioPlayer.pause();
            }
        }
    }

    // 3. Teclas 1, 2 y 3 para cambiar de Modo de Aprendizaje
    const mapaTeclasModos = {
        "Digit1": 0, "Numpad1": 0, // 1 -> Comprensión
        "Digit2": 1, "Numpad2": 1, // 2 -> Adquisición
        "Digit3": 2, "Numpad3": 2  // 3 -> Inmersión
    };

    if (mapaTeclasModos.hasOwnProperty(event.code)) {
        const indiceBoton = mapaTeclasModos[event.code];
        if (modeBtns[indiceBoton]) {
            event.preventDefault(); 
            modeBtns[indiceBoton].click(); 
        }
    }


    // 4. Tecla W: Reproducir la línea/audio anterior
    if (event.code === "KeyW") {
        // Verificamos que haya una historia activa (índice mayor o igual a 0)
        // y que no estemos en la primera línea (porque no hay anterior)
        if (indiceAudioActual > 0) {
            event.preventDefault();
            reproducirDesde(indiceAudioActual - 1);
        }
    }

    // 5. Tecla C: Reiniciar el audio actual desde el principio
    if (event.code === "KeyC") {
        // Validamos que haya un audio cargado en el reproductor
        if (audioPlayer && audioPlayer.src) {
            event.preventDefault();
            audioPlayer.currentTime = 0; // Regresamos la pista al segundo cero
            audioPlayer.play(); 
        }
    }

    if (event.code === "KeyV") {
        // Validamos que haya un audio cargado en el reproductor
        if (audioPlayer && audioPlayer.src) {
            event.preventDefault();
            audioPlayer.currentTime = 0; // Regresamos la pista al segundo cero
            audioPlayer.pause(); // Pausamos el audio para que el usuario decida cuándo reanudar
        }
    }
});