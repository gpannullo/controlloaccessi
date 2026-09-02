from django.core.exceptions import ValidationError
from django.db import transaction

from accounts.services.directory_admin_service import DirectoryAdminService
from access_control.models import AssegnazioneUfficio, GruppoOrganizzativo, Ufficio


class OfficeAssignmentService:
    """Mantiene coerenti assegnazioni ufficio, gruppi Django e gruppi AD."""

    @staticmethod
    def _gruppi_gestiti():
        return GruppoOrganizzativo.objects.filter(
            tipo=GruppoOrganizzativo.Tipo.ORGANIZZATIVO,
            uffici__isnull=False,
        ).distinct()

    def _gruppi_necessari(self, utente, ufficio_aggiuntivo=None, ufficio_rimosso=None):
        uffici_ids = set(
            AssegnazioneUfficio.objects.filter(utente=utente, attiva=True)
            .values_list("ufficio_id", flat=True)
        )
        if ufficio_aggiuntivo:
            uffici_ids.add(ufficio_aggiuntivo.pk)
        if ufficio_rimosso:
            uffici_ids.discard(ufficio_rimosso.pk)
        return set(
            Ufficio.objects.filter(
                pk__in=uffici_ids,
                gruppo_operativo__isnull=False,
                gruppo_operativo__attivo=True,
            ).values_list("gruppo_operativo__directory_name", flat=True)
        )

    def _sincronizza_gruppi(self, utente, necessari):
        gruppi_gestiti = self._gruppi_gestiti()
        correnti = set(
            utente.groups.filter(
                gruppo_organizzativo__in=gruppi_gestiti,
            ).values_list("gruppo_organizzativo__directory_name", flat=True)
        )
        da_aggiungere = necessari - correnti
        da_rimuovere = correnti - necessari
        DirectoryAdminService().sincronizza_gruppi_selezionati(
            utente.username,
            da_aggiungere=da_aggiungere,
            da_rimuovere=da_rimuovere,
        )

        if da_aggiungere:
            utente.groups.add(
                *GruppoOrganizzativo.objects.filter(
                    directory_name__in=da_aggiungere,
                ).values_list("django_group", flat=True)
            )
        if da_rimuovere:
            utente.groups.remove(
                *GruppoOrganizzativo.objects.filter(
                    directory_name__in=da_rimuovere,
                ).values_list("django_group", flat=True)
            )

    @transaction.atomic
    def assegna(self, utente, ufficio):
        if not ufficio.gruppo_operativo_id:
            raise ValidationError("L'ufficio non ha un Gruppo Operativo configurato.")
        assegnazione, creata = AssegnazioneUfficio.objects.get_or_create(
            utente=utente,
            ufficio=ufficio,
            defaults={"attiva": True},
        )
        if not creata and assegnazione.attiva:
            return assegnazione, False
        necessari = self._gruppi_necessari(utente, ufficio_aggiuntivo=ufficio)
        self._sincronizza_gruppi(utente, necessari)
        if not assegnazione.attiva:
            assegnazione.attiva = True
            assegnazione.save(update_fields=["attiva", "aggiornata_il"])
        return assegnazione, True

    @transaction.atomic
    def rimuovi(self, utente, ufficio):
        assegnazione = AssegnazioneUfficio.objects.filter(
            utente=utente,
            ufficio=ufficio,
            attiva=True,
        ).first()
        if not assegnazione:
            return False
        necessari = self._gruppi_necessari(utente, ufficio_rimosso=ufficio)
        self._sincronizza_gruppi(utente, necessari)
        assegnazione.attiva = False
        assegnazione.save(update_fields=["attiva", "aggiornata_il"])
        return True
