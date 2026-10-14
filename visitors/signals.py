"""Segnali per aggiornare l'App IO quando cambia lo stato della coda."""

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from visitors.models import AccessoVisitatore
from visitors.services.queue_io_notification_service import QueueIONotificationService


@receiver(pre_save, sender=AccessoVisitatore, dispatch_uid="visitors.queue_io_before_save")
def memorizza_stato_coda_precedente(sender, instance, **kwargs):
    if not instance.pk:
        instance._stato_coda_precedente = None
        return
    instance._stato_coda_precedente = sender.objects.filter(pk=instance.pk).values(
        "stato_coda", "ufficio_destinazione_id", "visita_conclusa_il"
    ).first()


@receiver(post_save, sender=AccessoVisitatore, dispatch_uid="visitors.queue_io_after_save")
def notifica_variazione_coda(sender, instance, created, **kwargs):
    precedente = getattr(instance, "_stato_coda_precedente", None)
    conclusa = bool(instance.visita_conclusa_il)
    cambiata = (
        created
        or precedente is None
        or precedente["stato_coda"] != instance.stato_coda
        or precedente["ufficio_destinazione_id"] != instance.ufficio_destinazione_id
        or bool(precedente["visita_conclusa_il"]) != conclusa
    )
    if not cambiata:
        return

    accesso_id = instance.pk
    stato_coda = instance.stato_coda
    ufficio_id = instance.ufficio_destinazione_id
    transaction.on_commit(
        lambda: QueueIONotificationService.invia_se_coerente(
            accesso_id, stato_coda, ufficio_id, conclusa
        )
    )
