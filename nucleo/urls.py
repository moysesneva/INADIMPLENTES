from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("devedor/<int:pk>/", views.devedor_detail, name="devedor_detail"),
    path("devedor/<int:pk>/acordo/", views.gerar_acordo, name="gerar_acordo"),
    path("devedor/<int:pk>/salvar-acordo/", views.salvar_acordo, name="salvar_acordo"),
    path("acordo/<int:pk>/imprimir/", views.imprimir_acordo, name="imprimir_acordo"),
    path("acordos/", views.acordo_list, name="acordo_list"),
    path("acordos/exportar/", views.exportar_acordos, name="exportar_acordos"),
    path("devedores/", views.devedor_list, name="devedor_list"),
    path("devedores/exportar/", views.exportar_devedores, name="exportar_devedores"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("acordo/<int:pk>/status/", views.alterar_status_acordo, name="alterar_status_acordo"),
    path("parcela/<int:pk>/baixar/", views.baixar_parcela, name="baixar_parcela"),
    
    # Módulo Financeiro (Fase E)
    path("financeiro/", views.financeiro_dashboard, name="financeiro_dashboard"),
    path("financeiro/importar/", views.importar_retorno, name="importar_retorno"),
    path("financeiro/lote/<int:pk>/", views.revisar_lote, name="revisar_lote"),
    path("financeiro/pendencia/<int:pk>/resolver/", views.resolver_pendencia, name="resolver_pendencia"),
    # Portal do Devedor (Fase H)
    path("p/<uuid:token>/", views.portal_devedor, name="portal_devedor"),
]