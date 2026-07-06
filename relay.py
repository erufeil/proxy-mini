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
