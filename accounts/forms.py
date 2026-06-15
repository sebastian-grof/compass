from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy as _


class EmailLoginForm(AuthenticationForm):
    """Login form that presents the username field as an email and adds a
    'remember me' checkbox to control session lifetime."""

    remember_me = forms.BooleanField(required=False, initial=True, label=_("Keep me signed in"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = _("Email")
        self.fields["username"].widget = forms.EmailInput(
            attrs={
                "autofocus": True,
                "autocomplete": "email",
                "inputmode": "email",
                "placeholder": "you@example.com",
            }
        )
        self.fields["password"].label = _("Password")
        self.fields["password"].widget.attrs.update(
            {"autocomplete": "current-password", "placeholder": "••••••••••"}
        )


class SettingsForm(forms.ModelForm):
    """The preferences an adjudicator can edit themselves."""

    class Meta:
        model = get_user_model()
        fields = ["auto_redirect"]
        labels = {"auto_redirect": _("Open tournament immediately")}
        help_texts = {
            "auto_redirect": _(
                "If you have exactly one active tournament, the app redirects you "
                "straight there without showing the list. After returning from "
                "Tabbycat, the list appears normally."
            )
        }
