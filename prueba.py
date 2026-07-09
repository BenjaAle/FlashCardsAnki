import asyncio
import edge_tts

# El texto de prueba
texto_prueba = "Don't cut in when I'm speaking.That car just cut in front of me. Cut out the coupon. I'm trying to cut out junk food. The engine suddenly cut out. He's cut out for teaching."

# Diccionario con las 3 mejores voces
voces_a_probar = {
    "Ava": "en-US-AvaNeural",
    "Andrew": "en-US-AndrewNeural",
    "Ryan": "en-GB-RyanNeural",
}


async def generar_audios_comparativos():
    print("Iniciando la generación de audios de prueba...\n")

    for nombre, codigo_voz in voces_a_probar.items():
        archivo_salida = f"prueba_{nombre}.mp3"
        print(f"Generando audio con la voz de {nombre} ({codigo_voz})...")

        # Crea la comunicación con edge-tts
        comunicacion = edge_tts.Communicate(texto_prueba, codigo_voz)

        # Guarda el archivo
        await comunicacion.save(archivo_salida)
        print(f" -> Guardado exitosamente como: {archivo_salida}\n")

    print("¡Proceso terminado! Ya puedes reproducir los 3 archivos MP3 y compararlos.")


if __name__ == "__main__":
    asyncio.run(generar_audios_comparativos())
