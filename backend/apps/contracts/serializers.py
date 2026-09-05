from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import (
    ApprovalAction,
    ApprovalTask,
    AuditEvent,
    Clause,
    ClauseVersion,
    Contract,
    ContractTemplate,
    ContractVersion,
    ReviewCase,
    RiskFinding,
    TemplateClause,
    TemplateStatus,
    TemplateVersion,
    VariableDefinition,
)


class ClauseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Clause
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at"]


class ClauseVersionSerializer(serializers.ModelSerializer):
    clause_code = serializers.CharField(source="clause.code", read_only=True)
    clause_title = serializers.CharField(source="clause.title", read_only=True)

    class Meta:
        model = ClauseVersion
        fields = "__all__"
        read_only_fields = ["created_by", "content_hash", "created_at", "updated_at"]

    def create(self, validated_data):
        return ClauseVersion.objects.create(
            created_by=self.context["request"].user, **validated_data
        )

    def update(self, instance, validated_data):
        raise serializers.ValidationError("条款版本不可修改，请创建新版本")


class TemplateClauseSerializer(serializers.ModelSerializer):
    clause_code = serializers.CharField(source="clause_version.clause.code", read_only=True)
    clause_title = serializers.CharField(source="clause_version.clause.title", read_only=True)
    content = serializers.CharField(source="clause_version.content", read_only=True)
    is_core = serializers.BooleanField(source="clause_version.is_core", read_only=True)

    class Meta:
        model = TemplateClause
        fields = "__all__"

    def validate_template_version(self, value):
        if value.status != TemplateStatus.DRAFT:
            raise serializers.ValidationError("只能编辑草稿模板版本")
        return value

    def update(self, instance, validated_data):
        if instance.template_version.status != TemplateStatus.DRAFT:
            raise serializers.ValidationError("只能编辑草稿模板版本")
        return super().update(instance, validated_data)


class VariableDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = VariableDefinition
        fields = "__all__"

    def validate_template_version(self, value):
        if value.status != TemplateStatus.DRAFT:
            raise serializers.ValidationError("只能编辑草稿模板版本")
        return value

    def update(self, instance, validated_data):
        if instance.template_version.status != TemplateStatus.DRAFT:
            raise serializers.ValidationError("只能编辑草稿模板版本")
        return super().update(instance, validated_data)


class TemplateVersionSerializer(serializers.ModelSerializer):
    template_name = serializers.CharField(source="template.name", read_only=True)
    template_code = serializers.CharField(source="template.code", read_only=True)
    template_clauses = TemplateClauseSerializer(many=True, read_only=True)
    variables = VariableDefinitionSerializer(many=True, read_only=True)

    class Meta:
        model = TemplateVersion
        fields = "__all__"
        read_only_fields = [
            "status",
            "content_hash",
            "published_at",
            "published_by",
            "created_at",
            "updated_at",
        ]

    def update(self, instance, validated_data):
        if instance.status != TemplateStatus.DRAFT:
            raise serializers.ValidationError("已发布或停用的模板版本不可修改")
        return super().update(instance, validated_data)


class ContractTemplateSerializer(serializers.ModelSerializer):
    versions = TemplateVersionSerializer(many=True, read_only=True)

    class Meta:
        model = ContractTemplate
        fields = "__all__"
        read_only_fields = ["status", "created_by", "created_at", "updated_at"]

    def create(self, validated_data):
        return ContractTemplate.objects.create(
            created_by=self.context["request"].user, **validated_data
        )


class ContractVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractVersion
        fields = "__all__"
        read_only_fields = [
            "contract",
            "version_no",
            "content_hash",
            "submitted_by",
            "submitted_at",
            "is_final",
            "created_at",
            "updated_at",
        ]


class ContractSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source="owner.username", read_only=True)
    template_name = serializers.CharField(source="template_version.template.name", read_only=True)
    template_label = serializers.SerializerMethodField()
    versions = ContractVersionSerializer(many=True, read_only=True)

    class Meta:
        model = Contract
        fields = "__all__"
        read_only_fields = ["owner", "status", "risk_level", "created_at", "updated_at"]

    def get_template_label(self, obj):
        return f"{obj.template_version.template.name} v{obj.template_version.version}"

    def validate_template_version(self, value):
        if value.status != TemplateStatus.PUBLISHED:
            raise serializers.ValidationError("必须选择已发布的模板版本")
        if (
            self.instance
            and self.instance.versions.exists()
            and value.pk != self.instance.template_version_id
        ):
            raise serializers.ValidationError("已有合同版本后不能更换模板基线")
        return value

    def create(self, validated_data):
        return Contract.objects.create(owner=self.context["request"].user, **validated_data)


class RiskFindingSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiskFinding
        fields = "__all__"


class ApprovalActionSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.username", read_only=True)

    class Meta:
        model = ApprovalAction
        fields = "__all__"


class ApprovalTaskSerializer(serializers.ModelSerializer):
    actions = ApprovalActionSerializer(many=True, read_only=True)
    contract_code = serializers.CharField(
        source="review_case.contract_version.contract.code", read_only=True
    )
    contract_title = serializers.CharField(
        source="review_case.contract_version.contract.title", read_only=True
    )

    class Meta:
        model = ApprovalTask
        fields = "__all__"


class ReviewCaseSerializer(serializers.ModelSerializer):
    findings = RiskFindingSerializer(many=True, read_only=True)
    tasks = ApprovalTaskSerializer(many=True, read_only=True)
    contract_code = serializers.CharField(source="contract_version.contract.code", read_only=True)
    contract_title = serializers.CharField(source="contract_version.contract.title", read_only=True)

    class Meta:
        model = ReviewCase
        fields = "__all__"


class AuditEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.username", read_only=True)

    class Meta:
        model = AuditEvent
        fields = "__all__"


def as_api_validation_error(exc: DjangoValidationError) -> serializers.ValidationError:
    if hasattr(exc, "message_dict"):
        return serializers.ValidationError(exc.message_dict)
    return serializers.ValidationError(exc.messages)
