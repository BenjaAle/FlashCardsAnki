import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from google import genai

# 1. Cargar la clave de Gemini
load_dotenv()
api_key_gemini = os.getenv("GEMINI_API_KEY")
if not api_key_gemini:
    raise ValueError("❌ Falla: GEMINI_API_KEY no está definida en tu .env")

# 2. Inicializar Gemini y crear una "Sesión de Chat"
# A diferencia de generate_content, 'chats.create' guarda el historial automáticamente
client = genai.Client(api_key=api_key_gemini)
chat_ia = client.chats.create(
    model='gemini-2.5-flash',
    config={"system_instruction": "Eres un amigable y experto tutor de inglés. Responde de forma concisa, conversacional y educativa. Corrige al usuario si comete errores."}
)

# 3. Configurar FastAPI
app = FastAPI(title="Tutor de Inglés con IA")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Definimos la estructura de los datos que recibiremos del navegador
class Mensaje(BaseModel):
    texto: str

# Ruta para la página visual
@app.get("/", response_class=HTMLResponse)
def pagina_principal(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

# 🌟 NUEVA RUTA: El motor del chat
@app.post("/chat")
def conversar(mensaje: Mensaje):
    try:
        # Enviamos el texto del navegador a la memoria de Gemini
        respuesta = chat_ia.send_message(mensaje.texto)
        return {"respuesta": respuesta.text}
    except Exception as e:
        return {"respuesta": f"Lo siento, hubo un error de conexión: {str(e)}"}
    
# uvicorn main:app --reload