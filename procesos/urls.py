from django.urls import path

from procesos import views

app_name = "procesos"

urlpatterns = [
    path("procesos/", views.lista_procesos, name="lista"),
]
