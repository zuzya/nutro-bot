import logging
from pythonjsonlogger import jsonlogger
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from prometheus_client import start_http_server, Counter
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
    # Запускаем HTTP сервер для Prometheus
    start_http_server(port=8000)
    
    # Создаем основные метрики
    meal_counter = Counter(
        'meals_added_total',
        'Number of meals added'
    )
    
    goal_counter = Counter(
        'goals_set_total',
        'Number of goals set'
    )
    
    user_counter = Counter(
        'active_users_total',
        'Number of active users'
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