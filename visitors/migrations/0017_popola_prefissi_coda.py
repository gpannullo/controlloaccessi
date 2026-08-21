from django.db import migrations


def popola_prefissi(apps, schema_editor):
    Ufficio = apps.get_model("access_control", "Ufficio")
    AccessoVisitatore = apps.get_model("visitors", "AccessoVisitatore")

    for ufficio in Ufficio.objects.all().only("pk", "codice", "prefisso_coda"):
        prefisso = (ufficio.prefisso_coda or ufficio.codice[:1] or "A").upper()
        AccessoVisitatore.objects.filter(
            ufficio_destinazione_id=ufficio.pk,
            prefisso_coda="",
        ).update(prefisso_coda=prefisso)


class Migration(migrations.Migration):
    dependencies = [("visitors", "0016_ticket_pubblico_e_prefisso_coda")]

    operations = [migrations.RunPython(popola_prefissi, migrations.RunPython.noop)]
