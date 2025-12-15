from django.contrib import admin
from .models import NivelPrioridade, TipoDocumento, Remetente, Documento, Anexo

# Classe para permitir adicionar Anexos na mesma tela do Documento
class AnexoInline(admin.TabularInline):
    model = Anexo
    extra = 1 # Quantos campos de upload extra mostrar

# Classe para melhorar a exibição de Niveis de Prioridade
class NivelPrioridadeAdmin(admin.ModelAdmin):
    list_display = ('descricao', 'prazo_dias')

# Classe para melhorar a exibição de Documentos no admin
class DocumentoAdmin(admin.ModelAdmin):
    list_display = ('protocolo', 'status', 'remetente', 'procurador_atribuido', 'data_atribuicao', 'data_limite') # <-- CAMPO ADICIONADO
    list_filter = ('status', 'prioridade', 'procurador_atribuido', 'data_limite') # <-- CAMPO ADICIONADO
    search_fields = ('protocolo', 'remetente__nome_razao_social')
    inlines = [AnexoInline]
    
    # Faz com que campos de data (que são automáticos) fiquem apenas como leitura
    readonly_fields = ('data_limite',) 

# Register your models here.
admin.site.register(NivelPrioridade, NivelPrioridadeAdmin) # <-- MUDANÇA AQUI
admin.site.register(TipoDocumento)
admin.site.register(Remetente)
admin.site.register(Documento, DocumentoAdmin)