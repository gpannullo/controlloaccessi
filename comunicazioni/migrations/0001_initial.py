from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("access_control", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="ComunicazioneEmail",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("oggetto", models.CharField(max_length=255)),
                ("messaggio", models.TextField(help_text="Testo in formato semplice dell'e-mail.")),
                ("destinazione", models.CharField(choices=[("IST", "E-mail istituzionale"), ("PER", "E-mail personale"), ("AGG", "E-mail aggiuntiva")], default="IST", max_length=3)),
                ("tutti_gli_utenti_attivi", models.BooleanField(default=False, verbose_name="Tutti gli utenti attivi")),
                ("stato", models.CharField(choices=[("BOZ", "Bozza"), ("QUE", "Accodata per l'invio")], default="BOZ", editable=False, max_length=3)),
                ("creato_il", models.DateTimeField(auto_now_add=True)),
                ("accodata_il", models.DateTimeField(blank=True, editable=False, null=True)),
                ("creata_da", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="comunicazioni_create", to=settings.AUTH_USER_MODEL)),
                ("destinatari", models.ManyToManyField(blank=True, related_name="comunicazioni_ricevute", to=settings.AUTH_USER_MODEL)),
                ("gruppi", models.ManyToManyField(blank=True, related_name="comunicazioni_email", to="auth.group")),
                ("uffici", models.ManyToManyField(blank=True, related_name="comunicazioni_email", to="access_control.ufficio")),
            ],
            options={"verbose_name": "Comunicazione e-mail", "verbose_name_plural": "Comunicazioni e-mail", "ordering": ["-creato_il"]},
        ),
        migrations.CreateModel(
            name="DestinatarioComunicazioneEmail",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("indirizzo_email", models.EmailField(max_length=254)),
                ("accodato_il", models.DateTimeField(auto_now_add=True)),
                ("comunicazione", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="invii", to="comunicazioni.comunicazioneemail")),
                ("utente", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "Destinatario comunicazione", "verbose_name_plural": "Destinatari comunicazione", "ordering": ["indirizzo_email"]},
        ),
        migrations.AddConstraint(
            model_name="destinatariocomunicazioneemail",
            constraint=models.UniqueConstraint(fields=("comunicazione", "indirizzo_email"), name="destinatario_comunicazione_email_unico"),
        ),
    ]
