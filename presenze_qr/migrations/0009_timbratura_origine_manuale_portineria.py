from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('presenze_qr', '0008_default_annullata')]
    operations = [
        migrations.AlterField(
            model_name='timbratura', name='origine',
            field=models.CharField(max_length=24, choices=[('QR', 'QR'), ('AUTOMATICO', 'Sistema automatico'), ('MANUALE_DA_PORTINERIA', 'Manuale da portineria')], default='QR', editable=False),
        ),
    ]
