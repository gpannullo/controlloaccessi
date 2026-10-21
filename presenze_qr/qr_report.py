from datetime import datetime, time, timedelta
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Prefetch
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from dashboard.permissions import dirigenza_required
from visitors.report_views import VisitorReportForm
from .models import Timbratura, Attivita

ROME = ZoneInfo('Europe/Rome')


def report_rows(start, end, generated):
    begin = datetime.combine(start, time.min, tzinfo=ROME)
    finish = datetime.combine(end + timedelta(days=1), time.min, tzinfo=ROME)
    return Timbratura.objects.filter(origine='QR', registrata_il__gte=begin,
        registrata_il__lt=finish, registrata_il__lte=generated).select_related('utente', 'postazione').prefetch_related(
            Prefetch('attivita_set', queryset=Attivita.objects.filter(azione='CORREZIONE', registrata_il__lte=generated).order_by('registrata_il', 'pk'))
        ).order_by('registrata_il', 'pk')


def build_qr_report(rows, start, end, generated, author):
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    rows = list(rows)
    output = BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='CellQR', fontSize=8, leading=11))
    styles.add(ParagraphStyle(name='HeadQR', parent=styles['CellQR'], textColor=colors.white))
    def p(value, style='CellQR'):
        return Paragraph(escape(str(value)).replace('\n', '<br/>'), styles[style])
    def local(value):
        return value.astimezone(ROME).strftime('%d/%m/%Y %H:%M')
    logo = Path(settings.BASE_DIR) / 'visitors/static/visitors/images/stemma-comune-aversa.jpg'
    if not logo.is_file():
        raise FileNotFoundError('Stemma del Comune non disponibile')
    report_id = str(uuid4())
    def header(canvas, doc):
        canvas.saveState()
        canvas.drawImage(str(logo), 18*mm, 264*mm, width=19*mm, height=23*mm, preserveAspectRatio=True, mask='auto')
        canvas.setFillColor(colors.HexColor('#173b59'))
        canvas.setFont('Helvetica-Bold', 15)
        canvas.drawString(42*mm, 280*mm, 'COMUNE DI AVERSA')
        canvas.setFont('Helvetica', 9)
        canvas.drawString(42*mm, 274*mm, 'Registro passaggi del personale - Sistema QR')
        canvas.line(18*mm, 261*mm, 192*mm, 261*mm)
        canvas.setFont('Helvetica', 7)
        canvas.drawString(18*mm, 15*mm, 'Documento riservato - Dati personali - Da protocollare')
        canvas.drawRightString(192*mm, 15*mm, f'Pagina {doc.page}')
        canvas.drawString(18*mm, 11*mm, f'ID estrazione: {report_id}')
        canvas.restoreState()
    story = [p('Report entrate e uscite QR', 'Title'),
        p(f'Periodo: {start:%d/%m/%Y} - {end:%d/%m/%Y}, date inclusive. Fuso Europe/Rome.'),
        p(f'Generato il {local(generated)} - Operatore: {author}'), Spacer(1, 4*mm),
        p(f'Persone: {len({r.utente_id for r in rows})} | Passaggi: {len(rows)} | Entrate: {sum(r.verso == "I" for r in rows)} | Uscite: {sum(r.verso == "U" for r in rows)}'),
        Spacer(1, 3*mm), p('Sono inclusi tutti i passaggi QR del periodo, anche di utenti ora disattivati. Sono esclusi i passaggi importati dai lettori badge. Il verso è quello attualmente registrato; eventuali correzioni sono riportate. Non vengono dedotte ore lavorate né ricostruiti passaggi mancanti. Nomi e postazioni sono quelli attuali.'), Spacer(1, 4*mm)]
    if rows:
        data = [[p(x, 'HeadQR') for x in ['Data / ID', 'Dipendente', 'Verso', 'Postazione', 'IP', 'Correzioni']]]
        for row in rows:
            corrections = [f'{local(a.registrata_il)}: {a.verso_prima} -> {a.verso_dopo}' for a in row.attivita_set.all()]
            note = '\n'.join(corrections) or ('Verso originale: '+row.verso_originale if row.verso_originale != row.verso else '-')
            data.append([p(x) for x in [f'{local(row.registrata_il)}\n#{row.pk}',
                f'{row.utente.get_full_name() or row.utente.username}\n{row.utente.username}',
                row.get_verso_display(), row.postazione.nome if row.postazione else 'Non registrata', row.ip or 'Non registrato', note]])
        table = Table(data, colWidths=[32*mm, 39*mm, 18*mm, 25*mm, 25*mm, 35*mm], repeatRows=1, splitInRow=1)
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#173b59')),
            ('VALIGN',(0,0),(-1,-1),'TOP'), ('TOPPADDING',(0,0),(-1,-1),6), ('BOTTOMPADDING',(0,0),(-1,-1),6),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.whitesmoke,colors.white]), ('LINEBELOW',(0,0),(-1,-1),.3,colors.lightgrey)]))
        story.append(table)
        story.extend([Spacer(1, 3*mm), p('Legenda correzioni: I = Entrata; U = Uscita.')])
    else:
        story.append(p('Nessun passaggio QR registrato nel periodo selezionato.'))
    doc = SimpleDocTemplate(output, pagesize=(210*mm,297*mm), leftMargin=18*mm, rightMargin=18*mm,
        topMargin=42*mm, bottomMargin=24*mm, title='Comune di Aversa - Passaggi QR', author=author)
    doc.build(story, onFirstPage=header, onLaterPages=header)
    return output.getvalue()


@dirigenza_required
@never_cache
@require_GET
def report_qr(request):
    today = timezone.localdate(timezone=ROME)
    form = VisitorReportForm(request.GET if request.GET else None, initial={'dal': today, 'al': today})
    if request.GET.get('formato') == 'pdf' and form.is_valid():
        start, end = form.cleaned_data['dal'], form.cleaned_data['al']
        generated = timezone.now()
        rows = list(report_rows(start, end, generated)[:5001])
        if len(rows) > 5000:
            form.add_error(None, 'Il periodo contiene più di 5000 passaggi. Ridurre l’intervallo.')
        else:
            pdf = build_qr_report(rows, start, end, generated, request.user.get_full_name() or request.user.username)
            response = HttpResponse(pdf, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="report-qr-{start:%Y%m%d}-{end:%Y%m%d}.pdf"'
            response['X-Content-Type-Options'] = 'nosniff'
            return response
    return render(request, 'presenze_qr/report.html', {'form': form})
