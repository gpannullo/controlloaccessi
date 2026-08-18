from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("visitors", "0013_accompagnato_rientro_badge"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AmministratoreEnte",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=100, verbose_name="Nome")),
                ("cognome", models.CharField(max_length=100, verbose_name="Cognome")),
                ("carica", models.CharField(blank=True, max_length=150, verbose_name="Carica")),
                ("attivo", models.BooleanField(default=True, verbose_name="Attivo")),
                ("ordine", models.PositiveIntegerField(default=0, verbose_name="Ordine")),
            ],
            options={
                "verbose_name": "Amministratore dell'Ente",
                "verbose_name_plural": "Amministratori dell'Ente",
                "ordering": ["ordine", "cognome", "nome"],
            },
        ),
        migrations.CreateModel(
            name="TransitoAmministratore",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo", models.CharField(choices=[("IN", "Ingresso"), ("OUT", "Uscita")], db_index=True, max_length=3, verbose_name="Tipo transito")),
                ("timestamp", models.DateTimeField(db_index=True, default=django.utils.timezone.now, verbose_name="Data e ora")),
                ("amministratore", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="transiti", to="visitors.amministratoreente", verbose_name="Amministratore")),
                ("operatore", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="transiti_amministratori_registrati", to=settings.AUTH_USER_MODEL, verbose_name="Registrato da")),
            ],
            options={
                "verbose_name": "Transito amministratore",
                "verbose_name_plural": "Transiti amministratori",
                "ordering": ["-timestamp", "-pk"],
            },
        ),
        migrations.AddIndex(
            model_name="transitoamministratore",
            index=models.Index(fields=["amministratore", "timestamp"], name="idx_amm_transito_data"),
        ),
    ]
