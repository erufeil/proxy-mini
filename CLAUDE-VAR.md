# xero-proxy — Variables de entorno y contratos REST

## Variables de entorno (.env)

Todas las variables propias de xero-proxy (excepto `HOST`) llevan el prefijo `PROXY_`.
Este es el nombre que lee `config.py` y el que va en `.env` — no hay un nombre alternativo.

| Variable | Default | Descripción |
|----------|---------|-------------|
| `PROXY_TOKEN` | — (obligatorio) | Bearer token para auth. Min 32 chars. Generar: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `HOST` | `0.0.0.0` | IP donde escucha el servidor |
| `PROXY_RELAY_PORT` | `8080` | Puerto REST relay (Modo A) |
| `PROXY_CONNECT_ENABLED` | `false` | Activar CONNECT proxy (Modo B) |
| `PROXY_CONNECT_PORT` | `8888` | Puerto CONNECT proxy (Modo B) |
| `PROXY_ALLOWED_HOSTS` | `youtube.com,ytimg.com,googlevideo.com,yt3.ggpht.com` | Dominios permitidos (separados por coma). Incluye subdominios automáticamente. |
| `PROXY_RATE_LIMIT_RPM` | `60` | Max requests por minuto por IP (en memoria, no persistente) |
| `PROXY_LOG_LEVEL` | `INFO` | Nivel de logging (`DEBUG`, `INFO`, `WARNING`) |

No existe una variable propia de xero-proxy para "mi propia URL pública" (el tunnel la
resuelve Cloudflare). Ese valor solo se usa del lado cliente, ver `YOUTUBE_RELAY_URL` en
"Integración en PDFexport" más abajo.

### .env.example

```env
HOST=0.0.0.0
PROXY_RELAY_PORT=8080
PROXY_TOKEN=cambia_esto_por_token_seguro_de_32_chars
PROXY_ALLOWED_HOSTS=youtube.com,ytimg.com,googlevideo.com,yt3.ggpht.com
PROXY_CONNECT_ENABLED=false
PROXY_CONNECT_PORT=8888
PROXY_LOG_LEVEL=INFO
PROXY_RATE_LIMIT_RPM=60
```

---

## Contratos REST (Modo A)

### GET /health — sin autenticación

```
GET /health HTTP/1.1
```

Response `200`:
```json
{"ok": true, "version": "1.0.0"}
```

---

### POST /relay — fetch genérico

```
POST /relay HTTP/1.1
Authorization: Bearer {PROXY_TOKEN}
Content-Type: application/json

{
  "url": "https://www.youtube.com/watch?v=VIDEO_ID",
  "method": "GET",
  "headers": {"User-Agent": "Mozilla/5.0 ..."},
  "timeout": 30
}
```

Response `200`:
```json
{
  "ok": true,
  "status": 200,
  "headers": {"Content-Type": "text/html; charset=utf-8"},
  "body_b64": "<base64 del body>",
  "ms": 342
}
```

Response `403` (host no permitido):
```json
{"ok": false, "error": "Host no permitido: evil.com"}
```

Response `502` (error al fetch):
```json
{"ok": false, "error": "Connection timeout"}
```

---

### POST /yt-transcript — transcript de YouTube

```
POST /yt-transcript HTTP/1.1
Authorization: Bearer {PROXY_TOKEN}
Content-Type: application/json

{
  "video_id": "4-R4qB9rH1U",
  "idioma": "auto"
}
```

`idioma`: `"auto"` (primera disponible, manual antes que auto-generada) | `"es"` | `"en"` | cualquier código ISO 639-1

Response `200`:
```json
{
  "ok": true,
  "fragmentos": [
    {"text": "Hello and welcome", "start": 3.2, "duration": 2.4},
    {"text": "to another video", "start": 5.6, "duration": 2.3}
  ],
  "idioma": "en"
}
```

Response `422` (sin subtítulos / idioma no encontrado):
```json
{"ok": false, "error": "El video no tiene subtítulos habilitados"}
```

Response `502` (error YouTube):
```json
{"ok": false, "error": "Could not retrieve transcript ..."}
```

---

## CONNECT proxy (Modo B) — protocolo HTTP estándar

El cliente configura el proxy como `http://proxy-host:8888`.
La lib `requests` envía automáticamente:

```
CONNECT youtube.com:443 HTTP/1.1
Host: youtube.com:443
Proxy-Authorization: Bearer {PROXY_TOKEN}
```

El proxy responde:
```
HTTP/1.1 200 Connection Established
```

Luego el tráfico HTTPS fluye como TCP tunnel. El proxy no puede ver el contenido.

---

## Integración en PDFexport

### Nuevas vars en PDFexport config.py

```python
# Relay xero-proxy (Modo A — Cloudflare compatible)
YOUTUBE_RELAY_URL   = os.getenv('YOUTUBE_RELAY_URL', '').strip()
YOUTUBE_RELAY_TOKEN = os.getenv('YOUTUBE_RELAY_TOKEN', '').strip()
```

### PDFexport .env (producción con relay)

```env
YOUTUBE_RELAY_URL=https://proxy-s12.xero-one.com
YOUTUBE_RELAY_TOKEN=mismo_token_que_PROXY_TOKEN
```

### PDFexport .env (producción con CONNECT directo)

```env
YOUTUBE_PROXY_URL=http://TOKEN@ip-on-premise:8888
```

### Prioridad en youtube_to_md.py

```
1. YOUTUBE_RELAY_URL  → REST relay (Cloudflare)
2. YOUTUBE_PROXY_URL  → CONNECT proxy (puerto directo)
3. YOUTUBE_COOKIES_FILE / data/youtube_cookies.txt → sesión con cookies
4. Sin nada → ytt directo (solo funciona si la IP no está bloqueada)
```

---

## Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080 8888
CMD ["python", "proxy_server.py"]
```

```yaml
# docker-compose.yml
services:
  xero-proxy:
    build: .
    ports:
      - "${PROXY_RELAY_PORT:-8080}:${PROXY_RELAY_PORT:-8080}"     # REST relay
      - "${PROXY_CONNECT_PORT:-8888}:${PROXY_CONNECT_PORT:-8888}" # CONNECT proxy (si PROXY_CONNECT_ENABLED=true)
    env_file: .env
    restart: unless-stopped
```

### Cloudflare tunnel config (config.yml del cloudflared)

```yaml
tunnel: <TUNNEL_ID>
credentials-file: /root/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: proxy-s12.xero-one.com
    service: http://localhost:8080
  - service: http_status:404
```

---

## requirements.txt

```
aiohttp==3.9.5
python-dotenv==1.0.0
youtube-transcript-api==1.2.4
```
