from typing import List

import os
import asyncio

import uvicorn
from fastapi import FastAPI, APIRouter
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse
from starlette.requests import Request

from configs.config import AppConfig, ModelConfig
from infrastructure.models import TritonTextClassificationModel
from service.recognition import TextClassificationService
from handlers.recognition import PredictionHandler
from handlers.data_models import ResponseSchema


def build_models(model_configs: List[ModelConfig], triton_url: str, batch_size: int) -> List[TritonTextClassificationModel]:
    models = [
            TritonTextClassificationModel(conf.model, conf.triton_model_name, triton_url, batch_size, conf.model_labels)
            for conf in model_configs
        ]
    return models


config = AppConfig.parse_file("./app/configs/app_config.yaml")
env_triton_url = os.getenv("TRITON_URL", None)
config.triton_url = config.triton_url if not env_triton_url else f"{env_triton_url}:8000"
models = build_models(config.models, config.triton_url, config.batch_size)

recognition_service = TextClassificationService(models)
recognition_handler = PredictionHandler(recognition_service, config.timeout)

app = FastAPI()
router = APIRouter()


async def create_queue():
    app.models_queues = {}
    for md in models:
        task_queue = asyncio.Queue()
        app.models_queues[md.name] = task_queue
        asyncio.create_task(recognition_handler.handle(md.name, task_queue))


@router.post("/process", response_model=ResponseSchema)
async def process(request: Request):
    text = (await request.body()).decode()

    results = []
    response_q = asyncio.Queue() # init a response queue for every request, one for all models
    for model_name, model_queue in app.models_queues.items():
        await model_queue.put((text, response_q))
        model_res = await response_q.get()
        results.append(model_res)
    return recognition_handler.serialize_answer(results)


app.include_router(router)


@app.get("/healthcheck")
async def main():
    return {"message": "I am alive"}


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="NLP Model Service",
        version="0.1.0",
        description="Inca test task",
        routes=app.routes,
    )
    app.openapi_schema = openapi_schema
    return app.openapi_schema


@app.get(
    "/documentation/swagger-ui/",
    response_class=HTMLResponse,
)
async def swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url="/documentation/openapi.json",
        title="API documentation"
    )


@app.get(
    "/documentation/openapi.json",
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def openapi_endpoint():
    return custom_openapi()


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8080, workers=1)

