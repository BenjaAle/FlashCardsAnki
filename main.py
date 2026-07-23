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
from dotenv import load_dotenv
from google import genai  # Comunicacion con gemini
from google.genai import types  # Memoria de chat
import edge_tts
from models import (
    CartaUnicaRequest,
    EntrenamientoPares,
    ExtraerRequest,
    InyectarRequest,
    Mensaje,
    NuevoChat,
    NuevaHistoria,
    RenombrarRequest,
)

# ==========================================
# ⚙️ CONFIGURACIÓN GENERAL
# ==========================================
NOMBRE_MAZO = "Ingles_IA"
NOMBRE_TIPO_CARTA = "Basic"
CAMPO_FRENTE = "Front"
CAMPO_REVERSO = "Back"
GEMINI_MODEL = "gemini-2.5-flash"
# Otras opciones son:

# GEMINI_MODEL = "gemini-2.5-pro"
# GEMINI_MODEL = "gemini-1.5-pro"

load_dotenv()
api_key_gemini = os.getenv("GEMINI_API_KEY")
api_key_pexels = os.getenv("PEXELS_API_KEY")

if not api_key_gemini or not api_key_pexels:
    raise ValueError(
        "❌ Falla: Revisa que GEMINI_API_KEY y PEXELS_API_KEY estén en tu .env"
    )

client = genai.Client(api_key=api_key_gemini)


VOCAL_TTS = "en-US-AvaNeural"


# Podria usar edge_tts.Communicate(texto, voz, rate="-10%") por si quiero menos velocidad
async def generar_audio(texto, nombre_archivo, voz=VOCAL_TTS):
    comunicacion = edge_tts.Communicate(texto, voz, rate="-5%")
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
    # id, titulo del chat
    c.execute(
        """CREATE TABLE IF NOT EXISTS chats (id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT)"""
    )
    # Tabla para guardar los mensajes de cada chat (extraidos para memoria y extracción a Anki)
    # rol: yo o IA. extraido: 0 = no extraido, 1 = ya extraido a Anki
    # id, chat_id, rol, texto, extraido
    c.execute(
        """CREATE TABLE IF NOT EXISTS mensajes (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, rol TEXT, texto TEXT, extraido INTEGER DEFAULT 0)"""
    )

    # Tabla para guardar historias
    # id, titulo (lo pone la IA), tematica (la que le doy yo)
    c.execute(
        """CREATE TABLE IF NOT EXISTS historias (id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT, tematica TEXT)"""
    )

    # Tabla para guardar las líneas de cada historia
    # id, historia_id, orden (0,1,2...), oracion_en, oracion_es, ruta_audio
    c.execute("""CREATE TABLE IF NOT EXISTS lineas_historia (
                 id INTEGER PRIMARY KEY AUTOINCREMENT, 
                 historia_id INTEGER, 
                 orden INTEGER, 
                 oracion_en TEXT, 
                 oracion_es TEXT, 
                 ruta_audio TEXT)""")

    # Se agrega la columna oracion_ipa
    try:
        c.execute("ALTER TABLE lineas_historia ADD COLUMN oracion_ipa TEXT")
    except sqlite3.OperationalError:
        pass  # Si la columna ya existe, simplemente ignora el error
    
    # Tabla para destacar las palabras extraidas de las historias.
    c.execute('''CREATE TABLE IF NOT EXISTS vocabulario_anki (
                    palabra TEXT UNIQUE COLLATE NOCASE
                )''')

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

    # Ejemplo: [{"id": 1, "titulo": "Chat 1"}, {"id": 2, "titulo": "Chat 2"}]
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
    
    # fetchall() devuelve la lista de tuplas (rol, texto)
    mensajes = [{"rol": row[0], "texto": row[1]} for row in c.fetchall()]
    conn.close()
    return mensajes


# 6. El motor de conversación con memoria
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

        # B) Reconstruimos la memoria para Gemini, leyendo la base de datos
        c.execute(
            "SELECT rol, texto FROM mensajes WHERE chat_id = ? ORDER BY id DESC LIMIT 15",
            (mensaje.chat_id,),
        )
        historial_bd = c.fetchall()
        
        # Los invertimos para que queden en orden cronológico correcto (del más viejo al más nuevo)
        historial_bd.reverse()  

        historial_gemini = []
        # Pasamos todos los mensajes menos el último (que es el que enviaremos ahora, para que no lo lea 2 veces)
        for rol, texto in historial_bd[:-1]:
            
            # gemini pide roles "user" o "model", mientras que en la BDD tenemos "user" y "bot"
            gemini_rol = "user" if rol == "user" else "model"
            
            # se agregan a las cajas de memoria content y part de Gemini
            historial_gemini.append(
                types.Content(role=gemini_rol, parts=[types.Part.from_text(text=texto)])
            )

        # C) Creamos la sesión de IA inyectándole la memoria del pasado
        chat_ia = client.chats.create(
            model=GEMINI_MODEL,
            # Reglas de comportamiento de la IA
            config={ 
                "system_instruction": "Eres un amigable y experto tutor de inglés. Responde de forma concisa, conversacional y educativa."
            },
            # Contexto de la conversación (memoria)
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
    # Crea el historial de conversación obtenido de la base de datos, para pasarlo a Gemini
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
    REGLA 8 (PRONUNCIACIÓN IPA): En el campo "frente", añade SIEMPRE la transcripción fonética IPA entre paréntesis al lado del término. Ejemplo: "Thought (/θɔːt/)". NO añadas transcripciones fonéticas en los campos de ejemplos.
    Historial a procesar:
    {historial_texto}
    """

    try:
        # sesion puntual sin memoria
        response = client.models.generate_content(
            model=GEMINI_MODEL, contents=prompt
        )
        # lo que hace replace es quitar los bloques de código que Gemini a veces pone,
        # para que quede un JSON limpio (quita ```json y ``` al inicio y final), y los
        # espacios en blanco al inicio y final con strip()
        respuesta_limpia = (
            response.text.replace("```json", "").replace("```", "").strip()
        )

        # respuesta_limpia es un string que debería ser un JSON, lo convertimos a objeto Python
        datos_brutos = json.loads(respuesta_limpia)
        
        # Si la respuesta es un diccionario, buscamos la primera lista que contenga y la devolvemos.
        # Si es una lista, la devolvemos directamente. Si no es ninguna de las dos, devolvemos una lista vacía.
        # next recorre el generador y devuelve el primer valor que cumpla la condición isinstance(v, list), o [] si no encuentra ninguno
        if isinstance(datos_brutos, dict):
            lista_cartas = next( 
                (v for v in datos_brutos.values() if isinstance(v, list)), []
            )
        else: # si es una lista, se devuelve directamente
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

        # enumerate nos da el índice i y la carta en cada iteración
        for i, carta in enumerate(req.cartas):
            
            # carta es un json con campos "frente", "reverso", "ejemplo_ingles", "ejemplo_espanol", "termino_imagen", "categoria"
            # con get busco acceder a la clave "frente", si no existe devuelve ""
            texto_frente = str(carta.get("frente", "")).strip()
            
            # pregunta si es alfanumerico (numero o texto) y si no lo es, lo reemplaza por "_".
            # esto lo hace para que sea un nombre de archivo valido.
            # Solo toma los primeros 15 caracteres para el nombre del archivo.mp3
            # "".join indica el separador (vacio en este caso) juntando todos los elementos de la lista
            nombre_limpio = "".join(
                c if c.isalnum() else "_" for c in texto_frente[:15]
            )

            # 1. Preparar audio del Frente
            # Toma un parentesis abierto \( , toma su contenido .*? hasta el parentesis final \) y reemplaza por ""
            # borrar ** y * y luego hace strip() para quitar espacios al inicio y final
            texto_audio_frente = (
                re.sub(r"\(.*?\)", "", texto_frente)
                .replace("**", "")
                .replace("*", "")
                .strip()
            )
            nombre_archivo_frente = f"ia_audio_frente_{nombre_limpio}_{i}.mp3"
            if texto_audio_frente:
                # Agregamos la corrutina a la lista de tareas (sin ejecutarla aún)
                # genera el audio del texto y lo guarda en el nombre de archivo mp3 correspondiente
                tareas_audio.append(
                    generar_audio(texto_audio_frente, nombre_archivo_frente)
                )

            # 2. Preparar audios de los Ejemplos Múltiples
            # accede al campo "ejemplo_ingles" de la carta JSON, sino devuelve "".
            texto_ejemplo = str(carta.get("ejemplo_ingles", "")).strip()
            if texto_ejemplo:
                # crea una lista separando por el símbolo "|" y eliminando los espacios
                # al inicio y final de cada oración, y descartando las que queden vacías
                oraciones_en = [
                    o.strip() for o in texto_ejemplo.split("|") if o.strip()
                ]
                # enumerate nos da el índice j y la oración en cada iteración
                for j, oracion_en in enumerate(oraciones_en):
                    texto_audio_ejemplo = (
                        oracion_en.replace("**", "").replace("*", "").strip()
                    )
                    nombre_archivo_ejemplo = (
                        f"ia_audio_ejemplo_{nombre_limpio}_{i}_{j}.mp3"
                    )
                    if texto_audio_ejemplo:
                        # Agregamos la corrutina a la lista de tareas
                        # genera el audio del texto y lo guarda en el nombre de archivo mp3 correspondiente
                        tareas_audio.append(
                            generar_audio(texto_audio_ejemplo, nombre_archivo_ejemplo)
                        )

        # Disparamos todas las descargas de audio simultáneamente a internet y esperamos que terminen
        if tareas_audio:
            await asyncio.gather(*tareas_audio) # Desempaquetar la lista (rompe los [] y pasa cada elemento como argumento)

        # ------------------------------------------------------------------
        # 🌟 FASE 2: INYECCIÓN SECUENCIAL A ANKI (Los archivos ya existen en disco)
        # ------------------------------------------------------------------
        cartas_agregadas = 0

        for i, carta in enumerate(req.cartas):
            # Obtener los campos de la carta JSON
            texto_frente = str(carta.get("frente", "")).strip()
            texto_reverso_base = str(carta.get("reverso", "")).strip()
            texto_ejemplo = str(carta.get("ejemplo_ingles", "")).strip()
            termino_imagen = str(carta.get("termino_imagen", "")).strip()

            # Busca la llave "categoria" y si no la encuentra, asigna "Vocabulario"
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
            
            # pregunta si es alfanumerico (numero o texto) y si no lo es, lo reemplaza por "_".
            # Solo toma los primeros 15 caracteres para el nombre del archivo.mp3
            # "".join indica el separador (vacio en este caso) juntando todos los elementos de la lista
            nombre_limpio = "".join(
                c if c.isalnum() else "_" for c in texto_frente[:15]
            )

            def md_a_html(texto):
                # Busca dos asteriscos \*\*.
                # Luego, atrapa todo el texto que haya en el medio (.*?) y guárdalo en tu memoria.
                # Finalmente, detente cuando veas otros dos asteriscos \*\*
                # Pon una etiqueta HTML de inicio de negrita <b>.
                # Luego, pon el texto exacto que atrapaste en tu memoria (\1 significa 'Grupo de captura 1').
                # Por último, cierra la etiqueta </b>
                texto = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", texto)
                # lo mismo pero con un solo asterisco
                texto = re.sub(r"\*(.*?)\*", r"<i>\1</i>", texto)
                return texto
            
            # pasar campos de las cartas de markdown a HTML para que Anki los interprete correctamente
            texto_frente_html = md_a_html(texto_frente)
            texto_reverso_base_html = md_a_html(texto_reverso_base)
            texto_ejemplo_html = md_a_html(texto_ejemplo)
            traduccion_ejemplo = str(carta.get("ejemplo_espanol", "")).strip()
            traduccion_ejemplo_html = md_a_html(traduccion_ejemplo)

            # <br> es salto de linea.
            # si hay, es porque gemini envió una explicacion larga con saltos de linea, entonces no se le agrega negrita.
            # si no hay, es porque gemini envió una definicion corta, entonces se le agrega negrita al reverso.
            if "<br>" in texto_reverso_base_html:
                texto_reverso_final = texto_reverso_base_html
            else:
                texto_reverso_final = f"<b>{texto_reverso_base_html}</b>"

            # 1. IMAGEN DE PEXELS
            if termino_imagen:
                # por si no carga bien la imagen, uso try
                try:
                    url_busqueda = f"https://api.pexels.com/v1/search?query={termino_imagen}&per_page=1"
                    # Hago la petición a Pexels con requests y un timeout de 5 segundos
                    respuesta_pexels = requests.get(
                        url_busqueda,
                        headers={"Authorization": api_key_pexels},
                        timeout=5, # cancela si pasan 5 segundos sin respuesta
                    )
                    if respuesta_pexels.status_code == 200:
                        datos_pexels = respuesta_pexels.json()
                        if datos_pexels.get("photos"):
                            # Si hay fotos, tomo la primera y su URL de tamaño medio
                            url_imagen = datos_pexels["photos"][0]["src"]["medium"]
                            
                            # descargar la imagen y guardarla en memoria
                            # .content devuelve el contenido binario de la respuesta
                            # (la imagen en bytes)
                            img_data = requests.get(url_imagen, timeout=5).content
                            nombre_archivo_img = f"ia_img_{nombre_limpio}_{i}.jpg"
                            
                            # Invocar AnkiConnect para almacenar la imagen en la colección de Anki
                            invoke_anki(
                                "storeMediaFile",
                                filename=nombre_archivo_img,
                                data=base64.b64encode(img_data).decode("utf-8"),
                            )
                            # Se agrega la imagen al reverso de la carta, antes del texto
                            texto_reverso_final = (
                                f"<img src='{nombre_archivo_img}'><br><br>"
                                + texto_reverso_final
                            )
                except:
                    pass

            # 2. VINCULAR AUDIO FRENTE (El archivo ya fue creado en la Fase 1)
            nombre_archivo_frente = f"ia_audio_frente_{nombre_limpio}_{i}.mp3"
            
            # verificamos que el archivo se creó correctamente antes de intentar abrirlo
            if os.path.exists(nombre_archivo_frente):
                try:
                    # read binary = "rb"
                    with open(nombre_archivo_frente, "rb") as f:
                        # anki guarda el audio en su carpeta de medios, codificado como base64
                        invoke_anki(
                            "storeMediaFile",
                            filename=nombre_archivo_frente,
                            data=base64.b64encode(f.read()).decode("utf-8"),
                        )
                    # formato para que anki esconda el texto para que dibuje el boton de play
                    texto_frente_html += f" [sound:{nombre_archivo_frente}]"
                except:
                    pass
                # terminado todo, se borran los archivos mp3
                finally:
                    if os.path.exists(nombre_archivo_frente):
                        os.remove(nombre_archivo_frente)

            # 3. VINCULAR AUDIOS DE EJEMPLOS MÚLTIPLES
            if texto_ejemplo:
                # crea una lista separando por el símbolo "|" y eliminando los espacios
                oraciones_en = [
                    o.strip() for o in texto_ejemplo.split("|") if o.strip()
                ]
                oraciones_es = (
                    [o.strip() for o in traduccion_ejemplo.split("|") if o.strip()]
                    if traduccion_ejemplo
                    else []
                )
                
                # Si hay traducción pero la cantidad de oraciones no coincide,
                # se asume que es un error de Gemini y se reemplaza por una sola oración limpia.
                if traduccion_ejemplo and len(oraciones_en) != len(oraciones_es):
                    oraciones_en = [texto_ejemplo.replace("|", "")]
                    oraciones_es = [traduccion_ejemplo.replace("|", "")]

                # procesar cada oración en inglés y su respectiva traducción al español
                for j, oracion_en in enumerate(oraciones_en):
                    oracion_en_html = md_a_html(oracion_en)
                    oracion_es_html = (
                        md_a_html(oraciones_es[j]) if j < len(oraciones_es) else ""
                    )
                    nombre_archivo_ejemplo = (
                        f"ia_audio_ejemplo_{nombre_limpio}_{i}_{j}.mp3"
                    )
                    # preparar el boton visual de audio para el reverso de la carta
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
                            # borra los mp3 de ejemplos
                            if os.path.exists(nombre_archivo_ejemplo):
                                os.remove(nombre_archivo_ejemplo)

                    # añadimos el ejemplo, su traduccion y el audio al reverso de la carta (por cada oracion j)
                    if oracion_es_html:
                        texto_reverso_final += f"<br><br>{oracion_en_html}<br><i>{oracion_es_html}</i>{audio_tag}"
                    else:
                        texto_reverso_final += f"<br><br>{oracion_en_html}{audio_tag}"

            # 4. INYECTAR A ANKI
            try:
                invoke_anki(
                    "addNote",
                    note={
                        "deckName": mazo_destino,       # mazo
                        "modelName": NOMBRE_TIPO_CARTA, # tipo de carta: basico
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
                # por si hay una duplicada, se intenta inyectar la carta con un solo ejemplo en su frente
                if texto_ejemplo and "duplicate" in str(e).lower():
                    primera_frase = texto_ejemplo_html.split("|")[0].strip()
                    frente_alternativo = primera_frase
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
            "mensaje": f"🎉 ¡Éxito! Se inyectaron {cartas_agregadas} cartas."
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
    
    REGLA 1: La historia debe tener entre 35 y 40 oraciones en total.
    REGLA 2: Devuelve ESTRICTAMENTE un objeto JSON puro, sin formato markdown, ni bloques ```json.
    
    Formato esperado:
    {{
      "titulo": "Un título corto y atractivo en español",
      "lineas": [
        {{"en": "Oración en inglés.", "es": "Traducción natural al español.", "ipa": "/transcripción fonética exacta de toda la oración/"}}
      ]
    }}
    """

    try:
        # 2. Pedir la historia a Gemini
        response = client.models.generate_content(
            model=GEMINI_MODEL, contents=prompt
        )
        respuesta_limpia = (
            response.text.replace("```json", "").replace("```", "").strip()
        )
        # Convertir la respuesta limpia (string) en un objeto Python (diccionario)
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
        # Obtener el ID de la historia recién creada
        historia_id = c.lastrowid

        # Crear una subcarpeta específica para esta historia
        carpeta_historia = f"static/audios/historia_{historia_id}"
        os.makedirs(carpeta_historia, exist_ok=True)

        # 4. Generar audios de forma concurrente
        tareas_audio = []
        rutas_audios = []

        for i, linea in enumerate(lineas):
            # busca la llave "en" y si no la encuentra, asigna un string vacío. Luego hace strip() para quitar espacios al inicio y final.
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
                "INSERT INTO lineas_historia (historia_id, orden, oracion_en, oracion_es, ruta_audio, oracion_ipa) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    historia_id,
                    i,
                    linea.get("en", ""),
                    linea.get("es", ""),
                    rutas_audios[i],
                    linea.get("ipa", ""),
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
        "SELECT orden, oracion_en, oracion_es, ruta_audio, oracion_ipa FROM lineas_historia WHERE historia_id = ? ORDER BY orden ASC",
        (historia_id,),
    )
    # Importante: Agregamos el "/" al inicio de la ruta del audio para que el HTML lo encuentre bien
    lineas = [
        {
            "orden": row[0],
            "en": row[1],
            "es": row[2],
            "audio": f"/{row[3]}",
            "ipa": row[4],
        }
        for row in c.fetchall()
    ]
    conn.close()
    return {"lineas": lineas}


# ==========================================
# 🗑️ ELIMINAR HISTORIA
# ==========================================
@app.delete("/api/historias/{historia_id}")
def eliminar_historia(historia_id: int):
    conn = sqlite3.connect("tutor.db")
    c = conn.cursor()

    # Recuperamos las rutas de audio antes de borrar las filas
    c.execute(
        "SELECT ruta_audio FROM lineas_historia WHERE historia_id = ?",
        (historia_id,),
    )
    rutas_audio = [row[0] for row in c.fetchall() if row[0]]

    # Borramos primero los archivos mp3 asociados
    for ruta_audio in rutas_audio:
        ruta_normalizada = ruta_audio.replace("\\", "/")
        if os.path.exists(ruta_normalizada):
            try:
                os.remove(ruta_normalizada)
            except OSError:
                pass

    # Intentamos limpiar la carpeta de la historia si quedó vacía
    carpeta_historia = f"static/audios/historia_{historia_id}"
    if os.path.isdir(carpeta_historia):
        try:
            os.rmdir(carpeta_historia)
        except OSError:
            pass

    # Borramos primero las líneas y audios asociados a la historia
    c.execute("DELETE FROM lineas_historia WHERE historia_id = ?", (historia_id,))

    # Luego borramos la historia principal
    c.execute("DELETE FROM historias WHERE id = ?", (historia_id,))

    conn.commit()
    conn.close()

    return {"mensaje": "Historia eliminada correctamente"}


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
    Crea UNA SOLA flashcard perfecta para este término, escribiendo su traducción al español y explicando su significado dentro de ese contexto específico.
    
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
    REGLA 4 (PHRASAL VERBS): Si es phrasal verb, añade su tipo entre paréntesis en el frente (si es separable o inseparable), enumera significados en el reverso, y da un ejemplo por cada significado, separados por " | ", alternando los tiempos verbales.
    REGLA 5 (IMÁGENES): "termino_imagen" NUNCA debe estar vacío. Usa palabras abstractas en inglés si es necesario.
    REGLA 6 : Si el término tiene múltiples significados, crea un ejemplo en inglés y su traducción al español para cada significado, separados por " | ".
    REGLA 7: Siempre incluye como minimo 2 ejemplos.
    REGLA 8 (PRONUNCIACIÓN IPA): En el campo "frente", añade SIEMPRE la transcripción fonética IPA entre paréntesis al lado del término. Ejemplo: "Thought (/θɔːt/)". NO añadas transcripciones fonéticas en el campo de ejemplo en inglés.
    """

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL, contents=prompt
        )
        
        # 1. Guardamos el texto (puede ser un string o puede ser None)
        texto_generado = response.text
        
        # 2. Verificamos si vino vacío (None)
        if not texto_generado:
             return {"error": "La IA no devolvió ningún texto."}
        
        respuesta_limpia = (
            texto_generado.replace("```json", "").replace("```", "").strip()
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
        {
            "id": "schwa",
            "simbolo": "/\u0259/",
            "nombre": "El Schwa (Sonido Rey)",
            "desc": "Relaja TODA la boca y la lengua. No muevas los labios. Haz un sonido corto y gutural desde la garganta.",
            "ejemplos": [
                "about (/\u0259\u02c8ba\u028at/)",
                "taken (/\u02c8te\u026ak\u0259n/)",
                "pencil (/\u02c8p\u025bns\u0259l/)",
            ],
        },
        {
            "id": "i_corta",
            "simbolo": "/\u026a/",
            "nombre": "La 'i' Corta",
            "desc": "Boca relajada, un poco abierta. NO sonrías. Suena a medio camino entre tu 'e' y tu 'i'.",
            "ejemplos": [
                "ship (/\u0283\u026ap/)",
                "sit (/s\u026at/)",
                "kid (/k\u026ad/)",
            ],
        },
        {
            "id": "i_larga",
            "simbolo": "/i\u02d0/",
            "nombre": "La 'i' Larga",
            "desc": "Estira los labios tensándolos como si sonrieras grande. Tensa la lengua hacia arriba y adelante.",
            "ejemplos": [
                "sheep (/\u0283i\u02d0p/)",
                "seat (/si\u02d0t/)",
                "key (/ki\u02d0/)",
            ],
        },
        {
            "id": "u_corta",
            "simbolo": "/\u028a/",
            "nombre": "La 'u' Corta",
            "desc": "Labios ligeramente redondeados pero muy relajados (no apretados). Lengua hacia atrás.",
            "ejemplos": [
                "book (/b\u028ak/)",
                "put (/p\u028at/)",
                "good (/\u0261\u028ad/)",
            ],
        },
        {
            "id": "u_larga",
            "simbolo": "/u\u02d0/",
            "nombre": "La 'u' Larga",
            "desc": "Haz un círculo pequeño y muy apretado con los labios (como para soplar una vela). Tensa la boca.",
            "ejemplos": [
                "blue (/blu\u02d0/)",
                "food (/fu\u02d0d/)",
                "shoe (/\u0283u\u02d0/)",
            ],
        },
        {
            "id": "e_corta",
            "simbolo": "/\u025b/",
            "nombre": "La 'e' Corta",
            "desc": "Abre la boca un poco más, labios relajados, lengua en el centro. (Igual a la 'e' de España).",
            "ejemplos": ["bed (/b\u025bd/)", "red (/r\u025bd/)", "head (/h\u025bd/)"],
        },
        {
            "id": "schwa_largo",
            "simbolo": "/\u025c\u02d0/",
            "nombre": "El Schwa Largo",
            "desc": "Boca entreabierta y relajada, lengua plana. Haz vibrar la garganta de forma alargada.",
            "ejemplos": [
                "bird (/b\u025c\u02d0rd/)",
                "work (/w\u025c\u02d0rk/)",
                "learn (/l\u025c\u02d0rn/)",
            ],
        },
        {
            "id": "o_larga",
            "simbolo": "/\u0254\u02d0/",
            "nombre": "La 'o' Larga",
            "desc": "Abre la boca formando una 'O' vertical alta, tensa los labios. Lengua plana y atrás.",
            "ejemplos": [
                "door (/d\u0254\u02d0r/)",
                "more (/m\u0254\u02d0r/)",
                "board (/b\u0254\u02d0rd/)",
            ],
        },
        {
            "id": "a_gato",
            "simbolo": "/\u00e6/",
            "nombre": "La 'A' Abierta",
            "desc": "Boca ABIERTA hacia abajo al máximo. Estira los labios a los lados y empuja la lengua hacia adelante. Intenta decir 'a' pero sonando a 'e'.",
            "ejemplos": ["cat (/k\u00e6t/)", "black (/bl\u00e6k/)", "map (/m\u00e6p/)"],
        },
        {
            "id": "a_neutra",
            "simbolo": "/\u028c/",
            "nombre": "La 'a' Neutra",
            "desc": "Boca semiabierta. Lengua relajada. Da un golpe de sonido corto y seco desde la garganta.",
            "ejemplos": [
                "cup (/k\u028cp/)",
                "luck (/l\u028ck/)",
                "blood (/bl\u028cd/)",
            ],
        },
        {
            "id": "a_larga",
            "simbolo": "/\u0251\u02d0/",
            "nombre": "La 'a' Larga",
            "desc": "Abre la boca al máximo (como en el dentista). Lengua totalmente plana abajo. Sonido largo.",
            "ejemplos": [
                "car (/k\u0251\u02d0r/)",
                "father (/\u02c8f\u0251\u02d0\u00f0\u0259r/)",
                "star (/st\u0251\u02d0r/)",
            ],
        },
        {
            "id": "o_corta",
            "simbolo": "/\u0252/",
            "nombre": "La 'o' Corta",
            "desc": "Labios en forma redonda pero con la mandíbula caída muy abierta. Golpe de voz corto.",
            "ejemplos": ["hot (/h\u0252t/)", "box (/b\u0252ks/)", "stop (/st\u0252p/)"],
        },
        # --- DIPTONGOS (8) ---
        {
            "id": "dip_ei",
            "simbolo": "/e\u026a/",
            "nombre": "Diptongo EI",
            "desc": "Empieza con boca abierta relajada y ciérrala estirando a una sonrisa tensa.",
            "ejemplos": ["day (/de\u026a/)", "say (/se\u026a/)", "make (/me\u026ak/)"],
        },
        {
            "id": "dip_ai",
            "simbolo": "/a\u026a/",
            "nombre": "Diptongo AI",
            "desc": "Abre la boca en grande y deslízala cerrando hacia una sonrisa tensa.",
            "ejemplos": ["my (/ma\u026a/)", "eye (/a\u026a/)", "time (/ta\u026am/)"],
        },
        {
            "id": "dip_oi",
            "simbolo": "/\u0254\u026a/",
            "nombre": "Diptongo OI",
            "desc": "Empieza con labios en 'O' redonda y desliza hacia una sonrisa estirada.",
            "ejemplos": [
                "boy (/b\u0254\u026a/)",
                "toy (/t\u0254\u026a/)",
                "coin (/k\u0254\u026an/)",
            ],
        },
        {
            "id": "dip_au",
            "simbolo": "/a\u028a/",
            "nombre": "Diptongo AU",
            "desc": "Abre la boca en grande y ciérrala haciendo un círculo apretado con los labios.",
            "ejemplos": ["now (/na\u028a/)", "how (/ha\u028a/)", "house (/ha\u028as/)"],
        },
        {
            "id": "dip_ou",
            "simbolo": "/o\u028a/",
            "nombre": "Diptongo OU",
            "desc": "Haz una 'O' relajada y aprieta los labios hasta hacer un círculo pequeñito.",
            "ejemplos": [
                "go (/\u0261o\u028a/)",
                "no (/no\u028a/)",
                "show (/\u0283o\u028a/)",
            ],
        },
        {
            "id": "dip_ia",
            "simbolo": "/\u026a\u0259/",
            "nombre": "Diptongo IA",
            "desc": "Empieza con sonrisa relajada y suelta la tensión volviendo al centro (Schwa).",
            "ejemplos": [
                "here (/h\u026a\u0259r/)",
                "near (/n\u026a\u0259r/)",
                "idea (/a\u026a\u02c8d\u026a\u0259/)",
            ],
        },
        {
            "id": "dip_ea",
            "simbolo": "/e\u0259/",
            "nombre": "Diptongo EA",
            "desc": "Empieza con boca entreabierta y relaja toda la boca volviendo al centro (Schwa).",
            "ejemplos": [
                "hair (/he\u0259r/)",
                "there (/\u00f0e\u0259r/)",
                "care (/ke\u0259r/)",
            ],
        },
        {
            "id": "dip_ua",
            "simbolo": "/\u028a\u0259/",
            "nombre": "Diptongo UA",
            "desc": "Empieza con labios redondeados y relájalos completamente (Schwa).",
            "ejemplos": [
                "tour (/t\u028a\u0259r/)",
                "pure (/pj\u028a\u0259r/)",
                "cure (/kj\u028a\u0259r/)",
            ],
        },
        # --- CONSONANTES (24) ---
        {
            "id": "p_fuerte",
            "simbolo": "/p/",
            "nombre": "La 'P' Explosiva",
            "desc": "Junta los labios apretados. Suelta el aire de golpe estallando. SIN vibrar la garganta.",
            "ejemplos": [
                "pen (/p\u025bn/)",
                "top (/t\u0252p/)",
                "push (/p\u028a\u0283/)",
            ],
        },
        {
            "id": "b_fuerte",
            "simbolo": "/b/",
            "nombre": "La 'B' Fuerte",
            "desc": "Junta los labios. Suelta el aire de golpe, pero HACIENDO VIBRAR la garganta.",
            "ejemplos": [
                "berry (/\u02c8b\u025bri/)",
                "bowel (/\u02c8ba\u028a\u0259l/)",
                "back (/b\u00e6k/)",
            ],
        },
        {
            "id": "t_fuerte",
            "simbolo": "/t/",
            "nombre": "La 'T' Explosiva",
            "desc": "Punta de la lengua justo detrás de los dientes superiores. Estalla el aire. SIN vibrar.",
            "ejemplos": ["time (/ta\u026am/)", "cat (/k\u00e6t/)", "tell (/t\u025bl/)"],
        },
        {
            "id": "d_fuerte",
            "simbolo": "/d/",
            "nombre": "La 'D' Fuerte",
            "desc": "Lengua detrás de los dientes superiores. Suelta el aire VIBRANDO la garganta.",
            "ejemplos": [
                "dog (/d\u0252\u0261/)",
                "day (/de\u026a/)",
                "bed (/b\u025bd/)",
            ],
        },
        {
            "id": "k_fuerte",
            "simbolo": "/k/",
            "nombre": "La 'K' Fuerte",
            "desc": "Sube la parte de atrás de la lengua para bloquear la garganta. Estalla el aire. SIN vibrar.",
            "ejemplos": ["cat (/k\u00e6t/)", "key (/ki\u02d0/)", "back (/b\u00e6k/)"],
        },
        {
            "id": "g_fuerte",
            "simbolo": "/g/",
            "nombre": "La 'G' Fuerte",
            "desc": "Igual que la /k/, pero VIBRANDO fuertemente la garganta.",
            "ejemplos": [
                "go (/\u0261o\u028a/)",
                "get (/\u0261\u025bt/)",
                "big (/b\u026a\u0261/)",
            ],
        },
        {
            "id": "f_suave",
            "simbolo": "/f/",
            "nombre": "La 'F'",
            "desc": "Apoya los dientes superiores sobre tu labio inferior. Sopla aire. SIN vibrar.",
            "ejemplos": [
                "fly (/fla\u026a/)",
                "four (/f\u0254\u02d0r/)",
                "leaf (/li\u02d0f/)",
            ],
        },
        {
            "id": "v_labio",
            "simbolo": "/v/",
            "nombre": "La 'V' Vibrante",
            "desc": "Dientes superiores sobre labio inferior. Sopla aire y VIBRA la garganta fuerte (cosquillas en el labio).",
            "ejemplos": [
                "very (/\u02c8v\u025bri/)",
                "vowel (/\u02c8va\u028a\u0259l/)",
                "save (/se\u026av/)",
            ],
        },
        {
            "id": "th_sordo",
            "simbolo": "/\u03b8/",
            "nombre": "El 'TH' Sordo",
            "desc": "Saca la punta de la lengua entre los dientes. Sopla aire continuo. SIN vibrar la garganta.",
            "ejemplos": [
                "think (/\u03b8\u026a\u014bk/)",
                "math (/m\u00e6\u03b8/)",
                "both (/bo\u028a\u03b8/)",
            ],
        },
        {
            "id": "th_sonoro",
            "simbolo": "/\u00f0/",
            "nombre": "El 'TH' Vibrante",
            "desc": "Lengua entre los dientes. Sopla aire y VIBRA la garganta (se siente como un zumbido de abeja).",
            "ejemplos": [
                "this (/\u00f0\u026as/)",
                "mother (/\u02c8m\u028c\u00f0\u0259r/)",
                "breathe (/bri\u02d0\u00f0/)",
            ],
        },
        {
            "id": "s_suave",
            "simbolo": "/s/",
            "nombre": "La 'S' Suave",
            "desc": "Junta los dientes, lengua detrás. Sopla aire siseando. SIN vibrar.",
            "ejemplos": ["sue (/su\u02d0/)", "bus (/b\u028cs/)", "face (/fe\u026as/)"],
        },
        {
            "id": "z_vibra",
            "simbolo": "/z/",
            "nombre": "La 'Z' de Abeja",
            "desc": "Junta los dientes. Sopla aire y VIBRA la garganta fuerte (imita a una mosca/abeja).",
            "ejemplos": [
                "zoo (/zu\u02d0/)",
                "buzz (/b\u028cz/)",
                "phase (/fe\u026az/)",
            ],
        },
        {
            "id": "sh_silencio",
            "simbolo": "/\u0283/",
            "nombre": "El sonido 'SH'",
            "desc": "Empuja los labios hacia afuera (como pidiendo silencio 'shhh'). Sopla aire. SIN vibrar.",
            "ejemplos": [
                "she (/\u0283i\u02d0/)",
                "shoe (/\u0283u\u02d0/)",
                "crash (/kr\u00e6\u0283/)",
            ],
        },
        {
            "id": "zh_suave",
            "simbolo": "/\u0292/",
            "nombre": "La 'SH' Vibrante",
            "desc": "Labios hacia afuera como 'shhh', pero VIBRANDO la garganta (como un motor).",
            "ejemplos": [
                "measure (/\u02c8m\u025b\u0292\u0259r/)",
                "vision (/\u02c8v\u026a\u0292\u0259n/)",
                "television (/\u02c8t\u025bl\u026av\u026a\u0292\u0259n/)",
            ],
        },
        {
            "id": "h_aire",
            "simbolo": "/h/",
            "nombre": "La 'H' Aspirada",
            "desc": "Abre la boca relajada y exhala aire desde el fondo (como empañando un espejo). SIN raspar.",
            "ejemplos": [
                "hat (/h\u00e6t/)",
                "home (/ho\u028am/)",
                "hello (/h\u0259\u02c8lo\u028a/)",
            ],
        },
        {
            "id": "ch_fuerte",
            "simbolo": "/t\u0283/",
            "nombre": "El sonido 'CH'",
            "desc": "Empieza con la lengua tocando el paladar (T) y explota hacia afuera con labios redondos (SH).",
            "ejemplos": [
                "chair (/t\u0283e\u0259r/)",
                "cheese (/t\u0283i\u02d0z/)",
                "match (/m\u00e6t\u0283/)",
            ],
        },
        {
            "id": "j_fuerte",
            "simbolo": "/d\u0292/",
            "nombre": "La 'J' Inglesa",
            "desc": "Igual que CH, pero VIBRANDO la garganta. Suena fuerte y golpeado.",
            "ejemplos": [
                "job (/d\u0292\u0252b/)",
                "juice (/d\u0292u\u02d0s/)",
                "age (/e\u026ad\u0292/)",
            ],
        },
        {
            "id": "m_nasal",
            "simbolo": "/m/",
            "nombre": "La 'M' Nasal",
            "desc": "Junta los labios. No sueltes aire por la boca, sácalo por la nariz y VIBRA la garganta.",
            "ejemplos": [
                "man (/m\u00e6n/)",
                "make (/me\u026ak/)",
                "time (/ta\u026am/)",
            ],
        },
        {
            "id": "n_nasal",
            "simbolo": "/n/",
            "nombre": "La 'N' Nasal",
            "desc": "Lengua presionando detrás de los dientes de arriba. Aire por la nariz y VIBRA.",
            "ejemplos": ["no (/no\u028a/)", "name (/ne\u026am/)", "sun (/s\u028cn/)"],
        },
        {
            "id": "ng_nasal",
            "simbolo": "/\u014b/",
            "nombre": "La 'NG' Nasal",
            "desc": "Parte de atrás de la lengua sube y bloquea la garganta. Aire por la nariz y VIBRA.",
            "ejemplos": [
                "sing (/s\u026a\u014b/)",
                "king (/k\u026a\u014b/)",
                "ring (/r\u026a\u014b/)",
            ],
        },
        {
            "id": "l_lateral",
            "simbolo": "/l/",
            "nombre": "La 'L'",
            "desc": "Punta de la lengua firme contra el paladar. Deja que el aire escape por los lados de la lengua.",
            "ejemplos": [
                "leg (/l\u025b\u0261/)",
                "love (/l\u028cv/)",
                "feel (/fi\u02d0l/)",
            ],
        },
        {
            "id": "r_suave",
            "simbolo": "/r/",
            "nombre": "La 'R' Inglesa",
            "desc": "Tira la lengua hacia ATRÁS sin tocar el paladar en absoluto. Redondea los labios. VIBRA.",
            "ejemplos": [
                "red (/r\u025bd/)",
                "run (/r\u028cn/)",
                "car (/k\u0251\u02d0r/)",
            ],
        },
        {
            "id": "w_desliza",
            "simbolo": "/w/",
            "nombre": "La 'W'",
            "desc": "Círculo pequeño y tenso con los labios. Desliza rápido hacia el siguiente sonido vocal.",
            "ejemplos": [
                "we (/wi\u02d0/)",
                "water (/\u02c8w\u0254\u02d0t\u0259r/)",
                "win (/w\u026an/)",
            ],
        },
        {
            "id": "y_desliza",
            "simbolo": "/j/",
            "nombre": "La 'Y'",
            "desc": "Lengua arriba casi tocando el paladar (como sonriendo tensamente). Desliza rápido a la vocal.",
            "ejemplos": [
                "yes (/j\u025bs/)",
                "yellow (/\u02c8j\u025blo\u028a/)",
                "you (/ju\u02d0/)",
            ],
        },
    ]
    return fonemas_prioritarios


# 2.5 Base de datos estática de Reglas de Connected Speech
@app.get("/api/connected_speech")
def obtener_connected_speech():
    reglas = [
        {
            "id": "assim_t",
            "regla": "T + Y = CH",
            "nombre": "Asimilación de la T",
            "desc": "Cuando una palabra termina en sonido /t/ y la siguiente empieza con /j/ (y), se fusionan en CH.",
            "ejemplos": ["Don't you (Donchu)", "Let you (Lechu)", "Meet you (Meechu)"],
        },
        {
            "id": "assim_d",
            "regla": "D + Y = J",
            "nombre": "Asimilación de la D",
            "desc": "Cuando una palabra termina en sonido /d/ y la siguiente empieza con /j/ (y), se fusionan en la J inglesa vibrante.",
            "ejemplos": ["Did you (Didja)", "Would you (Woulja)", "Find you (Finja)"],
        },
        {
            "id": "flap_t",
            "regla": "La Flap 'T'",
            "nombre": "La 'T' Americana",
            "desc": "En USA, cuando una 't' o 'tt' queda atrapada entre dos sonidos vocales, se pronuncia como una 'r' suave y rápida.",
            "ejemplos": ["Water (Wader)", "Better (Beder)", "City (Cidy)"],
        },
        {
            "id": "elision_h",
            "regla": "Adiós a la 'H'",
            "nombre": "Elisión de Pronombres",
            "desc": "La 'h' inicial en him, her, he, his a menudo desaparece al hablar rápido porque el aire no se detiene.",
            "ejemplos": [
                "Tell him (Tellim)",
                "Call her (Caller)",
                "I like his (I likis)",
            ],
        },
        {
            "id": "link_cv",
            "regla": "Consonante + Vocal",
            "nombre": "Linking C-V",
            "desc": "Si una palabra termina en consonante y la otra empieza en vocal, se unen como si fueran una sola palabra larga.",
            "ejemplos": [
                "Stop it (Sto pit)",
                "Not at all (No ta tall)",
                "An apple (A napple)",
            ],
        },
        # 👇 NUEVAS TARJETAS DE REDUCCIONES 👇
        {
            "id": "red_verbos",
            "regla": "Gonna / Wanna",
            "nombre": "Reducción de Verbos",
            "desc": "El 'to' pierde toda su fuerza y se fusiona con el verbo anterior convirtiéndose en un sonido Schwa.",
            "ejemplos": ["Going to (Gonna)", "Want to (Wanna)", "Got to (Gotta)"],
        },
        {
            "id": "red_obligacion",
            "regla": "Hafta / Usta",
            "nombre": "Obligación y Costumbre",
            "desc": "La 'v' y la 'd' se contagian del sonido sordo de la 't'. El 'to' se reduce a Schwa.",
            "ejemplos": ["Have to (Hafta)", "Used to (Usta)", "Need to (Needa)"],
        },
        {
            "id": "red_pron",
            "regla": "Lemme / Gimme",
            "nombre": "Fusión de Pronombres",
            "desc": "Al hablar rápido, el pronombre 'me' es absorbido por la consonante del verbo de acción que lo precede.",
            "ejemplos": ["Let me (Lemme)", "Give me (Gimme)", "Don't know (Dunno)"],
        },
        {
            "id": "red_prep",
            "regla": "Kinda / Sorta",
            "nombre": "Colapso de Preposiciones",
            "desc": "La preposición 'of' pierde su consonante (f/v) por completo, dejando solo un rastro de sonido Schwa.",
            "ejemplos": ["Kind of (Kinda)", "Sort of (Sorta)", "Out of (Outta)"],
        },
        {
            "id": "red_extrema",
            "regla": "I'ma",
            "nombre": "Colapso Extremo",
            "desc": "Frases completas que colapsan por inercia vocal en una sola sílaba.",
            "ejemplos": ["I am going to (I'ma)", "Come on (C'mon)"],
        },
    ]
    return reglas


# 3. El Motor del "Gimnasio"
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
            model=GEMINI_MODEL, contents=prompt
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

@app.get('/api/vocabulario')
async def obtener_vocabulario():
    conn = sqlite3.connect("tutor.db")
    c = conn.cursor()
    
    # Devolvemos todas las palabras guardadas
    c.execute("SELECT palabra FROM vocabulario_anki")
    palabras = [fila[0] for fila in c.fetchall()]
    conn.close()
    
    # FastAPI convierte esta lista de Python a JSON automáticamente
    return palabras 

@app.post('/api/vocabulario')
async def guardar_vocabulario(request: Request):
    conn = sqlite3.connect("tutor.db")
    c = conn.cursor()
    
    # Extraemos los datos del frontend usando await
    datos = await request.json()
    palabra = datos.get('palabra', '').strip()
    
    if palabra:
        try:
            c.execute("INSERT INTO vocabulario_anki (palabra) VALUES (?)", (palabra,))
            conn.commit()
        except sqlite3.IntegrityError:
            pass # Si la palabra ya existe, lo ignoramos sin crashear
            
    conn.close()
    
    # FastAPI convierte este diccionario a JSON automáticamente
    return {"status": "guardado"}



# uvicorn main:app --port 8080 --reload
