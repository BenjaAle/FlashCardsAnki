const gridFonemas = document.getElementById("grid-fonemas");
const inputF1 = document.getElementById("fonema-1");
const inputF2 = document.getElementById("fonema-2");
const btnEntrenar = document.getElementById("btn-entrenar");

const gymZone = document.getElementById("gym-zone");
const gymStatus = document.getElementById("gym-status");
const btnPlayGym = document.getElementById("btn-play-gym");
const gymOptions = document.getElementById("gym-options");
const btnOptA = document.getElementById("btn-opt-a");
const btnOptB = document.getElementById("btn-opt-b");

let paresActuales = [];
let indicePar = 0;
let audioJuego = new Audio();

// 1. Cargar la Tabla Fonética
async function cargarFonemas() {
  const res = await fetch("/api/fonemas");
  const fonemas = await res.json();

  fonemas.forEach((f) => {
    const card = document.createElement("div");
    card.className = "card-fonema";

// Al hacer clic en un fonema, lo pasamos a la barra lateral y reproducimos sus ejemplos
        card.onclick = () => {
            if (!inputF1.value || (inputF1.value && inputF2.value)) {
                inputF1.value = f.simbolo;
                inputF2.value = "";
            } else {
                inputF2.value = f.simbolo;
            }
            
            window.speechSynthesis.cancel();

            // ✨ LA MAGIA OCURRE AQUÍ:
            // "book (/bʊk/)" -> al hacer split(" ") toma solo "book".
            const palabrasLimpias = f.ejemplos.map(ej => ej.split(" ")[0]);
            
            // Las unimos con coma para la pausa dramática
            const textoAReproducir = palabrasLimpias.join(", ");
            
            const utterance = new SpeechSynthesisUtterance(textoAReproducir);
            utterance.lang = 'en-US';
            utterance.rate = 0.70; 
            utterance.pitch = 1.0; 
            
            window.speechSynthesis.speak(utterance);
        };

    card.innerHTML = `
            <div class="simbolo-fonema">${f.simbolo}</div>
            <div style="font-weight:bold; font-size:14px;">${f.nombre}</div>
            <div style="font-size:12px; color:#64748b; margin-top:5px; margin-bottom:10px;">${f.desc}</div>
            <div style="font-size:13px; font-style:italic;">Ej: ${f.ejemplos.join(", ")}</div>
        `;
    gridFonemas.appendChild(card);
  });
}

cargarFonemas();

// 2. Lógica del Gimnasio (Pares Mínimos)
btnEntrenar.addEventListener("click", async () => {
  const f1 = inputF1.value.trim();
  const f2 = inputF2.value.trim();
  if (!f1 || !f2)
    return alert("Por favor, selecciona dos símbolos (ej: /ɪ/ y /iː/).");

  // Mostramos el gimnasio y ocultamos controles de la ronda anterior
  gymZone.style.display = "block";
  gymOptions.style.display = "none";
  btnPlayGym.style.display = "none";
  gymStatus.textContent = `Creando rutina para ${f1} vs ${f2}... ⏳`;
  btnEntrenar.disabled = true;

  try {
    const res = await fetch("/api/entrenar_pares", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fonema_1: f1, fonema_2: f2 }),
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    paresActuales = data.pares;
    indicePar = 0;
    iniciarRonda();
  } catch (err) {
    // En lugar de un mensaje genérico, ahora mostrará exactamente qué falló
    gymStatus.textContent = `🚨 ${err.message}`;
    console.error("Error detallado:", err);
  } finally {
    btnEntrenar.disabled = false;
  }
});

function iniciarRonda() {
  if (indicePar >= paresActuales.length) {
    gymStatus.textContent = "🎉 ¡Entrenamiento completado!";
    gymOptions.style.display = "none";
    btnPlayGym.style.display = "none";
    return;
  }

  const parActual = paresActuales[indicePar];

  // Configurar interfaz
  gymStatus.textContent = `Escucha y elige (${indicePar + 1}/${paresActuales.length})`;
  btnOptA.textContent = parActual.opcion_a;
  btnOptB.textContent = parActual.opcion_b;

  // Limpiar clases de colores
  btnOptA.className = "gym-btn";
  btnOptB.className = "gym-btn";

  gymOptions.style.display = "flex";
  gymOptions.style.justifyContent = "center";
  btnPlayGym.style.display = "inline-block";

  // Cargar audio
  audioJuego.src = "/" + parActual.ruta_audio;

  // Auto-reproducir
  audioJuego.play();
}

// Reproducir manual
btnPlayGym.onclick = () => audioJuego.play();

// Evaluar respuesta
function evaluarRespuesta(botonSeleccionado, identificador) {
  const parActual = paresActuales[indicePar];

  if (identificador === parActual.correcta) {
    botonSeleccionado.classList.add("correct");
    setTimeout(() => {
      indicePar++;
      iniciarRonda();
    }, 1500); // Avanzar después de 1.5s
  } else {
    botonSeleccionado.classList.add("wrong");
    // Le damos otra oportunidad
    audioJuego.play();
  }
}

btnOptA.onclick = () => evaluarRespuesta(btnOptA, "opcion_a");
btnOptB.onclick = () => evaluarRespuesta(btnOptB, "opcion_b");

// ==========================================
// 🔗 LÓGICA DE CONNECTED SPEECH
// ==========================================
const gridConnected = document.getElementById("grid-connected");

async function cargarConnectedSpeech() {
    const res = await fetch("/api/connected_speech");
    const reglas = await res.json();

    reglas.forEach(r => {
        const card = document.createElement("div");
        card.className = "card-fonema"; // Reutilizamos tu elegante diseño CSS
        
        // Al hacer clic, lee las frases con velocidad normal para forzar el "Connected Speech"
        card.onclick = () => {
            window.speechSynthesis.cancel();
            
            // Extraemos solo el texto real (ej: "Don't you"), ignorando nuestra pista fonética (Donchu)
            const frasesLimpias = r.ejemplos.map(ej => ej.split(" (")[0]);
            const textoAReproducir = frasesLimpias.join(". "); // Ponemos punto para una pausa clara
            
            const utterance = new SpeechSynthesisUtterance(textoAReproducir);
            utterance.lang = 'en-US';
            utterance.rate = 1.0; // Velocidad 100% (nativa)
            
            window.speechSynthesis.speak(utterance);
        };

        // Formateamos los ejemplos para que aparezcan uno debajo del otro con saltos de línea
        const ejemplosHTML = r.ejemplos.join("<br>➔ ");

        card.innerHTML = `
            <div class="simbolo-fonema" style="font-size: 24px; color: #e67e22;">${r.regla}</div>
            <div style="font-weight:bold; font-size:14px;">${r.nombre}</div>
            <div style="font-size:12px; color:#64748b; margin-top:5px; margin-bottom:10px;">${r.desc}</div>
            <div style="font-size:13px; font-style:italic; text-align: left; padding-left: 10px;">
                ➔ ${ejemplosHTML}
            </div>
        `;
        gridConnected.appendChild(card);
    });
}

// Inicializamos la sección
cargarConnectedSpeech();