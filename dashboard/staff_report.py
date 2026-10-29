import calendar
from collections import defaultdict
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from dashboard.permissions import directory_admin_required
from presenze_qr.models import Timbratura

MONTHS = ('Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno',
          'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre')
DAYS = ('Lunedì', 'Martedì', 'Mercoledì', 'Giovedì', 'Venerdì', 'Sabato', 'Domenica')
ROME = ZoneInfo('Europe/Rome')


class MonthlyStaffForm(forms.Form):
    gruppo = forms.ModelChoiceField(queryset=Group.objects.order_by('name'), label='Gruppo',
                                   widget=forms.Select(attrs={'class': 'form-select'}))
    mese = forms.TypedChoiceField(choices=[(i, name) for i, name in enumerate(MONTHS, 1)],
                                 coerce=int, label='Mese', widget=forms.Select(attrs={'class': 'form-select'}))
    anno = forms.IntegerField(min_value=2000, max_value=2100, label='Anno',
                             widget=forms.NumberInput(attrs={'class': 'form-control'}))


def monthly_staff(group, year, month):
    start = datetime.combine(date(year, month, 1), time.min, tzinfo=ROME)
    end = datetime.combine(date(year+1, 1, 1) if month == 12 else date(year, month+1, 1), time.min, tzinfo=ROME)
    users = list(get_user_model().objects.filter(groups=group).distinct()
                 .order_by('last_name', 'first_name', 'username').prefetch_related('assegnazioni_ufficio__ufficio'))
    movements = defaultdict(list)
    for punch in Timbratura.objects.filter(utente_id__in=[u.pk for u in users],
            registrata_il__gte=start, registrata_il__lt=end).order_by('registrata_il', 'pk'):
        local = timezone.localtime(punch.registrata_il, ROME)
        movements[(punch.utente_id, local.day)].append({
            'ora': local.strftime('%H:%M'), 'verso': punch.get_verso_display(),
            'origine': punch.get_origine_display(),
        })
    reports = []
    for user in users:
        offices = sorted({a.ufficio.nome for a in user.assegnazioni_ufficio.all() if a.attiva})
        days = []
        for number in range(1, calendar.monthrange(year, month)[1]+1):
            day = date(year, month, number)
            days.append({'data': day, 'giorno': DAYS[day.weekday()],
                         'passaggi': movements[(user.pk, number)], 'festivo': day.weekday() >= 5})
        reports.append({'utente': user, 'uffici': offices, 'giorni': days})
    return reports


@never_cache
@directory_admin_required
@require_GET
def staff_monthly_report(request):
    today = timezone.localdate()
    form = MonthlyStaffForm(request.GET if request.GET else None,
                            initial={'mese': today.month, 'anno': today.year})
    context = {'form': form, 'generato': False}
    if form.is_bound and form.is_valid():
        values = form.cleaned_data
        context.update(generato=True, gruppo=values['gruppo'], mese=MONTHS[values['mese']-1],
                       anno=values['anno'], statini=monthly_staff(values['gruppo'], values['anno'], values['mese']))
    return render(request, 'dashboard/staff_monthly_report.html', context)
