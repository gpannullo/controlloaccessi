from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("spid_cie", "0002_messaggioio")]

    operations = [
        migrations.CreateModel(
            name="CodiceAccessoGateway",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("codice_hash", models.CharField(max_length=64, unique=True)),
                ("codice_fiscale", models.CharField(max_length=16)),
                ("nome", models.CharField(blank=True, max_length=100)),
                ("cognome", models.CharField(blank=True, max_length=100)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("destinazione", models.CharField(max_length=500)),
                ("scade_il", models.DateTimeField(db_index=True)),
                ("usato_il", models.DateTimeField(blank=True, null=True)),
                ("creato_il", models.DateTimeField(auto_now_add=True)),
            ],
            options={"verbose_name": "Codice accesso gateway SPID", "verbose_name_plural": "Codici accesso gateway SPID", "ordering": ["-creato_il"]},
        ),
    ]
