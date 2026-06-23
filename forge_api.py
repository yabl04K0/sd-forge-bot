import base64
import json

import aiohttp


class ForgeAPI:
    def __init__(self, base_url: str, timeout: int = 300):
        self.base_url = base_url.rstrip("/")
        self.timeout = aiohttp.ClientTimeout(total=timeout)

    async def _get(self, endpoint: str) -> dict:
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.get(f"{self.base_url}{endpoint}") as resp:
                return await resp.json()

    async def _post(self, endpoint: str, data: dict) -> dict:
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.post(
                f"{self.base_url}{endpoint}",
                json=data,
                headers={"Content-Type": "application/json"}
            ) as resp:
                return await resp.json()

    async def check_connection(self) -> bool:
        """Проверка подключения к Forge"""
        try:
            result = await self._get("/sdapi/v1/sd-models")
            return isinstance(result, list)
        except Exception:
            return False

    async def get_models(self) -> list[dict]:
        """Список доступных моделей"""
        try:
            models = await self._get("/sdapi/v1/sd-models")
            return models
        except Exception:
            return []

    async def get_current_model(self) -> str:
        """Текущая модель"""
        try:
            options = await self._get("/sdapi/v1/options")
            return options.get("sd_model_checkpoint", "Unknown")
        except Exception:
            return "Unknown"

    async def set_model(self, model_name: str) -> bool:
        """Сменить модель"""
        try:
            await self._post("/sdapi/v1/options", {"sd_model_checkpoint": model_name})
            return True
        except Exception:
            return False

    async def get_loras(self) -> list[dict]:
        """Список доступных LoRA"""
        try:
            loras = await self._get("/sdapi/v1/loras")
            return loras
        except Exception:
            return []

    async def get_samplers(self) -> list[str]:
        """Список доступных сэмплеров"""
        try:
            samplers = await self._get("/sdapi/v1/samplers")
            return [s["name"] for s in samplers]
        except Exception:
            return []

    async def get_schedulers(self) -> list[str]:
        """Список доступных планировщиков"""
        try:
            schedulers = await self._get("/sdapi/v1/schedulers")
            return [s["name"] for s in schedulers]
        except Exception:
            return []

    async def get_upscalers(self) -> list[str]:
        """Список апскейлеров"""
        try:
            upscalers = await self._get("/sdapi/v1/upscalers")
            return [u["name"] for u in upscalers]
        except Exception:
            return []

    async def get_progress(self) -> dict:
        """Прогресс текущей генерации"""
        try:
            return await self._get("/sdapi/v1/progress")
        except Exception:
            return {"progress": 0, "state": {}}

    async def interrupt(self) -> bool:
        """Остановить генерацию"""
        try:
            await self._post("/sdapi/v1/interrupt", {})
            return True
        except Exception:
            return False

    async def txt2img(self, params: dict) -> tuple[bytes | None, dict]:
        """
        Генерация текст → изображение
        Возвращает (bytes изображения, инфо словарь)
        """
        payload = {
            "prompt": params.get("prompt", ""),
            "negative_prompt": params.get("negative_prompt", ""),
            "steps": params.get("steps", 25),
            "cfg_scale": params.get("cfg_scale", 7.0),
            "width": params.get("width", 512),
            "height": params.get("height", 768),
            "sampler_name": params.get("sampler", "Euler a"),
            "scheduler": params.get("scheduler", "Karras"),
            "seed": params.get("seed", -1),
            "batch_size": params.get("batch_size", 1),
            "restore_faces": params.get("restore_faces", False),
            "tiling": params.get("tiling", False),
            "enable_hr": params.get("enable_hr", False),
            "hr_scale": params.get("hr_scale", 2.0),
            "hr_upscaler": params.get("hr_upscaler", "Latent"),
            "denoising_strength": params.get("denoising_strength", 0.7),
        }

        # Добавляем LoRA в промпт если выбрана
        lora = params.get("selected_lora")
        lora_weight = params.get("lora_weight", 0.8)
        if lora:
            payload["prompt"] += f" <lora:{lora}:{lora_weight}>"

        result = await self._post("/sdapi/v1/txt2img", payload)

        if "images" not in result or not result["images"]:
            return None, {}

        img_bytes = base64.b64decode(result["images"][0])
        info = {}
        if "info" in result:
            try:
                info = json.loads(result["info"])
            except Exception:
                info = {}

        return img_bytes, info

    async def img2img(self, image_bytes: bytes, params: dict) -> tuple[bytes | None, dict]:
        """
        Генерация изображение → изображение
        """
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        payload = {
            "init_images": [image_b64],
            "prompt": params.get("prompt", ""),
            "negative_prompt": params.get("negative_prompt", ""),
            "steps": params.get("steps", 25),
            "cfg_scale": params.get("cfg_scale", 7.0),
            "width": params.get("width", 512),
            "height": params.get("height", 768),
            "sampler_name": params.get("sampler", "Euler a"),
            "scheduler": params.get("scheduler", "Karras"),
            "seed": params.get("seed", -1),
            "denoising_strength": params.get("denoising_strength", 0.75),
            "resize_mode": 0,
        }

        lora = params.get("selected_lora")
        lora_weight = params.get("lora_weight", 0.8)
        if lora:
            payload["prompt"] += f" <lora:{lora}:{lora_weight}>"

        result = await self._post("/sdapi/v1/img2img", payload)

        if "images" not in result or not result["images"]:
            return None, {}

        img_bytes = base64.b64decode(result["images"][0])
        info = {}
        if "info" in result:
            try:
                info = json.loads(result["info"])
            except Exception:
                info = {}

        return img_bytes, info

    async def upscale(self, image_bytes: bytes, upscaler: str = "R-ESRGAN 4x+", scale: float = 2.0) -> bytes | None:
        """Апскейл изображения"""
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        payload = {
            "resize_mode": 0,
            "show_extras_results": True,
            "upscaling_resize": scale,
            "upscaler_1": upscaler,
            "image": image_b64,
        }
        try:
            result = await self._post("/sdapi/v1/extra-single-image", payload)
            if "image" in result:
                return base64.b64decode(result["image"])
        except Exception:
            pass
        return None

    async def get_embeddings(self) -> list[str]:
        """Список доступных embeddings/textual inversions"""
        try:
            result = await self._get("/sdapi/v1/embeddings")
            loaded = result.get("loaded", {})
            return list(loaded.keys())
        except Exception:
            return []

    async def png_info(self, image_bytes: bytes) -> dict:
        """Получить метаданные PNG (параметры генерации)"""
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        try:
            result = await self._post("/sdapi/v1/png-info", {"image": f"data:image/png;base64,{image_b64}"})
            return result
        except Exception:
            return {}
