import os
try:
 from celery import Celery
except ImportError:
 Celery=None
broker_url=os.getenv('CELERY_BROKER_URL','redis://redis:6379/0')
result_backend=os.getenv('CELERY_RESULT_BACKEND',broker_url)
celery_app=Celery('voicelens',broker=broker_url,backend=result_backend) if Celery else None
if celery_app: celery_app.conf.update(
    task_track_started=True,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    # -A 只指向本模块;include 让 worker 启动时注册队列任务。
    # 注意是 celery_tasks,不是 tasks——app/tasks.py 是 W15 领域状态机,里面没有队列任务。
    include=['services.api.app.celery_tasks'],
)
