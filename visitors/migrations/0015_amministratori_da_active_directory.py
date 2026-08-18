from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("visitors", "0014_amministratori_transiti"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="amministratoreente",
            name="utente",
            field=models.OneToOneField(
                limit_choices_to={"is_active": True},
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="profilo_amministratore_ente",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Utente Active Directory",
            ),
        ),
        migrations.RemoveField(
            model_name="amministratoreente",
            name="nome",
        ),
        migrations.RemoveField(
            model_name="amministratoreente",
            name="cognome",
        ),
        migrations.AlterModelOptions(
            name="amministratoreente",
            options={
                "ordering": [
                    "ordine",
                    "utente__last_name",
                    "utente__first_name",
                    "utente__username",
                ],
                "verbose_name": "Amministratore dell'Ente",
                "verbose_name_plural": "Amministratori dell'Ente",
            },
        ),
    ]
