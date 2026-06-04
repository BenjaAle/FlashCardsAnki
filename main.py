import os
import json
import urllib.request
import base64
import re
import requests
import sqlite3  # 👈 ¡Nueva importación para la Base de Datos!
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from google import genai
from google.genai import types  # 👈 Para estructurar el historial
from gtts import gTTS

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


# ==========================================
# 🗄️ INICIALIZACIÓN DE LA BASE DE DATOS
# ==========================================
def iniciar_bd():
    conn = sqlite3.connect("tutor.db")
    c = conn.cursor()
    # Tabla para guardar las sesiones de chat (barra lateral)
    c.execute(
        """CREATE TABLE IF NOT EXISTS chats (id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT)"""
    )
    # Tabla para guardar los mensajes de cada chat (extraidos para memoria y extracción a Anki)
    c.execute(
        """CREATE TABLE IF NOT EXISTS mensajes (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, rol TEXT, texto TEXT, extraido INTEGER DEFAULT 0)"""
    )
    conn.commit()
    conn.close()


iniciar_bd()  # Creamos el archivo tutor.db si no existe

# ==========================================
# 🚀 CONFIGURACIÓN DE FASTAPI
# ==========================================
app = FastAPI(title="Tutor de Inglés con IA")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# Estructuras de datos que recibiremos del navegador
class Mensaje(BaseModel):
    texto: str
    chat_id: int  # 👈 Ahora necesitamos saber en qué chat estamos hablando


class NuevoChat(BaseModel):
    titulo: str


class ExtraerRequest(BaseModel):
    chat_id: int


# ==========================================
# 🔌 FUNCIONES DE ANKI
# ==========================================
def request_anki(action, **params):
    return {"action": action, "version": 6, "params": params}


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
    c.execute("INSERT INTO chats (titulo) VALUES (?)", (datos.titulo,))
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


# 3. Obtener los mensajes antiguos de un chat específico
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


# 4. El motor de conversación con memoria real
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
            "SELECT rol, texto FROM mensajes WHERE chat_id = ? ORDER BY id ASC",
            (mensaje.chat_id,),
        )
        historial_bd = c.fetchall()

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


# 5. Extraer cartas a Anki leyendo directamente de la Base de Datos
@app.post("/extraer")
def extraer_anki(req: ExtraerRequest):
    conn = sqlite3.connect("tutor.db")
    c = conn.cursor()
    c.execute(
        "SELECT id, rol, texto FROM mensajes WHERE chat_id = ? AND extraido = 0 ORDER BY id ASC",
        (req.chat_id,),
    )
    historial_bd = c.fetchall()
    conn.close()

    if not historial_bd:
        return {
            "mensaje": "⚠️ No hay conversación aún para extraer. ¡Hablemos primero!"
        }

    # Convertimos la base de datos a texto para el Prompt
    historial_texto = ""
    # Recolectamos los IDs para marcarlos como extraídos después
    ids_mensajes = []
    for msg_id, rol, texto in historial_bd:
        quien = "Alumno" if rol == "user" else "Tutor"
        historial_texto += f"{quien}: {texto}\n\n"

    prompt = f"""
    Eres un creador de flashcards experto. Analiza el siguiente historial de conversación entre un alumno y su tutor de inglés.
    REGLA 1: Extrae ÚNICAMENTE el vocabulario útil, phrasal verbs, o correcciones clave. Si no hay nada útil, devuelve []
    REGLA 2: Devuelve ESTRICTAMENTE un arreglo JSON puro sin formato markdown.
    Formato esperado:
    [
      {{
        "frente": "Palabra o concepto",
        "reverso": "Definición en HTML",
        "ejemplo_ingles": "Oración de ejemplo en inglés.",
        "termino_imagen": "Palabra clave visual en inglés o vacío.",
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

    REGLA 4: El campo "reverso" DEBE contener obligatoriamente:
    1. El significado en español (destaca lo importante con <b>).
    2. La oración de ejemplo en inglés completa.
    3. La traducción de esa oración al español (en <i>).
    IMPORTANTE PARA EL FORMATO: Usa obligatoriamente una doble línea en blanco (<br><br>) para separar la definición inicial de los ejemplos, y también para separar un ejemplo de otro. Usa una sola línea (<br>) ÚNICAMENTE para separar la oración en inglés de su propia traducción al español.

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

        if not lista_cartas:
            return {
                "mensaje": "🤷‍♂️ No encontré vocabulario nuevo en esta charla para crear cartas."
            }

        cartas_agregadas = 0
        for i, carta in enumerate(lista_cartas):
            texto_frente = str(carta.get("frente", "")).strip()
            texto_reverso = str(carta.get("reverso", "")).strip()
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
                            texto_reverso = (
                                f"<img src='{nombre_archivo_img}'><br><br>"
                                + texto_reverso
                            )
                except:
                    pass

            nombre_archivo_frente = f"ia_audio_frente_{nombre_limpio}_{i}.mp3"
            try:
                texto_audio_frente = re.sub(r"\(.*?\)", "", texto_frente).strip()
                gTTS(texto_audio_frente, lang="en").save(nombre_archivo_frente)
                with open(nombre_archivo_frente, "rb") as f:
                    invoke_anki(
                        "storeMediaFile",
                        filename=nombre_archivo_frente,
                        data=base64.b64encode(f.read()).decode("utf-8"),
                    )
                texto_frente += f" [sound:{nombre_archivo_frente}]"
            except:
                pass
            finally:
                if os.path.exists(nombre_archivo_frente):
                    os.remove(nombre_archivo_frente)

            if texto_ejemplo:
                nombre_archivo_ejemplo = f"ia_audio_ejemplo_{nombre_limpio}_{i}.mp3"
                try:
                    gTTS(texto_ejemplo, lang="en").save(nombre_archivo_ejemplo)
                    with open(nombre_archivo_ejemplo, "rb") as f:
                        invoke_anki(
                            "storeMediaFile",
                            filename=nombre_archivo_ejemplo,
                            data=base64.b64encode(f.read()).decode("utf-8"),
                        )
                    texto_reverso += (
                        f"<br><br>🔊 <b>Listen:</b> [sound:{nombre_archivo_ejemplo}]"
                    )
                except:
                    pass
                finally:
                    if os.path.exists(nombre_archivo_ejemplo):
                        os.remove(nombre_archivo_ejemplo)

            try:
                invoke_anki(
                    "addNote",
                    note={
                        "deckName": mazo_destino,
                        "modelName": NOMBRE_TIPO_CARTA,
                        "fields": {
                            CAMPO_FRENTE: texto_frente,
                            CAMPO_REVERSO: texto_reverso,
                        },
                        "options": {"allowDuplicate": False},
                        "tags": ["generado_por_ia_python"],
                    },
                )
                cartas_agregadas += 1
            except:
                pass

        for msg_id in ids_mensajes:
            c.execute("UPDATE mensajes SET extraido = 1 WHERE id = ?", (msg_id,))
        conn.commit()
        conn.close()

        return {
            "mensaje": f"🎉 ¡Éxito! Se inyectaron {cartas_agregadas} cartas organizadas en sus submazos."
        }

    # 🌟 NUEVO: Si llegamos hasta aquí, marcamos esos mensajes específicos como extraídos (1)
    except Exception as e:
        if "conn" in locals():
            conn.close()
        return {"mensaje": f"⚠️ Error en el procesamiento: {str(e)}"}


# uvicorn main:app --reload
