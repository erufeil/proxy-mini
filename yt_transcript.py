# Usa youtube-transcript-api localmente (IP on-premise, no bloqueada).
# Devuelve fragmentos raw como JSON para que PDFexport arme el Markdown.

from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
    CouldNotRetrieveTranscript,
)
from aiohttp import web
import asyncio

async def manejar_yt_transcript(request):
    datos = await request.json()
    video_id = datos.get('video_id', '').strip()
    idioma   = datos.get('idioma', 'auto')

    if not video_id:
        return web.json_response({'ok': False, 'error': 'video_id requerido'}, status=400)

    try:
        # youtube-transcript-api es síncrono → correr en thread pool
        resultado = await asyncio.get_event_loop().run_in_executor(
            None, _obtener_transcript, video_id, idioma
        )
        return web.json_response({'ok': True, **resultado})
    except ValueError as e:
        return web.json_response({'ok': False, 'error': str(e)}, status=422)
    except Exception as e:
        return web.json_response({'ok': False, 'error': str(e)}, status=502)

def _obtener_transcript(video_id: str, idioma: str) -> dict:
    ytt = YouTubeTranscriptApi()

    if idioma == 'auto':
        lista = ytt.list(video_id)
        try:
            t = lista.find_manually_created_transcript(['es', 'en'])
        except NoTranscriptFound:
            t = lista.find_generated_transcript(['es', 'en'])
        fetched = t.fetch()
        idioma_usado = t.language_code
    else:
        try:
            fetched = ytt.fetch(video_id, languages=[idioma])
            idioma_usado = idioma
        except NoTranscriptFound:
            raise ValueError(f"No hay transcripción en idioma '{idioma}'")
        except TranscriptsDisabled:
            raise ValueError("El video no tiene subtítulos habilitados")

    fragmentos = fetched.to_raw_data()
    return {'fragmentos': fragmentos, 'idioma': idioma_usado}
