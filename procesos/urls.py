from django.urls import path

from procesos import views

app_name = "procesos"

urlpatterns = [
    path("procesos/", views.lista_procesos, name="lista"),
    path("procesos/<uuid:pk>/", views.detalle_proceso, name="detalle"),
    path(
        "procesos/<uuid:pk>/transicion/<str:transicion>/",
        views.transicionar_proceso,
        name="transicionar",
    ),
    path("procesos/<uuid:pk>/verificar-fechas/", views.verificar_fechas, name="verificar_fechas"),
    path("procesos/<uuid:pk>/mover/<str:estado_destino>/", views.mover_kanban, name="mover_kanban"),
]
