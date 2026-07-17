import asyncio
import os
import json
import urllib.request  # Web: Para comunicarnos con AnkiConnect
import base64  # Codificar imagenes y audios para Anki
import re
import requests  # Para consumir la API de Pexels
import sqlite3
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles  # Para que la web lea estaticos js y css
from pydantic import BaseModel
from dotenv import load_dotenv
from google import genai  # Comunicacion con gemini
from google.genai import types  # Memoria de chat
import edge_tts

# ==========================================
# ⚙️ CONFIGURACIÓN GENERAL
# ==========================================
NOMBRE_MAZO = "Ingles_IA"
NOMBRE_TIPO_CARTA = "Basic"
CAMPO_FRENTE = "Front"
CAMPO_REVERSO = "Back"

load_dotenv()
api_key_gemini = os.getenv("GEMINI_API_KEY")
api_key_pexels = os.getenv("PEXELS_API_KEY")

if not api_key_gemini or not api_key_pexels:
    raise ValueError(
        "❌ Falla: Revisa que GEMINI_API_KEY y PEXELS_API_KEY estén en tu .env"
    )

client = genai.Client(api_key=api_key_gemini)


VOCAL_TTS = "en-US-AvaNeural"


async def generar_audio(texto, nombre_archivo, voz=VOCAL_TTS):
    comunicacion = edge_tts.Communicate(texto, voz)
    await comunicacion.save(nombre_archivo)


# ==========================================
# 🗄️ INICIALIZACIÓN DE LA BASE DE DATOS
# ==========================================
def iniciar_bd():
    # Abrir archivo de la BDD (o crearlo)
    conn = sqlite3.connect("tutor.db")

    # Crear cursor para ejecutar comandos SQL
    c = conn.cursor()

    # Tabla para guardar las sesiones de chat (barra lateral)
    c.execute(
        """CREATE TABLE IF NOT EXISTS chats (id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT)"""
    )
    # Tabla para guardar los mensajes de cada chat (extraidos para memoria y extracción a Anki)
    # rol: yo o IA.
    c.execute(
        """CREATE TABLE IF NOT EXISTS mensajes (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, rol TEXT, texto TEXT, extraido INTEGER DEFAULT 0)"""
    )

    # Tabla para guardar historias
    c.execute(
        """CREATE TABLE IF NOT EXISTS historias (id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT, tematica TEXT)"""
    )
    c.execute("""CREATE TABLE IF NOT EXISTS lineas_historia (
                 id INTEGER PRIMARY KEY AUTOINCREMENT, 
                 historia_id INTEGER, 
                 orden INTEGER, 
                 oracion_en TEXT, 
                 oracion_es TEXT, 
                 ruta_audio TEXT)""")

    conn.commit()
    conn.close()

    # Crear carpeta para guardar los audios de las historias si no existe
    os.makedirs("static/audios", exist_ok=True)


iniciar_bd()

# ==========================================
# 🚀 CONFIGURACIÓN DE FASTAPI
# ==========================================
app = FastAPI(title="Tutor de Inglés con IA")

# Permiso para ver la carpeta static
app.mount("/static", StaticFiles(directory="static"), name="static")
# Permiso para ver la carpeta templates
templates = Jinja2Templates(directory="templates")


# Estructuras de datos que recibiremos del navegador
class Mensaje(BaseModel):
    texto: str
    chat_id: int  # Para saber a qué chat pertenece el mensaje


class NuevoChat(BaseModel):
    titulo: str


class ExtraerRequest(BaseModel):
    chat_id: int


# Estructura para renombrar
class RenombrarRequest(BaseModel):
    titulo: str


# Extraer cartas a Anki leyendo directamente de la Base de Datos
# Se define la nueva estructura de datos que enviará el navegador para la inyección final
class InyectarRequest(BaseModel):
    chat_id: int
    cartas: list


# Estructura para crear una nueva historia
class NuevaHistoria(BaseModel):
    tematica: str
    nivel: str = "Avanzado"


class CartaUnicaRequest(BaseModel):
    palabra: str
    contexto: str


class EntrenamientoPares(BaseModel):
    fonema_1: str
    fonema_2: str


# ==========================================
# 🔌 FUNCIONES DE ANKI
# ==========================================


# Función para crear la estructura de la petición a AnkiConnect
def request_anki(action, **params):
    return {"action": action, "version": 6, "params": params}


# Función para invocar AnkiConnect


def invoke_anki(action, **params):
    requestJson = json.dumps(request_anki(action, **params)).encode("utf-8")
    response = json.load(
        urllib.request.urlopen(
            urllib.request.Request("http://127.0.0.1:8765", requestJson)
        )
    )
    if response["error"] is not None:
        raise Exception(response["error"])
    return response["result"]


# ==========================================
# 🌐 RUTAS WEB Y BASE DE DATOS
# ==========================================
@app.get("/", response_class=HTMLResponse)
def pagina_principal(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


# 1. Crear un chat nuevo
@app.post("/crear_chat")
def crear_chat(datos: NuevoChat):
    conn = sqlite3.connect("tutor.db")
    c = conn.cursor()

    # Consulta parametrizada para evitar inyecciones SQL
    c.execute("INSERT INTO chats (titulo) VALUES (?)", (datos.titulo,))

    # Obtener el ID del chat recién creado
    chat_id = c.lastrowid
    conn.commit()
    conn.close()
    return {"chat_id": chat_id, "titulo": datos.titulo}


# 2. Obtener la lista de chats para la barra lateral
@app.get("/chats")
def obtener_chats():
    conn = sqlite3.connect("tutor.db")
    c = conn.cursor()
    c.execute("SELECT id, titulo FROM chats ORDER BY id DESC")
    chats = [{"id": row[0], "titulo": row[1]} for row in c.fetchall()]
    conn.close()
    return chats


# 3. Renombrar un chat existente
@app.put("/chats/{chat_id}")
def renombrar_chat(chat_id: int, req: RenombrarRequest):
    conn = sqlite3.connect("tutor.db")
    c = conn.cursor()

    # (req.titulo, chat_id) va dentro
    c.execute("UPDATE chats SET titulo = ? WHERE id = ?", (req.titulo, chat_id))
    conn.commit()
    conn.close()
    return {"mensaje": "Renombrado exitosamente"}


# 4. Eliminar un chat y sus mensajes.
@app.delete("/chats/{chat_id}")
def eliminar_chat(chat_id: int):
    conn = sqlite3.connect("tutor.db")
    c = conn.cursor()
    c.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
    c.execute("DELETE FROM mensajes WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()
    return {"mensaje": "Eliminado exitosamente"}


# 5. Obtener los mensajes antiguos de un chat específico
@app.get("/chats/{chat_id}/mensajes")
def obtener_mensajes(chat_id: int):
    conn = sqlite3.connect("tutor.db")
    c = conn.cursor()
    c.execute(
        "SELECT rol, texto FROM mensajes WHERE chat_id = ? ORDER BY id ASC", (chat_id,)
    )
    mensajes = [{"rol": row[0], "texto": row[1]} for row in c.fetchall()]
    conn.close()
    return mensajes


# 6. El motor de conversación con memoria real
@app.post("/chat")
def conversar(mensaje: Mensaje):
    try:
        conn = sqlite3.connect("tutor.db")
        c = conn.cursor()

        # A) Guardamos lo que dijo el usuario
        c.execute(
            "INSERT INTO mensajes (chat_id, rol, texto) VALUES (?, ?, ?)",
            (mensaje.chat_id, "user", mensaje.texto),
        )
        conn.commit()

        # B) Reconstruimos la memoria para Gemini leyendo la base de datos
        c.execute(
            "SELECT rol, texto FROM mensajes WHERE chat_id = ? ORDER BY id DESC LIMIT 12",
            (mensaje.chat_id,),
        )
        historial_bd = c.fetchall()
        historial_bd.reverse()  # Los invertimos para que queden en orden cronológico correcto (del más viejo al más nuevo)

        historial_gemini = []
        # Pasamos todos los mensajes menos el último (que es el que enviaremos ahora)
        for rol, texto in historial_bd[:-1]:
            gemini_rol = "user" if rol == "user" else "model"
            historial_gemini.append(
                types.Content(role=gemini_rol, parts=[types.Part.from_text(text=texto)])
            )

        # C) Creamos la sesión de IA inyectándole la memoria del pasado
        chat_ia = client.chats.create(
            model="gemini-2.5-flash",
            config={
                "system_instruction": "Eres un amigable y experto tutor de inglés. Responde de forma concisa, conversacional y educativa."
            },
            history=historial_gemini,
        )

        # D) Le enviamos el mensaje actual
        respuesta = chat_ia.send_message(mensaje.texto)

        # E) Guardamos la respuesta de la IA
        c.execute(
            "INSERT INTO mensajes (chat_id, rol, texto) VALUES (?, ?, ?)",
            (mensaje.chat_id, "bot", respuesta.text),
        )
        conn.commit()
        conn.close()

        return {"respuesta": respuesta.text}
    except Exception as e:
        return {"respuesta": f"Error: {str(e)}"}


# 7. Generar propuestas de cartas
@app.post("/proponer_cartas")
def proponer_cartas(req: ExtraerRequest):
    conn = sqlite3.connect("tutor.db")
    c = conn.cursor()
    c.execute(
        "SELECT rol, texto FROM mensajes WHERE chat_id = ? AND extraido = 0 ORDER BY id ASC",
        (req.chat_id,),
    )
    historial_bd = c.fetchall()
    conn.close()

    if not historial_bd:
        return {"error": "⚠️ No hay vocabulario nuevo desde la última extracción."}

    historial_texto = ""
    for rol, texto in historial_bd:
        quien = "Alumno" if rol == "user" else "Tutor"
        historial_texto += f"{quien}: {texto}\n\n"

    prompt = f"""
    Eres un creador de flashcards experto. Analiza el siguiente historial de conversación entre un alumno y su tutor de inglés.
    REGLA 1: Extrae ÚNICAMENTE el vocabulario útil, phrasal verbs, frases completas o correcciones clave. Si no hay nada útil, devuelve []
    REGLA 2: Devuelve ESTRICTAMENTE un arreglo JSON puro sin formato markdown ni bloques ```json.
    Formato esperado:
    [
      {{
        "frente": "Palabra o concepto",
        "reverso": "Definición básica en español",
        "ejemplo_ingles": "Oración de ejemplo en inglés.",
        "ejemplo_espanol": "Traducción natural de la oración de ejemplo al español.",
        "termino_imagen": "Palabra clave visual en inglés",
        "categoria": "ELIGE_UNA_CATEGORIA"
      }}
    ]
    REGLA 3: El campo "categoria" DEBE ser ESTRICTAMENTE una de las siguientes:
    - Vocabulario
    - Phrasal Verbs
    - Falsos Amigos
    - Verbos Irregulares
    - Gramatica y Teoria
    - Expresiones Nativas
    - Colocaciones
    - Otros
    REGLA 4 (VERBOS E INTELIGENCIA DE CONJUGACIÓN): Si el término extraído es un VERBO, aplica esta lógica para los campos "ejemplo_ingles" y "ejemplo_espanol":
    - Si el verbo es REGULAR: Crea EXACTAMENTE 2 ejemplos (uno en presente, y otro en pasado simple o presente perfecto).
    - Si el verbo es IRREGULAR: Crea EXACTAMENTE 3 ejemplos (presente, pasado simple y presente perfecto usando el participio).
    ¡VITAL!: Debes separar cada ejemplo usando el símbolo " | ". 
    Por ejemplo, "ejemplo_ingles": "I go to the park. | He went home! | We have gone far." y su respectivo "ejemplo_espanol": "Voy al parque. | ¡Él se fue a casa! | Hemos ido lejos."
    REGLA 5 (PHRASAL VERBS MÚLTIPLES SIGNIFICADOS): Si el término extraído pertenece a la categoría "Phrasal Verbs":
    1. En el campo "frente", añade entre paréntesis su tipo gramatical exacto: "(Sin objeto)", "(Separable)" o "(Inseparable)". Ejemplo: "Work out (Sin objeto)" o "Turn on (Separable)".
    2. En el campo "reverso", enumera sus significados más comunes (ej: "1. Hacer ejercicio. <br> 2. Resolver / Calcular.").
    3. En los campos "ejemplo_ingles" y "ejemplo_espanol", crea un ejemplo por CADA UNO de los significados.
    4. ¡VITAL!: Separa los ejemplos usando estrictamente el símbolo " | " (igual que en la Regla 4).
    REGLA 6 (UN EJEMPLO POR CADA SIGNIFICADO): Si el término extraído tiene múltiples significados, crea un ejemplo en inglés y su traducción al español para cada significado. Separa los ejemplos usando estrictamente el símbolo " | ".
    REGLA 7 (IMÁGENES SIEMPRE): El campo "termino_imagen" NUNCA debe estar vacío. Si el concepto es muy abstracto (ej. preposiciones, tiempos verbales), asigna un término visual simple en inglés (ej: "talking", "idea", "study", "person"). Usa siempre palabras en inglés.

    Historial a procesar:
    {historial_texto}
    """

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=prompt
        )
        respuesta_limpia = (
            response.text.replace("```json", "").replace("```", "").strip()
        )

        datos_brutos = json.loads(respuesta_limpia)
        if isinstance(datos_brutos, dict):
            lista_cartas = next(
                (v for v in datos_brutos.values() if isinstance(v, list)), []
            )
        else:
            lista_cartas = datos_brutos if isinstance(datos_brutos, list) else []

        return {"cartas": lista_cartas}
    except Exception as e:
        return {"error": f"Error al generar propuestas: {str(e)}"}


# 8. Toma las cartas propuestas y las inyecta a Anki, generando audios e imágenes en paralelo
@app.post("/inyectar_cartas")
async def inyectar_cartas(req: InyectarRequest):
    try:
        if not req.cartas:
            return {"mensaje": "🤷‍♂️ No se enviaron cartas para inyectar."}

        # ------------------------------------------------------------------
        # 🌟 FASE 1: RECOPILAR Y GENERAR TODOS LOS AUDIOS EN PARALELO (CONCURRENTE)
        # ------------------------------------------------------------------
        tareas_audio = []

        for i, carta in enumerate(req.cartas):
            texto_frente = str(carta.get("frente", "")).strip()
            nombre_limpio = "".join(
                c if c.isalnum() else "_" for c in texto_frente[:15]
            )

            # 1. Preparar audio del Frente
            texto_audio_frente = (
                re.sub(r"\(.*?\)", "", texto_frente)
                .replace("**", "")
                .replace("*", "")
                .strip()
            )
            nombre_archivo_frente = f"ia_audio_frente_{nombre_limpio}_{i}.mp3"
            if texto_audio_frente:
                # Agregamos la corrutina a la lista de tareas (sin ejecutarla aún)
                tareas_audio.append(
                    generar_audio(texto_audio_frente, nombre_archivo_frente)
                )

            # 2. Preparar audios de los Ejemplos Múltiples
            texto_ejemplo = str(carta.get("ejemplo_ingles", "")).strip()
            if texto_ejemplo:
                oraciones_en = [
                    o.strip() for o in texto_ejemplo.split("|") if o.strip()
                ]
                for j, oracion_en in enumerate(oraciones_en):
                    texto_audio_ejemplo = (
                        oracion_en.replace("**", "").replace("*", "").strip()
                    )
                    nombre_archivo_ejemplo = (
                        f"ia_audio_ejemplo_{nombre_limpio}_{i}_{j}.mp3"
                    )
                    if texto_audio_ejemplo:
                        # Agregamos la corrutina a la lista de tareas
                        tareas_audio.append(
                            generar_audio(texto_audio_ejemplo, nombre_archivo_ejemplo)
                        )

        # Disparamos todas las descargas de audio simultáneamente a internet y esperamos que terminen
        if tareas_audio:
            await asyncio.gather(*tareas_audio)

        # ------------------------------------------------------------------
        # 🌟 FASE 2: INYECCIÓN SECUENCIAL A ANKI (Los archivos ya existen en disco)
        # ------------------------------------------------------------------
        cartas_agregadas = 0

        for i, carta in enumerate(req.cartas):
            texto_frente = str(carta.get("frente", "")).strip()
            texto_reverso_base = str(carta.get("reverso", "")).strip()
            texto_ejemplo = str(carta.get("ejemplo_ingles", "")).strip()
            termino_imagen = str(carta.get("termino_imagen", "")).strip()

            categoria_elegida = str(carta.get("categoria", "Vocabulario")).strip()
            categorias_validas = [
                "Vocabulario",
                "Phrasal Verbs",
                "Falsos Amigos",
                "Verbos Irregulares",
                "Gramatica y Teoria",
                "Expresiones Nativas",
                "Colocaciones",
                "Otros",
            ]
            if categoria_elegida not in categorias_validas:
                categoria_elegida = "Otros"

            mazo_destino = f"{NOMBRE_MAZO}::{categoria_elegida}"

            try:
                invoke_anki("createDeck", deck=mazo_destino)
            except:
                pass

            nombre_limpio = "".join(
                c if c.isalnum() else "_" for c in texto_frente[:15]
            )

            def md_a_html(texto):
                texto = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", texto)
                texto = re.sub(r"\*(.*?)\*", r"<i>\1</i>", texto)
                return texto

            texto_frente_html = md_a_html(texto_frente)
            texto_reverso_base_html = md_a_html(texto_reverso_base)
            texto_ejemplo_html = md_a_html(texto_ejemplo)
            traduccion_ejemplo = str(carta.get("ejemplo_espanol", "")).strip()
            traduccion_ejemplo_html = md_a_html(traduccion_ejemplo)

            if "<br>" in texto_reverso_base_html:
                texto_reverso_final = texto_reverso_base_html
            else:
                texto_reverso_final = f"<b>{texto_reverso_base_html}</b>"

            # 1. IMAGEN DE PEXELS (Se mantiene igual)
            if termino_imagen:
                try:
                    url_busqueda = f"https://api.pexels.com/v1/search?query={termino_imagen}&per_page=1"
                    respuesta_pexels = requests.get(
                        url_busqueda,
                        headers={"Authorization": api_key_pexels},
                        timeout=5,
                    )
                    if respuesta_pexels.status_code == 200:
                        datos_pexels = respuesta_pexels.json()
                        if datos_pexels.get("photos"):
                            url_imagen = datos_pexels["photos"][0]["src"]["medium"]
                            img_data = requests.get(url_imagen, timeout=5).content
                            nombre_archivo_img = f"ia_img_{nombre_limpio}_{i}.jpg"
                            invoke_anki(
                                "storeMediaFile",
                                filename=nombre_archivo_img,
                                data=base64.b64encode(img_data).decode("utf-8"),
                            )
                            texto_reverso_final = (
                                f"<img src='{nombre_archivo_img}'><br><br>"
                                + texto_reverso_final
                            )
                except:
                    pass

            # 2. VINCULAR AUDIO FRENTE (El archivo ya fue creado en la Fase 1)
            nombre_archivo_frente = f"ia_audio_frente_{nombre_limpio}_{i}.mp3"
            if os.path.exists(nombre_archivo_frente):
                try:
                    with open(nombre_archivo_frente, "rb") as f:
                        invoke_anki(
                            "storeMediaFile",
                            filename=nombre_archivo_frente,
                            data=base64.b64encode(f.read()).decode("utf-8"),
                        )
                    texto_frente_html += f" [sound:{nombre_archivo_frente}]"
                except:
                    pass
                finally:
                    if os.path.exists(nombre_archivo_frente):
                        os.remove(nombre_archivo_frente)

            # 3. VINCULAR AUDIOS DE EJEMPLOS MÚLTIPLES
            if texto_ejemplo:
                oraciones_en = [
                    o.strip() for o in texto_ejemplo.split("|") if o.strip()
                ]
                oraciones_es = (
                    [o.strip() for o in traduccion_ejemplo.split("|") if o.strip()]
                    if traduccion_ejemplo
                    else []
                )

                if traduccion_ejemplo and len(oraciones_en) != len(oraciones_es):
                    oraciones_en = [texto_ejemplo.replace("|", "")]
                    oraciones_es = [traduccion_ejemplo.replace("|", "")]

                for j, oracion_en in enumerate(oraciones_en):
                    oracion_en_html = md_a_html(oracion_en)
                    oracion_es_html = (
                        md_a_html(oraciones_es[j]) if j < len(oraciones_es) else ""
                    )
                    nombre_archivo_ejemplo = (
                        f"ia_audio_ejemplo_{nombre_limpio}_{i}_{j}.mp3"
                    )
                    audio_tag = ""

                    # Vincular si el archivo fue creado con éxito en la Fase 1
                    if os.path.exists(nombre_archivo_ejemplo):
                        try:
                            with open(nombre_archivo_ejemplo, "rb") as f:
                                invoke_anki(
                                    "storeMediaFile",
                                    filename=nombre_archivo_ejemplo,
                                    data=base64.b64encode(f.read()).decode("utf-8"),
                                )
                            audio_tag = f"<br>🔊 <b>Listen:</b> [sound:{nombre_archivo_ejemplo}]"
                        except:
                            pass
                        finally:
                            if os.path.exists(nombre_archivo_ejemplo):
                                os.remove(nombre_archivo_ejemplo)

                    if oracion_es_html:
                        texto_reverso_final += f"<br><br>{oracion_en_html}<br><i>{oracion_es_html}</i>{audio_tag}"
                    else:
                        texto_reverso_final += f"<br><br>{oracion_en_html}{audio_tag}"

            # 4. INYECTAR A ANKI
            try:
                invoke_anki(
                    "addNote",
                    note={
                        "deckName": mazo_destino,
                        "modelName": NOMBRE_TIPO_CARTA,
                        "fields": {
                            CAMPO_FRENTE: texto_frente_html,
                            CAMPO_REVERSO: texto_reverso_final,
                        },
                        "options": {"allowDuplicate": False},
                        "tags": ["generado_por_ia_python"],
                    },
                )
                cartas_agregadas += 1
            except Exception as e:
                if texto_ejemplo and "duplicate" in str(e).lower():
                    frente_alternativo = texto_ejemplo_html
                    reverso_alternativo = f"🎯 <b>Contexto original:</b> {texto_frente_html}<br><br>{texto_reverso_final}"
                    try:
                        invoke_anki(
                            "addNote",
                            note={
                                "deckName": mazo_destino,
                                "modelName": NOMBRE_TIPO_CARTA,
                                "fields": {
                                    CAMPO_FRENTE: frente_alternativo,
                                    CAMPO_REVERSO: reverso_alternativo,
                                },
                                "options": {"allowDuplicate": False},
                                "tags": ["generado_por_ia_python", "frase_contexto"],
                            },
                        )
                        cartas_agregadas += 1
                    except:
                        pass

        # Marcar mensajes como extraídos
        conn = sqlite3.connect("tutor.db")
        c = conn.cursor()
        c.execute(
            "UPDATE mensajes SET extraido = 1 WHERE chat_id = ? AND extraido = 0",
            (req.chat_id,),
        )
        conn.commit()
        conn.close()

        return {
            "mensaje": f"🎉 ¡Éxito! Se inyectaron {cartas_agregadas} cartas revisadas en tiempo récord gracias a la concurrencia."
        }

    except Exception as e:
        return {"mensaje": f"⚠️ Error en el procesamiento final: {str(e)}"}


# 9. Ruta de historias interactivas
@app.post("/generar_historia")
async def generar_historia(req: NuevaHistoria):
    # 1. Prompt para que Gemini devuelva un JSON perfecto
    prompt = f"""
    Eres un experto profesor de inglés. Crea una historia interesante y atractiva sobre el siguiente tema: "{req.tematica}".
    El nivel de inglés debe ser {req.nivel}.
    
    REGLA 1: La historia debe tener entre 8 y 12 oraciones en total.
    REGLA 2: Devuelve ESTRICTAMENTE un objeto JSON puro, sin formato markdown, ni bloques ```json.
    
    Formato esperado:
    {{
      "titulo": "Un título corto y atractivo en español",
      "lineas": [
        {{"en": "Oración en inglés aquí.", "es": "Traducción natural al español aquí."}},
        {{"en": "Siguiente oración en inglés.", "es": "Siguiente traducción."}}
      ]
    }}
    """

    try:
        # 2. Pedir la historia a Gemini
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=prompt
        )
        respuesta_limpia = (
            response.text.replace("```json", "").replace("```", "").strip()
        )
        datos_historia = json.loads(respuesta_limpia)

        titulo = datos_historia.get("titulo", "Historia sin título")
        lineas = datos_historia.get("lineas", [])

        if not lineas:
            return {"error": "No se pudieron generar las líneas de la historia."}

        # 3. Guardar la historia principal en la BDD para obtener su ID
        conn = sqlite3.connect("tutor.db")
        c = conn.cursor()
        c.execute(
            "INSERT INTO historias (titulo, tematica) VALUES (?, ?)",
            (titulo, req.tematica),
        )
        historia_id = c.lastrowid

        # 👇 NUEVO: Crear una subcarpeta específica para esta historia
        carpeta_historia = f"static/audios/historia_{historia_id}"
        os.makedirs(carpeta_historia, exist_ok=True)

        # 4. Generar audios de forma concurrente
        tareas_audio = []
        rutas_audios = []

        for i, linea in enumerate(lineas):
            texto_en = linea.get("en", "").strip()
            # Ruta única para cada audio dentro de la carpeta static
            ruta_audio = f"{carpeta_historia}/linea_{i}.mp3"
            rutas_audios.append(ruta_audio)

            # Agregamos a la lista de tareas concurrentes
            tareas_audio.append(generar_audio(texto_en, ruta_audio))

        # Ejecutar todos los audios al mismo tiempo
        if tareas_audio:
            await asyncio.gather(*tareas_audio)

        # 5. Guardar las líneas y sus rutas de audio en la BDD
        for i, linea in enumerate(lineas):
            c.execute(
                "INSERT INTO lineas_historia (historia_id, orden, oracion_en, oracion_es, ruta_audio) VALUES (?, ?, ?, ?, ?)",
                (
                    historia_id,
                    i,
                    linea.get("en", ""),
                    linea.get("es", ""),
                    rutas_audios[i],
                ),
            )

        conn.commit()
        conn.close()

        return {
            "mensaje": "Historia generada y audios creados con éxito.",
            "historia_id": historia_id,
            "titulo": titulo,
        }

    except Exception as e:
        return {"error": f"Error al generar la historia: {str(e)}"}


# 1. Pagina html de las historias
@app.get("/historias", response_class=HTMLResponse)
def pagina_historias(request: Request):
    return templates.TemplateResponse(request=request, name="historias.html")


# 2. Obtiene las líneas y audios de una historia específica
@app.get("/api/historias/{historia_id}")
def obtener_detalles_historia(historia_id: int):
    conn = sqlite3.connect("tutor.db")
    c = conn.cursor()
    c.execute(
        "SELECT orden, oracion_en, oracion_es, ruta_audio FROM lineas_historia WHERE historia_id = ? ORDER BY orden ASC",
        (historia_id,),
    )
    # Importante: Agregamos el "/" al inicio de la ruta del audio para que el HTML lo encuentre bien
    lineas = [
        {"orden": row[0], "en": row[1], "es": row[2], "audio": f"/{row[3]}"}
        for row in c.fetchall()
    ]
    conn.close()
    return {"lineas": lineas}


# 3. Obtener la lista de historias creadas para la barra lateral
@app.get("/api/lista_historias")
def obtener_lista_historias():
    conn = sqlite3.connect("tutor.db")
    c = conn.cursor()
    c.execute("SELECT id, titulo FROM historias ORDER BY id DESC")
    historias = [{"id": row[0], "titulo": row[1]} for row in c.fetchall()]
    conn.close()
    return historias


# 4. Proponer una carta única para un término específico
@app.post("/proponer_carta_unica")
def proponer_carta_unica(req: CartaUnicaRequest):
    prompt = f"""
    Eres un creador de flashcards experto. El alumno no conoce el término "{req.palabra}" que leyó en la siguiente oración: "{req.contexto}".
    Crea UNA SOLA flashcard perfecta para este término, explicando su significado dentro de ese contexto específico.
    
    REGLA 1: Devuelve ESTRICTAMENTE un arreglo JSON puro de un solo elemento, sin formato markdown ni bloques ```json.
    Formato esperado:
    [
      {{
        "frente": "Palabra o concepto",
        "reverso": "Definición básica en español",
        "ejemplo_ingles": "Oración de ejemplo en inglés.",
        "ejemplo_espanol": "Traducción natural de la oración.",
        "termino_imagen": "Palabra clave visual en inglés",
        "categoria": "ELIGE_UNA_CATEGORIA"
      }}
    ]
    REGLA 2: El campo "categoria" DEBE ser ESTRICTAMENTE una de las siguientes: Vocabulario, Phrasal Verbs, Falsos Amigos, Verbos Irregulares, Gramatica y Teoria, Expresiones Nativas, Colocaciones, Otros.
    REGLA 3 (VERBOS): Si es un verbo, crea ejemplos según su tipo (2 si es regular, 3 si es irregular). Separa cada ejemplo usando " | ".
    REGLA 4 (PHRASAL VERBS): Si es phrasal verb, añade su tipo entre paréntesis en el frente, enumera significados en el reverso, y da un ejemplo por cada significado, separados por " | ".
    REGLA 5 (IMÁGENES): "termino_imagen" NUNCA debe estar vacío. Usa palabras abstractas en inglés si es necesario.
    REGLA 6 : Si el término tiene múltiples significados, crea un ejemplo en inglés y su traducción al español para cada significado, separados por " | ".
    REGLA 7: Siempre incluye como minimo 2 ejemplos.
    """

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=prompt
        )
        respuesta_limpia = (
            response.text.replace("```json", "").replace("```", "").strip()
        )

        datos_brutos = json.loads(respuesta_limpia)
        if isinstance(datos_brutos, dict):
            lista_cartas = next(
                (v for v in datos_brutos.values() if isinstance(v, list)), []
            )
        else:
            lista_cartas = datos_brutos if isinstance(datos_brutos, list) else []

        return {"cartas": lista_cartas}
    except Exception as e:
        return {"error": f"Error al generar propuesta: {str(e)}"}


# ==========================================
# 🗣️ RUTAS DE LABORATORIO DE PRONUNCIACIÓN
# ==========================================


# 1. Servir la vista HTML
@app.get("/fonetica", response_class=HTMLResponse)
def pagina_fonetica(request: Request):
    return templates.TemplateResponse(request=request, name="fonetica.html")


# 2. Base de datos estática de los 44 fonemas del inglés (Con transcripción IPA)
@app.get("/api/fonemas")
def obtener_fonemas():
    fonemas_prioritarios = [
        # --- VOCALES (12) ---
        {"id": "schwa", "simbolo": "/ə/", "nombre": "El Schwa (Sonido Rey)", "desc": "Relaja TODA la boca y la lengua. No muevas los labios. Haz un sonido corto y gutural desde la garganta.", "ejemplos": ["about (/əˈbaʊt/)", "taken (/ˈteɪkən/)", "pencil (/ˈpɛnsəl/)"]},
        {"id": "i_corta", "simbolo": "/ɪ/", "nombre": "La 'i' Corta", "desc": "Boca relajada, un poco abierta. NO sonrías. Suena a medio camino entre tu 'e' y tu 'i'.", "ejemplos": ["ship (/ʃɪp/)", "sit (/sɪt/)", "kid (/kɪd/)"]},
        {"id": "i_larga", "simbolo": "/iː/", "nombre": "La 'i' Larga", "desc": "Estira los labios tensándolos como si sonrieras grande. Tensa la lengua hacia arriba y adelante.", "ejemplos": ["sheep (/ʃiːp/)", "seat (/siːt/)", "key (/kiː/)"]},
        {"id": "u_corta", "simbolo": "/ʊ/", "nombre": "La 'u' Corta", "desc": "Labios ligeramente redondeados pero muy relajados (no apretados). Lengua hacia atrás.", "ejemplos": ["book (/bʊk/)", "put (/pʊt/)", "good (/ɡʊd/)"]},
        {"id": "u_larga", "simbolo": "/uː/", "nombre": "La 'u' Larga", "desc": "Haz un círculo pequeño y muy apretado con los labios (como para soplar una vela). Tensa la boca.", "ejemplos": ["blue (/bluː/)", "food (/fuːd/)", "shoe (/ʃuː/)"]},
        {"id": "e_corta", "simbolo": "/e/", "nombre": "La 'e' Corta", "desc": "Abre la boca un poco más, labios relajados, lengua en el centro. (Igual a la 'e' de España).", "ejemplos": ["bed (/bɛd/)", "red (/rɛd/)", "head (/hɛd/)"]},
        {"id": "schwa_largo", "simbolo": "/ɜː/", "nombre": "El Schwa Largo", "desc": "Boca entreabierta y relajada, lengua plana. Haz vibrar la garganta de forma alargada.", "ejemplos": ["bird (/bɜːrd/)", "work (/wɜːrk/)", "learn (/lɜːrn/)"]},
        {"id": "o_larga", "simbolo": "/ɔː/", "nombre": "La 'o' Larga", "desc": "Abre la boca formando una 'O' vertical alta, tensa los labios. Lengua plana y atrás.", "ejemplos": ["door (/dɔːr/)", "more (/mɔːr/)", "board (/bɔːrd/)"]},
        {"id": "a_gato", "simbolo": "/æ/", "nombre": "La 'A' Abierta", "desc": "Boca ABIERTA hacia abajo al máximo. Estira los labios a los lados y empuja la lengua hacia adelante. Intenta decir 'a' pero sonando a 'e'.", "ejemplos": ["cat (/kæt/)", "black (/blæk/)", "map (/mæp/)"]},
        {"id": "a_neutra", "simbolo": "/ʌ/", "nombre": "La 'a' Neutra", "desc": "Boca semiabierta. Lengua relajada. Da un golpe de sonido corto y seco desde la garganta.", "ejemplos": ["cup (/kʌp/)", "luck (/lʌk/)", "blood (/blʌd/)"]},
        {"id": "a_larga", "simbolo": "/ɑː/", "nombre": "La 'a' Larga", "desc": "Abre la boca al máximo (como en el dentista). Lengua totalmente plana abajo. Sonido largo.", "ejemplos": ["car (/kɑːr/)", "father (/ˈfɑːðər/)", "star (/stɑːr/)"]},
        {"id": "o_corta", "simbolo": "/ɒ/", "nombre": "La 'o' Corta", "desc": "Labios en forma redonda pero con la mandíbula caída muy abierta. Golpe de voz corto.", "ejemplos": ["hot (/hɒt/)", "box (/bɒks/)", "stop (/stɒp/)"]},

        # --- DIPTONGOS (8) ---
        {"id": "dip_ei", "simbolo": "/eɪ/", "nombre": "Diptongo EI", "desc": "Empieza con boca abierta relajada y ciérrala estirando a una sonrisa tensa.", "ejemplos": ["day (/deɪ/)", "say (/seɪ/)", "make (/meɪk/)"]},
        {"id": "dip_ai", "simbolo": "/aɪ/", "nombre": "Diptongo AI", "desc": "Abre la boca en grande y deslízala cerrando hacia una sonrisa tensa.", "ejemplos": ["my (/maɪ/)", "eye (/aɪ/)", "time (/taɪm/)"]},
        {"id": "dip_oi", "simbolo": "/ɔɪ/", "nombre": "Diptongo OI", "desc": "Empieza con labios en 'O' redonda y desliza hacia una sonrisa estirada.", "ejemplos": ["boy (/bɔɪ/)", "toy (/tɔɪ/)", "coin (/kɔɪn/)"]},
        {"id": "dip_au", "simbolo": "/aʊ/", "nombre": "Diptongo AU", "desc": "Abre la boca en grande y ciérrala haciendo un círculo apretado con los labios.", "ejemplos": ["now (/naʊ/)", "how (/haʊ/)", "house (/haʊs/)"]},
        {"id": "dip_ou", "simbolo": "/oʊ/", "nombre": "Diptongo OU", "desc": "Haz una 'O' relajada y aprieta los labios hasta hacer un círculo pequeñito.", "ejemplos": ["go (/ɡoʊ/)", "no (/noʊ/)", "show (/ʃoʊ/)"]},
        {"id": "dip_ia", "simbolo": "/ɪə/", "nombre": "Diptongo IA", "desc": "Empieza con sonrisa relajada y suelta la tensión volviendo al centro (Schwa).", "ejemplos": ["here (/hɪər/)", "near (/nɪər/)", "idea (/aɪˈdɪə/)"]},
        {"id": "dip_ea", "simbolo": "/eə/", "nombre": "Diptongo EA", "desc": "Empieza con boca entreabierta y relaja toda la boca volviendo al centro (Schwa).", "ejemplos": ["hair (/heər/)", "there (/ðeər/)", "care (/keər/)"]},
        {"id": "dip_ua", "simbolo": "/ʊə/", "nombre": "Diptongo UA", "desc": "Empieza con labios redondeados y relájalos completamente (Schwa).", "ejemplos": ["tour (/tʊər/)", "pure (/pjʊər/)", "cure (/kjʊər/)"]},

        # --- CONSONANTES (24) ---
        {"id": "p_fuerte", "simbolo": "/p/", "nombre": "La 'P' Explosiva", "desc": "Junta los labios apretados. Suelta el aire de golpe estallando. SIN vibrar la garganta.", "ejemplos": ["pen (/pɛn/)", "top (/tɒp/)", "push (/pʊʃ/)"]},
        {"id": "b_fuerte", "simbolo": "/b/", "nombre": "La 'B' Fuerte", "desc": "Junta los labios. Suelta el aire de golpe, pero HACIENDO VIBRAR la garganta.", "ejemplos": ["berry (/ˈbɛri/)", "bowel (/ˈbaʊəl/)", "back (/bæk/)"]},
        {"id": "t_fuerte", "simbolo": "/t/", "nombre": "La 'T' Explosiva", "desc": "Punta de la lengua justo detrás de los dientes superiores. Estalla el aire. SIN vibrar.", "ejemplos": ["time (/taɪm/)", "cat (/kæt/)", "tell (/tɛl/)"]},
        {"id": "d_fuerte", "simbolo": "/d/", "nombre": "La 'D' Fuerte", "desc": "Lengua detrás de los dientes superiores. Suelta el aire VIBRANDO la garganta.", "ejemplos": ["dog (/dɒɡ/)", "day (/deɪ/)", "bed (/bɛd/)"]},
        {"id": "k_fuerte", "simbolo": "/k/", "nombre": "La 'K' Fuerte", "desc": "Sube la parte de atrás de la lengua para bloquear la garganta. Estalla el aire. SIN vibrar.", "ejemplos": ["cat (/kæt/)", "key (/kiː/)", "back (/bæk/)"]},
        {"id": "g_fuerte", "simbolo": "/g/", "nombre": "La 'G' Fuerte", "desc": "Igual que la /k/, pero VIBRANDO fuertemente la garganta.", "ejemplos": ["go (/ɡoʊ/)", "get (/ɡɛt/)", "big (/bɪɡ/)"]},
        {"id": "f_suave", "simbolo": "/f/", "nombre": "La 'F'", "desc": "Apoya los dientes superiores sobre tu labio inferior. Sopla aire. SIN vibrar.", "ejemplos": ["fly (/flaɪ/)", "four (/fɔːr/)", "leaf (/liːf/)"]},
        {"id": "v_labio", "simbolo": "/v/", "nombre": "La 'V' Vibrante", "desc": "Dientes superiores sobre labio inferior. Sopla aire y VIBRA la garganta fuerte (cosquillas en el labio).", "ejemplos": ["very (/ˈvɛri/)", "vowel (/ˈvaʊəl/)", "save (/seɪv/)"]},
        {"id": "th_sordo", "simbolo": "/θ/", "nombre": "El 'TH' Sordo", "desc": "Saca la punta de la lengua entre los dientes. Sopla aire continuo. SIN vibrar la garganta.", "ejemplos": ["think (/θɪŋk/)", "math (/mæθ/)", "both (/boʊθ/)"]},
        {"id": "th_sonoro", "simbolo": "/ð/", "nombre": "El 'TH' Vibrante", "desc": "Lengua entre los dientes. Sopla aire y VIBRA la garganta (se siente como un zumbido de abeja).", "ejemplos": ["this (/ðɪs/)", "mother (/ˈmʌðər/)", "breathe (/briːð/)"]},
        {"id": "s_suave", "simbolo": "/s/", "nombre": "La 'S' Suave", "desc": "Junta los dientes, lengua detrás. Sopla aire siseando. SIN vibrar.", "ejemplos": ["sue (/suː/)", "bus (/bʌs/)", "face (/feɪs/)"]},
        {"id": "z_vibra", "simbolo": "/z/", "nombre": "La 'Z' de Abeja", "desc": "Junta los dientes. Sopla aire y VIBRA la garganta fuerte (imita a una mosca/abeja).", "ejemplos": ["zoo (/zuː/)", "buzz (/bʌz/)", "phase (/feɪz/)"]},
        {"id": "sh_silencio", "simbolo": "/ʃ/", "nombre": "El sonido 'SH'", "desc": "Empuja los labios hacia afuera (como pidiendo silencio 'shhh'). Sopla aire. SIN vibrar.", "ejemplos": ["she (/ʃiː/)", "shoe (/ʃuː/)", "crash (/kræʃ/)"]},
        {"id": "zh_suave", "simbolo": "/ʒ/", "nombre": "La 'SH' Vibrante", "desc": "Labios hacia afuera como 'shhh', pero VIBRANDO la garganta (como un motor).", "ejemplos": ["measure (/ˈmɛʒər/)", "vision (/ˈvɪʒən/)", "television (/ˈtɛlɪvɪʒən/)"]},
        {"id": "h_aire", "simbolo": "/h/", "nombre": "La 'H' Aspirada", "desc": "Abre la boca relajada y exhala aire desde el fondo (como empañando un espejo). SIN raspar.", "ejemplos": ["hat (/hæt/)", "home (/hoʊm/)", "hello (/həˈloʊ/)"]},
        {"id": "ch_fuerte", "simbolo": "/tʃ/", "nombre": "El sonido 'CH'", "desc": "Empieza con la lengua tocando el paladar (T) y explota hacia afuera con labios redondos (SH).", "ejemplos": ["chair (/tʃeər/)", "cheese (/tʃiːz/)", "match (/mætʃ/)"]},
        {"id": "j_fuerte", "simbolo": "/dʒ/", "nombre": "La 'J' Inglesa", "desc": "Igual que CH, pero VIBRANDO la garganta. Suena fuerte y golpeado.", "ejemplos": ["job (/dʒɒb/)", "juice (/dʒuːs/)", "age (/eɪdʒ/)"]},
        {"id": "m_nasal", "simbolo": "/m/", "nombre": "La 'M' Nasal", "desc": "Junta los labios. No sueltes aire por la boca, sácalo por la nariz y VIBRA la garganta.", "ejemplos": ["man (/mæn/)", "make (/meɪk/)", "time (/taɪm/)"]},
        {"id": "n_nasal", "simbolo": "/n/", "nombre": "La 'N' Nasal", "desc": "Lengua presionando detrás de los dientes de arriba. Aire por la nariz y VIBRA.", "ejemplos": ["no (/noʊ/)", "name (/neɪm/)", "sun (/sʌn/)"]},
        {"id": "ng_nasal", "simbolo": "/ŋ/", "nombre": "La 'NG' Nasal", "desc": "Parte de atrás de la lengua sube y bloquea la garganta. Aire por la nariz y VIBRA.", "ejemplos": ["sing (/sɪŋ/)", "king (/kɪŋ/)", "ring (/rɪŋ/)"]},
        {"id": "l_lateral", "simbolo": "/l/", "nombre": "La 'L'", "desc": "Punta de la lengua firme contra el paladar. Deja que el aire escape por los lados de la lengua.", "ejemplos": ["leg (/lɛɡ/)", "love (/lʌv/)", "feel (/fiːl/)"]},
        {"id": "r_suave", "simbolo": "/r/", "nombre": "La 'R' Inglesa", "desc": "Tira la lengua hacia ATRÁS sin tocar el paladar en absoluto. Redondea los labios. VIBRA.", "ejemplos": ["red (/rɛd/)", "run (/rʌn/)", "car (/kɑːr/)"]},
        {"id": "w_desliza", "simbolo": "/w/", "nombre": "La 'W'", "desc": "Círculo pequeño y tenso con los labios. Desliza rápido hacia el siguiente sonido vocal.", "ejemplos": ["we (/wiː/)", "water (/ˈwɔːtər/)", "win (/wɪn/)"]},
        {"id": "y_desliza", "simbolo": "/j/", "nombre": "La 'Y'", "desc": "Lengua arriba casi tocando el paladar (como sonriendo tensamente). Desliza rápido a la vocal.", "ejemplos": ["yes (/jɛs/)", "yellow (/ˈjɛloʊ/)", "you (/juː/)"]}
    ]
    return fonemas_prioritarios

# 2.5 Base de datos estática de Reglas de Connected Speech
@app.get("/api/connected_speech")
def obtener_connected_speech():
    reglas = [
        {"id": "assim_t", "regla": "T + Y = CH", "nombre": "Asimilación de la T", "desc": "Cuando una palabra termina en sonido /t/ y la siguiente empieza con /j/ (y), se fusionan en CH.", "ejemplos": ["Don't you (Donchu)", "Let you (Lechu)", "Meet you (Meechu)"]},
        {"id": "assim_d", "regla": "D + Y = J", "nombre": "Asimilación de la D", "desc": "Cuando una palabra termina en sonido /d/ y la siguiente empieza con /j/ (y), se fusionan en la J inglesa vibrante.", "ejemplos": ["Did you (Didja)", "Would you (Woulja)", "Find you (Finja)"]},
        {"id": "flap_t", "regla": "La Flap 'T'", "nombre": "La 'T' Americana", "desc": "En USA, cuando una 't' o 'tt' queda atrapada entre dos sonidos vocales, se pronuncia como una 'r' suave y rápida.", "ejemplos": ["Water (Wader)", "Better (Beder)", "City (Cidy)"]},
        {"id": "elision_h", "regla": "Adiós a la 'H'", "nombre": "Elisión de Pronombres", "desc": "La 'h' inicial en him, her, he, his a menudo desaparece al hablar rápido porque el aire no se detiene.", "ejemplos": ["Tell him (Tellim)", "Call her (Caller)", "I like his (I likis)"]},
        {"id": "link_cv", "regla": "Consonante + Vocal", "nombre": "Linking C-V", "desc": "Si una palabra termina en consonante y la otra empieza en vocal, se unen como si fueran una sola palabra larga.", "ejemplos": ["Stop it (Sto pit)", "Not at all (No ta tall)", "An apple (A napple)"]},
        {"id": "reductions", "regla": "Reducciones", "nombre": "Palabras Perezosas", "desc": "Palabras estructurales (to, for, and, of) se relajan tanto que se convierten en un simple Schwa.", "ejemplos": ["Rock and roll (Rock n roll)", "Going to (Gonna)", "Want to (Wanna)"]}
    ]
    return reglas

# 3. El Motor del "Gimnasio" (Minijuego de Pares Mínimos)
@app.post("/api/entrenar_pares")
async def entrenar_pares(req: EntrenamientoPares):
    prompt = f"""
    Eres un experto en fonética inglesa. El alumno hispanohablante confunde los fonemas {req.fonema_1} y {req.fonema_2}.
    Genera EXACTAMENTE 4 pares mínimos que contrasten ambos sonidos. 
    IMPORTANTE: La clave "correcta" debe contener ESTRICTAMENTE el texto "opcion_a" o "opcion_b", no la palabra.
    
    Devuelve ESTRICTAMENTE un arreglo JSON puro, sin comillas triples ni formato markdown.
    Formato:
    [
      {{"opcion_a": "ship", "opcion_b": "sheep", "correcta": "opcion_a"}},
      {{"opcion_a": "eat", "opcion_b": "it", "correcta": "opcion_b"}}
    ]
    """
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=prompt
        )

        # 1. Limpieza ultra-agresiva por si Gemini añade formato Markdown
        texto = response.text.strip()
        if texto.startswith("```json"):
            texto = texto[7:]
        if texto.startswith("```"):
            texto = texto[3:]
        if texto.endswith("```"):
            texto = texto[:-3]

        respuesta_limpia = texto.strip()
        pares = json.loads(respuesta_limpia)

        os.makedirs("static/audios/fonetica", exist_ok=True)
        tareas_audio = []

        for i, par in enumerate(pares):
            # 2. Blindaje: ¿Qué pasa si Gemini puso "ship" en lugar de "opcion_a"?
            valor_correcta = str(par.get("correcta", "opcion_a")).lower()

            if valor_correcta in ["opcion_a", "opcion_b"]:
                palabra_correcta = par.get(valor_correcta, "error")
            else:
                # Si se equivocó, asumimos que escribió la palabra directamente y lo autocorregimos
                palabra_correcta = valor_correcta
                if par.get("opcion_a", "").lower() == palabra_correcta.lower():
                    par["correcta"] = "opcion_a"
                else:
                    par["correcta"] = "opcion_b"

            # 3. Limpiar caracteres raros en el nombre del archivo para evitar errores de Windows/Mac
            nombre_limpio = "".join(c if c.isalnum() else "_" for c in palabra_correcta)
            ruta_audio = f"static/audios/fonetica/par_{i}_{nombre_limpio}.mp3"
            par["ruta_audio"] = ruta_audio

            # Generamos el audio
            tareas_audio.append(generar_audio(palabra_correcta, ruta_audio))

        if tareas_audio:
            await asyncio.gather(*tareas_audio)

        return {"pares": pares}

    except Exception as e:
        # Esto imprimirá el error real en tu consola negra (uvicorn)
        print(f"🚨 ERROR EN EL BACKEND: {str(e)}")
        return {"error": f"Error interno: {str(e)}"}



# uvicorn main:app --reload
