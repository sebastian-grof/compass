from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("go/<int:tournament_id>/", views.go, name="go"),
    path("add/", views.add_tournament, name="add_tournament"),
    path("remove/<int:tournament_id>/", views.remove_tournament, name="remove_tournament"),
    path("guest/", views.guest, name="guest"),
    path("privacy/", views.privacy, name="privacy"),
    path("offline/", views.offline, name="offline"),
    path("import-guest/", views.import_guest, name="import_guest"),
]
