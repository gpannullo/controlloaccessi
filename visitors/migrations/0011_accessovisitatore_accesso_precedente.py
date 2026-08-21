from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("visitors", "0015_amministratori_da_active_directory")]
    operations = [
        migrations.AddField(
            model_name="accessovisitatore",
            name="accesso_precedente",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="accessi_successivi", to="visitors.accessovisitatore", verbose_name="Accesso precedente"),
        ),
    ]
