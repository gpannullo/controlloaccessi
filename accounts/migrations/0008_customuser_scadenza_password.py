from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("accounts", "0007_customuser_recapiti_aggiuntivi")]
    operations = [
        migrations.AddField(model_name="customuser", name="scadenza_password", field=models.DateTimeField(blank=True, editable=False, null=True)),
        migrations.AddField(model_name="customuser", name="password_senza_scadenza", field=models.BooleanField(default=False, editable=False)),
    ]
