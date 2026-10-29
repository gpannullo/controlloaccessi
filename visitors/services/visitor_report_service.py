"""PDF riservato: dati registrati, senza ricostruire eventi mancanti."""
from collections import OrderedDict
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from xml.sax.saxutils import escape

from django.conf import settings
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak


def date_text(value):
    return timezone.localtime(value).strftime('%d/%m/%Y %H:%M:%S') if value else 'Non registrato'


def duration_text(start, end, ongoing=False):
    if not start or not end:
        return 'Non determinabile'
    seconds = int((end - start).total_seconds())
    if seconds < 0:
        return 'Anomalia cronologica'
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}' + (' (in corso)' if ongoing else '')


def queue_durations(access, generated):
    """Use endpoints only when recorded; no assumed zero-length queues."""
    closed = access.uscita or access.visita_conclusa_il
    hall_end = access.spostato_fuori_ufficio_il
    hall_live = not hall_end and not closed and access.stato_coda == 'HALL'
    door_end = access.ingresso_ufficio_il
    door_live = not door_end and not closed and access.stato_coda == 'PORTA'
    office_end = access.visita_conclusa_il or access.uscita
    office_live = not office_end and access.stato_coda == 'UFF'
    return [
        ('Attesa in hall', duration_text(access.ingresso, generated if hall_live else hall_end, hall_live)),
        ('Attesa fuori ufficio', duration_text(access.spostato_fuori_ufficio_il, generated if door_live else door_end, door_live)),
        ('Permanenza in ufficio', duration_text(access.ingresso_ufficio_il, generated if office_live else office_end, office_live)),
        ('Durata accesso / segmento', duration_text(access.ingresso, access.uscita or (generated if access.stato == 'IN' else None), not access.uscita and access.stato == 'IN')),
    ]


def build_visitor_report(accesses, start_date, end_date, generated, author):
    accesses = list(accesses)
    output = BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='SmallReport', fontName='Helvetica', fontSize=8, leading=11, spaceAfter=3))
    styles.add(ParagraphStyle(name='TableHeadReport', parent=styles['SmallReport'], textColor=colors.white))
    styles.add(ParagraphStyle(name='TitleReport', fontName='Helvetica-Bold', fontSize=18, leading=22, textColor=colors.HexColor('#173b59'), spaceAfter=12))
    def p(value, style='SmallReport'):
        return Paragraph(escape(str(value if value is not None else '')).replace('\n', '<br/>'), styles[style])
    def table(rows, widths, headers=None):
        data = ([[p(h, 'TableHeadReport') for h in headers]] if headers else []) + [[p(v) for v in row] for row in rows]
        t = Table(data, colWidths=[w*mm for w in widths], repeatRows=1 if headers else 0, hAlign='LEFT', splitInRow=1)
        commands = [('VALIGN', (0,0), (-1,-1), 'TOP'), ('LEFTPADDING',(0,0),(-1,-1),6), ('RIGHTPADDING',(0,0),(-1,-1),6), ('TOPPADDING',(0,0),(-1,-1),6), ('BOTTOMPADDING',(0,0),(-1,-1),6), ('LINEBELOW',(0,0),(-1,-1),0.3,colors.HexColor('#dce3e9'))]
        if headers: commands += [('BACKGROUND',(0,0),(-1,0),colors.HexColor('#173b59'))]
        t.setStyle(TableStyle(commands))
        return t
    report_id = str(uuid4())
    logo = Path(settings.BASE_DIR) / 'visitors/static/visitors/images/stemma-comune-aversa.jpg'
    if not logo.is_file():
        raise FileNotFoundError('Stemma del Comune non disponibile per il report')
    def stationery(canvas, doc):
        canvas.saveState()
        canvas.drawImage(str(logo), 18*mm, 264*mm, width=19*mm, height=23*mm, preserveAspectRatio=True, mask='auto')
        canvas.setFillColor(colors.HexColor('#173b59'))
        canvas.setFont('Helvetica-Bold', 15)
        canvas.drawString(42*mm, 280*mm, 'COMUNE DI AVERSA')
        canvas.setFont('Helvetica', 9)
        canvas.drawString(42*mm, 274*mm, 'Controllo accessi - Registro visitatori')
        canvas.setStrokeColor(colors.HexColor('#173b59'))
        canvas.line(18*mm, 261*mm, 192*mm, 261*mm)
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(colors.HexColor('#555555'))
        canvas.drawString(18*mm, 15*mm, 'Documento riservato - Dati personali - Da protocollare')
        canvas.drawRightString(192*mm, 15*mm, f'Pagina {doc.page}')
        canvas.drawString(18*mm, 11*mm, f'ID estrazione: {report_id}')
        canvas.restoreState()
    doc = SimpleDocTemplate(output, pagesize=(210*mm,297*mm), leftMargin=18*mm, rightMargin=18*mm, topMargin=42*mm, bottomMargin=24*mm, title='Comune di Aversa - Report visitatori', author=author)
    persons = OrderedDict()
    for access in accesses:
        persons.setdefault(access.visitatore_id, []).append(access)
    story = [p('Report dei visitatori', 'TitleReport'), p(f'Accessi presenti o con passaggi dal {start_date:%d/%m/%Y} al {end_date:%d/%m/%Y} (date inclusive, ora di Roma).'), p('Le schede riportano la cronologia completa disponibile degli accessi selezionati, anche fuori periodo, aggiornata al momento della generazione.'), p(f'Generato il {date_text(generated)} - Operatore: {author}'), p(f'Visitatori distinti: {len(persons)} - Accessi / segmenti: {len(accesses)}'), Spacer(1,4*mm), p('Riepilogo', 'Heading2')]
    story.append(p('Ogni riga identifica un accesso a un ufficio. Un trasferimento genera un nuovo segmento: la chiusura del precedente non indica necessariamente l’uscita fisica dalla sede.'))
    if accesses:
        story.append(table([
            [f'{a.visitatore.cognome} {a.visitatore.nome}\nAccesso #{a.pk}', a.badge.codice if a.badge else 'Non assegnato', a.ufficio_destinazione.nome, a.numero_coda_formattato, date_text(a.ingresso), date_text(a.uscita) if a.uscita else 'Non registrata / aperto']
            for a in accesses], [40,17,35,16,33,33], ['Visitatore / ID','Badge','Ufficio','Coda','Entrata','Uscita / chiusura']))
    else:
        story.append(p('Nessun accesso registrato nel periodo selezionato.'))
    for records in persons.values():
        person = records[0].visitatore
        story += [PageBreak(), p(f'{person.cognome} {person.nome}', 'TitleReport'), p(f'Scheda visitatore #{person.pk} - {len(records)} accesso/i nel periodo'), p('I tempi in corso sono calcolati all’istante di generazione. Dati mancanti o incoerenti sono segnalati; la cronologia non ricostruisce passaggi mai registrati. Anagrafica, badge e nomi degli uffici sono quelli attualmente presenti nel sistema.'), Spacer(1,3*mm)]
        for a in records:
            story += [p(f'Accesso #{a.pk} - {a.ufficio_destinazione.nome}', 'Heading2'), p(f'Badge: {a.badge.codice if a.badge else "Non assegnato"} | Coda: {a.numero_coda_formattato} | Tipo: {a.get_tipo_accesso_display()}'), p(f'Stato accesso: {a.get_stato_display()} - Stato coda memorizzato: {a.get_stato_coda_display()}'), p(f'Motivo: {a.motivo or "Non indicato"}'), p(f'Note aggiuntive: {a.note or "Nessuna"}')]
            if a.accesso_precedente_id:
                story.append(p(f'Provenienza: accesso #{a.accesso_precedente_id} (può essere esterno al periodo selezionato).'))
            successors = list(a.accessi_successivi.all())
            if successors:
                story.append(p('Trasferimenti successivi: ' + ', '.join(f'#{x.pk} - {x.ufficio_destinazione.nome}' for x in successors)))
            story += [table([(label,date_text(value)) for label,value in [('Entrata / apertura segmento',a.ingresso),('Invio fuori ufficio',a.spostato_fuori_ufficio_il),('Ingresso in ufficio',a.ingresso_ufficio_il),('Visita conclusa',a.visita_conclusa_il),('Uscita / chiusura segmento',a.uscita)]], [80,94]), Spacer(1,3*mm), table(queue_durations(a,generated), [80,94], ['Tempi di permanenza','Durata (ore:minuti:secondi)']), Spacer(1,3*mm), p('Cronologia degli eventi registrati', 'Heading3')]
            events = sorted(a.eventi.all(), key=lambda e:(e.timestamp,e.pk))
            if events:
                story.append(table([(date_text(e.timestamp),e.get_tipo_display(),e.descrizione or '-', (e.operatore.get_full_name() or e.operatore.username) if e.operatore else 'Non registrato') for e in events], [33,32,77,32], ['Data e ora','Evento','Descrizione','Operatore']))
            else:
                story.append(p('Non sono presenti eventi storici per questo accesso. Fare riferimento agli orari registrati sopra.'))
            story.append(Spacer(1,5*mm))
    doc.build(story, onFirstPage=stationery, onLaterPages=stationery)
    return output.getvalue()
