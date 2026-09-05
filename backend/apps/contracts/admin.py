from django.contrib import admin

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
    TemplateVersion,
    VariableDefinition,
)


class TemplateClauseInline(admin.TabularInline):
    model = TemplateClause
    extra = 0


class VariableInline(admin.TabularInline):
    model = VariableDefinition
    extra = 0


@admin.register(ContractTemplate)
class ContractTemplateAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "status", "created_by", "updated_at")
    list_filter = ("status",)
    search_fields = ("code", "name")


@admin.register(TemplateVersion)
class TemplateVersionAdmin(admin.ModelAdmin):
    list_display = ("template", "version", "status", "published_at", "content_hash")
    list_filter = ("status",)
    inlines = (TemplateClauseInline, VariableInline)


@admin.register(Clause)
class ClauseAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "category")
    search_fields = ("code", "title", "category")


@admin.register(ClauseVersion)
class ClauseVersionAdmin(admin.ModelAdmin):
    list_display = ("clause", "version", "is_core", "risk_level", "content_hash")
    list_filter = ("is_core", "risk_level")
    readonly_fields = ("content_hash",)


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "counterparty", "owner", "status", "risk_level")
    list_filter = ("status", "risk_level")
    search_fields = ("code", "title", "counterparty")


@admin.register(ContractVersion)
class ContractVersionAdmin(admin.ModelAdmin):
    list_display = ("contract", "version_no", "submitted_at", "is_final", "content_hash")
    readonly_fields = ("content_hash", "submitted_at", "is_final")


@admin.register(ReviewCase)
class ReviewCaseAdmin(admin.ModelAdmin):
    list_display = ("contract_version", "risk_level", "status", "rule_set_version", "completed_at")
    list_filter = ("risk_level", "status")


@admin.register(RiskFinding)
class RiskFindingAdmin(admin.ModelAdmin):
    list_display = ("review_case", "source", "severity", "clause_code", "title", "resolved")
    list_filter = ("source", "severity", "resolved")


@admin.register(ApprovalTask)
class ApprovalTaskAdmin(admin.ModelAdmin):
    list_display = ("review_case", "name", "role_code", "assignee", "status", "completed_at")
    list_filter = ("role_code", "status")


@admin.register(ApprovalAction)
class ApprovalActionAdmin(admin.ModelAdmin):
    list_display = ("task", "actor", "action", "created_at")
    readonly_fields = ("task", "actor", "action", "comment", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "entity_type", "entity_id", "event_hash")
    readonly_fields = (
        "actor",
        "action",
        "entity_type",
        "entity_id",
        "payload",
        "previous_hash",
        "event_hash",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
