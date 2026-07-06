# xero-proxy — Plan de implementación

## Tabla de etapas

| Etapa | Descripción | Archivos | Estado |
|-------|-------------|----------|--------|
| 1 | Estructura base + /health | config.py, proxy_server.py, auth.py | Completa |
| 2 | REST relay + allowlist | relay.py | Completa |
| 3 | Endpoint /yt-transcript | yt_transcript.py | Completa |
| 4 | CONNECT proxy (Modo B) | connect_proxy.py | Completa |
| 5 | Rate limiting | auth.py (extender) | Completa |
| 6 | Docker + README | Dockerfile, docker-compose.yml | Completa (build de Docker no verificado: Docker no disponible en este entorno) |
| 7 | Integración PDFexport | services/youtube_to_md.py, config.py | Pendiente |

---

## Etapa 1 — Estructura base + /health

**Objetivo:** proyecto corriendo, /health responde, token requerido en todo lo demás.

Archivos a crear:
- `config.py` — leer todas las env vars, validar PROXY_TOKEN al arrancar
- `auth.py` — middleware aiohttp que valida Bearer token (excluyendo /health)
- `proxy_server.py` — entry point, monta app aiohttp, arranca servidor
- `requirements.txt` — aiohttp, python-dotenv, youtube-transcript-api
- `.env.example`

Verificación (con `PROXY_RELAY_PORT=8080`, el default) — ejecutada y confirmada:
```bash
curl http://localhost:8080/health
# → 200 {"ok": true, "version": "1.0.0"}

curl http://localhost:8080/relay
# → 401 (sin token; el middleware corre antes que el ruteo, incluso en rutas inexistentes)

curl http://localhost:8080/relay -H "Authorization: Bearer mal-token"
# → 401

curl http://localhost:8080/relay -H "Authorization: Bearer TOKEN"
# → 404 (token válido, pero /relay todavía no existe — se crea en Etapa 2, ahí dará 400 sin body)
```

---

## Etapa 2 — REST relay genérico

**Objetivo:** `POST /relay` hace fetch de cualquier URL en la allowlist.

Archivos:
- `relay.py` — función `manejar_relay` con cliente aiohttp
- Actualizar `proxy_server.py` para registrar la ruta

Verificación:
```bash
curl -X POST http://localhost:8080/relay \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://httpbin.org/get"}'
# → {"ok": false, "error": "Host no permitido: httpbin.org"}

# Agregar httpbin.org a PROXY_ALLOWED_HOSTS temporalmente:
curl -X POST http://localhost:8080/relay \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://httpbin.org/get"}'
# → {"ok": true, "status": 200, "body_b64": "...", "ms": 123}
```

---

## Etapa 3 — Endpoint /yt-transcript

**Objetivo:** transcribir video de YouTube desde la IP local del proxy.

Archivos:
- `yt_transcript.py` — `manejar_yt_transcript` + `_obtener_transcript`
- Actualizar `proxy_server.py` para registrar la ruta

Verificación:
```bash
curl -X POST http://localhost:8080/yt-transcript \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"video_id": "4-R4qB9rH1U", "idioma": "auto"}'
# → {"ok": true, "fragmentos": [...], "idioma": "en"}

# Video sin subtítulos:
curl -X POST http://localhost:8080/yt-transcript \
  -H "Authorization: Bearer TOKEN" \
  -d '{"video_id": "ID_SIN_CC", "idioma": "auto"}'
# → {"ok": false, "error": "El video no tiene subtítulos habilitados"}
```

---

## Etapa 4 — CONNECT proxy (Modo B)

**Objetivo:** proxy HTTP CONNECT para uso con `requests` directamente (sin Cloudflare).

Archivos:
- `connect_proxy.py` — servidor asyncio que maneja CONNECT + pipe bidireccional
- Actualizar `proxy_server.py` para arrancar el segundo servidor si `PROXY_CONNECT_ENABLED=true`

Verificación:
```bash
# Con PROXY_CONNECT_ENABLED=true, PROXY_CONNECT_PORT=8888
curl -x http://localhost:8888 \
  -H "Proxy-Authorization: Bearer TOKEN" \
  https://www.youtube.com/watch?v=4-R4qB9rH1U
# → HTML de YouTube (200)

# Sin token:
curl -x http://localhost:8888 https://youtube.com
# → 407
```

---

## Etapa 5 — Rate limiting

**Objetivo:** evitar abuso. Max N requests/minuto por IP de origen.

Archivos:
- `auth.py` (extender) — agregar dict en memoria con timestamps por IP
- La limpieza de timestamps viejos ocurre en cada check (no hay tarea background)

Configuración: `PROXY_RATE_LIMIT_RPM=60` (default)

---

## Etapa 6 — Docker + README

**Objetivo:** imagen Docker lista para deploy en servidor on-premise.

Archivos:
- `Dockerfile` — python:3.11-slim, EXPOSE 8080 8888
- `docker-compose.yml` — con env_file y restart
- `README.md` — instrucciones de deploy, configuración de Cloudflare tunnel

Sección README debe incluir:
1. Requisitos (Docker, cloudflared instalado)
2. Generar PROXY_TOKEN
3. `.env` mínimo
4. `docker compose up -d`
5. Configurar cloudflare tunnel (config.yml)
6. Configurar PDFexport con YOUTUBE_RELAY_URL

---

## Etapa 7 — Integración PDFexport

**Objetivo:** PDFexport usa el relay para YouTube en vez de conectarse directo.

Archivos a modificar en PDFexport:
- `config.py` — agregar `YOUTUBE_RELAY_URL`, `YOUTUBE_RELAY_TOKEN`
- `services/youtube_to_md.py` — función `_obtener_via_relay()`, prioridad en `_obtener_transcripcion()`

Prioridad de configuración en `_obtener_transcripcion()`:
```
1. YOUTUBE_RELAY_URL configurada → _obtener_via_relay()
2. YOUTUBE_PROXY_URL configurada → _crear_ytt() con GenericProxyConfig
3. data/youtube_cookies.txt existe → _crear_ytt() con Session+cookies
4. Sin nada → _crear_ytt() sin config (funciona si IP no bloqueada)
```

Verificación end-to-end:
```bash
# En .env del PDFexport:
YOUTUBE_RELAY_URL=https://proxy-s12.xero-one.com
YOUTUBE_RELAY_TOKEN=TOKEN

# Intentar convertir video desde la UI → debe funcionar desde IP cloud
```

---

## Notas de deploy

### Cloudflare tunnel

El tunnel debe apuntar al servicio HTTP interno (no HTTPS — CF maneja TLS):

```
hostname: proxy-s12.xero-one.com → http://localhost:8080
```

El cliente (PDFexport) llama a `https://proxy-s12.xero-one.com` (HTTPS via CF).
El tunnel lo lleva a `http://localhost:8080` (HTTP interno). Correcto.

### No exponer CONNECT proxy en Cloudflare

El Modo B (CONNECT proxy, puerto 8888) NO funciona a través de CF tunnel porque
CF no soporta TCP tunnel post-CONNECT. Solo usar Modo B si:
- Se abre el puerto 8888 directamente en el firewall
- Y se configura `YOUTUBE_PROXY_URL=http://TOKEN@ip-publica:8888` en PDFexport

### Seguridad en producción

- `PROXY_TOKEN` mínimo 32 chars: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
- `PROXY_ALLOWED_HOSTS` debe ser lo más restrictivo posible
- No loguear el token nunca
- El servidor no necesita puerto 8888 abierto si solo se usa Modo A
