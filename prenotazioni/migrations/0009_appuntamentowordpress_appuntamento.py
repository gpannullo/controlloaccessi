from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("prenotazioni", "0008_appuntamentowordpress_nome_prenotato"),
        ("visitors", "0018_alter_accessovisitatore_prefisso_coda"),
    ]

    operations = [
        migrations.AddField(
            model_name="appuntamentowordpress",
            name="appuntamento",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="origine_wordpress",
                to="visitors.appuntamento",
                verbose_name="Appuntamento locale collegato",
            ),
        ),
    ]
