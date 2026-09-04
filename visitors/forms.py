from django import forms
from django.utils import timezone
from datetime import timedelta

from access_control.models import IndisponibilitaUfficio, Ufficio
from access_control.services.office_service import OfficeService
from visitors.models import AccessoVisitatore


class IndisponibilitaUfficioForm(forms.ModelForm):
    class Meta:
        model = IndisponibilitaUfficio
        fields = ("data_inizio", "data_fine", "motivo")
        widgets = {
            "data_inizio": forms.DateInput(attrs={"type": "date"}),
            "data_fine": forms.DateInput(attrs={"type": "date"}),
            "motivo": forms.TextInput(attrs={"placeholder": "Es. ferie del personale"}),
        }
        labels = {
            "data_inizio": "Dal giorno",
            "data_fine": "Al giorno",
            "motivo": "Motivazione",
        }


class RegistrazioneVisitatoreForm(forms.Form):
    documento_presentato = forms.BooleanField(
        required=False,
        initial=True,
        label="Il visitatore ha presentato un documento",
    )

    documento_tipo = forms.ChoiceField(
        required=False,
        label="Tipo documento",
        choices=[
            ("", "Seleziona il tipo di documento"),
            ("CIE", "Carta di Identità Elettronica"),
            ("CI", "Carta di identità cartacea"),
            ("PATENTE", "Patente"),
            ("PASSAPORTO", "Passaporto"),
            ("ALTRO", "Altro documento"),
        ],
    )

    documento_numero = forms.CharField(
        max_length=50,
        required=False,
        label="Numero documento",
    )

    documento_scadenza = forms.DateField(
        required=False,
        label="Scadenza documento",
        widget=forms.DateInput(
            attrs={
                "type": "date",
            }
        ),
    )

    codice_fiscale = forms.CharField(
        max_length=16,
        required=False,
        label="Codice fiscale",
    )

    nome = forms.CharField(
        max_length=100,
        label="Nome",
    )

    cognome = forms.CharField(
        max_length=100,
        label="Cognome",
    )

    telefono = forms.CharField(
        max_length=50,
        required=True,
        label="Telefono",
    )

    accompagnato = forms.BooleanField(
        required=False,
        initial=False,
        label="Il visitatore è accompagnato",
    )

    ufficio = forms.ModelChoiceField(
        queryset=Ufficio.objects.none(),
        label="Ufficio di destinazione",
        empty_label="Seleziona un ufficio",
    )

    motivo = forms.CharField(
        max_length=255,
        required=True,
        label="Motivo della visita",
        widget=forms.TextInput(
            attrs={
                "list": "motivi-visita",
                "autocomplete": "off",
            }
        ),
    )

    note = forms.CharField(
        required=False,
        label="Note della portineria",
        widget=forms.Textarea(
            attrs={
                "rows": 3,
            }
        ),
    )

    def __init__(
        self,
        *args,
        tipo_accesso=AccessoVisitatore.TipoAccesso.RICEVIMENTO,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.tipo_accesso = tipo_accesso

        if (
            tipo_accesso
            == AccessoVisitatore.TipoAccesso.VISITA
        ):
            uffici = (
                OfficeService
                .get_offices_with_present_staff()
            )
        else:
            uffici = (
                OfficeService
                .get_offices_receiving_with_present_staff()
            )

        self.fields["ufficio"].queryset = uffici

        for field in self.fields.values():
            if isinstance(
                    field.widget,
                    forms.CheckboxInput,
            ):
                field.widget.attrs["class"] = (
                    "form-check-input"
                )

            elif isinstance(
                    field.widget,
                    forms.Select,
            ):
                field.widget.attrs["class"] = (
                    "form-select"
                )

            else:
                field.widget.attrs["class"] = (
                    "form-control"
                )

        self.fields["documento_numero"].widget.attrs.update(
            {
                "autocomplete": "off",
            }
        )

        self.fields["codice_fiscale"].widget.attrs.update(
            {
                "autocomplete": "off",
                "maxlength": "16",
            }
        )

        self.fields["telefono"].widget.attrs.update(
            {
                "autocomplete": "tel",
            }
        )

    def clean_codice_fiscale(self):
        codice_fiscale = (
                self.cleaned_data.get("codice_fiscale")
                or ""
        )

        return (
            codice_fiscale
            .strip()
            .upper()
            .replace(" ", "")
        )

    def clean_documento_numero(self):
        numero = (
                self.cleaned_data.get("documento_numero")
                or ""
        )

        return numero.strip().upper()

    def clean_motivo(self):
        motivo = (
                self.cleaned_data.get("motivo")
                or ""
        )

        motivo = " ".join(
            motivo.strip().split()
        )

        if not motivo:
            raise forms.ValidationError(
                "Indicare il motivo della visita."
            )

        return motivo

    def clean(self):
        cleaned_data = super().clean()

        documento_presentato = cleaned_data.get(
            "documento_presentato",
            False,
        )

        documento_tipo = cleaned_data.get(
            "documento_tipo",
        )

        documento_numero = cleaned_data.get(
            "documento_numero",
        )

        documento_scadenza = cleaned_data.get(
            "documento_scadenza",
        )

        if documento_presentato:
            if not documento_tipo:
                self.add_error(
                    "documento_tipo",
                    "Selezionare il tipo di documento.",
                )

            if not documento_numero:
                self.add_error(
                    "documento_numero",
                    "Inserire il numero del documento.",
                )

        else:
            cleaned_data["documento_tipo"] = ""
            cleaned_data["documento_numero"] = ""
            cleaned_data["documento_scadenza"] = None

        return cleaned_data


class RientroBadgeForm(forms.Form):
    badge = forms.CharField(
        max_length=10,
        label="Codice badge",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "autocomplete": "off",
                "autofocus": True,
            }
        ),
    )

    def clean_badge(self):
        return self.cleaned_data["badge"].strip().upper()


class ChiusuraAccessoForm(forms.Form):
    uscita = forms.DateTimeField(
        label="Data e ora effettive di uscita",
        input_formats=[
            "%Y-%m-%dT%H:%M",
        ],
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={
                "type": "datetime-local",
                "class": "form-control",
            },
        ),
    )

    note_chiusura = forms.CharField(
        required=False,
        label="Note sulla chiusura",
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "class": "form-control",
            }
        ),
    )

    def __init__(self, *args, accesso=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.accesso = accesso

        if not self.is_bound:
            self.fields["uscita"].initial = (
                timezone.localtime()
                .replace(second=0, microsecond=0)
            )

    def clean_uscita(self):
        uscita = self.cleaned_data["uscita"]

        if timezone.is_naive(uscita):
            uscita = timezone.make_aware(
                uscita,
                timezone.get_current_timezone(),
            )

        if self.accesso and uscita < self.accesso.ingresso:
            raise forms.ValidationError(
                "L’orario di uscita non può essere precedente "
                "all’orario di ingresso."
            )

        if uscita > timezone.now() + timedelta(minutes=5):
            raise forms.ValidationError(
                "L’orario di uscita non può essere nel futuro."
            )

        return uscita
