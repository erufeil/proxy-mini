# xero-proxy

Servicio relay HTTP ligero y seguro. Corre on-premise (con IP residencial/empresarial),
expuesto vía Cloudflare tunnel. Permite que servicios cloud (ej. PDFexport, con IP
bloqueada por YouTube) hagan requests a través de la IP local de este servidor.

```
PDFexport (cloud) → HTTPS → Cloudflare tunnel → xero-proxy (on-prem) → YouTube/internet
```

## Modos

- **Modo A — REST relay** (`POST /relay`, `POST /yt-transcript`): compatible con Cloudflare tunnel. Modo primario.
- **Modo B — CONNECT proxy** (puerto directo): compatible con `requests`/`YOUTUBE_PROXY_URL`, pero no funciona a través de Cloudflare (CF no pasa TCP tunnel post-CONNECT). Requiere abrir un puerto directo en el firewall.

Ver `CLAUDE-VAR.md` para el detalle de variables de entorno y contratos REST.

## Requisitos

- Docker y Docker Compose
- [`cloudflared`](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) instalado y un tunnel de Cloudflare configurado

## Deploy

### 1. Generar `PROXY_TOKEN`

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 2. Crear `.env`

Copiar `.env.example` a `.env` y completar `PROXY_TOKEN`:

```env
HOST=0.0.0.0
PROXY_RELAY_PORT=8080
PROXY_TOKEN=<token generado en el paso anterior>
PROXY_ALLOWED_HOSTS=youtube.com,ytimg.com,googlevideo.com,yt3.ggpht.com
PROXY_CONNECT_ENABLED=false
PROXY_CONNECT_PORT=8888
PROXY_LOG_LEVEL=INFO
PROXY_RATE_LIMIT_RPM=60
```

### 3. Levantar el servicio

```bash
docker compose up -d
```

Verificar:

```bash
curl http://localhost:8080/health
# → {"ok": true, "version": "1.0.0"}
```

### 4. Configurar el Cloudflare tunnel

En el `config.yml` de `cloudflared` (en el servidor on-premise):

```yaml
tunnel: <TUNNEL_ID>
credentials-file: /root/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: proxy-s12.xero-one.com
    service: http://localhost:8080
  - service: http_status:404
```

El tunnel apunta al puerto HTTP interno (no HTTPS — Cloudflare maneja el TLS).

```bash
cloudflared tunnel run <TUNNEL_ID>
```

### 5. Configurar PDFexport

En el `.env` de PDFexport:

```env
YOUTUBE_RELAY_URL=https://proxy-s12.xero-one.com
YOUTUBE_RELAY_TOKEN=<mismo valor que PROXY_TOKEN>
```

PDFexport prioriza `YOUTUBE_RELAY_URL` sobre `YOUTUBE_PROXY_URL` y cookies locales — ver
`CLAUDE-VAR.md` para el detalle de la lógica de prioridad.

## Uso directo (Modo B, sin Cloudflare)

Solo si se abre el puerto `PROXY_CONNECT_PORT` (default `8888`) en el firewall y se
activa `PROXY_CONNECT_ENABLED=true`:

```env
YOUTUBE_PROXY_URL=http://<PROXY_TOKEN>@<ip-publica>:8888
```

## Endpoints

| Endpoint | Auth | Descripción |
|----------|------|-------------|
| `GET /health` | No | Estado del servicio |
| `POST /relay` | Sí | Fetch genérico de una URL en la allowlist |
| `POST /yt-transcript` | Sí | Transcript de un video de YouTube |

Detalle de request/response en `CLAUDE-VAR.md`.
