from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, update_session_auth_hash
from django.contrib.auth.views import LoginView
from django.contrib import messages
from django.core.mail import send_mail
from .models import CustomUser, OTPCode
from datetime import timedelta
from django.utils import timezone
from .forms import SignupForm, LoginForm, ForgotPasswordForm, VerifyCodeForm, ResetPasswordForm, CustomPasswordChangeForm
import random

from ..products.models import Order


# Login
class CustomLoginView(LoginView):
    template_name = 'accounts/login.html'
    authentication_form = LoginForm

# Signup
def signup_view(request):
    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Account created successfully!')
            return redirect('login')
    else:
        form = SignupForm()
    return render(request, 'accounts/signin.html', {'form': form})


def forgot_password_view(request):
    if request.method == 'POST':
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            try:
                user = CustomUser.objects.get(email=email)
                code = f"{random.randint(100000, 999999)}"
                OTPCode.objects.create(user=user, code=code)
                send_mail(
                    'Your OTP Code',
                    f'Your verification code is {code}',
                    '22201138@uap-bd.edu',
                    [email],
                    fail_silently=False,
                )
                request.session['reset_user'] = user.id
                return redirect('verify_code')
            except CustomUser.DoesNotExist:
                messages.error(request, 'Email not found')
    else:
        form = ForgotPasswordForm()
    return render(request, 'accounts/forgot_password.html', {'form': form})

# Verify Code
def verify_code_view(request):
    user_id = request.session.get('reset_user')
    remaining_seconds = 0
    user = None

    if user_id:
        user = CustomUser.objects.get(id=user_id)
        otp = OTPCode.objects.filter(user=user).last()

        if otp:
            expiration_time = otp.created_at + timedelta(minutes=1)
            remaining_seconds = int((expiration_time - timezone.now()).total_seconds())
            if remaining_seconds < 0:
                remaining_seconds = 0

    if request.method == 'POST':
        form = VerifyCodeForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['code']

            if user:
                otp = OTPCode.objects.filter(user=user, code=code).last()

                if otp:
                    if otp.is_expired():
                        otp.delete()
                        messages.error(request, 'OTP has expired. Please request a new code.')
                        return redirect('forgot_password')
                    else:
                        otp.delete()
                        request.session['verified_user'] = user.id
                        return redirect('reset_password')
                else:
                    messages.error(request, 'Invalid Code')
                    return redirect('verify_code')
        else:
            messages.error(request, "Invalid form input.")
    else:
        form = VerifyCodeForm()

    context = {
        'form': form,
        'remaining_seconds': remaining_seconds
    }

    return render(request, 'accounts/verify_code.html', context)
# Reset Password
def reset_password_view(request):
    user_id = request.session.get('verified_user')
    if not user_id:
        return redirect('forgot_password')
    user = CustomUser.objects.get(id=user_id)
    if request.method == 'POST':
        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            user.set_password(form.cleaned_data['password1'])
            user.save()
            messages.success(request, 'Password reset successfully!')
            return redirect('login')
    else:
        form = ResetPasswordForm()
    return render(request, 'accounts/reset_password.html', {'form': form})

# Change Password (Logged in user)
def change_password_view(request):
    if request.method == 'POST':
        form = CustomPasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            form.save()
            update_session_auth_hash(request, request.user)
            messages.success(request, 'Password changed successfully!')
            return redirect('profile')
    else:
        form = CustomPasswordChangeForm(user=request.user)
    return render(request, 'accounts/change_password.html', {'form': form})

