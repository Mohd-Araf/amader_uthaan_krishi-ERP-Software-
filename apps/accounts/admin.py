from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, OTPCode

class CustomUserAdmin(UserAdmin):

    model = CustomUser

    list_display = (
        'username',
        'email',
        'country',
        'location',
        'phone_number',
        'is_staff'
    )

    fieldsets = UserAdmin.fieldsets + (
        ('Additional Info', {
            'fields': ('country', 'location', 'phone_number')
        }),
    )


admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(OTPCode)