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
