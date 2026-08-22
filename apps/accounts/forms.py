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
        ]
        # password1 & password2 handled automatically by UserCreationForm

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if CustomUser.objects.filter(email=email).exists():
            raise forms.ValidationError("This email is already registered. Only one account per email is allowed.")
        return email

    def clean_phone_number(self):
        phone = self.cleaned_data.get('phone_number')
        if phone:
            if not phone.startswith("+880"):
                raise forms.ValidationError("Phone number must start with +880")
        return phone


class LoginForm(AuthenticationForm):
    username = forms.EmailField(label='Email')


class ForgotPasswordForm(forms.Form):
    email = forms.EmailField()


class VerifyCodeForm(forms.Form):
    code = forms.CharField(max_length=6)


class ResetPasswordForm(forms.Form):
    password1 = forms.CharField(widget=forms.PasswordInput, label="New Password")
    password2 = forms.CharField(widget=forms.PasswordInput, label="Confirm Password")

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password1')
        p2 = cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Passwords do not match")
        if p1 and len(p1) < 4:
            raise forms.ValidationError("Password must be at least 4 characters.")
        return cleaned_data


class CustomPasswordChangeForm(PasswordChangeForm):
    pass