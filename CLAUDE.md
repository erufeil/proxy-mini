# xero-proxy — instrucciones para Claude

---

## Modo de Ejecución Autónoma

Ejecuta las etapas solicitadas de `CLAUDE-plan.md` de forma autónoma, de principio a fin, sin consultar al usuario. Ante cualquier decisión técnica, elige la opción más estándar según las buenas prácticas, evitando sobreingeniería. Solo interrumpe si hay un error bloqueante que no puedas resolver por tus propios medios. Actualiza los archivos CLAUDE-*.md al finalizar cada etapa.

---

## Objetivo

Servicio relay HTTP ligero y seguro. Corre on-premise (con IP residencial/empresarial),
expuesto vía Cloudflare tunnel en `proxy-s12.xero-one.com`.

**Caso principal:** PDFexport (servidor cloud, IP bloqueada por YouTube) llama al relay,
que hace el fetch desde la IP local y devuelve la respuesta. PDFexport configura
`YOUTUBE_RELAY_URL=https://proxy-s12.xero-one.com` (la URL pública del tunnel, no una
variable de este proyecto — ver `YOUTUBE_RELAY_URL`/`YOUTUBE_RELAY_TOKEN` en CLAUDE-VAR.md).

```cmd
PDFexport (cloud) → HTTPS → Cloudflare tunnel → xero-proxy (on-prem) → YouTube/internet
```

---

## Arquitectura: dos modos

### Modo A — REST relay (primario, Cloudflare-compatible)

- Endpoint `POST /relay` — fetch genérico de URLs con allowlist
- Endpoint `POST /yt-transcript` — usa youtube-transcript-api instalado localmente
- Cloudflare termina TLS, reenvía HTTP normal al proxy. Funciona perfecto.
- PDFexport llama via `YOUTUBE_RELAY_URL=https://proxy-s12.xero-one.com`

### Modo B — HTTP CONNECT proxy (alternativo, sin Cloudflare)

- Escucha en puerto directo (`PROXY_CONNECT_PORT`) con `Proxy-Authorization: Bearer TOKEN`
- Compatible con `requests` / `YOUTUBE_PROXY_URL=http://TOKEN@host:PROXY_CONNECT_PORT`
- NO funciona a través de Cloudflare tunnel (CF no pasa TCP tunnel post-CONNECT)
- Útil si se abre el puerto directo en el firewall

Ambos modos corren en el mismo proceso. Si hay Cloudflare → usar Modo A.
Si hay puerto directo → usar Modo B. Se pueden activar juntos.

---

## Stack

- Python 3.10+
- `aiohttp` — servidor async y cliente HTTP para el relay
- `youtube-transcript-api==1.2.4` — para el endpoint `/yt-transcript`
- Sin framework extra, sin DB, sin ORM
- Un solo proceso, sin workers externos

## Estructura de archivos

```cmd
xero-proxy/
├── proxy_server.py      # Entry point: aiohttp app + rutas
├── relay.py             # Lógica fetch genérico (Modo A)
├── yt_transcript.py     # Lógica YouTube transcript (usa ytapi)
├── connect_proxy.py     # CONNECT proxy asyncio (Modo B)
├── auth.py              # Validación de token Bearer
├── config.py            # Variables de entorno
├── requirements.txt
├── Dockerfile
├── .env.example
└── README.md            # deploy + uso (ver checklist)
```

---

## Seguridad

- **Token obligatorio** en todos los endpoints: `Authorization: Bearer {PROXY_TOKEN}`
- `PROXY_TOKEN` — al menos 32 chars aleatorios, generado con `python -c "import secrets; print(secrets.token_urlsafe(32))"`
- `PROXY_ALLOWED_HOSTS` — allowlist de dominios para relay genérico (default: youtube.com y relacionados)
- Sin allowlist → bloquear el request con 403
- Rate limiting simple: max 60 req/min por IP, configurable por `PROXY_RATE_LIMIT_RPM` (en memoria, no persistente)
- Solo HTTPS en producción (Cloudflare maneja el TLS; internamente HTTP)
- Logs estructurados a stdout (no a archivo): timestamp + método + destino + status + ms
- No loguear tokens ni payloads completos
- Nada hardcodeado, todo configurable en .env file

---

## Reglas de código

- Python con async/await (aiohttp), no threading
- Variables y comentarios en español
- Sin over-engineering: no abstracciones si hay una sola implementación
- Validar solo en entry points (routes): el interior confía en los datos ya validados
- No retornar stack traces al cliente: mensajes de error genéricos hacia afuera, detalle en logs
- config.py es la única fuente de vars de entorno

---

## Checklist al finalizar etapa

1. Verificar que nombres de funciones/vars existan en el resto del código
2. Actualizar CLAUDE-CODE.md si hay patrones nuevos
3. Actualizar CLAUDE-VAR.md si cambian contratos o env vars
4. Actualizar CLAUDE-PLAN.md con estado de etapas
5. Actualizar README.md (deploy + uso)

