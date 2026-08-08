from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, PasswordChangeForm
from .models import CustomUser

class SignupForm(UserCreationForm):

    class Meta:
        model = CustomUser
        fields = [
            'username',
            'email',
            'country',
            'location',
            'phone_number',
            'password1',
            'password2'
        ]
class LoginForm(AuthenticationForm):
    username = forms.EmailField(label='Email')

class ForgotPasswordForm(forms.Form):
    email = forms.EmailField()

class VerifyCodeForm(forms.Form):
    code = forms.CharField(max_length=6)

class ResetPasswordForm(forms.Form):
    password1 = forms.CharField(widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput)

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password1')
        p2 = cleaned_data.get('password2')
        if p1 != p2:
            raise forms.ValidationError("Passwords do not match")
        return cleaned_data
def clean_phone_number(self):
    phone = self.cleaned_data['phone_number']

    if not phone.startswith("+880"):
        raise forms.ValidationError("Phone number must start with +880")

    return phone

class CustomPasswordChangeForm(PasswordChangeForm):
    pass