from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('access_control', '0010_indisponibilitaufficio')]
    operations = [migrations.AddField(
        model_name='ufficio', name='codice_protocollo',
        field=models.CharField(blank=True, help_text="Codice dell'ufficio nell'organigramma del gestionale di protocollo.", max_length=50, null=True, unique=True, verbose_name='Codice protocollo'),
    )]
