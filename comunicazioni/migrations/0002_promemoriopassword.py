from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('comunicazioni', '0001_initial'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(
        name='PromemoriaPassword',
        fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('giorno', models.DateField()),
            ('scadenza', models.DateTimeField()),
            ('destinatario', models.EmailField(max_length=254)),
            ('creato_il', models.DateTimeField(auto_now_add=True)),
            ('utente', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
        ],
        options={'constraints': [models.UniqueConstraint(fields=('utente', 'giorno'), name='promemoria_password_giornaliero')]},
    )]
