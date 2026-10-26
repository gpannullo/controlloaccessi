"""Generazione degli statini mensili del personale."""
from calendar import monthrange
from datetime import date, datetime, time, timedelta
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

from presenze_qr.models import Timbratura

User = get_user_model()
ORE_GIORNALIERE = timedelta(hours=5)
GIORNI = ('lunedì', 'martedì', 'mercoledì', 'giovedì', 'venerdì', 'sabato', 'domenica')
MESI = ('gennaio', 'febbraio', 'marzo', 'aprile', 'maggio', 'giugno', 'luglio', 'agosto', 'settembre', 'ottobre', 'novembre', 'dicembre')


def _pasqua(anno):
    """Data della domenica di Pasqua (algoritmo gregoriano)."""
    a = anno % 19; b = anno // 100; c = anno % 100; d = b // 4; e = b % 4
    f = (b + 8) // 25; g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30; i = c // 4; k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7; m = (a + 11 * h + 22 * l) // 451
    mese = (h + l - 7 * m + 114) // 31; giorno = ((h + l - 7 * m + 114) % 31) + 1
    return date(anno, mese, giorno)


def _festivo(giorno):
    """Festività nazionali italiane e patrono locale di Aversa (20 gennaio)."""
    fissi = {(1, 1), (1, 6), (4, 25), (5, 1), (6, 2), (8, 15), (11, 1), (12, 8), (12, 25), (12, 26), (1, 20)}
    return giorno.weekday() >= 6 or (giorno.month, giorno.day) in fissi or giorno in (_pasqua(giorno.year), _pasqua(giorno.year) + timedelta(days=1))


def _non_lavorativo(giorno):
    """Comprende festivi e prefestivi (sabato o giorno precedente a una festa)."""
    return _festivo(giorno) or giorno.weekday() == 5 or _festivo(giorno + timedelta(days=1))


def _ore(delta, segno=False):
    secondi = int(abs(delta.total_seconds()))
    testo = f'{secondi // 3600:02d}:{(secondi % 3600) // 60:02d}'
    if segno and delta.total_seconds() > 0:
        return '+' + testo
    if segno and delta.total_seconds() < 0:
        return '-' + testo
    return testo


def _normalizza(orario, verso):
    """Applica la tolleranza prevista dal servizio civile."""
    if verso == 'I' and orario <= time(8, 33):
        return time(8, 30)
    if verso == 'U' and time(13, 27) <= orario <= time(13, 33):
        return time(13, 30)
    return orario


def _coppie(timbrature):
    aperta = None
    risultato = []
    for t in sorted(timbrature, key=lambda x: x.registrata_il):
        if t.verso == 'I':
            if aperta is None:
                aperta = t
        elif t.verso == 'U' and aperta is not None:
            ingresso = _normalizza(aperta.registrata_il.time(), 'I')
            uscita = _normalizza(t.registrata_il.time(), 'U')
            start = datetime.combine(aperta.registrata_il.date(), ingresso)
            end = datetime.combine(t.registrata_il.date(), uscita)
            risultato.append((start, end, max(timedelta(0), end - start)))
            aperta = None
    return risultato


def utenti_gruppo(nome='Servizio Civile'):
    return User.objects.filter(is_active=True, groups__name__iexact=nome).distinct().order_by('last_name', 'first_name', 'username')


def costruisci_statino(mese, nome_gruppo='Servizio Civile', autore='Sistema'):
    """Restituisce il PDF mensile per tutti gli utenti del gruppo indicato."""
    if isinstance(mese, str):
        mese = date.fromisoformat(mese + '-01') if len(mese) == 7 else date.fromisoformat(mese)
    primo = mese.replace(day=1)
    ultimo = mese.replace(day=monthrange(mese.year, mese.month)[1])
    start = timezone.make_aware(datetime.combine(primo, time.min))
    end = timezone.make_aware(datetime.combine(ultimo + timedelta(days=1), time.min))
    utenti = list(utenti_gruppo(nome_gruppo))
    timb = Timbratura.objects.filter(utente__in=utenti, registrata_il__gte=start, registrata_il__lt=end).order_by('utente_id', 'registrata_il')
    per_utente = {u.pk: [] for u in utenti}
    for t in timb:
        per_utente[t.utente_id].append(t)

    output = BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='StatinoSmall', parent=styles['Normal'], fontSize=7, leading=9))
    styles.add(ParagraphStyle(name='StatinoHeader', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7, leading=8, textColor=colors.white))
    styles.add(ParagraphStyle(name='StatinoTitle', parent=styles['Title'], fontSize=16, textColor=colors.HexColor('#173b59')))
    p = lambda value, style='StatinoSmall': Paragraph(str(value), styles[style])
    logo = Path(settings.BASE_DIR) / 'visitors/static/visitors/images/stemma-comune-aversa.jpg'
    def header(canvas, doc):
        canvas.saveState()
        if logo.is_file(): canvas.drawImage(str(logo), 18*mm, 264*mm, width=18*mm, height=22*mm, preserveAspectRatio=True, mask='auto')
        canvas.setFont('Helvetica-Bold', 14); canvas.setFillColor(colors.HexColor('#173b59')); canvas.drawString(40*mm, 280*mm, 'COMUNE DI AVERSA')
        canvas.setFont('Helvetica', 8); canvas.drawString(40*mm, 274*mm, 'Statino mensile presenze - Servizio Civile')
        canvas.line(18*mm, 261*mm, 192*mm, 261*mm)
        canvas.setFont('Helvetica', 7); canvas.setFillColor(colors.grey); canvas.drawRightString(192*mm, 12*mm, f'Pagina {doc.page}')
        canvas.restoreState()
    doc = SimpleDocTemplate(output, pagesize=(210*mm, 297*mm), leftMargin=15*mm, rightMargin=15*mm, topMargin=42*mm, bottomMargin=18*mm, title=f'Statino {primo:%m/%Y}', author=autore)
    story = [p(f'Statino presenze - {MESI[primo.month - 1]} {primo.year}', 'StatinoTitle'), p(f'Gruppo: {nome_gruppo} - Ore teoriche giornaliere: 05:00 - Generato da: {autore}'), Spacer(1, 4*mm)]
    for index, utente in enumerate(utenti):
        if index: story.append(PageBreak())
        uffici = ', '.join(a.ufficio.nome for a in utente.assegnazioni_ufficio.filter(attiva=True).select_related('ufficio')) or 'Nessun ufficio'
        story += [p(f'{utente.last_name} {utente.first_name}', 'Heading2'), p(f'Username: {utente.username} | Badge: {utente.badge or "-"}'), p(f'Ufficio/i: {uffici}'), Spacer(1, 2*mm)]
        rows = []
        totale = timedelta(0)
        for giorno in range(1, ultimo.day + 1):
            giorno_date = primo.replace(day=giorno)
            giornalieri = [t for t in per_utente[utente.pk] if timezone.localtime(t.registrata_il).date() == giorno_date]
            coppie = _coppie(giornalieri)
            durata = sum((x[2] for x in coppie), timedelta())
            totale += durata
            entrate = ' / '.join(x[0].strftime('%H:%M') for x in coppie) or '-'
            uscite = ' / '.join(x[1].strftime('%H:%M') for x in coppie) or '-'
            differenza = durata - ORE_GIORNALIERE
            if _non_lavorativo(giorno_date) and not coppie:
                differenza, esito = timedelta(0), 'Non lavorativo'
            else:
                esito = 'Credito' if differenza > timedelta(0) else ('Deficit' if differenza < timedelta(0) else 'Regolare')
            scarto = '-' if _non_lavorativo(giorno_date) and not coppie else _ore(differenza, segno=True)
            rows.append([giorno_date.strftime('%d/%m/%Y'), GIORNI[giorno_date.weekday()], entrate, uscite, _ore(durata), scarto])
        giorni_lavorativi = sum(not _non_lavorativo(primo.replace(day=g)) for g in range(1, ultimo.day + 1))
        atteso = ORE_GIORNALIERE * giorni_lavorativi
        scarto_totale = totale - atteso
        rows.append(['', 'TOTALE', '', '', _ore(totale), _ore(scarto_totale, segno=True)])
        table_data = [[p(x, 'StatinoHeader') for x in ['Data','Giorno','Entrate','Uscite','Ore lavorate','Scarto']]] + [[p(x) for x in row] for row in rows]
        table = Table(table_data, colWidths=[27*mm, 27*mm, 31*mm, 31*mm, 29*mm, 29*mm], repeatRows=1)
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#173b59')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),.25,colors.HexColor('#ccd5dc')),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('FONTSIZE',(0,0),(-1,-1),7),('BACKGROUND',(0,-1),(-1,-1),colors.HexColor('#e9f1f7'))]))
        story.append(table)
    if not utenti: story.append(p('Nessun utente attivo appartiene al gruppo indicato.'))
    doc.build(story, onFirstPage=header, onLaterPages=header)
    return output.getvalue()
