from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("presenze_qr", "0004_giustificativi_autodichiarazioni")]
    operations = [
        migrations.RemoveField(model_name="gruppopresenze", name="nome"),
        migrations.AddConstraint(
            model_name="gruppopresenze",
            constraint=models.UniqueConstraint(fields=("gruppo_ad", "referente"), name="gruppo_presenze_ad_referente_unico"),
        ),
    ]
