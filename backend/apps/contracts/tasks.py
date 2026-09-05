from celery import shared_task


@shared_task(autoretry_for=(OSError,), retry_backoff=True, max_retries=3)
def document_job_placeholder(contract_version_id: str) -> dict:
    """Reserved boundary for document rendering and commercial Word comparison.

    The task intentionally does not claim a document was reviewed. Production wiring
    must persist the document-service response before changing review state.
    """
    return {
        "contract_version_id": contract_version_id,
        "status": "NOT_CONFIGURED",
        "detail": "Document engine adapter has not been configured.",
    }
