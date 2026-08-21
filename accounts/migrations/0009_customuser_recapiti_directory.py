from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("accounts", "0008_customuser_scadenza_password")]
    operations = [
        migrations.AddField(model_name="customuser", name="email_personale", field=models.EmailField(blank=True, editable=False, max_length=254)),
        migrations.AddField(model_name="customuser", name="cellulare_personale", field=models.CharField(blank=True, editable=False, max_length=50)),
    ]
