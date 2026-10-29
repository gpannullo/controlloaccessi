from django.db import models

class Event(models.Model):
    fingerprint = models.CharField(max_length=64, unique=True)
    source = models.GenericIPAddressField(db_index=True)
    computer = models.CharField(max_length=255)
    record_id = models.PositiveBigIntegerField()
    event_id = models.PositiveIntegerField(db_index=True)
    occurred_at = models.DateTimeField(db_index=True)
    received_at = models.DateTimeField(auto_now_add=True)
    username = models.CharField(max_length=255, blank=True, db_index=True)
    client_ip = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    workstation = models.CharField(max_length=255, blank=True)
    protocol = models.CharField(max_length=100, blank=True)
    logon_type = models.CharField(max_length=20, blank=True)
    data = models.JSONField(default=dict)

    class Meta:
        ordering = ['-occurred_at', '-pk']
        indexes = [models.Index(fields=['client_ip', 'event_id', 'occurred_at'])]
        verbose_name = 'Evento AD'
        verbose_name_plural = 'Eventi AD'

class Alert(models.Model):
    key = models.CharField(max_length=128, unique=True)
    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name='alerts')
    rule = models.CharField(max_length=50, db_index=True)
    severity = models.CharField(max_length=10, choices=[('warning', 'Avviso'), ('high', 'Alta')])
    description = models.TextField()
    evidence = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Segnalazione AD'
        verbose_name_plural = 'Segnalazioni AD'
