from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.contracts.models import Contract, ContractTemplate, TemplateStatus, TemplateVersion


class ApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="owner", password="test-password-2026")
        self.other = user_model.objects.create_user(username="other", password="test-password-2026")
        template = ContractTemplate.objects.create(
            code="API-TEMPLATE",
            name="接口模板",
            created_by=self.user,
            status=TemplateStatus.PUBLISHED,
        )
        self.template_version = TemplateVersion.objects.create(
            template=template, version="1.0", status=TemplateStatus.PUBLISHED
        )
        self.contract = Contract.objects.create(
            code="OWNER-ONLY",
            title="仅负责人可见",
            counterparty="相对方",
            owner=self.user,
            template_version=self.template_version,
        )

    def test_health_is_public(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_login_returns_token_and_user(self):
        response = self.client.post(
            reverse("login"), {"username": "owner", "password": "test-password-2026"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["token"])
        self.assertEqual(response.json()["user"]["username"], "owner")

    def test_contract_queryset_does_not_leak_other_owners(self):
        self.client.force_authenticate(self.other)
        response = self.client.get("/api/contracts/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 0)
