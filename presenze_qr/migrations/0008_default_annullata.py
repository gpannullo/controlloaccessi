from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('presenze_qr', '0007_gruppopresenze_duplicabile')]

    operations = [
        migrations.RunSQL(
            sql=(
                'UPDATE presenze_qr_timbratura SET annullata = FALSE '
                'WHERE annullata IS NULL; '
                'ALTER TABLE presenze_qr_timbratura '
                'ALTER COLUMN annullata SET DEFAULT FALSE; '
                'ALTER TABLE presenze_qr_timbratura '
                'ALTER COLUMN annullata SET NOT NULL;'
            ),
            reverse_sql=(
                'ALTER TABLE presenze_qr_timbratura '
                'ALTER COLUMN annullata DROP NOT NULL; '
                'ALTER TABLE presenze_qr_timbratura '
                'ALTER COLUMN annullata DROP DEFAULT;'
            ),
        ),
    ]
