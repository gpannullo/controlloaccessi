from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("visitors", "0012_alter_accessovisitatore_tipo_accesso"),
    ]

    operations = [
        migrations.AddField(
            model_name="badge",
            name="riservato_rientro",
            field=models.BooleanField(
                db_index=True,
                default=False,
                verbose_name="Riservato per rientro",
            ),
        ),
        migrations.AddField(
            model_name="accessovisitatore",
            name="accompagnato",
            field=models.BooleanField(
                default=False,
                verbose_name="Visitatore accompagnato",
            ),
        ),
        migrations.AddField(
            model_name="accessovisitatore",
            name="rientro_prioritario",
            field=models.BooleanField(
                db_index=True,
                default=False,
                verbose_name="Rientro prioritario",
            ),
        ),
    ]
