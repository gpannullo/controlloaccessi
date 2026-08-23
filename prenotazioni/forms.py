from django import forms

from .services import slot_disponibili, uffici_prenotabili


class UfficioForm(forms.Form):
    ufficio = forms.ModelChoiceField(queryset=uffici_prenotabili(), label="Ufficio", empty_label="Scegli l'ufficio")


class SlotForm(forms.Form):
    data = forms.DateField(label="Data", widget=forms.DateInput(attrs={"type": "date"}))
    orario = forms.ChoiceField(label="Appuntamenti disponibili")

    def __init__(self, *args, ufficio=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.ufficio = ufficio
        data = self.data.get("data") or self.initial.get("data")
        if data and ufficio:
            try:
                parsed = forms.DateField().to_python(data)
                self.fields["orario"].choices = [(slot.isoformat(), slot.strftime("%H:%M")) for slot in slot_disponibili(ufficio, parsed)]
            except (TypeError, ValueError):
                pass
        if not self.fields["orario"].choices:
            self.fields["orario"].choices = [("", "Prima selezionare una data")]

    def clean(self):
        cleaned = super().clean()
        if not self.ufficio or not cleaned.get("data"):
            return cleaned
        choices = dict((slot.isoformat(), slot) for slot in slot_disponibili(self.ufficio, cleaned["data"]))
        value = cleaned.get("orario")
        if value not in choices:
            self.add_error("orario", "Lo slot selezionato non è più disponibile.")
        else:
            cleaned["data_ora"] = choices[value]
        return cleaned


class DettagliForm(forms.Form):
    motivo = forms.CharField(max_length=255, label="Motivo")
    dettagli = forms.CharField(max_length=200, required=False, label="Dettagli", widget=forms.Textarea(attrs={"rows": 4}))


class RichiedenteForm(forms.Form):
    nome = forms.CharField(max_length=100, label="Nome")
    cognome = forms.CharField(max_length=100, label="Cognome")
    codice_fiscale = forms.CharField(max_length=16, min_length=16, label="Codice fiscale")
    email = forms.EmailField(label="Email")
    telefono = forms.CharField(max_length=50, required=False, label="Telefono")

    def clean_codice_fiscale(self):
        value = self.cleaned_data["codice_fiscale"].strip().upper()
        if not value.isalnum():
            raise forms.ValidationError("Indicare un codice fiscale valido.")
        return value
