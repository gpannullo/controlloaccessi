from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('accounts', '0012_customuser_ultima_timbratura_fields')]
    operations = [migrations.AddField(
        model_name='customuser', name='codice_protocollo',
        field=models.CharField(blank=True, help_text="Codice della persona nel gestionale di protocollo.", max_length=50, null=True, unique=True, verbose_name='Codice protocollo'),
    )]
