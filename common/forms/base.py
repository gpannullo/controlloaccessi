from django import forms


class BaseForm(forms.ModelForm):
    """
    Form base dell'applicazione.
    Applica automaticamente lo stile Bootstrap.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():

            css = field.widget.attrs.get("class", "")

            field.widget.attrs["class"] = (
                css + " form-control"
            ).strip()