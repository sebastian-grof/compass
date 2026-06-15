from django.contrib.auth import views as auth_views
from django.urls import path

from .views import LoginView, settings_view

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("settings/", settings_view, name="settings"),

    # Password reset = the "set your password" invite flow. With the console email
    # backend (dev) the link prints to the terminal; configure SMTP to send for real.
    path("password-reset/", auth_views.PasswordResetView.as_view(), name="password_reset"),
    path("password-reset/sent/", auth_views.PasswordResetDoneView.as_view(), name="password_reset_done"),
    path("reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("reset/done/", auth_views.PasswordResetCompleteView.as_view(), name="password_reset_complete"),
]
