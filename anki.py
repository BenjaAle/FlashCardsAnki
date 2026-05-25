import json
import os
import urllib.request
from dotenv import load_dotenv
from google import genai

# ==========================================
# Configuración de Anki
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
        f"Se ha creado '{archivo_lectura}'. Pega tu texto ahí y vuelve a ejecutar."
    )
    exit()

with open(archivo_lectura, "r", encoding="utf-8") as f:
    texto_estudio = f.read().strip()

if not texto_estudio:
    print(f"El archivo '{archivo_lectura}' está vacío.")
    exit()

# 2. Conectamos con tu clave
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("Error: GEMINI_API_KEY no está definida en tu .env")

client = genai.Client(api_key=api_key)

# Prompt principal
prompt = f"""
Eres un creador de flashcards experto. Analiza el siguiente texto proporcionado por el usuario.
REGLA 1: Si el texto está en español y no contiene inglés, devuelve estrictamente una lista vacía: []
REGLA 2: Identifica el tipo de contenido (Vocabulario, Diferencia de palabras, Gramática, Ejercicio).
REGLA 3: Devuelve ESTRICTAMENTE un arreglo JSON puro (JSON array). No envuelvas la respuesta en objetos.
Ejemplo de formato exacto esperado:
[
  {{
    "frente": "Tu título o palabra aquí",
    "reverso": "Tu explicación en HTML aquí"
  }}
]
REGLA 4: El "reverso" debe estar en HTML limpio (<br>, <b>, <i>). Debe contener la explicación, ejemplos y traducciones. No uses lenguaje conversacional.

Texto a procesar:
{texto_estudio}
"""

print("Analizando...")
response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)

# Procesar respuesta y corregir formato
respuesta_limpia = response.text.replace("```json", "").replace("```", "").strip()

try:
    datos_brutos = json.loads(respuesta_limpia)

    # Por si se envolvió la lista en un diccionario, se extrae
    if isinstance(datos_brutos, dict):
        lista_cartas = next(
            (valor for valor in datos_brutos.values() if isinstance(valor, list)), []
        )
    elif isinstance(datos_brutos, list):
        lista_cartas = datos_brutos
    else:
        lista_cartas = []

except json.JSONDecodeError:
    print("Error, se devolvió un formato ilegible. Revisa tu lectura.txt.")
    print("Respuesta cruda:", respuesta_limpia)
    exit()

if not lista_cartas:
    print(
        "Se detectó que el texto no contiene material válido o hubo un error de formato."
    )
    exit()

print(f"Se crearon {len(lista_cartas)} cartas. Enviando directamente a Anki...")

# Ingresar cartas directamente a AnkiConnect
print(f"Verificando mazo '{NOMBRE_MAZO}'...")
try:
    # Este comando crea el mazo si no existe, o no hace nada si ya existe
    invoke("createDeck", deck=NOMBRE_MAZO)
except Exception as e:
    print(f"⚠️ Aviso al crear el mazo: {e}")

cartas_agregadas = 0
for carta in lista_cartas:
    nota = {
        "deckName": NOMBRE_MAZO,
        "modelName": NOMBRE_TIPO_CARTA,
        "fields": {
            CAMPO_FRENTE: str(carta.get("frente", "")),
            CAMPO_REVERSO: str(carta.get("reverso", "")),
        },
        "options": {"allowDuplicate": False},
        "tags": ["generado_por_ia_python"],
    }

    try:
        invoke("addNote", note=nota)
        cartas_agregadas += 1
    except Exception as e:
        print(f"Error al agregar la carta '{carta.get('frente', '')}': {e}")

print(
    f"Proceso Terminado. Se inyectaron {cartas_agregadas} cartas directamente a tu mazo '{NOMBRE_MAZO}'."
)