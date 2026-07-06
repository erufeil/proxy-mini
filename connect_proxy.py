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
