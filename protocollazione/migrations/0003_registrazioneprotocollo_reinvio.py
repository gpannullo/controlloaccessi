from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('protocollazione', '0002_reportgiornaliero')]
    operations = [
        migrations.AddField('registrazioneprotocollo', 'reinvio_autorizzato', models.BooleanField(default=False, editable=False)),
        migrations.AddField('registrazioneprotocollo', 'reinvio_autorizzato_il', models.DateTimeField(blank=True, editable=False, null=True)),
    ]
