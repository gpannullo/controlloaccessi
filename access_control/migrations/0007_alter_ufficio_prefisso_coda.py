from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("access_control", "0006_alter_gruppoorganizzativo_django_group"),
    ]

    operations = [
        migrations.AlterField(
            model_name="ufficio",
            name="prefisso_coda",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Generato automaticamente se non indicato (A, B, …, poi AB, AC, …). "
                    "Impostare un prefisso diverso per ogni ufficio."
                ),
                max_length=2,
                verbose_name="Prefisso coda",
            ),
        ),
    ]
