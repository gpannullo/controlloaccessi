from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("visitors", "0017_popola_prefissi_coda"),
    ]

    operations = [
        migrations.AlterField(
            model_name="accessovisitatore",
            name="prefisso_coda",
            field=models.CharField(
                blank=True,
                editable=False,
                max_length=2,
                verbose_name="Prefisso della coda",
            ),
        ),
    ]
