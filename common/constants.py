from datetime import timedelta

from django.db import models

# Durata predefinita di uno slot appuntamento
DEFAULT_APPOINTMENT_DURATION = timedelta(minutes=30)

# Prefisso badge visitatori
VISITOR_BADGE_PREFIX = "V"

# Lunghezza massima codice badge
VISITOR_BADGE_LENGTH = 6

# Numero massimo di visitatori contemporaneamente presenti
MAX_VISITORS = 500


class StatoVisita(models.TextChoices):
    REGISTRATO = "REG", "Registrato"
    SALA_ATTESA = "ATT", "Sala d'attesa"
    CHIAMATO = "CHI", "Chiamato"
    FUORI_PORTA = "POR", "Fuori porta"
    IN_VISITA = "VIS", "In visita"
    TERMINATA = "TER", "Terminata"
    ANNULLATA = "ANN", "Annullata"
