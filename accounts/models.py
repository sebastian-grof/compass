from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    """User manager keyed on email instead of a username."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """An adjudicator (or admin) account. Logs in with email, not a username."""

    username = None
    first_name = None
    last_name = None

    email = models.EmailField(_("email address"), unique=True)
    name = models.CharField(_("full name"), max_length=150, blank=True)

    # When True and the adjudicator has exactly one active tournament, the home
    # page redirects straight to that tournament's private URL.
    auto_redirect = models.BooleanField(
        _("auto-redirect to single tournament"), default=False,
        help_text=_("Skip the list and go straight in when only one tournament is active."),
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.name or self.email

    @property
    def all_emails(self):
        """Every email that should match this user in Tabbycat (primary + aliases)."""
        return [self.email, *self.email_aliases.values_list("email", flat=True)]


class EmailAlias(models.Model):
    """Extra email addresses that resolve to a user.

    Adjudicators are matched to Tabbycat records by email. If someone's
    registered email changes between tournaments, an alias keeps the link.
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="email_aliases",
    )
    email = models.EmailField(unique=True)

    class Meta:
        verbose_name = "email alias"
        verbose_name_plural = "email aliases"

    def __str__(self):
        return self.email
