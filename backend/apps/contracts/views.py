from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from .models import (
    ApprovalTask,
    AuditEvent,
    Clause,
    ClauseVersion,
    Contract,
    ContractTemplate,
    ContractVersion,
    ReviewCase,
    TaskStatus,
    TemplateClause,
    TemplateVersion,
    VariableDefinition,
)
from .permissions import ReadOnlyOrAdmin
from .serializers import (
    ApprovalTaskSerializer,
    AuditEventSerializer,
    ClauseSerializer,
    ClauseVersionSerializer,
    ContractSerializer,
    ContractTemplateSerializer,
    ContractVersionSerializer,
    ReviewCaseSerializer,
    TemplateClauseSerializer,
    TemplateVersionSerializer,
    VariableDefinitionSerializer,
    as_api_validation_error,
)
from .services import (
    create_contract_version,
    decide_task,
    publish_template_version,
    submit_for_review,
)


class ContractTemplateViewSet(viewsets.ModelViewSet):
    queryset = ContractTemplate.objects.prefetch_related("versions").all()
    serializer_class = ContractTemplateSerializer
    permission_classes = [ReadOnlyOrAdmin]
    search_fields = ["code", "name"]


class TemplateVersionViewSet(viewsets.ModelViewSet):
    queryset = TemplateVersion.objects.select_related("template").prefetch_related(
        "template_clauses__clause_version__clause", "variables"
    )
    serializer_class = TemplateVersionSerializer
    permission_classes = [ReadOnlyOrAdmin]

    @action(detail=True, methods=["post"], permission_classes=[IsAdminUser])
    def publish(self, request, pk=None):
        try:
            version = publish_template_version(self.get_object(), request.user)
        except DjangoValidationError as exc:
            raise as_api_validation_error(exc) from exc
        return Response(self.get_serializer(version).data)


class ClauseViewSet(viewsets.ModelViewSet):
    queryset = Clause.objects.all()
    serializer_class = ClauseSerializer
    permission_classes = [ReadOnlyOrAdmin]


class ClauseVersionViewSet(viewsets.ModelViewSet):
    queryset = ClauseVersion.objects.select_related("clause", "created_by")
    serializer_class = ClauseVersionSerializer
    permission_classes = [ReadOnlyOrAdmin]


class TemplateClauseViewSet(viewsets.ModelViewSet):
    queryset = TemplateClause.objects.select_related("template_version", "clause_version__clause")
    serializer_class = TemplateClauseSerializer
    permission_classes = [ReadOnlyOrAdmin]


class VariableDefinitionViewSet(viewsets.ModelViewSet):
    queryset = VariableDefinition.objects.select_related("template_version")
    serializer_class = VariableDefinitionSerializer
    permission_classes = [ReadOnlyOrAdmin]


class ContractViewSet(viewsets.ModelViewSet):
    serializer_class = ContractSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, FormParser, MultiPartParser]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        queryset = Contract.objects.select_related(
            "owner", "template_version__template"
        ).prefetch_related("versions")
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(
            Q(owner=self.request.user)
            | Q(versions__review_case__tasks__assignee=self.request.user)
            | Q(versions__review_case__tasks__role_code__in=self.request.user.groups.values("name"))
        ).distinct()

    @action(detail=True, methods=["post"], url_path="versions")
    def create_version(self, request, pk=None):
        contract = self.get_object()
        if not request.user.is_staff and contract.owner_id != request.user.pk:
            return Response({"detail": "只有合同负责人可以创建版本"}, status=403)
        source_file = request.FILES.get("source_file")
        snapshot = request.data.get("snapshot", {})
        if isinstance(snapshot, str):
            import json

            try:
                snapshot = json.loads(snapshot)
            except json.JSONDecodeError:
                return Response(
                    {"snapshot": ["必须是有效 JSON"]}, status=status.HTTP_400_BAD_REQUEST
                )
        try:
            version = create_contract_version(
                contract=contract,
                snapshot=snapshot,
                source_file=source_file,
                actor=request.user,
            )
        except DjangoValidationError as exc:
            raise as_api_validation_error(exc) from exc
        return Response(ContractVersionSerializer(version).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        if not self.request.user.is_staff and serializer.instance.owner_id != self.request.user.pk:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("只有合同负责人可以修改合同")
        serializer.save()


class ContractVersionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ContractVersion.objects.select_related("contract", "submitted_by")
    serializer_class = ContractVersionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        return (
            queryset
            if self.request.user.is_staff
            else queryset.filter(contract__owner=self.request.user)
        )

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        try:
            review = submit_for_review(self.get_object(), request.user)
        except DjangoValidationError as exc:
            raise as_api_validation_error(exc) from exc
        return Response(ReviewCaseSerializer(review).data, status=status.HTTP_201_CREATED)


class ReviewCaseViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ReviewCaseSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = ReviewCase.objects.select_related("contract_version__contract").prefetch_related(
            "findings", "tasks__actions"
        )
        if self.request.user.is_staff:
            return queryset
        roles = self.request.user.groups.values_list("name", flat=True)
        return queryset.filter(
            Q(contract_version__contract__owner=self.request.user)
            | Q(tasks__assignee=self.request.user)
            | Q(tasks__role_code__in=roles)
        ).distinct()


class ApprovalTaskViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ApprovalTaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = ApprovalTask.objects.select_related(
            "review_case__contract_version__contract", "assignee"
        ).prefetch_related("actions")
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(
            Q(assignee=self.request.user) | Q(role_code__in=self.request.user.groups.values("name"))
        ).distinct()

    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        decision = request.data.get("decision", "")
        comment = request.data.get("comment", "")
        if decision not in {TaskStatus.APPROVED, TaskStatus.REJECTED}:
            return Response(
                {"decision": ["只能是 APPROVED 或 REJECTED"]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            task = decide_task(
                task=self.get_object(), actor=request.user, decision=decision, comment=comment
            )
        except DjangoValidationError as exc:
            raise as_api_validation_error(exc) from exc
        return Response(self.get_serializer(task).data)


class AuditEventViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditEvent.objects.select_related("actor")
    serializer_class = AuditEventSerializer
    permission_classes = [IsAdminUser]
