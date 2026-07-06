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
