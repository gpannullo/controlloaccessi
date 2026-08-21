from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0006_alter_customuser_tipo_attivita")]

    operations = [
        migrations.AddField(model_name="customuser", name="email_aggiuntiva", field=models.EmailField(blank=True, max_length=254, verbose_name="E-mail aggiuntiva")),
        migrations.AddField(model_name="customuser", name="telefono_aggiuntivo", field=models.CharField(blank=True, max_length=50, verbose_name="Telefono aggiuntivo")),
    ]
