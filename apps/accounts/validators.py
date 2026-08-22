from django.core.exceptions import ValidationError


class MinimumLengthValidator:
    """
    Only requires a minimum of 4 characters. No other restrictions.
    """
    def __init__(self, min_length=4):
        self.min_length = min_length

    def validate(self, password, user=None):
        if len(password) < self.min_length:
            raise ValidationError(
                f"Password must be at least {self.min_length} characters long.",
                code='password_too_short',
            )

    def get_help_text(self):
        return f"Your password must contain at least {self.min_length} characters."