from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("prenotazioni", "0007_unitaorganizzativawordpress_responsabile"),
    ]

    operations = [
        migrations.AddField(
            model_name="appuntamentowordpress",
            name="nome_prenotato",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
