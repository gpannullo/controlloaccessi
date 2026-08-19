from django.core.management.base import BaseCommand

from accounts.services.snapshot_presence_service import (
    SnapshotPresenzaService,
)


class Command(BaseCommand):
    help = (
        "Salva uno snapshot della presenza dei dipendenti "
        "per tutti gli uffici attivi."
    )

    def handle(self, *args, **options):
        snapshots = (
            SnapshotPresenzaService
            .crea_snapshot_tutti_uffici()
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Creati {len(snapshots)} snapshot presenza."
            )
        )

        for snapshot in snapshots:
            self.stdout.write(
                (
                    f"- {snapshot.ufficio.nome}: "
                    f"{snapshot.dipendenti_presenti}/"
                    f"{snapshot.dipendenti_totali} dipendenti; "
                    f"{snapshot.sportellisti_presenti}/"
                    f"{snapshot.sportellisti_totali} sportellisti."
                )
            )
