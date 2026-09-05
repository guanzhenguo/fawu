import hashlib
import json
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


def normalize_text(value: str) -> str:
    return " ".join(value.split())


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(UUIDModel):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TemplateStatus(models.TextChoices):
    DRAFT = "DRAFT", "草稿"
    PUBLISHED = "PUBLISHED", "已发布"
    RETIRED = "RETIRED", "已停用"


class RiskLevel(models.TextChoices):
    LOW = "LOW", "低风险"
    MEDIUM = "MEDIUM", "中风险"
    HIGH = "HIGH", "高风险"


class ContractStatus(models.TextChoices):
    DRAFT = "DRAFT", "草稿"
    IN_REVIEW = "IN_REVIEW", "审核中"
    APPROVED = "APPROVED", "已审核"
    REJECTED = "REJECTED", "已驳回"
    SIGNED = "SIGNED", "已签署"
    ARCHIVED = "ARCHIVED", "已归档"


class ReviewStatus(models.TextChoices):
    PENDING = "PENDING", "待处理"
    IN_PROGRESS = "IN_PROGRESS", "审核中"
    COMPLETED = "COMPLETED", "已完成"
    REJECTED = "REJECTED", "已驳回"


class TaskStatus(models.TextChoices):
    PENDING = "PENDING", "待处理"
    APPROVED = "APPROVED", "已通过"
    REJECTED = "REJECTED", "已驳回"
    CANCELLED = "CANCELLED", "已取消"


class ContractTemplate(TimeStampedModel):
    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=16, choices=TemplateStatus.choices, default=TemplateStatus.DRAFT
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_templates"
    )

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} {self.name}"


class TemplateVersion(TimeStampedModel):
    template = models.ForeignKey(
        ContractTemplate, on_delete=models.PROTECT, related_name="versions"
    )
    version = models.CharField(max_length=32)
    status = models.CharField(
        max_length=16, choices=TemplateStatus.choices, default=TemplateStatus.DRAFT
    )
    change_note = models.TextField(blank=True)
    guidance = models.TextField(blank=True)
    risk_notice = models.TextField(blank=True)
    content_hash = models.CharField(max_length=64, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="published_template_versions",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["template", "version"], name="unique_template_version")
        ]
        ordering = ["template__code", "-created_at"]

    def __str__(self):
        return f"{self.template.code} v{self.version}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            previous = TemplateVersion.objects.get(pk=self.pk)
            if previous.status != TemplateStatus.DRAFT:
                raise ValidationError("已发布或停用的模板版本不可修改")
        super().save(*args, **kwargs)


class Clause(TimeStampedModel):
    code = models.CharField(max_length=64, unique=True)
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} {self.title}"


class ClauseVersion(TimeStampedModel):
    clause = models.ForeignKey(Clause, on_delete=models.PROTECT, related_name="versions")
    version = models.CharField(max_length=32)
    content = models.TextField()
    is_core = models.BooleanField(default=False)
    risk_level = models.CharField(
        max_length=16, choices=RiskLevel.choices, default=RiskLevel.MEDIUM
    )
    content_hash = models.CharField(max_length=64, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_clause_versions"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["clause", "version"], name="unique_clause_version")
        ]
        ordering = ["clause__code", "-created_at"]

    def __str__(self):
        return f"{self.clause.code} v{self.version}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("条款版本不可修改，请创建新版本")
        self.content_hash = hashlib.sha256(normalize_text(self.content).encode()).hexdigest()
        super().save(*args, **kwargs)


class TemplateClause(UUIDModel):
    template_version = models.ForeignKey(
        TemplateVersion, on_delete=models.CASCADE, related_name="template_clauses"
    )
    clause_version = models.ForeignKey(ClauseVersion, on_delete=models.PROTECT)
    sequence = models.PositiveIntegerField()
    required = models.BooleanField(default=True)
    locked = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["template_version", "clause_version"],
                name="unique_clause_in_template_version",
            ),
            models.UniqueConstraint(
                fields=["template_version", "sequence"], name="unique_clause_sequence_in_template"
            ),
        ]
        ordering = ["sequence"]

    def save(self, *args, **kwargs):
        status = TemplateVersion.objects.values_list("status", flat=True).get(
            pk=self.template_version_id
        )
        if status != TemplateStatus.DRAFT:
            raise ValidationError("已发布模板的条款配置不可修改")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        status = TemplateVersion.objects.values_list("status", flat=True).get(
            pk=self.template_version_id
        )
        if status != TemplateStatus.DRAFT:
            raise ValidationError("已发布模板的条款配置不可删除")
        return super().delete(*args, **kwargs)


class VariableDefinition(UUIDModel):
    class DataType(models.TextChoices):
        TEXT = "TEXT", "文本"
        NUMBER = "NUMBER", "数字"
        MONEY = "MONEY", "金额"
        DATE = "DATE", "日期"
        ENUM = "ENUM", "枚举"

    template_version = models.ForeignKey(
        TemplateVersion, on_delete=models.CASCADE, related_name="variables"
    )
    key = models.SlugField(max_length=64)
    label = models.CharField(max_length=100)
    data_type = models.CharField(max_length=16, choices=DataType.choices, default=DataType.TEXT)
    required = models.BooleanField(default=False)
    validation = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["template_version", "key"], name="unique_variable_in_template_version"
            )
        ]
        ordering = ["key"]

    def save(self, *args, **kwargs):
        status = TemplateVersion.objects.values_list("status", flat=True).get(
            pk=self.template_version_id
        )
        if status != TemplateStatus.DRAFT:
            raise ValidationError("已发布模板的变量配置不可修改")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        status = TemplateVersion.objects.values_list("status", flat=True).get(
            pk=self.template_version_id
        )
        if status != TemplateStatus.DRAFT:
            raise ValidationError("已发布模板的变量配置不可删除")
        return super().delete(*args, **kwargs)


class Contract(TimeStampedModel):
    code = models.CharField(max_length=64, unique=True)
    title = models.CharField(max_length=200)
    counterparty = models.CharField(max_length=200)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="contracts"
    )
    template_version = models.ForeignKey(
        TemplateVersion, on_delete=models.PROTECT, related_name="contracts"
    )
    status = models.CharField(
        max_length=16, choices=ContractStatus.choices, default=ContractStatus.DRAFT
    )
    amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=8, default="CNY")
    risk_level = models.CharField(max_length=16, choices=RiskLevel.choices, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.code} {self.title}"


class ContractVersion(TimeStampedModel):
    contract = models.ForeignKey(Contract, on_delete=models.PROTECT, related_name="versions")
    version_no = models.PositiveIntegerField()
    snapshot = models.JSONField(default=dict)
    source_file = models.FileField(upload_to="contracts/%Y/%m/", null=True, blank=True)
    content_hash = models.CharField(max_length=64, editable=False)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="submitted_contract_versions",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    is_final = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["contract", "version_no"], name="unique_contract_version"
            )
        ]
        ordering = ["contract", "-version_no"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            previous = ContractVersion.objects.get(pk=self.pk)
            protected_changed = any(
                (
                    previous.contract_id != self.contract_id,
                    previous.version_no != self.version_no,
                    previous.snapshot != self.snapshot,
                    previous.source_file.name != self.source_file.name,
                    previous.submitted_by_id != self.submitted_by_id,
                )
            )
            if previous.is_final or protected_changed:
                raise ValidationError("合同版本内容不可修改，请创建新版本")
        payload = json.dumps(
            self.snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        self.content_hash = hashlib.sha256(payload.encode()).hexdigest()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.contract.code} #{self.version_no}"


class ReviewCase(TimeStampedModel):
    contract_version = models.OneToOneField(
        ContractVersion, on_delete=models.PROTECT, related_name="review_case"
    )
    status = models.CharField(
        max_length=16, choices=ReviewStatus.choices, default=ReviewStatus.PENDING
    )
    risk_level = models.CharField(max_length=16, choices=RiskLevel.choices)
    summary = models.TextField(blank=True)
    rule_set_version = models.CharField(max_length=32, default="2026.09.1")
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class RiskFinding(UUIDModel):
    class Source(models.TextChoices):
        RULE = "RULE", "规则"
        DIFF = "DIFF", "比对"
        AI = "AI", "AI"

    review_case = models.ForeignKey(ReviewCase, on_delete=models.CASCADE, related_name="findings")
    source = models.CharField(max_length=16, choices=Source.choices)
    severity = models.CharField(max_length=16, choices=RiskLevel.choices)
    clause_code = models.CharField(max_length=64, blank=True)
    title = models.CharField(max_length=200)
    detail = models.TextField()
    confidence = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    resolved = models.BooleanField(default=False)

    class Meta:
        ordering = ["-severity", "clause_code"]


class ApprovalTask(UUIDModel):
    review_case = models.ForeignKey(ReviewCase, on_delete=models.PROTECT, related_name="tasks")
    step_order = models.PositiveIntegerField(default=1)
    name = models.CharField(max_length=100)
    role_code = models.CharField(max_length=64)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approval_tasks",
    )
    status = models.CharField(max_length=16, choices=TaskStatus.choices, default=TaskStatus.PENDING)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["step_order", "name"]


class ApprovalAction(UUIDModel):
    task = models.ForeignKey(ApprovalTask, on_delete=models.PROTECT, related_name="actions")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=16, choices=TaskStatus.choices)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("审批动作不可修改")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("审批动作不可删除")


class AuditEvent(UUIDModel):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True
    )
    action = models.CharField(max_length=100)
    entity_type = models.CharField(max_length=100)
    entity_id = models.CharField(max_length=64)
    payload = models.JSONField(default=dict, blank=True)
    previous_hash = models.CharField(max_length=64, blank=True)
    event_hash = models.CharField(max_length=64, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("审计事件不可修改")
        previous = AuditEvent.objects.order_by("-created_at", "-id").first()
        self.previous_hash = previous.event_hash if previous else ""
        self.event_hash = self.calculate_hash()
        super().save(*args, **kwargs)

    def calculate_hash(self) -> str:
        canonical = json.dumps(
            {
                "action": self.action,
                "actor": self.actor_id,
                "entity_id": self.entity_id,
                "entity_type": self.entity_type,
                "event_id": self.pk,
                "payload": self.payload,
                "previous_hash": self.previous_hash,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    def delete(self, *args, **kwargs):
        raise ValidationError("审计事件不可删除")
