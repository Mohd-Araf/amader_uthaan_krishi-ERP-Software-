from django.contrib.auth.models import AbstractUser
from django.db import models
from datetime import timedelta
from django.utils import timezone
class CustomUser(AbstractUser):

    email = models.EmailField(unique=True)

    COUNTRY_CHOICES = [
        ('BD', 'Bangladesh'),
        ('IN', 'India'),
        ('PK', 'Pakistan'),
        ('US', 'United States'),
        ('UK', 'United Kingdom'),
    ]

    country = models.CharField(max_length=50, choices=COUNTRY_CHOICES, blank=True, null=True)
    location = models.CharField(max_length=150, blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']
    profile_image = models.ImageField(
        upload_to='profiles/',
        blank=True,
        null=True
    )

    def __str__(self):
        return self.username

class OTPCode(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} - {self.code}"

    def is_expired(self):
        return timezone.now() > self.created_at + timedelta(minutes=1)