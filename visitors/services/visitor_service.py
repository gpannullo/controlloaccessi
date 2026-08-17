from visitors.models import Visitatore


class VisitorService:

    @staticmethod
    def find_or_create(**kwargs):

        visitatore, _ = Visitatore.objects.get_or_create(
            nome=kwargs["nome"],
            cognome=kwargs["cognome"],
            defaults=kwargs,
        )

        return visitatore