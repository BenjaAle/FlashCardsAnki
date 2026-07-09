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
    conn.commit()
    conn.close()


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


# Toma las cartas propuestas y las inyecta a Anki, generando audios e imágenes en paralelo
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
            nombre_limpio = "".join(c if c.isalnum() else "_" for c in texto_frente[:15])

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
                tareas_audio.append(generar_audio(texto_audio_frente, nombre_archivo_frente))

            # 2. Preparar audios de los Ejemplos Múltiples
            texto_ejemplo = str(carta.get("ejemplo_ingles", "")).strip()
            if texto_ejemplo:
                oraciones_en = [o.strip() for o in texto_ejemplo.split("|") if o.strip()]
                for j, oracion_en in enumerate(oraciones_en):
                    texto_audio_ejemplo = oracion_en.replace("**", "").replace("*", "").strip()
                    nombre_archivo_ejemplo = f"ia_audio_ejemplo_{nombre_limpio}_{i}_{j}.mp3"
                    if texto_audio_ejemplo:
                        # Agregamos la corrutina a la lista de tareas
                        tareas_audio.append(generar_audio(texto_audio_ejemplo, nombre_archivo_ejemplo))

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
                "Vocabulario", "Phrasal Verbs", "Falsos Amigos", 
                "Verbos Irregulares", "Gramatica y Teoria", 
                "Expresiones Nativas", "Colocaciones", "Otros"
            ]
            if categoria_elegida not in categorias_validas:
                categoria_elegida = "Otros"

            mazo_destino = f"{NOMBRE_MAZO}::{categoria_elegida}"

            try:
                invoke_anki("createDeck", deck=mazo_destino)
            except:
                pass

            nombre_limpio = "".join(c if c.isalnum() else "_" for c in texto_frente[:15])

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
                            texto_reverso_final = f"<img src='{nombre_archivo_img}'><br><br>" + texto_reverso_final
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
                oraciones_en = [o.strip() for o in texto_ejemplo.split("|") if o.strip()]
                oraciones_es = [o.strip() for o in traduccion_ejemplo.split("|") if o.strip()] if traduccion_ejemplo else []

                if traduccion_ejemplo and len(oraciones_en) != len(oraciones_es):
                    oraciones_en = [texto_ejemplo.replace("|", "")]
                    oraciones_es = [traduccion_ejemplo.replace("|", "")]

                for j, oracion_en in enumerate(oraciones_en):
                    oracion_en_html = md_a_html(oracion_en)
                    oracion_es_html = md_a_html(oraciones_es[j]) if j < len(oraciones_es) else ""
                    nombre_archivo_ejemplo = f"ia_audio_ejemplo_{nombre_limpio}_{i}_{j}.mp3"
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
        c.execute("UPDATE mensajes SET extraido = 1 WHERE chat_id = ? AND extraido = 0", (req.chat_id,))
        conn.commit()
        conn.close()

        return {"mensaje": f"🎉 ¡Éxito! Se inyectaron {cartas_agregadas} cartas revisadas en tiempo récord gracias a la concurrencia."}

    except Exception as e:
        return {"mensaje": f"⚠️ Error en el procesamiento final: {str(e)}"}


# uvicorn main:app --reload
