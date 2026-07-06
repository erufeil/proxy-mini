# xero-proxy — Patrones de código verificados

## Entry point: proxy_server.py

```python
# -*- coding: utf-8 -*-
import asyncio
import logging
from aiohttp import web
import config
from auth import validar_token
from relay import manejar_relay
from yt_transcript import manejar_yt_transcript
from connect_proxy import iniciar_connect_proxy

logging.basicConfig(level=config.LOG_LEVEL, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

async def health(request):
    return web.json_response({'ok': True, 'version': config.VERSION})

def crear_app():
    app = web.Application(middlewares=[validar_token])
    app.router.add_get('/health', health)        # sin auth
    app.router.add_post('/relay', manejar_relay)
    app.router.add_post('/yt-transcript', manejar_yt_transcript)
    return app

async def main():
    app = crear_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.HOST, config.RELAY_PORT)
    await site.start()
    logger.info(f'REST relay escuchando en {config.HOST}:{config.RELAY_PORT}')

    if config.CONNECT_ENABLED:
        await iniciar_connect_proxy(config.HOST, config.CONNECT_PORT)
        logger.info(f'CONNECT proxy en {config.HOST}:{config.CONNECT_PORT}')

    await asyncio.Event().wait()  # mantener proceso vivo

if __name__ == '__main__':
    asyncio.run(main())
```

---

## auth.py — Middleware de token + rate limiting

```python
# Valida Bearer token en Authorization header y aplica rate limiting por IP.
# /health es pública (sin auth, pero sí cuenta para el rate limit).
import time
from collections import defaultdict
import config
from aiohttp import web

RUTAS_PUBLICAS = {'/health'}

# Rate limiter simple en memoria. Se resetea al reiniciar el proceso.
_ventanas: dict[str, list[float]] = defaultdict(list)

def _rate_ok(ip: str, rpm: int) -> bool:
    ahora = time.monotonic()
    ventana = [t for t in _ventanas[ip] if ahora - t < 60]  # limpia timestamps > 60s
    if len(ventana) >= rpm:
        _ventanas[ip] = ventana
        return False
    ventana.append(ahora)
    _ventanas[ip] = ventana
    return True

@web.middleware
async def validar_token(request, handler):
    if not _rate_ok(request.remote or 'desconocido', config.RATE_LIMIT_RPM):
        return web.json_response({'ok': False, 'error': 'Rate limit excedido'}, status=429)

    if request.path in RUTAS_PUBLICAS:
        return await handler(request)

    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer ') or auth[7:] != config.PROXY_TOKEN:
        return web.json_response({'ok': False, 'error': 'Unauthorized'}, status=401)

    return await handler(request)
```

---

## relay.py — Fetch genérico

```python
# Hace fetch de una URL en nombre del cliente.
# Solo permite hosts en PROXY_ALLOWED_HOSTS.

import base64
import time
from urllib.parse import urlparse
import aiohttp
import config
from aiohttp import web

async def manejar_relay(request):
    datos = await request.json()
    url     = datos.get('url', '').strip()
    metodo  = datos.get('method', 'GET').upper()
    headers = datos.get('headers', {})
    timeout = int(datos.get('timeout', 30))

    if not url:
        return web.json_response({'ok': False, 'error': 'url requerida'}, status=400)

    host = urlparse(url).hostname or ''
    if not _host_permitido(host):
        return web.json_response({'ok': False, 'error': f'Host no permitido: {host}'}, status=403)

    t0 = time.monotonic()
    try:
        timeout_cfg = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(timeout=timeout_cfg) as sesion:
            async with sesion.request(metodo, url, headers=headers) as resp:
                cuerpo = await resp.read()
                ms = int((time.monotonic() - t0) * 1000)
                return web.json_response({
                    'ok': True,
                    'status': resp.status,
                    'headers': dict(resp.headers),
                    'body_b64': base64.b64encode(cuerpo).decode(),
                    'ms': ms,
                })
    except Exception as e:
        return web.json_response({'ok': False, 'error': str(e)}, status=502)

def _host_permitido(host: str) -> bool:
    if not config.PROXY_ALLOWED_HOSTS:
        return False  # sin allowlist → todo bloqueado
    return any(host == h or host.endswith('.' + h) for h in config.PROXY_ALLOWED_HOSTS)
```

---

## yt_transcript.py — Endpoint YouTube

```python
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
```

---

## connect_proxy.py — CONNECT proxy (Modo B)

```python
# HTTP CONNECT proxy puro asyncio. Solo para uso sin Cloudflare (puerto directo).
# Valida Proxy-Authorization: Bearer TOKEN en el CONNECT inicial.
# Luego hace pipe bidireccional entre cliente y destino.

import asyncio
import re
import config

async def iniciar_connect_proxy(host: str, port: int):
    server = await asyncio.start_server(_handle_connect, host, port)
    asyncio.create_task(server.serve_forever())

async def _handle_connect(reader, writer):
    try:
        cabecera = await reader.readuntil(b'\r\n\r\n')
        linea = cabecera.split(b'\r\n')[0].decode()
        headers_raw = cabecera.decode()

        # Validar token
        auth_match = re.search(r'Proxy-Authorization:\s*Bearer\s+(\S+)', headers_raw, re.IGNORECASE)
        if not auth_match or auth_match.group(1) != config.PROXY_TOKEN:
            writer.write(b'HTTP/1.1 407 Proxy Authentication Required\r\n\r\n')
            await writer.drain(); writer.close(); return

        # Parsear CONNECT host:port
        match = re.match(r'CONNECT\s+([^:]+):(\d+)\s+HTTP', linea)
        if not match:
            writer.write(b'HTTP/1.1 400 Bad Request\r\n\r\n')
            await writer.drain(); writer.close(); return

        destino_host, destino_port = match.group(1), int(match.group(2))

        # Verificar allowlist
        if config.PROXY_ALLOWED_HOSTS and not any(
            destino_host == h or destino_host.endswith('.' + h)
            for h in config.PROXY_ALLOWED_HOSTS
        ):
            writer.write(b'HTTP/1.1 403 Forbidden\r\n\r\n')
            await writer.drain(); writer.close(); return

        dest_reader, dest_writer = await asyncio.open_connection(destino_host, destino_port)
        writer.write(b'HTTP/1.1 200 Connection Established\r\n\r\n')
        await writer.drain()

        # Pipe bidireccional
        await asyncio.gather(
            _pipe(reader, dest_writer),
            _pipe(dest_reader, writer),
            return_exceptions=True,
        )
    except Exception:
        pass
    finally:
        try: writer.close()
        except Exception: pass

async def _pipe(src, dst):
    try:
        while True:
            data = await src.read(65536)
            if not data:
                break
            dst.write(data)
            await dst.drain()
    except Exception:
        pass
    finally:
        try: dst.close()
        except Exception: pass
```

---

## config.py

```python
import os
from dotenv import load_dotenv
load_dotenv()

VERSION = '1.0.0'
HOST    = os.getenv('HOST', '0.0.0.0')

# REST relay (Modo A — Cloudflare)
RELAY_PORT = int(os.getenv('PROXY_RELAY_PORT', 8080))

# CONNECT proxy (Modo B — puerto directo)
CONNECT_ENABLED = os.getenv('PROXY_CONNECT_ENABLED', 'false').lower() == 'true'
CONNECT_PORT    = int(os.getenv('PROXY_CONNECT_PORT', 8888))

# Seguridad
PROXY_TOKEN = os.getenv('PROXY_TOKEN', '')
if not PROXY_TOKEN:
    raise RuntimeError('PROXY_TOKEN no configurado')

# Allowlist de dominios para relay y CONNECT
# Separados por coma. Vacío = bloquea todo.
_hosts_raw = os.getenv('PROXY_ALLOWED_HOSTS', 'youtube.com,ytimg.com,googlevideo.com,yt3.ggpht.com')
PROXY_ALLOWED_HOSTS = [h.strip() for h in _hosts_raw.split(',') if h.strip()]

# Rate limiting (max requests por minuto por IP)
RATE_LIMIT_RPM = int(os.getenv('PROXY_RATE_LIMIT_RPM', 60))

# Logging
LOG_LEVEL = os.getenv('PROXY_LOG_LEVEL', 'INFO').upper()
```

---

## Integración en PDFexport (services/youtube_to_md.py)

Cuando `YOUTUBE_RELAY_URL` está configurado, llamar al relay en lugar de
usar youtube-transcript-api localmente:

```python
# En _obtener_transcripcion(), antes de crear _crear_ytt():
relay_url = config.YOUTUBE_RELAY_URL  # nueva var en PDFexport
if relay_url:
    return _obtener_via_relay(relay_url, video_id, idioma)
# else: flujo normal (ytt local o con proxy)

def _obtener_via_relay(relay_url: str, video_id: str, idioma: str) -> tuple:
    import requests, os
    token = config.YOUTUBE_RELAY_TOKEN
    r = requests.post(
        f'{relay_url.rstrip("/")}/yt-transcript',
        json={'video_id': video_id, 'idioma': idioma},
        headers={'Authorization': f'Bearer {token}'},
        timeout=30,
    )
    r.raise_for_status()
    d = r.json()
    if not d.get('ok'):
        raise ValueError(d.get('error', 'Error en relay'))
    fragmentos = d['fragmentos']
    idioma_usado = d['idioma']
    partes = [re.sub(r'\[.*?\]', '', f['text']).strip() for f in fragmentos if f.get('text')]
    texto = ' '.join(p for p in partes if p)
    return re.sub(r' {2,}', ' ', texto).strip(), idioma_usado
```

Nuevas vars en PDFexport config.py:
```python
YOUTUBE_RELAY_URL   = os.getenv('YOUTUBE_RELAY_URL', '').strip()
YOUTUBE_RELAY_TOKEN = os.getenv('YOUTUBE_RELAY_TOKEN', '').strip()
```
