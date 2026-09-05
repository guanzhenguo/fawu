import os

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError

from apps.contracts.models import (
    Clause,
    ClauseVersion,
    ContractTemplate,
    RiskLevel,
    TemplateClause,
    TemplateStatus,
    TemplateVersion,
    VariableDefinition,
)
from apps.contracts.services import publish_template_version


class Command(BaseCommand):
    help = "创建本地演示管理员、审批角色和一份已发布销售合同模板"

    def add_arguments(self, parser):
        parser.add_argument("--username", default="admin")

    def handle(self, *args, **options):
        password = os.getenv("FAWU_BOOTSTRAP_PASSWORD")
        if not password or len(password) < 10:
            raise CommandError("请先设置至少 10 位的 FAWU_BOOTSTRAP_PASSWORD 环境变量")

        user_model = get_user_model()
        user, _ = user_model.objects.get_or_create(username=options["username"])
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.save()

        for role in ("LEGAL_REVIEWER", "LEGAL_MANAGER", "BUSINESS_LEADER"):
            group, _ = Group.objects.get_or_create(name=role)
            user.groups.add(group)

        template, _ = ContractTemplate.objects.get_or_create(
            code="SALE-GENERAL",
            defaults={
                "name": "通用销售合同",
                "description": "系统初始化演示模板",
                "created_by": user,
            },
        )
        version, _ = TemplateVersion.objects.get_or_create(
            template=template,
            version="1.0",
            defaults={
                "guidance": "适用于一般产品或服务销售场景。",
                "risk_notice": "管辖、违约责任为核心条款，修改后触发高级审核。",
            },
        )
        if version.status == TemplateStatus.DRAFT:
            clause_specs = [
                (
                    "SUBJECT",
                    "合同标的",
                    "甲方向乙方提供本合同约定的产品或服务。",
                    False,
                    RiskLevel.MEDIUM,
                ),
                (
                    "PAYMENT",
                    "付款安排",
                    "乙方应在验收合格后十个工作日内支付全部价款。",
                    False,
                    RiskLevel.MEDIUM,
                ),
                (
                    "LIABILITY",
                    "违约责任",
                    "违约方应赔偿守约方因此遭受的实际损失。",
                    True,
                    RiskLevel.HIGH,
                ),
                (
                    "DISPUTE",
                    "争议解决",
                    "因本合同发生的争议由甲方所在地有管辖权的人民法院管辖。",
                    True,
                    RiskLevel.HIGH,
                ),
            ]
            for sequence, (code, title, content, is_core, risk_level) in enumerate(
                clause_specs, start=1
            ):
                clause, _ = Clause.objects.get_or_create(code=code, defaults={"title": title})
                clause_version, _ = ClauseVersion.objects.get_or_create(
                    clause=clause,
                    version="1.0",
                    defaults={
                        "content": content,
                        "is_core": is_core,
                        "risk_level": risk_level,
                        "created_by": user,
                    },
                )
                TemplateClause.objects.get_or_create(
                    template_version=version,
                    clause_version=clause_version,
                    defaults={"sequence": sequence, "required": True, "locked": is_core},
                )
            VariableDefinition.objects.get_or_create(
                template_version=version,
                key="contract_amount",
                defaults={"label": "合同金额", "data_type": "MONEY", "required": True},
            )
            publish_template_version(version, user)

        self.stdout.write(
            self.style.SUCCESS(
                f"初始化完成。登录用户名：{user.username}；模板：{template.code} v{version.version}"
            )
        )
