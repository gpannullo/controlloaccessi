from datetime import datetime, time, timedelta

from django import forms
from django.db.models import Prefetch, Q
from zoneinfo import ZoneInfo
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from visitors.models import AccessoVisitatore, EventoAccesso
from dashboard.permissions import dirigenza_required


class VisitorReportForm(forms.Form):
    dal = forms.DateField(label='Dal', widget=forms.DateInput(attrs={'type':'date', 'class':'form-control'}, format='%Y-%m-%d'))
    al = forms.DateField(label='Al', widget=forms.DateInput(attrs={'type':'date', 'class':'form-control'}, format='%Y-%m-%d'))

    def clean(self):
        data = super().clean()
        if data.get('dal') and data.get('al'):
            if data['al'] < data['dal']:
                raise forms.ValidationError('La data finale deve essere successiva o uguale a quella iniziale.')
            if (data['al'] - data['dal']).days > 365:
                raise forms.ValidationError('Selezionare un intervallo massimo di 366 giorni.')
        return data


def report_period_context():
    today = timezone.localdate(timezone=ZoneInfo('Europe/Rome'))
    return {'report_today': today, 'report_yesterday': today - timedelta(days=1)}


@dirigenza_required
@never_cache
@require_GET
def report_visitatori(request):
    period = report_period_context()
    yesterday = period['report_yesterday']
    form = VisitorReportForm(request.GET if request.GET else None, initial={'dal':yesterday, 'al':yesterday})
    if request.GET.get('formato') == 'pdf' and form.is_valid():
        from visitors.services.visitor_report_service import build_visitor_report
        start, end = form.cleaned_data['dal'], form.cleaned_data['al']
        tz = ZoneInfo('Europe/Rome')
        begin = timezone.make_aware(datetime.combine(start,time.min),tz)
        finish = timezone.make_aware(datetime.combine(end+timedelta(days=1),time.min),tz)
        generated = timezone.now()
        activity = Q(ingresso__lt=finish) & (Q(uscita__gte=begin) | Q(uscita__isnull=True))
        activity |= Q(eventi__timestamp__gte=begin, eventi__timestamp__lt=finish)
        for field in ('ingresso', 'uscita', 'spostato_fuori_ufficio_il', 'ingresso_ufficio_il', 'visita_conclusa_il'):
            activity |= Q(**{field+'__gte': begin, field+'__lt': finish})
        records = AccessoVisitatore.objects.filter(activity, ingresso__lte=generated).distinct().select_related('visitatore','badge','ufficio_destinazione').prefetch_related(Prefetch('eventi',queryset=EventoAccesso.objects.filter(timestamp__lte=generated).select_related('operatore')), Prefetch('accessi_successivi',queryset=AccessoVisitatore.objects.select_related('ufficio_destinazione'))).order_by('visitatore__cognome','visitatore__nome','visitatore_id','ingresso','pk')
        # Bound the synchronous export to avoid exhausting web workers.
        accesses = list(records[:2001])
        if len(accesses) > 2000:
            form.add_error(None,'Il periodo contiene più di 2000 accessi. Ridurre l’intervallo per generare il PDF.')
        else:
            pdf = build_visitor_report(accesses,start,end,generated,request.user.get_full_name() or request.user.username)
            response = HttpResponse(pdf,content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="report-visitatori-{start:%Y%m%d}-{end:%Y%m%d}.pdf"'
            response['X-Content-Type-Options'] = 'nosniff'
            return response
    return render(request,'visitors/report_visitatori.html',{'form':form, **period})
