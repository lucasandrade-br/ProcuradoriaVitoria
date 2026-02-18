from django.urls import path
from . import views # Importa o arquivo views.py que acabamos de editar

app_name = 'gestao'

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('cadastrar/', views.documento_create_view, name='documento_create'),
    path('distribuir/', views.distribuicao_view, name='distribuicao'),
    path('meus-documentos/', views.procurador_dashboard_view, name='procurador_dashboard'),
    path('documento/<int:pk>/', views.documento_detail_view, name='documento_detail'),
    path('monitorar/', views.monitoramento_analises_view, name='monitoramento_analises'),
    path('finalizar/<int:pk>/', views.finalizacao_detail_view, name='finalizacao_detail'),
    path('busca/', views.busca_view, name='busca'),
    path('consulta/<int:pk>/', views.documento_consulta_view, name='documento_consulta'),
    path('documento/<int:pk>/devolver/', views.devolver_documento_view, name='devolver_documento'),
    path('reativar/<int:pk>/', views.reativar_documento_view, name='reativar_documento'),
    path('confirmacao/<int:pk>/', views.documento_confirmacao_view, name='documento_confirmacao'),
    path('remetente/novo/ajax/', views.cadastrar_remetente_ajax_view, name='cadastrar_remetente_ajax'),
    path('remetente/autocomplete/', views.remetente_autocomplete_view, name='remetente_autocomplete'),
    path('lembrete/<int:pk>/', views.enviar_lembrete_view, name='enviar_lembrete'),
    path('confirmar/', views.confirmacao_lista_view, name='confirmacao_lista'),
    path('confirmar/<int:pk>/', views.confirmacao_detail_view, name='confirmacao_detail'),
    path('definir-pin/', views.definir_pin_view, name='definir_pin'),
    path('verificar-pin/ajax/', views.verificar_pin_ajax_view, name='verificar_pin_ajax'),
    path('rejeitar/<int:pk>/', views.rejeitar_confirmacao_view, name='rejeitar_confirmacao'),
    path('documento/<int:pk>/excluir_anexo/<int:anexo_id>/', views.excluir_anexo_view, name='excluir_anexo'),
    path('documento/<int:pk>/editar/', views.documento_update_view, name='documento_update'),
    path('diligencias/', views.diligencias_pendentes_view, name='diligencias'),
    path('diligencia/decidir/<int:diligencia_id>/', views.decidir_diligencia_view, name='decidir_diligencia'),
    path('documento/atribuir/<int:pk>/', views.atribuir_procurador_direto_view, name='atribuir_procurador_direto'),
    path('redistribuir-ferias/', views.redistribuir_ferias_view, name='redistribuir_ferias'),
    path('ajax/get-process-count/', views.get_process_count_ajax, name='get_process_count'),
]

