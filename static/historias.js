const btnGenerar = document.getElementById("btn-generar");
const temaInput = document.getElementById("tema-input");
const btnPlayAll = document.getElementById("btn-play-all");
const storyBoard = document.getElementById("story-board");
const historiaTitulo = document.getElementById("historia-titulo");
const modeBtns = document.querySelectorAll(".mode-btn");
const listaHistoriasContainer = document.getElementById("lista-historias");

let lineasActuales = [];
let audioObjects = [];
let reproduciendo = false;
let indiceAudioActual = 0;

// 1. Lógica para cambiar de Modo (Ocultar/Mostrar texto)
modeBtns.forEach((btn) => {
  btn.addEventListener("click", () => {
    // Quitar la clase active a todos y dársela al presionado
    modeBtns.forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");

    const modo = btn.dataset.mode;

    // Limpiar clases del tablero
    storyBoard.classList.remove("hide-es", "hide-en");

    if (modo === "lectura") {
      storyBoard.classList.add("hide-es"); // Oculta español
    } else if (modo === "escucha") {
      storyBoard.classList.add("hide-en", "hide-es"); // Oculta todo
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
    // 🛠️ FIX AL BUG: Detener cualquier audio sonando antes de cargar lo nuevo
    audioPlayer.pause();
    audioPlayer.src = "";
    audioPlayer.style.display = "none";
    reproduciendo = false;
    btnPlayAll.textContent = "▶ Reproducir Historia";
    btnPlayAll.style.background = "#27ae60";

    const res = await fetch(`/api/historias/${historia_id}`);
    const data = await res.json();
    
    lineasActuales = data.lineas;
    storyBoard.innerHTML = "";

    lineasActuales.forEach((linea, index) => {
        const div = document.createElement("div");
        div.className = "story-line";
        div.id = `linea-${index}`;
        
        // ✨ NUEVA FUNCIÓN: Haz clic en cualquier oración para reproducirla desde ahí
        div.style.cursor = "pointer";
        div.onclick = () => reproducirDesde(index);
        
        div.innerHTML = `
            <div class="text-en">${linea.en}</div>
            <div class="text-es">${linea.es}</div>
        `;
        storyBoard.appendChild(div);
    });
}

// 4. Lógica del Reproductor Único y Visible
function reproducirDesde(index) {
    if (index >= lineasActuales.length) {
        // Terminó la historia
        reproduciendo = false;
        btnPlayAll.textContent = "▶ Reproducir Historia";
        btnPlayAll.style.background = "#27ae60";
        document.querySelectorAll(".story-line").forEach(el => el.classList.remove("playing"));
        return;
    }

    reproduciendo = true;
    indiceAudioActual = index;
    
    // Cambiamos el texto del botón
    btnPlayAll.textContent = "⏸ Pausar";
    btnPlayAll.style.background = "#e74c3c";

    // Cargamos el archivo en el reproductor visible y lo hacemos aparecer
    audioPlayer.style.display = "block";
    audioPlayer.src = lineasActuales[index].audio;
    audioPlayer.play();

    // Limpiar resaltados anteriores y resaltar el actual
    document.querySelectorAll(".story-line").forEach(el => el.classList.remove("playing"));
    document.getElementById(`linea-${index}`).classList.add("playing");
    
    // Auto-scroll para que la línea siempre se vea
    document.getElementById(`linea-${index}`).scrollIntoView({ behavior: "smooth", block: "center" });
}

// Escuchamos el evento nativo del reproductor: cuando termina un audio, pasa al siguiente
audioPlayer.onended = () => {
    reproducirDesde(indiceAudioActual + 1);
};

// Control maestro desde el botón verde/rojo
btnPlayAll.addEventListener("click", () => {
    if (lineasActuales.length === 0) return;

    if (reproduciendo) {
        // Si estaba sonando, lo pausamos nativamente
        audioPlayer.pause();
        reproduciendo = false;
        btnPlayAll.textContent = "▶ Reanudar";
        btnPlayAll.style.background = "#f39c12"; // Color naranja para indicar pausa
    } else {
        // Si hay un audio cargado (pausado), lo reanudamos desde donde quedó
        if (audioPlayer.src && audioPlayer.src !== window.location.href) {
            audioPlayer.play();
            reproduciendo = true;
            btnPlayAll.textContent = "⏸ Pausar";
            btnPlayAll.style.background = "#e74c3c";
        } else {
            // Si está desde cero, empezamos por la línea 0
            reproducirDesde(0);
        }
    }
});

// 5. Cargar la lista de historias en la barra lateral
async function cargarListaHistorias() {
    const res = await fetch("/api/lista_historias");
    const historias = await res.json();
    
    listaHistoriasContainer.innerHTML = "";

    historias.forEach((historia) => {
        const div = document.createElement("div");
        div.className = "chat-item"; 
        
        const titleSpan = document.createElement("span");
        titleSpan.className = "chat-item-title";
        titleSpan.textContent = historia.titulo;
        
        // Al hacer clic, cargamos esa historia y actualizamos el título
        div.onclick = () => {
            historiaTitulo.textContent = `📚 ${historia.titulo}`;
            cargarHistoria(historia.id);
        };

        div.appendChild(titleSpan);
        listaHistoriasContainer.appendChild(div);
    });
}

// 🚀 AL INICIAR: Cargar la lista automáticamente
cargarListaHistorias();