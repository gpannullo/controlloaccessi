from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("access_control", "0004_ufficio_numero_visite_media_ufficio_overbooking_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="ufficio",
            name="prefisso_coda",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Una lettera visibile sul ticket (es. A per A001). "
                    "Impostare un prefisso diverso per ogni ufficio."
                ),
                max_length=1,
                verbose_name="Prefisso coda",
            ),
        ),
    ]
