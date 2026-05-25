import json
import os
import urllib.request
import base64
import re  # 👈 Añadimos esta librería nativa para limpiar los paréntesis
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

# 1. Leer el archivo de estudio
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

# 2. Conectamos con tu clave
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("❌ Falla: GEMINI_API_KEY no está definida en tu .env")

client = genai.Client(api_key=api_key)

# 3. El Prompt Arquitecto
prompt = f"""
Eres un creador de flashcards experto. Analiza el siguiente texto proporcionado por el usuario.
REGLA 1: Si el texto está en español y no contiene inglés, devuelve estrictamente una lista vacía: []
REGLA 2: Identifica el tipo de contenido (Vocabulario, Diferencia de palabras, Gramática, Ejercicio).
REGLA 3: Devuelve ESTRICTAMENTE un arreglo JSON puro (JSON array). 
Ejemplo de formato exacto esperado:
[
  {{
    "frente": "Tu título o palabra aquí",
    "reverso": "Tu explicación en HTML aquí",
    "ejemplo_ingles": "Escribe AQUÍ SOLO la oración principal de ejemplo en inglés. Si no hay ejemplo, déjalo en blanco."
  }}
]
REGLA 4: El "reverso" debe estar en HTML limpio (<br>, <b>, <i>). Debe contener la explicación, los ejemplos y sus traducciones al español.

Texto a procesar:
{texto_estudio}
"""

print("🧠 Gemini está analizando y estructurando la información...")
response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)

# 4. Procesar respuesta
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
    print("❌ Error: Gemini devolvió un formato ilegible. Revisa tu lectura.txt.")
    exit()

if not lista_cartas:
    print("❌ Gemini detectó que el texto no contiene material válido o hubo un error.")
    exit()

print(
    f"✅ Gemini creó {len(lista_cartas)} cartas. Generando audios limpios y enviando a Anki..."
)

# 5. Inyectar cartas y audios directamente a AnkiConnect
try:
    invoke("createDeck", deck=NOMBRE_MAZO)
except Exception:
    pass

cartas_agregadas = 0
for i, carta in enumerate(lista_cartas):
    texto_frente = str(carta.get("frente", "")).strip()
    texto_reverso = str(carta.get("reverso", "")).strip()
    texto_ejemplo = str(carta.get("ejemplo_ingles", "")).strip()

    # --- 1. LÓGICA DE AUDIO (FRENTE LIMPIO) ---
    nombre_limpio_frente = "".join(c if c.isalnum() else "_" for c in texto_frente[:20])
    nombre_archivo_frente = f"ia_audio_frente_{nombre_limpio_frente}_{i}.mp3"

    try:
        # 💥 AQUÍ ESTÁ EL TRUCO: Creamos una versión de texto SIN paréntesis solo para el audio
        # re.sub busca los paréntesis y todo lo que esté adentro y lo reemplaza por nada ''
        texto_audio_frente = re.sub(r"\(.*?\)", "", texto_frente).strip()

        tts_frente = gTTS(texto_audio_frente, lang="en")
        tts_frente.save(nombre_archivo_frente)
        with open(nombre_archivo_frente, "rb") as f:
            audio_frente_b64 = base64.b64encode(f.read()).decode("utf-8")
        invoke("storeMediaFile", filename=nombre_archivo_frente, data=audio_frente_b64)
        os.remove(nombre_archivo_frente)

        # Al texto visual original (que mantiene los paréntesis) le añadimos el sonido
        texto_frente += f" [sound:{nombre_archivo_frente}]"
    except Exception as e:
        print(f"⚠️ No se pudo generar audio para el frente '{texto_frente}': {e}")

    # --- 2. LÓGICA DE AUDIO (EJEMPLO) ---
    if texto_ejemplo:
        nombre_limpio_ejemplo = "".join(
            c if c.isalnum() else "_" for c in texto_ejemplo[:15]
        )
        nombre_archivo_ejemplo = f"ia_audio_ejemplo_{nombre_limpio_ejemplo}_{i}.mp3"

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

            texto_reverso += f"<br><br>🔊 <b>Listen to the example:</b> [sound:{nombre_archivo_ejemplo}]"
        except Exception as e:
            print(f"⚠️ No se pudo generar audio para el ejemplo: {e}")

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
    f"🎉 ¡Proceso terminado! Se inyectaron {cartas_agregadas} cartas con AUDIO DOBLE LIMPIO a tu mazo '{NOMBRE_MAZO}'."
)
