import os
import asyncio
from dotenv import load_dotenv
from elevenlabs.client import AsyncElevenLabs

# Cargar variables de entorno (busca el archivo .env)
load_dotenv()

# Obtener la clave de la API
api_key_elevenlabs = os.getenv("ELEVENLABS_API_KEY")

# Inicializar el cliente asíncrono (Nueva API)
cliente_elevenlabs = AsyncElevenLabs(api_key=api_key_elevenlabs)

async def generar_audios_prueba():
    if not api_key_elevenlabs:
        print("❌ Error: No se encontró ELEVENLABS_API_KEY en tu archivo .env")
        return

    # El texto de prueba en inglés
    texto_prueba = (
        "Cut out the coupon."
        "I'm trying to cut out junk food."
        "The engine suddenly cut out."
        "He's cut out for teaching."
    )

    # 🌟 CÓDIGOS ÚNICOS GLOBALES (Voice IDs) de ElevenLabs
    voces = {
#        "Brian": "nPczCjzI2devNBz1zQrb",  # Masculino, acento muy natural (¡Ya comprobado!) (funciona pero no me gusta)
#        "Adam": "pNInz6obpgDQGcFmaJcg",   # Masculino, voz profunda y de narrador claro (fallo)
#        "Bella": "EXAVITQu4vr4xnSDxMaL",   # Femenina, voz suave, clara y estadounidense (me gustó)
        "Liam": "TX3LPaxmHKxFdv7VOQHJ"     # Masculino, joven y muy articulado (Estadounidense)
    }

    print("🚀 Iniciando prueba de generación de audio (Usando IDs directos)...\n")

    for nombre, voice_id in voces.items():
        nombre_archivo = f"prueba_audio_{nombre}.mp3"
        print(f"🎙️ Generando audio con la voz de '{nombre}' (ID: {voice_id})...")
        
        try:
            # Generar el audio directamente usando el ID oficial
            audio_stream = cliente_elevenlabs.text_to_speech.convert(
                voice_id=voice_id,
                text=texto_prueba,
                model_id="eleven_multilingual_v2",
                output_format="mp3_44100_128" # Calidad estándar MP3
            )
            
            # Guardar el audio en disco procesando los datos asíncronos
            with open(nombre_archivo, "wb") as archivo:
                async for chunk in audio_stream:
                    if chunk:
                        archivo.write(chunk)
                    
            print(f"✅ ¡Éxito! Audio guardado como: {nombre_archivo}\n")
            
        except Exception as e:
            print(f"❌ Error al generar audio con '{nombre}': {e}\n")
            # Si el error menciona quota o unauth, te avisa
            if "quota" in str(e).lower() or "credits" in str(e).lower():
                print("⚠️ Parece que te quedaste sin caracteres en tu límite gratuito.")
                break
            elif "unauthorized" in str(e).lower():
                print("⚠️ Problema de autorización. Revisa tu API Key y asegúrate de que le diste permiso de 'Acceso' al endpoint de Texto a Voz.")
                break

if __name__ == "__main__":
    asyncio.run(generar_audios_prueba())