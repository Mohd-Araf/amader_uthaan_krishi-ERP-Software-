import random
from datetime import timedelta
from django.shortcuts import render, redirect
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.mail import send_mail
from django.utils import timezone
from .models import CustomUser, OTPCode
from .forms import (
    SignupForm,
    LoginForm,
    ForgotPasswordForm,
    VerifyCodeForm,
    ResetPasswordForm,
    CustomPasswordChangeForm,
)


# Login View
class CustomLoginView(LoginView):
    template_name = 'accounts/login.html'
    authentication_form = LoginForm


# Signup View
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


# Forgot Password View
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


# Verify Code View
def verify_code_view(request):
    user_id = request.session.get('reset_user')
    if not user_id:
        messages.error(request, 'Session expired. Please request a new OTP.')
        return redirect('forgot_password')

    try:
        user = CustomUser.objects.get(id=user_id)
    except CustomUser.DoesNotExist:
        messages.error(request, 'User not found.')
        return redirect('forgot_password')

    otp = OTPCode.objects.filter(user=user).last()
    remaining_seconds = 0

    if otp:
        expiration_time = otp.created_at + timedelta(minutes=1)
        remaining_seconds = max(0, int((expiration_time - timezone.now()).total_seconds()))

    if request.method == 'POST':
        form = VerifyCodeForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['code']
            valid_otp = OTPCode.objects.filter(user=user, code=code).last()

            if valid_otp:
                if valid_otp.is_expired():
                    valid_otp.delete()
                    messages.error(request, 'OTP has expired. Please request a new code.')
                    return redirect('forgot_password')
                else:
                    valid_otp.delete()
                    request.session['verified_user'] = user.id
                    request.session.pop('reset_user', None)
                    return redirect('reset_password')
            else:
                messages.error(request, 'Invalid Code')
                return redirect('verify_code')
        else:
            messages.error(request, "Invalid form input.")
    else:
        form = VerifyCodeForm()

    return render(request, 'accounts/verify_code.html', {
        'form': form,
        'remaining_seconds': remaining_seconds,
    })


# Reset Password View
def reset_password_view(request):
    user_id = request.session.get('verified_user')
    if not user_id:
        messages.error(request, 'Unauthorized access or session expired.')
        return redirect('forgot_password')

    try:
        user = CustomUser.objects.get(id=user_id)
    except CustomUser.DoesNotExist:
        messages.error(request, 'User not found.')
        return redirect('forgot_password')

    if request.method == 'POST':
        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            user.set_password(form.cleaned_data['password1'])
            user.save()
            request.session.pop('verified_user', None)
            messages.success(request, 'Password reset successfully!')
            return redirect('login')
    else:
        form = ResetPasswordForm()
    return render(request, 'accounts/reset_password.html', {'form': form})


# Change Password View
@login_required
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