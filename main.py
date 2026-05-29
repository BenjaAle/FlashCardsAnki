import os
import json
import urllib.request
import base64
import re
import requests
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from google import genai
from gtts import gTTS

# ==========================================
# ⚙️ CONFIGURACIÓN DE TU ANKI
# ==========================================
NOMBRE_MAZO = "Ingles_IA"
NOMBRE_TIPO_CARTA = "Basic"
CAMPO_FRENTE = "Front"
CAMPO_REVERSO = "Back"
# ==========================================

load_dotenv()
api_key_gemini = os.getenv("GEMINI_API_KEY")
api_key_pexels = os.getenv("PEXELS_API_KEY")

if not api_key_gemini or not api_key_pexels:
    raise ValueError("❌ Falla: Revisa que GEMINI_API_KEY y PEXELS_API_KEY estén en tu .env")

# Inicializamos el cliente general y el chat
client = genai.Client(api_key=api_key_gemini)
chat_ia = client.chats.create(
    model='gemini-2.5-flash',
    config={"system_instruction": "Eres un amigable y experto tutor de inglés. Responde de forma concisa, conversacional y educativa. Usa ejemplos claros."}
)

app = FastAPI(title="Tutor de Inglés con IA")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Variable global para recordar qué han hablado
historial_conversacion = ""

class Mensaje(BaseModel):
    texto: str

# Funciones de AnkiConnect
def request_anki(action, **params):
    return {'action': action, 'version': 6, 'params': params}

def invoke_anki(action, **params):
    requestJson = json.dumps(request_anki(action, **params)).encode('utf-8')
    response = json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8765', requestJson)))
    if response['error'] is not None:
        raise Exception(response['error'])
    return response['result']

# Rutas del servidor
@app.get("/", response_class=HTMLResponse)
def pagina_principal(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.post("/chat")
def conversar(mensaje: Mensaje):
    global historial_conversacion
    try:
        respuesta = chat_ia.send_message(mensaje.texto)
        historial_conversacion += f"Alumno: {mensaje.texto}\nTutor: {respuesta.text}\n\n"
        return {"respuesta": respuesta.text}
    except Exception as e:
        return {"respuesta": f"Error: {str(e)}"}

# 🌟 FÁBRICA DE CARTAS BLINDADA CONTRA ARCHIVOS RESIDUALES
@app.post("/extraer")
def extraer_anki():
    global historial_conversacion
    
    if not historial_conversacion.strip():
        return {"mensaje": "⚠️ No hay conversación aún para extraer. ¡Hablemos primero!"}

    prompt = f"""
    Eres un creador de flashcards experto. Analiza el siguiente historial de conversación entre un alumno y su tutor de inglés.
    REGLA 1: Extrae ÚNICAMENTE el vocabulario útil, phrasal verbs, o correcciones clave que surgieron en la charla. Si no hay nada útil, devuelve []
    REGLA 2: Devuelve ESTRICTAMENTE un arreglo JSON puro.
    Formato esperado:
    [
      {{
        "frente": "Palabra o concepto en inglés",
        "reverso": "Definición en HTML",
        "ejemplo_ingles": "Oración de ejemplo en inglés.",
        "termino_imagen": "Palabra clave visual en inglés o vacío."
      }}
    ]
    REGLA 3: El campo "reverso" DEBE contener obligatoriamente:
    1. El significado en español (destaca lo importante con <b>).
    2. La oración de ejemplo en inglés completa.
    3. La traducción de esa oración al español (en <i>).
    Usa <br> para separar. No uses lenguaje conversacional.

    Historial a procesar:
    {historial_conversacion}
    """

    try:
        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        respuesta_limpia = response.text.replace('```json', '').replace('```', '').strip()
        
        datos_brutos = json.loads(respuesta_limpia)
        if isinstance(datos_brutos, dict):
            lista_cartas = next((v for v in datos_brutos.values() if isinstance(v, list)), [])
        else:
            lista_cartas = datos_brutos if isinstance(datos_brutos, list) else []
            
        if not lista_cartas:
            return {"mensaje": "🤷‍♂️ No encontré vocabulario nuevo en esta charla para crear cartas."}

        try:
            invoke_anki('createDeck', deck=NOMBRE_MAZO)
        except:
            pass

        cartas_agregadas = 0
        for i, carta in enumerate(lista_cartas):
            texto_frente = str(carta.get('frente', '')).strip()
            texto_reverso = str(carta.get('reverso', '')).strip()
            texto_ejemplo = str(carta.get('ejemplo_ingles', '')).strip()
            termino_imagen = str(carta.get('termino_imagen', '')).strip()
            nombre_limpio = "".join(c if c.isalnum() else "_" for c in texto_frente[:15])

            # 1. IMAGEN DE PEXELS (No deja residuos porque descarga directo a memoria RAM)
            if termino_imagen:
                try:
                    url_busqueda = f"https://api.pexels.com/v1/search?query={termino_imagen}&per_page=1"
                    respuesta_pexels = requests.get(url_busqueda, headers={"Authorization": api_key_pexels}, timeout=5)
                    if respuesta_pexels.status_code == 200:
                        datos_pexels = respuesta_pexels.json()
                        if datos_pexels.get('photos'):
                            url_imagen = datos_pexels['photos'][0]['src']['medium']
                            img_data = requests.get(url_imagen, timeout=5).content
                            nombre_archivo_img = f"ia_img_{nombre_limpio}_{i}.jpg"
                            invoke_anki('storeMediaFile', filename=nombre_archivo_img, data=base64.b64encode(img_data).decode('utf-8'))
                            texto_reverso = f"<img src='{nombre_archivo_img}'><br><br>" + texto_reverso
                except:
                    pass

            # 2. AUDIO FRENTE CON LIMPIEZA OBLIGATORIA
            nombre_archivo_frente = f"ia_audio_frente_{nombre_limpio}_{i}.mp3"
            try:
                texto_audio_frente = re.sub(r'\(.*?\)', '', texto_frente).strip()
                gTTS(texto_audio_frente, lang='en').save(nombre_archivo_frente)
                with open(nombre_archivo_frente, "rb") as f:
                    invoke_anki('storeMediaFile', filename=nombre_archivo_frente, data=base64.b64encode(f.read()).decode('utf-8'))
                texto_frente += f" [sound:{nombre_archivo_frente}]"
            except Exception as e:
                print(f"Error procesando audio del frente para {nombre_limpio}: {e}")
            finally:
                # ¡La magia ocurre aquí! Se borra sin importar qué haya pasado arriba
                if os.path.exists(nombre_archivo_frente):
                    os.remove(nombre_archivo_frente)

            # 3. AUDIO EJEMPLO CON LIMPIEZA OBLIGATORIA
            if texto_ejemplo:
                nombre_archivo_ejemplo = f"ia_audio_ejemplo_{nombre_limpio}_{i}.mp3"
                try:
                    gTTS(texto_ejemplo, lang='en').save(nombre_archivo_ejemplo)
                    with open(nombre_archivo_ejemplo, "rb") as f:
                        invoke_anki('storeMediaFile', filename=nombre_archivo_ejemplo, data=base64.b64encode(f.read()).decode('utf-8'))
                    texto_reverso += f"<br><br>🔊 <b>Listen:</b> [sound:{nombre_archivo_ejemplo}]"
                except Exception as e:
                    print(f"Error procesando audio del ejemplo para {nombre_limpio}: {e}")
                finally:
                    if os.path.exists(nombre_archivo_ejemplo):
                        os.remove(nombre_archivo_ejemplo)

            # 4. INYECTAR A ANKI
            try:
                invoke_anki('addNote', note={
                    "deckName": NOMBRE_MAZO,
                    "modelName": NOMBRE_TIPO_CARTA,
                    "fields": {CAMPO_FRENTE: texto_frente, CAMPO_REVERSO: texto_reverso},
                    "options": {"allowDuplicate": False},
                    "tags": ["generado_por_ia_python"]
                })
                cartas_agregadas += 1
            except:
                pass

        historial_conversacion = "" 
        return {"mensaje": f"🎉 ¡Éxito! Se inyectaron {cartas_agregadas} cartas nuevas a tu mazo de Anki."}
        
    except Exception as e:
        return {"mensaje": f"⚠️ Error en el procesamiento: {str(e)}"}
# uvicorn main:app --reload