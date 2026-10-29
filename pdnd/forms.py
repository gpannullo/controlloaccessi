from django import forms


class InterrogazionePDNDForm(forms.Form):
    identificativo = forms.CharField(
        label="Codice fiscale",
        min_length=11,
        max_length=16,
        help_text="Codice fiscale della persona o codice fiscale/partita IVA per il DURC.",
        widget=forms.TextInput(attrs={"class": "form-control text-uppercase", "autocomplete": "off"}),
    )

    def clean_identificativo(self):
        value = "".join(self.cleaned_data["identificativo"].upper().split())
        if not value.isalnum() or not 11 <= len(value) <= 16:
            raise forms.ValidationError("Indicare un codice fiscale o una partita IVA valida.")
        return value
