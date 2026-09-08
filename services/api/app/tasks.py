from .celery_app import celery_app
if celery_app:
 @celery_app.task(name='voicelens.run_analysis')
 def run_analysis_task(analysis_id: str):
  from .main import worker
  return worker.run(analysis_id)
else:
 def run_analysis_task(analysis_id: str):
  from .main import worker
  return worker.run(analysis_id)
