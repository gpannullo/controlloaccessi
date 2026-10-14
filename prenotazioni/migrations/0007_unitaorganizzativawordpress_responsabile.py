from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("prenotazioni", "0006_alter_personalewordpress_utente"),
    ]

    operations = [
        migrations.AddField(
            model_name="unitaorganizzativawordpress",
            name="responsabile",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="unita_organizzative_responsabili",
                to="prenotazioni.personalewordpress",
                verbose_name="Responsabile WordPress",
            ),
        ),
    ]
