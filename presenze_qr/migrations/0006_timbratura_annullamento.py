from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('presenze_qr', '0005_gruppopresenze_senza_nome')]
    operations = [
        migrations.AddField(model_name='timbratura', name='annullata', field=models.BooleanField(default=False)),
        migrations.AddField(model_name='timbratura', name='annullata_il', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='timbratura', name='annullata_da', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='timbrature_annullate', to=settings.AUTH_USER_MODEL)),
    ]
