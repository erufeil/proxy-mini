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
