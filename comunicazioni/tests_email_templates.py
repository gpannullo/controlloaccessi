from importlib import import_module
from types import SimpleNamespace
from django.apps import apps
from django.test import TestCase
from post_office import mail
from post_office.models import EmailTemplate

class EmailTemplateTests(TestCase):
    def test_seeded_and_rendered_without_sending(self):
        context = {'nome': '<Mario & Rossi>', 'username': 'm.rossi',
                   'password_provvisoria': 'Ab<&12345', 'url': 'https://example.org/account/',
                   'scadenza': '01/12/2026 alle 12:00', 'oggetto': 'Avviso & test',
                   'messaggio': 'Prima riga\n<script>test</script>'}
        for name in ('account_creato', 'password_reimpostata', 'password_in_scadenza',
                     'comunicazione_generica', 'campagna_cambio_password'):
            email = mail.send(recipients=['test@example.org'], sender='noreply@example.org',
                              template=name, context=context, priority='medium', commit=False)
            self.assertTrue(email.subject)
            self.assertTrue(email.message)
            self.assertTrue(email.html_message)
            self.assertNotIn('<script>', email.html_message)
            self.assertNotIn('{{', email.message)
            if name in ('account_creato', 'password_reimpostata'):
                self.assertIn('Ab<&12345', email.message)
                self.assertIn('Ab&lt;&amp;12345', email.html_message)
                self.assertIn('https://example.org/account/', email.message)

    def test_seed_preserves_customization(self):
        template = EmailTemplate.objects.get(name='account_creato')
        template.subject = 'Oggetto personalizzato'
        template.save()
        seed = import_module('comunicazioni.migrations.0004_postoffice_templates').seed
        seed(apps, SimpleNamespace(connection=SimpleNamespace(alias='default')))
        template.refresh_from_db()
        self.assertEqual(template.subject, 'Oggetto personalizzato')
        self.assertEqual(EmailTemplate.objects.filter(name='account_creato').count(), 1)
