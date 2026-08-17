from visitors.models import Appuntamento
from access_control.services.office_service import OfficeService

from common.exceptions import (
    AppointmentConflictException,
    OfficeClosedException,
)


class AppointmentService:

    @staticmethod
    def create(**kwargs):

        ufficio = kwargs["ufficio"]
        data_ora = kwargs["data_ora"]

        if not OfficeService.is_open(ufficio, data_ora):
            raise OfficeClosedException(
                "L'ufficio non è aperto."
            )

        if Appuntamento.objects.filter(
            ufficio=ufficio,
            data_ora=data_ora,
            stato__in=["PR", "CO"],
        ).exists():

            raise AppointmentConflictException(
                "Lo slot è già occupato."
            )

        return Appuntamento.objects.create(**kwargs)