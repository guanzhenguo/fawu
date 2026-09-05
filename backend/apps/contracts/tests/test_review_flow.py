from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.contracts.models import (
    AuditEvent,
    Clause,
    ClauseVersion,
    Contract,
    ContractStatus,
    ContractTemplate,
    RiskLevel,
    TaskStatus,
    TemplateClause,
    TemplateVersion,
)
from apps.contracts.services import (
    create_contract_version,
    decide_task,
    publish_template_version,
    submit_for_review,
)


class ReviewFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="legal", password="strong-test-password"
        )
        self.template = ContractTemplate.objects.create(
            code="SALE", name="销售合同", created_by=self.user
        )
        self.template_version = TemplateVersion.objects.create(
            template=self.template, version="1.0"
        )
        self.core_clause = Clause.objects.create(code="DISPUTE", title="争议解决")
        self.core_version = ClauseVersion.objects.create(
            clause=self.core_clause,
            version="1.0",
            content="争议由甲方所在地人民法院管辖。",
            is_core=True,
            risk_level=RiskLevel.HIGH,
            created_by=self.user,
        )
        self.normal_clause = Clause.objects.create(code="PAYMENT", title="付款")
        self.normal_version = ClauseVersion.objects.create(
            clause=self.normal_clause,
            version="1.0",
            content="验收合格后十个工作日内付款。",
            created_by=self.user,
        )
        TemplateClause.objects.create(
            template_version=self.template_version,
            clause_version=self.core_version,
            sequence=1,
            locked=True,
        )
        TemplateClause.objects.create(
            template_version=self.template_version,
            clause_version=self.normal_version,
            sequence=2,
        )
        publish_template_version(self.template_version, self.user)

    def make_contract_version(self, code, clauses):
        contract = Contract.objects.create(
            code=code,
            title=f"合同 {code}",
            counterparty="示例公司",
            owner=self.user,
            template_version=self.template_version,
        )
        version = create_contract_version(
            contract=contract,
            snapshot={"variables": {}, "clauses": clauses},
            actor=self.user,
        )
        return contract, version

    def test_unchanged_contract_is_auto_approved(self):
        contract, version = self.make_contract_version(
            "C-LOW",
            [
                {"code": "DISPUTE", "content": self.core_version.content},
                {"code": "PAYMENT", "content": self.normal_version.content},
            ],
        )
        review = submit_for_review(version, self.user)

        contract.refresh_from_db()
        version.refresh_from_db()
        self.assertEqual(review.risk_level, RiskLevel.LOW)
        self.assertEqual(contract.status, ContractStatus.APPROVED)
        self.assertTrue(version.is_final)
        self.assertFalse(review.tasks.exists())

    def test_normal_clause_change_routes_to_legal_reviewer(self):
        contract, version = self.make_contract_version(
            "C-MEDIUM",
            [
                {"code": "DISPUTE", "content": self.core_version.content},
                {"code": "PAYMENT", "content": "验收合格后六十日内付款。"},
            ],
        )
        review = submit_for_review(version, self.user)

        self.assertEqual(review.risk_level, RiskLevel.MEDIUM)
        self.assertEqual(review.tasks.count(), 1)
        self.assertEqual(review.tasks.get().role_code, "LEGAL_REVIEWER")
        self.assertEqual(review.findings.count(), 1)

    def test_core_change_requires_two_approvals(self):
        contract, version = self.make_contract_version(
            "C-HIGH",
            [
                {"code": "DISPUTE", "content": "争议由乙方所在地仲裁委员会仲裁。"},
                {"code": "PAYMENT", "content": self.normal_version.content},
            ],
        )
        review = submit_for_review(version, self.user)
        self.assertEqual(review.risk_level, RiskLevel.HIGH)
        self.assertEqual(review.tasks.count(), 2)

        first, second = list(review.tasks.all())
        decide_task(task=first, actor=self.user, decision=TaskStatus.APPROVED, comment="同意")
        contract.refresh_from_db()
        self.assertEqual(contract.status, ContractStatus.IN_REVIEW)

        decide_task(task=second, actor=self.user, decision=TaskStatus.APPROVED, comment="同意")
        contract.refresh_from_db()
        version.refresh_from_db()
        self.assertEqual(contract.status, ContractStatus.APPROVED)
        self.assertTrue(version.is_final)

    def test_rejection_cancels_parallel_task(self):
        contract, version = self.make_contract_version(
            "C-REJECT",
            [{"code": "DISPUTE", "content": "删除管辖限制"}],
        )
        review = submit_for_review(version, self.user)
        task = review.tasks.first()
        decide_task(task=task, actor=self.user, decision=TaskStatus.REJECTED, comment="风险过高")

        contract.refresh_from_db()
        self.assertEqual(contract.status, ContractStatus.REJECTED)
        self.assertFalse(review.tasks.filter(status=TaskStatus.PENDING).exists())

    def test_audit_event_is_immutable(self):
        event = AuditEvent.objects.first()
        event.action = "tampered"
        with self.assertRaises(ValidationError):
            event.save()

        with self.assertRaises(ValidationError):
            event.delete()
