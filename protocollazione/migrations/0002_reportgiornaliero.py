from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('protocollazione', '0001_initial')]
    operations = [migrations.CreateModel(
        name='ReportGiornaliero',
        fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('chiave', models.CharField(max_length=200, unique=True)),
            ('giorno', models.DateField()),
            ('tipo', models.CharField(max_length=20, choices=[('visitatori', 'Visitatori'), ('qr', 'Passaggi QR')])),
            ('documento', models.BinaryField(editable=False)),
            ('parametri', models.JSONField(default=dict)),
            ('generato_il', models.DateTimeField(auto_now_add=True)),
        ],
        options={'verbose_name': 'Report giornaliero da protocollare', 'verbose_name_plural': 'Report giornalieri da protocollare', 'ordering': ['-giorno', 'tipo']},
    )]
