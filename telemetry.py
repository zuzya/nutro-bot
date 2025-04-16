import logging
from pythonjsonlogger import jsonlogger
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from prometheus_client import start_http_server
import os

# Настройка JSON логирования
def setup_logging():
    logger = logging.getLogger()
    logHandler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        fmt='%(asctime)s %(levelname)s %(name)s %(message)s'
    )
    logHandler.setFormatter(formatter)
    logger.addHandler(logHandler)
    logger.setLevel(logging.INFO)
    
    # Добавляем файловый handler
    file_handler = logging.FileHandler('bot.log')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger

# Настройка трейсинга
def setup_tracing():
    resource = Resource.create({"service.name": "nutro-bot"})
    trace.set_tracer_provider(TracerProvider(resource=resource))
    tracer = trace.get_tracer(__name__)
    return tracer

# Настройка метрик
def setup_metrics():
    # Создаем reader для Prometheus
    reader = PrometheusMetricReader()
    provider = MeterProvider(resource=Resource.create({"service.name": "nutro-bot"}), metric_readers=[reader])
    metrics.set_meter_provider(provider)
    meter = metrics.get_meter(__name__)
    
    # Запускаем HTTP сервер для Prometheus
    start_http_server(port=8000)
    
    # Создаем основные метрики
    meal_counter = meter.create_counter(
        name="meals_added",
        description="Number of meals added",
        unit="1"
    )
    
    goal_counter = meter.create_counter(
        name="goals_set",
        description="Number of goals set",
        unit="1"
    )
    
    user_counter = meter.create_counter(
        name="active_users",
        description="Number of active users",
        unit="1"
    )
    
    return meal_counter, goal_counter, user_counter

# Инициализация инструментирования
def setup_instrumentation():
    # Инструментируем SQLAlchemy
    SQLAlchemyInstrumentor().instrument()
    
    # Инструментируем requests (для OpenAI API)
    RequestsInstrumentor().instrument()

def init_telemetry():
    """Инициализация всей телеметрии"""
    logger = setup_logging()
    tracer = setup_tracing()
    meal_counter, goal_counter, user_counter = setup_metrics()
    setup_instrumentation()
    
    return {
        'logger': logger,
        'tracer': tracer,
        'metrics': {
            'meal_counter': meal_counter,
            'goal_counter': goal_counter,
            'user_counter': user_counter
        }
    } 