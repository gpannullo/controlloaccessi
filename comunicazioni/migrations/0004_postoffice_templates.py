from django.db import migrations


def seed(apps, schema_editor):
    Template = apps.get_model('post_office', 'EmailTemplate')
    portal = '{{ url }}'
    credentials = ('Username: {{ username }}\nPassword provvisoria: {{ password_provvisoria }}\n\n'
                   'Per impostare o modificare una password, è disponibile il seguente portale di accesso:\n'
                   + portal + '\n\nAl primo accesso sarà richiesto di cambiare la password.')
    definitions = {
        'account_creato': ('Credenziali di accesso',
            'Buongiorno {{ nome }},\n\nè stato creato il suo account.\n' + credentials,
            'nome, username, password_provvisoria, url'),
        'password_reimpostata': ('Nuova password di accesso',
            'Buongiorno {{ nome }},\n\nla password del suo account è stata reimpostata.\n' + credentials,
            'nome, username, password_provvisoria, url'),
        'password_in_scadenza': ('Promemoria scadenza password - Comune di Aversa',
            'Gentile {{ nome }},\n\nla password del tuo account {{ username }} scadrà il {{ scadenza }}.\n\n'
            'Per impostare o modificare la password, accedi al portale:\n{{ url }}\n\n'
            'Riceverai questo promemoria ogni giorno negli ultimi 15 giorni di validità, fino al cambio password o alla scadenza.\n'
            'Non comunicare la tua password via e-mail e non rispondere a questo messaggio automatico.',
            'nome, username, scadenza, url'),
        'comunicazione_generica': ('{{ oggetto }}', '{{ messaggio }}', 'oggetto, messaggio, nome, username'),
        'campagna_cambio_password': ('Comune di Aversa - Cambio password entro il {{ scadenza }}',
            'Gentile {{ nome }},\n\nè richiesto il cambio della password del tuo account {{ username }} entro il {{ scadenza }}.\n\n'
            'Accedi al portale per cambiare la password:\n{{ url }}\n\n'
            'Riceverai un promemoria ogni giorno fino al cambio password e comunque non oltre il termine indicato.\n'
            'Non comunicare la password via email. Non rispondere a questo messaggio automatico.',
            'nome, username, scadenza, url'),
    }
    for name, (subject, body, variables) in definitions.items():
        html_body = body.replace('\n', '<br>')
        if name == 'comunicazione_generica':
            html_body = '{{ messaggio|linebreaksbr }}'
        Template.objects.using(schema_editor.connection.alias).get_or_create(
            name=name, language='', default_template=None,
            defaults={
                'description': 'Template IRIS. Variabili disponibili: ' + variables + '. Non rinominare il template.',
                'subject': '{% autoescape off %}' + subject + '{% endautoescape %}',
                'content': '{% autoescape off %}' + body + '{% endautoescape %}\n\nComune di Aversa - Centro Elaborazione Dati',
                'html_content': '<div style="font-family:Arial,sans-serif;max-width:640px;margin:auto;padding:24px;border-top:5px solid #0066a4">'
                    '<h2>Comune di Aversa</h2><div style="line-height:1.6">' + html_body + '</div>'
                    '<hr><p>Comune di Aversa - Centro Elaborazione Dati</p></div>',
            },
        )


class Migration(migrations.Migration):
    dependencies = [('comunicazioni', '0003_campagnapassword2026'), ('post_office', '0002_add_i18n_and_backend_alias')]
    # Preserve operator edits, including on rollback/reapplication.
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
