from django.core.management.base import BaseCommand, CommandError

from apps.contracts.models import AuditEvent


class Command(BaseCommand):
    help = "验证审计事件的前向哈希链是否完整"

    def handle(self, *args, **options):
        previous_hash = ""
        count = 0
        for event in AuditEvent.objects.order_by("created_at", "id").iterator():
            if event.previous_hash != previous_hash:
                raise CommandError(f"事件 {event.pk} 的 previous_hash 不匹配")
            if event.event_hash != event.calculate_hash():
                raise CommandError(f"事件 {event.pk} 的 event_hash 不匹配")
            previous_hash = event.event_hash
            count += 1
        self.stdout.write(self.style.SUCCESS(f"审计链验证通过，共 {count} 个事件"))
