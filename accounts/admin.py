from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import AdminPasswordChangeForm, PasswordResetForm

from .models import EmailAlias, User


class EmailAliasInline(admin.TabularInline):
    model = EmailAlias
    extra = 1


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin for the email-based custom user (no username field)."""

    change_password_form = AdminPasswordChangeForm
    ordering = ("email",)
    list_display = ("email", "name", "is_staff", "is_active", "auto_redirect")
    list_filter = ("is_staff", "is_superuser", "is_active")
    search_fields = ("email", "name")
    inlines = [EmailAliasInline]
    actions = ["send_set_password_email"]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("name", "auto_redirect")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "name", "password1", "password2"),
        }),
    )

    @admin.action(description="Send set-password / invite email")
    def send_set_password_email(self, request, queryset):
        sent = 0
        for user in queryset:
            form = PasswordResetForm({"email": user.email})
            if form.is_valid():
                form.save(
                    request=request,
                    use_https=request.is_secure(),
                    email_template_name="registration/password_reset_email.html",
                    subject_template_name="registration/password_reset_subject.txt",
                )
                sent += 1
        self.message_user(request, f"Sent set-password email to {sent} user(s).", messages.SUCCESS)
