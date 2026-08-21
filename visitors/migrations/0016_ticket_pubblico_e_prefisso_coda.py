from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("access_control", "0005_ufficio_prefisso_coda"),
        ("visitors", "0011_accessovisitatore_accesso_precedente"),
    ]

    operations = [
        migrations.AddField(
            model_name="accessovisitatore",
            name="prefisso_coda",
            field=models.CharField(
                blank=True,
                editable=False,
                max_length=1,
                verbose_name="Prefisso della coda",
            ),
        ),
        migrations.AddField(
            model_name="accessovisitatore",
            name="token_pubblico",
            field=models.CharField(
                blank=True,
                db_index=True,
                editable=False,
                max_length=64,
                null=True,
                unique=True,
                verbose_name="Token pubblico ticket",
            ),
        ),
        migrations.AddField(
            model_name="accessovisitatore",
            name="token_pubblico_creato_il",
            field=models.DateTimeField(
                blank=True,
                editable=False,
                null=True,
                verbose_name="Creazione token pubblico",
            ),
        ),
    ]
