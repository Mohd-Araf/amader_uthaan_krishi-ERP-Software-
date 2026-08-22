from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, OTPCode


class CustomUserAdmin(UserAdmin):
    model = CustomUser

    list_display = (
        'user_id',   # Custom ID shown in admin list
        'username',
        'email',
        'country',
        'location',
        'phone_number',
        'is_staff',
    )

    fieldsets = UserAdmin.fieldsets + (
        ('Additional Info', {
            'fields': ('country', 'location', 'phone_number', 'profile_image', 'user_id')
        }),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Additional Info', {
            'fields': ('country', 'location', 'phone_number', 'profile_image')
        }),
    )

    readonly_fields = ('user_id',)  # Auto-generated, not editable


admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(OTPCode)