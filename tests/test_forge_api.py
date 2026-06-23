"""Регрессия: forge_api должен поднимать HTTP-ошибки, а не молча рапортовать успех.

До фикта `_post`/`_get` возвращали JSON при любом статусе, поэтому `set_model`
возвращал True даже когда Forge отвечал 500 → бот показывал «✅ Модель загружена».
"""
from aiohttp import web

from forge_api import ForgeAPI


async def _start(app):
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    return runner, port


async def test_set_model_returns_false_on_http_error():
    app = web.Application()

    async def options(request):
        return web.json_response({"error": "boom"}, status=500)

    app.router.add_post("/sdapi/v1/options", options)
    runner, port = await _start(app)
    try:
        api = ForgeAPI(f"http://127.0.0.1:{port}", timeout=5)
        assert await api.set_model("whatever") is False
    finally:
        await runner.cleanup()


async def test_check_connection_true_on_ok_list():
    app = web.Application()

    async def models(request):
        return web.json_response([{"model_name": "x"}], status=200)

    app.router.add_get("/sdapi/v1/sd-models", models)
    runner, port = await _start(app)
    try:
        api = ForgeAPI(f"http://127.0.0.1:{port}", timeout=5)
        assert await api.check_connection() is True
    finally:
        await runner.cleanup()
