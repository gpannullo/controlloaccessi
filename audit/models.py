from django.conf import settings
from django.db import models


class AuditEvent(models.Model):

    class TipoEvento(models.TextChoices):
        LOGIN = "LOGIN", "Login"
        LOGOUT = "LOGOUT", "Logout"
        CREATE = "CREATE", "Creazione"
        UPDATE = "UPDATE", "Aggiornamento"
        DELETE = "DELETE", "Cancellazione"
        ACCESSO = "ACCESSO", "Accesso visitatore"
        SYSTEM = "SYSTEM", "Sistema"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    tipo = models.CharField(max_length=20, choices=TipoEvento.choices)

    oggetto = models.CharField(max_length=255, blank=True)

    descrizione = models.TextField(blank=True)

    timestamp = models.DateTimeField(auto_now_add=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.tipo} - {self.timestamp}"