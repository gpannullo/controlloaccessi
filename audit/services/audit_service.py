from audit.models import AuditEvent


class AuditService:

    @staticmethod
    def log(**kwargs):

        return AuditEvent.objects.create(**kwargs)