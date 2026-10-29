from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from access_control.models import GruppoOrganizzativo


class Command(BaseCommand):
    help = (
        "Crea i Gruppi Operativi mancanti a partire dai gruppi Django "
        "gia presenti nel database locale."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Esegue la creazione. Senza questa opzione mostra solo l'anteprima.",
        )
        parser.add_argument(
            "--tipo",
            choices=GruppoOrganizzativo.Tipo.values,
            default=GruppoOrganizzativo.Tipo.TECNICO,
            help="Tipo assegnato ai nuovi gruppi (predefinito: TEC).",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        tipo = options["tipo"]
        da_creare = []
        conflitti = []

        gruppi_esistenti = set(
            GruppoOrganizzativo.objects.values_list("django_group_id", flat=True)
        )
        nomi_occupati = set(
            GruppoOrganizzativo.objects.values_list("nome", flat=True)
        )
        directory_name_occupati = set(
            GruppoOrganizzativo.objects.values_list("directory_name", flat=True)
        )

        for django_group in Group.objects.order_by("name"):
            if django_group.pk in gruppi_esistenti:
                continue

            nome = django_group.name.strip()
            if not nome:
                conflitti.append((django_group.name, "nome gruppo vuoto"))
                continue

            if nome in nomi_occupati:
                conflitti.append(
                    (nome, "nome gia utilizzato da un altro Gruppo Operativo")
                )
                continue

            if nome in directory_name_occupati:
                conflitti.append(
                    (nome, "directory_name gia associato a un altro gruppo")
                )
                continue

            da_creare.append(django_group)
            nomi_occupati.add(nome)
            directory_name_occupati.add(nome)

        azione = "Creerebbe" if not apply_changes else "Creazione"
        self.stdout.write(f"{azione} di {len(da_creare)} Gruppi Operativi.")
        for django_group in da_creare:
            self.stdout.write(f"  - {django_group.name}")

        if conflitti:
            self.stderr.write(self.style.WARNING("Gruppi non elaborati:"))
            for nome, motivo in conflitti:
                self.stderr.write(self.style.WARNING(f"  - {nome}: {motivo}"))

        if not apply_changes:
            self.stdout.write(
                self.style.WARNING(
                    "Anteprima completata. Rieseguire con --apply per creare i record."
                )
            )
            return

        try:
            with transaction.atomic():
                GruppoOrganizzativo.objects.bulk_create(
                    [
                        GruppoOrganizzativo(
                            nome=django_group.name,
                            directory_name=django_group.name,
                            django_group=django_group,
                            tipo=tipo,
                            attivo=True,
                            sincronizzato=True,
                        )
                        for django_group in da_creare
                    ]
                )
        except Exception as exc:
            raise CommandError(f"Creazione annullata: {exc}") from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Creati correttamente {len(da_creare)} Gruppi Operativi."
            )
        )
