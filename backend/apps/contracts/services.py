import hashlib
import json
import zipfile

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .models import (
    ApprovalAction,
    ApprovalTask,
    AuditEvent,
    Contract,
    ContractStatus,
    ContractVersion,
    ReviewCase,
    ReviewStatus,
    RiskFinding,
    RiskLevel,
    TaskStatus,
    TemplateStatus,
    TemplateVersion,
    normalize_text,
)

RULE_SET_VERSION = "2026.09.1"


def write_audit(*, actor, action: str, entity, payload: dict | None = None) -> AuditEvent:
    return AuditEvent.objects.create(
        actor=actor,
        action=action,
        entity_type=entity.__class__.__name__,
        entity_id=str(entity.pk),
        payload=payload or {},
    )


@transaction.atomic
def publish_template_version(version: TemplateVersion, actor) -> TemplateVersion:
    version = (
        TemplateVersion.objects.select_for_update().select_related("template").get(pk=version.pk)
    )
    if version.status != TemplateStatus.DRAFT:
        raise ValidationError("只有草稿模板版本可以发布")
    clauses = list(
        version.template_clauses.select_related("clause_version__clause").order_by("sequence")
    )
    if not clauses:
        raise ValidationError("模板至少需要一个条款")

    canonical = {
        "template": version.template.code,
        "version": version.version,
        "clauses": [
            {
                "code": item.clause_version.clause.code,
                "hash": item.clause_version.content_hash,
                "locked": item.locked,
                "required": item.required,
                "sequence": item.sequence,
            }
            for item in clauses
        ],
        "variables": list(
            version.variables.order_by("key").values(
                "key", "label", "data_type", "required", "validation"
            )
        ),
    }
    version.content_hash = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()
    TemplateVersion.objects.filter(
        template=version.template, status=TemplateStatus.PUBLISHED
    ).update(status=TemplateStatus.RETIRED)
    version.status = TemplateStatus.PUBLISHED
    version.published_at = timezone.now()
    version.published_by = actor
    version.save(
        update_fields=["status", "content_hash", "published_at", "published_by", "updated_at"]
    )
    version.template.status = TemplateStatus.PUBLISHED
    version.template.save(update_fields=["status", "updated_at"])
    write_audit(
        actor=actor,
        action="template.version.published",
        entity=version,
        payload={"content_hash": version.content_hash, "version": version.version},
    )
    return version


@transaction.atomic
def create_contract_version(
    *, contract: Contract, snapshot: dict, actor, source_file=None
) -> ContractVersion:
    contract = Contract.objects.select_for_update().get(pk=contract.pk)
    if contract.status in {ContractStatus.SIGNED, ContractStatus.ARCHIVED}:
        raise ValidationError("已签署或归档合同不能创建新版本")
    if contract.template_version.status != TemplateStatus.PUBLISHED:
        raise ValidationError("合同只能使用已发布的模板版本")
    if not isinstance(snapshot, dict):
        raise ValidationError("snapshot 必须是对象")
    if source_file is not None:
        validate_contract_file(source_file)
    latest = contract.versions.aggregate(value=Max("version_no"))["value"] or 0
    version = ContractVersion.objects.create(
        contract=contract,
        version_no=latest + 1,
        snapshot=snapshot,
        source_file=source_file,
        submitted_by=actor,
    )
    contract.status = ContractStatus.DRAFT
    contract.save(update_fields=["status", "updated_at"])
    write_audit(
        actor=actor,
        action="contract.version.created",
        entity=version,
        payload={"contract": str(contract.pk), "version_no": version.version_no},
    )
    return version


def validate_contract_file(source_file) -> None:
    name = source_file.name.lower()
    if not name.endswith((".docx", ".pdf")):
        raise ValidationError("合同附件仅支持 DOCX 或 PDF")
    if source_file.size > 20 * 1024 * 1024:
        raise ValidationError("合同附件不能超过 20MB")
    if name.endswith(".docx"):
        try:
            with zipfile.ZipFile(source_file) as archive:
                names = archive.namelist()
                if "word/document.xml" not in names:
                    raise ValidationError("文件不是有效 DOCX")
                if sum(item.file_size for item in archive.infolist()) > 100 * 1024 * 1024:
                    raise ValidationError("DOCX 解压后体积过大")
                if any(item.lower().endswith("vbaproject.bin") for item in names):
                    raise ValidationError("不接受包含宏的合同文件")
        except zipfile.BadZipFile as exc:
            raise ValidationError("文件不是有效 DOCX") from exc
        finally:
            source_file.seek(0)


def _snapshot_clauses(snapshot: dict) -> dict[str, str]:
    clauses = snapshot.get("clauses", [])
    if not isinstance(clauses, list):
        raise ValidationError("snapshot.clauses 必须是数组")
    result = {}
    for item in clauses:
        if not isinstance(item, dict) or not item.get("code"):
            raise ValidationError("每个条款必须包含 code")
        result[str(item["code"])] = str(item.get("content", ""))
    return result


@transaction.atomic
def submit_for_review(version: ContractVersion, actor) -> ReviewCase:
    version = (
        ContractVersion.objects.select_for_update()
        .select_related("contract__template_version")
        .get(pk=version.pk)
    )
    if hasattr(version, "review_case"):
        raise ValidationError("该合同版本已经提交审核")
    contract = version.contract
    if contract.status not in {ContractStatus.DRAFT, ContractStatus.REJECTED}:
        raise ValidationError("当前合同状态不能提交审核")

    submitted = _snapshot_clauses(version.snapshot)
    baseline_items = list(
        contract.template_version.template_clauses.select_related("clause_version__clause").all()
    )
    findings: list[dict] = []
    baseline_codes = set()

    for item in baseline_items:
        clause_version = item.clause_version
        code = clause_version.clause.code
        baseline_codes.add(code)
        submitted_content = submitted.get(code)
        high_risk = item.locked or clause_version.is_core
        if submitted_content is None:
            if item.required:
                findings.append(
                    {
                        "source": RiskFinding.Source.DIFF,
                        "severity": RiskLevel.HIGH if high_risk else RiskLevel.MEDIUM,
                        "clause_code": code,
                        "title": "必选条款缺失",
                        "detail": f"合同中缺少必选条款：{clause_version.clause.title}",
                    }
                )
            continue
        submitted_hash = hashlib.sha256(normalize_text(submitted_content).encode()).hexdigest()
        if submitted_hash != clause_version.content_hash:
            findings.append(
                {
                    "source": RiskFinding.Source.DIFF,
                    "severity": RiskLevel.HIGH if high_risk else RiskLevel.MEDIUM,
                    "clause_code": code,
                    "title": "核心条款发生变更" if high_risk else "标准条款发生变更",
                    "detail": "提交内容与模板基线不一致，需要人工复核。",
                }
            )

    for added_code in sorted(set(submitted) - baseline_codes):
        findings.append(
            {
                "source": RiskFinding.Source.DIFF,
                "severity": RiskLevel.MEDIUM,
                "clause_code": added_code,
                "title": "新增非模板条款",
                "detail": "提交稿包含模板基线之外的条款。",
            }
        )

    variables = version.snapshot.get("variables", {})
    if not isinstance(variables, dict):
        raise ValidationError("snapshot.variables 必须是对象")
    for definition in contract.template_version.variables.filter(required=True):
        if variables.get(definition.key) in (None, ""):
            findings.append(
                {
                    "source": RiskFinding.Source.RULE,
                    "severity": RiskLevel.MEDIUM,
                    "clause_code": "",
                    "title": "必填变量缺失",
                    "detail": f"必填字段“{definition.label}”尚未填写。",
                }
            )

    severities = {item["severity"] for item in findings}
    risk_level = (
        RiskLevel.HIGH
        if RiskLevel.HIGH in severities
        else RiskLevel.MEDIUM
        if RiskLevel.MEDIUM in severities
        else RiskLevel.LOW
    )
    auto_approved = risk_level == RiskLevel.LOW
    review = ReviewCase.objects.create(
        contract_version=version,
        status=ReviewStatus.COMPLETED if auto_approved else ReviewStatus.IN_PROGRESS,
        risk_level=risk_level,
        summary=(
            "未发现模板偏离，规则自动通过。" if auto_approved else f"发现 {len(findings)} 项风险。"
        ),
        rule_set_version=RULE_SET_VERSION,
        completed_at=timezone.now() if auto_approved else None,
    )
    RiskFinding.objects.bulk_create([RiskFinding(review_case=review, **item) for item in findings])

    if risk_level == RiskLevel.MEDIUM:
        ApprovalTask.objects.create(
            review_case=review, step_order=1, name="法务专员审核", role_code="LEGAL_REVIEWER"
        )
    elif risk_level == RiskLevel.HIGH:
        ApprovalTask.objects.bulk_create(
            [
                ApprovalTask(
                    review_case=review,
                    step_order=1,
                    name="法务负责人审核",
                    role_code="LEGAL_MANAGER",
                ),
                ApprovalTask(
                    review_case=review,
                    step_order=1,
                    name="业务分管领导审核",
                    role_code="BUSINESS_LEADER",
                ),
            ]
        )

    version.submitted_at = timezone.now()
    version.is_final = auto_approved
    version.save(update_fields=["submitted_at", "is_final", "content_hash", "updated_at"])
    contract.status = ContractStatus.APPROVED if auto_approved else ContractStatus.IN_REVIEW
    contract.risk_level = risk_level
    contract.save(update_fields=["status", "risk_level", "updated_at"])
    write_audit(
        actor=actor,
        action="review.submitted",
        entity=review,
        payload={
            "risk_level": risk_level,
            "finding_count": len(findings),
            "rule_set_version": RULE_SET_VERSION,
            "auto_approved": auto_approved,
        },
    )
    return review


def can_decide_task(user, task: ApprovalTask) -> bool:
    return bool(
        user.is_superuser
        or task.assignee_id == user.pk
        or user.groups.filter(name=task.role_code).exists()
    )


@transaction.atomic
def decide_task(*, task: ApprovalTask, actor, decision: str, comment: str = "") -> ApprovalTask:
    task = (
        ApprovalTask.objects.select_for_update()
        .select_related("review_case__contract_version__contract")
        .get(pk=task.pk)
    )
    if task.status != TaskStatus.PENDING:
        raise ValidationError("该审批任务已经处理")
    if decision not in {TaskStatus.APPROVED, TaskStatus.REJECTED}:
        raise ValidationError("decision 只能是 APPROVED 或 REJECTED")
    if not can_decide_task(actor, task):
        raise ValidationError("你没有权限处理该审批任务")

    task.status = decision
    task.completed_at = timezone.now()
    task.save(update_fields=["status", "completed_at"])
    ApprovalAction.objects.create(task=task, actor=actor, action=decision, comment=comment)

    review = task.review_case
    contract_version = review.contract_version
    contract = contract_version.contract
    if decision == TaskStatus.REJECTED:
        review.tasks.filter(status=TaskStatus.PENDING).update(status=TaskStatus.CANCELLED)
        review.status = ReviewStatus.REJECTED
        review.completed_at = timezone.now()
        contract.status = ContractStatus.REJECTED
    elif not review.tasks.filter(status=TaskStatus.PENDING).exists():
        review.status = ReviewStatus.COMPLETED
        review.completed_at = timezone.now()
        contract_version.is_final = True
        contract_version.save(update_fields=["is_final", "content_hash", "updated_at"])
        contract.status = ContractStatus.APPROVED

    review.save(update_fields=["status", "completed_at", "updated_at"])
    contract.save(update_fields=["status", "updated_at"])
    write_audit(
        actor=actor,
        action="approval.decided",
        entity=task,
        payload={"decision": decision, "review_case": str(review.pk), "comment": comment},
    )
    return task
