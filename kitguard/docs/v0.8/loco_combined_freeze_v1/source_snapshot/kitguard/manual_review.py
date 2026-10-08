"""Human-declared reconciliation and explicit reopening; never changes AI output."""

from fastapi import APIRouter

from .schemas import ManualReviewRequest, ReopenRequest


def create_manual_review_router(store, verify_evidence_files):
    router = APIRouter(prefix="/api/orders")

    @router.post("/{order_id}/manual-review")
    def manual_review(order_id: str, body: ManualReviewRequest):
        return store.manual_review(order_id, body.model_dump(), verify_evidence_files)

    @router.post("/{order_id}/reopen")
    def reopen(order_id: str, body: ReopenRequest):
        return store.reopen(order_id, body.model_dump())

    return router
