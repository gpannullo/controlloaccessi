import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("presenze_qr", "0003_gruppopresenze")]
    operations = [
        migrations.CreateModel(
            name="GiustificativoPresenza",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("dal", models.DateField()), ("al", models.DateField()), ("causale", models.CharField(max_length=120)),
                ("note", models.TextField(blank=True)), ("allegato", models.FileField(blank=True, upload_to="presenze/giustificativi/")),
                ("stato", models.CharField(choices=[("ATTESA", "In attesa"), ("APPROVATO", "Approvato"), ("RIFIUTATO", "Rifiutato")], default="ATTESA", max_length=10)),
                ("creato_il", models.DateTimeField(auto_now_add=True)), ("approvato_il", models.DateTimeField(blank=True, null=True)),
                ("approvato_da", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="giustificativi_approvati", to=settings.AUTH_USER_MODEL)),
                ("gruppo", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="giustificativi", to="presenze_qr.gruppopresenze")),
                ("utente", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="giustificativi_presenza", to=settings.AUTH_USER_MODEL)),
            ], options={"ordering": ["-creato_il"]},
        ),
        migrations.CreateModel(
            name="AutodichiarazioneTimbratura",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("registrata_il", models.DateTimeField()), ("verso", models.CharField(choices=[("I", "Entrata"), ("U", "Uscita")], max_length=1)),
                ("motivazione", models.TextField()), ("token_approvazione", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("stato", models.CharField(choices=[("ATTESA", "In attesa"), ("APPROVATA", "Approvata"), ("RIFIUTATA", "Rifiutata")], default="ATTESA", max_length=10)),
                ("creata_il", models.DateTimeField(auto_now_add=True)), ("approvata_il", models.DateTimeField(blank=True, null=True)),
                ("approvata_da", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="autodichiarazioni_approvate", to=settings.AUTH_USER_MODEL)),
                ("gruppo", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="autodichiarazioni", to="presenze_qr.gruppopresenze")),
                ("timbratura", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="autodichiarazione", to="presenze_qr.timbratura")),
                ("utente", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="autodichiarazioni_presenza", to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
