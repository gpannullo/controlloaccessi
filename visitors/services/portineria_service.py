from django.utils import timezone
from django.db.models import Q

from audit.services.audit_service import AuditService
from visitors.models import Appuntamento, AccessoVisitatore
from visitors.utils import ufficio_aperto


class PortineriaService:

    def registra_ingresso(self, visitatore, ufficio, motivo=""):

        if not ufficio_aperto(ufficio):
            raise Exception("Ufficio chiuso")

        appuntamento = Appuntamento.objects.filter(
            nome_cittadino=visitatore.nome,
            cognome_cittadino=visitatore.cognome,
            ufficio=ufficio,
            stato="CO"
        ).first()

        accesso = AccessoVisitatore.objects.create(
            visitatore=visitatore,
            ufficio_destinazione=ufficio,
            motivo=motivo or ("Appuntamento" if appuntamento else "")
        )

        AuditService.log(
            user=None,
            tipo="ACCESSO",
            oggetto=str(visitatore),
            descrizione=f"Ingresso {'con appuntamento' if appuntamento else 'senza appuntamento'}"
        )

        return accesso
