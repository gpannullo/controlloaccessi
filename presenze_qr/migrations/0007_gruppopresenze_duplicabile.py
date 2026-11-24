from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('presenze_qr', '0006_timbratura_annullamento')]
    operations = [
        migrations.AlterField(
            model_name='gruppopresenze', name='gruppo_ad',
            field=models.ForeignKey(on_delete=models.PROTECT, related_name='gruppi_presenze', to='auth.group', verbose_name='Gruppo AD/Django'),
        ),
        migrations.RemoveConstraint(model_name='gruppopresenze', name='gruppo_presenze_ad_referente_unico'),
    ]
