from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("presenze_qr", "0002_alter_timbratura_options_timbratura_badge_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="GruppoPresenze",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=150, unique=True)),
                ("attivo", models.BooleanField(default=True)),
                ("gruppo_ad", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="gruppo_presenze", to="auth.group", verbose_name="Gruppo AD/Django")),
                ("referente", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="gruppi_presenze_referente", to=settings.AUTH_USER_MODEL, verbose_name="Referente presenze")),
                ("utenti", models.ManyToManyField(blank=True, related_name="gruppi_presenze", to=settings.AUTH_USER_MODEL, verbose_name="Utenti proposti")),
            ],
            options={"ordering": ["nome"], "verbose_name": "Gruppo presenze", "verbose_name_plural": "Gruppi presenze"},
        ),
    ]
