from rest_framework.routers import DefaultRouter

from .views import (
    ApprovalTaskViewSet,
    AuditEventViewSet,
    ClauseVersionViewSet,
    ClauseViewSet,
    ContractTemplateViewSet,
    ContractVersionViewSet,
    ContractViewSet,
    ReviewCaseViewSet,
    TemplateClauseViewSet,
    TemplateVersionViewSet,
    VariableDefinitionViewSet,
)

router = DefaultRouter()
router.register("templates", ContractTemplateViewSet, basename="template")
router.register("template-versions", TemplateVersionViewSet, basename="template-version")
router.register("clauses", ClauseViewSet, basename="clause")
router.register("clause-versions", ClauseVersionViewSet, basename="clause-version")
router.register("template-clauses", TemplateClauseViewSet, basename="template-clause")
router.register("variables", VariableDefinitionViewSet, basename="variable")
router.register("contracts", ContractViewSet, basename="contract")
router.register("contract-versions", ContractVersionViewSet, basename="contract-version")
router.register("reviews", ReviewCaseViewSet, basename="review")
router.register("approval-tasks", ApprovalTaskViewSet, basename="approval-task")
router.register("audit-events", AuditEventViewSet, basename="audit-event")

urlpatterns = router.urls
