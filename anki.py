import json
import os
import urllib.request
import base64
import re
import requests
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


# Funciones del puente de AnkiConnect
def request(action, **params):
    return {"action": action, "version": 6, "params": params}


def invoke(action, **params):
    requestJson = json.dumps(request(action, **params)).encode("utf-8")
    response = json.load(
        urllib.request.urlopen(
            urllib.request.Request("http://127.0.0.1:8765", requestJson)
        )
    )
    if response["error"] is not None:
        raise Exception(response["error"])
    return response["result"]


# Cargar variables de entorno
load_dotenv()

archivo_lectura = "lectura.txt"

if not os.path.exists(archivo_lectura):
    with open(archivo_lectura, "w", encoding="utf-8") as f:
        pass
    print(
        f"📄 Se ha creado '{archivo_lectura}'. Pega tu texto ahí y vuelve a ejecutar."
    )
    exit()

with open(archivo_lectura, "r", encoding="utf-8") as f:
    texto_estudio = f.read().strip()

if not texto_estudio:
    print(f"⚠️ El archivo '{archivo_lectura}' está vacío.")
    exit()

api_key_gemini = os.getenv("GEMINI_API_KEY")
api_key_pexels = os.getenv("PEXELS_API_KEY")

if not api_key_gemini:
    raise ValueError("❌ Falla: GEMINI_API_KEY no está definida en tu .env")
if not api_key_pexels:
    raise ValueError("❌ Falla: PEXELS_API_KEY no está definida en tu .env.")

client = genai.Client(api_key=api_key_gemini)

# 3. El Prompt Arquitecto (¡REGLA 4 REPARADA Y BLINDADA!)
prompt = f"""
Eres un creador de flashcards experto. Analiza el texto proporcionado.
REGLA 1: Si el texto está en español y no contiene inglés, devuelve estrictamente una lista vacía: []
REGLA 2: Identifica el tipo de contenido.
REGLA 3: Devuelve ESTRICTAMENTE un arreglo JSON puro. 
Ejemplo de formato exacto esperado:
[
  {{
    "frente": "Palabra o concepto",
    "reverso": "Definición en HTML con ejemplos",
    "ejemplo_ingles": "Oración de ejemplo limpia en inglés, o déjalo en blanco.",
    "termino_imagen": "Una palabra clave para buscar la foto."
  }}
]
REGLA 4: El campo "reverso" DEBE contener obligatoriamente tres cosas separadas por líneas:
1. El significado o explicación en español (destaca lo importante con <b>).
2. La oración de ejemplo en inglés completa.
3. La traducción de esa oración de ejemplo al español (en cursiva usando <i>).
Usa etiquetas <br> para separar visualmente estos elementos de forma elegante. No uses lenguaje conversacional.

Texto a procesar:
{texto_estudio}
"""

print("🧠 Gemini está analizando y diseñando la estrategia visual...")
response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)

respuesta_limpia = response.text.replace("```json", "").replace("```", "").strip()

try:
    datos_brutos = json.loads(respuesta_limpia)
    if isinstance(datos_brutos, dict):
        lista_cartas = next(
            (valor for valor in datos_brutos.values() if isinstance(valor, list)), []
        )
    elif isinstance(datos_brutos, list):
        lista_cartas = datos_brutos
    else:
        lista_cartas = []
except json.JSONDecodeError:
    print("❌ Error: Gemini devolvió un formato ilegible.")
    exit()

if not lista_cartas:
    print("❌ Gemini detectó que el texto no contiene material válido.")
    exit()

print(
    f"✅ Gemini creó {len(lista_cartas)} cartas. Descargando medios y enviando a Anki..."
)

try:
    invoke("createDeck", deck=NOMBRE_MAZO)
except Exception:
    pass

cartas_agregadas = 0
for i, carta in enumerate(lista_cartas):
    texto_frente = str(carta.get("frente", "")).strip()
    texto_reverso = str(carta.get("reverso", "")).strip()
    texto_ejemplo = str(carta.get("ejemplo_ingles", "")).strip()
    termino_imagen = str(carta.get("termino_imagen", "")).strip()

    nombre_limpio = "".join(c if c.isalnum() else "_" for c in texto_frente[:15])

    # --- 1. LÓGICA DE IMAGEN (PEXELS) ---
    if termino_imagen:
        print(f"   📸 Buscando imagen en Pexels para: '{termino_imagen}'...")
        try:
            url_busqueda = (
                f"https://api.pexels.com/v1/search?query={termino_imagen}&per_page=1"
            )
            headers = {"Authorization": api_key_pexels}
            respuesta_pexels = requests.get(url_busqueda, headers=headers, timeout=5)

            if respuesta_pexels.status_code == 200:
                datos_pexels = respuesta_pexels.json()
                if datos_pexels.get("photos") and len(datos_pexels["photos"]) > 0:
                    url_imagen = datos_pexels["photos"][0]["src"]["medium"]
                    respuesta_img = requests.get(url_imagen, timeout=5)
                    if respuesta_img.status_code == 200:
                        nombre_archivo_img = f"ia_img_{nombre_limpio}_{i}.jpg"
                        img_b64 = base64.b64encode(respuesta_img.content).decode(
                            "utf-8"
                        )
                        invoke(
                            "storeMediaFile", filename=nombre_archivo_img, data=img_b64
                        )
                        texto_reverso = (
                            f"<img src='{nombre_archivo_img}'><br><br>" + texto_reverso
                        )
                else:
                    print(
                        f"   ⚠️ Pexels no encontró ninguna foto para '{termino_imagen}'."
                    )
        except Exception as e:
            print(f"   ⚠️ No se pudo obtener imagen: {e}")

    # --- 2. LÓGICA DE AUDIO (FRENTE) ---
    nombre_archivo_frente = f"ia_audio_frente_{nombre_limpio}_{i}.mp3"
    try:
        texto_audio_frente = re.sub(r"\(.*?\)", "", texto_frente).strip()
        tts_frente = gTTS(texto_audio_frente, lang="en")
        tts_frente.save(nombre_archivo_frente)
        with open(nombre_archivo_frente, "rb") as f:
            audio_frente_b64 = base64.b64encode(f.read()).decode("utf-8")
        invoke("storeMediaFile", filename=nombre_archivo_frente, data=audio_frente_b64)
        os.remove(nombre_archivo_frente)
        texto_frente += f" [sound:{nombre_archivo_frente}]"
    except Exception as e:
        print(f"   ⚠️ No se pudo generar audio para el frente: {e}")

    # --- 3. LÓGICA DE AUDIO (EJEMPLO) ---
    if texto_ejemplo:
        nombre_archivo_ejemplo = f"ia_audio_ejemplo_{nombre_limpio}_{i}.mp3"
        try:
            tts_ejemplo = gTTS(texto_ejemplo, lang="en")
            tts_ejemplo.save(nombre_archivo_ejemplo)
            with open(nombre_archivo_ejemplo, "rb") as f:
                audio_ejemplo_b64 = base64.b64encode(f.read()).decode("utf-8")
            invoke(
                "storeMediaFile",
                filename=nombre_archivo_ejemplo,
                data=audio_ejemplo_b64,
            )
            os.remove(nombre_archivo_ejemplo)
            # Enganchamos el botón de audio abajo del texto que Gemini ya escribió
            texto_reverso += f"<br><br>🔊 <b>Listen to the example:</b> [sound:{nombre_archivo_ejemplo}]"
        except Exception as e:
            pass

    # --- INYECCIÓN A ANKI ---
    nota = {
        "deckName": NOMBRE_MAZO,
        "modelName": NOMBRE_TIPO_CARTA,
        "fields": {CAMPO_FRENTE: texto_frente, CAMPO_REVERSO: texto_reverso},
        "options": {"allowDuplicate": False},
        "tags": ["generado_por_ia_python"],
    }

    try:
        invoke("addNote", note=nota)
        cartas_agregadas += 1
    except Exception as e:
        print(f"⚠️ Error al agregar la carta '{texto_frente}': {e}")

print(
    f"🎉 ¡Proceso terminado! Se inyectaron {cartas_agregadas} cartas completas a tu mazo '{NOMBRE_MAZO}'."
)
