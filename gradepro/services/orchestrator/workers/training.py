import logging
from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, queue="training_queue")
def process_training_job(self, unit_id: str, unit_code: str, csv_path_r2: str):
    logger.info(f"Triggering submodel training for {unit_code} from {csv_path_r2}")
    # In production, invokes ml_inference /train endpoint
    return {"status": "trained", "unit_code": unit_code}
