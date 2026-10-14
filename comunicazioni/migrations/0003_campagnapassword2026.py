from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [('comunicazioni', '0002_promemoriopassword')]
    operations = [migrations.CreateModel(name='CampagnaPassword2026', fields=[
        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
        ('username', models.CharField(max_length=150)),
        ('pwd_last_set', models.CharField(max_length=100)),
        ('ad_guid', models.CharField(max_length=100)),
        ('completata', models.BooleanField(default=False)),
        ('ultimo_invio', models.DateField(null=True)),
        ('utente', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
    ])]
