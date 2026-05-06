import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def run_grading_analysis(lot_id: str):
    """Background AI analysis on grading data for a lot."""
    from apps.ai_assistant.services import process_ai_query
    from django.contrib.auth import get_user_model
    User = get_user_model()

    system_user = User.objects.filter(is_superuser=True).first()
    if not system_user:
        logger.warning("No system user for AI background task")
        return

    prompt = f"Analyze grading records for lot {lot_id} and flag any anomalies."
    try:
        result = process_ai_query(user=system_user, prompt=prompt)
        logger.info("Grading analysis for lot %s complete", lot_id)
        return result
    except Exception:
        logger.exception("Grading analysis failed for lot %s", lot_id)


@shared_task
def run_settlement_anomaly_review():
    """Periodic review of settlements for anomalies."""
    from apps.common.enums import SettlementStatus
    from apps.settlements.models import Settlement

    overdue = Settlement.objects.filter(status=SettlementStatus.PENDING)
    count = overdue.count()
    logger.info("Settlement anomaly review: %d pending settlements", count)
