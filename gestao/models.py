from django.db import models
from django.contrib.auth.models import User
from datetime import datetime, timedelta 
from django.utils import timezone
from django.core.validators import FileExtensionValidator

# Modelo para a tabela: niveis_prioridade
class NivelPrioridade(models.Model):
    descricao = models.CharField(max_length=50, unique=True, verbose_name="Descrição")
    prazo_dias = models.PositiveIntegerField(default=15, verbose_name="Prazo (em dias)") # <-- NOVO CAMPO
    
    def __str__(self):
        return self.descricao
        
    class Meta:
        verbose_name = "Nível de Prioridade"
        verbose_name_plural = "Níveis de Prioridade"


class TipoDocumento(models.Model):
    descricao = models.CharField(max_length=100, unique=True, verbose_name="Descrição")
    ativo = models.BooleanField(default=True, verbose_name="Ativo")
    
    def __str__(self):
        return self.descricao

    class Meta:
        verbose_name = "Tipo de Documento"
        verbose_name_plural = "Tipos de Documento"


class Remetente(models.Model):
    TIPO_CHOICES = [
        ('Pessoa Física', 'Pessoa Física'),
        ('Pessoa Jurídica', 'Pessoa Jurídica'),
        ('Órgão Público', 'Órgão Público'),
    ]
    
    tipo_remetente = models.CharField(max_length=50, choices=TIPO_CHOICES, verbose_name="Tipo de Remetente")
    nome_razao_social = models.CharField(max_length=255, verbose_name="Nome / Razão Social")
    cpf_cnpj = models.CharField(max_length=18, unique=True, verbose_name="CPF / CNPJ")
    email = models.EmailField(max_length=255, blank=True, null=True, verbose_name="E-mail")
    telefone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Telefone")

    def __str__(self):
        return self.nome_razao_social

    class Meta:
        verbose_name = "Remetente"
        verbose_name_plural = "Remetentes"
        
        
# Modelo para a tabela principal: documentos
class Documento(models.Model):
    STATUS_CHOICES = [
        ('Aguardando Distribuição', 'Aguardando Distribuição'),
        ('Em Análise', 'Em Análise'),
        ('Análise Concluída', 'Análise Concluída'),
        ('Aguardando Confirmação', 'Aguardando Confirmação'), 
        ('Devolvido pela Análise', 'Devolvido pela Análise'), # Movido para baixo por lógica
        ('Finalizado', 'Finalizado'),
    ]

    protocolo = models.CharField(max_length=50, unique=True, verbose_name="Protocolo")
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Aguardando Distribuição') # <-- Aumentei max_length para 50
    remetente = models.ForeignKey(Remetente, on_delete=models.PROTECT, verbose_name="Remetente")
    interessados = models.ManyToManyField(
        Remetente, 
        related_name='processos_interessados', 
        blank=True, 
        verbose_name="Interessados / Secretarias"
    )
    
   
    notificar_remetente = models.BooleanField(default=False, verbose_name="Notificar Remetente na Finalização?")
    tipo_documento = models.ForeignKey(TipoDocumento, on_delete=models.PROTECT, verbose_name="Tipo de Documento")
    prioridade = models.ForeignKey(NivelPrioridade, on_delete=models.PROTECT, verbose_name="Prioridade")
    num_doc_origem = models.CharField(max_length=100, verbose_name="Número do Doc. de Origem")
    data_doc_origem = models.DateField(verbose_name="Data do Doc. de Origem")
    observacoes_protocolo = models.TextField(blank=True, null=True, verbose_name="Observações do Protocolo")
    protocolado_por = models.ForeignKey(User, on_delete=models.PROTECT, related_name='documentos_protocolados', verbose_name="Protocolado por")
    procurador_atribuido = models.ForeignKey(User, on_delete=models.PROTECT, related_name='documentos_atribuidos', blank=True, null=True, verbose_name="Procurador Atribuído")

    data_recebimento = models.DateTimeField(auto_now_add=True, verbose_name="Data de Recebimento")
    data_atribuicao = models.DateTimeField(blank=True, null=True, verbose_name="Data de Atribuição")
    data_finalizacao = models.DateTimeField(blank=True, null=True, verbose_name="Data de Finalização")
    data_limite = models.DateField(blank=True, null=True, verbose_name="Data Limite para Resposta")
    data_resposta_procurador = models.DateTimeField(blank=True, null=True, verbose_name="Data da Resposta do Procurador")
    obs_finalizacao = models.TextField(blank=True, null=True, verbose_name="Observações da Finalização")

    finalizado_por = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='documentos_finalizados', # Nome interno diferente
        blank=True, null=True,                 # Permite ser nulo (antes de finalizar)
        verbose_name="Finalizado por"
    )
    motivo_ultima_devolucao = models.TextField(blank=True, null=True, verbose_name="Motivo da Última Devolução")
    motivo_ultima_reativacao = models.TextField(blank=True, null=True, verbose_name="Motivo da Última Reativação")
    motivo_rejeicao_analista = models.TextField(blank=True, null=True, verbose_name="Motivo da Rejeição (Analista)")
    
    @property
    def esta_atrasado(self):
        if self.data_limite and not self.data_finalizacao:
            return timezone.localdate() > self.data_limite
        return False

    def __str__(self):
        return self.protocolo

    class Meta:
        verbose_name = "Documento"
        verbose_name_plural = "Documentos"


    def save(self, *args, **kwargs):
        
        if not self.pk: 
            hoje = timezone.localdate()
            prefixo = hoje.strftime('%Y-%m-%d')
            
            ultimo_doc_hoje = Documento.objects.filter(protocolo__startswith=prefixo).order_by('-protocolo').first()
            
            sequencial = 1
            if ultimo_doc_hoje:
                try:
                    # Extrai o número sequencial (ex: '2025-10-23-005' -> '005')
                    ultimo_sequencial_str = ultimo_doc_hoje.protocolo.split('-')[-1]
                    sequencial = int(ultimo_sequencial_str) + 1
                except (IndexError, ValueError):
                    # Se houver erro ao extrair, volta para 1 por segurança
                    sequencial = 1
                    
            # Formata o sequencial com 3 dígitos (001, 002, ..., 010, ..., 100)
            sequencial_formatado = f"{sequencial:03d}" 
            
            self.protocolo = f"{prefixo}-{sequencial_formatado}"

        if self.data_atribuicao:
            dias_prazo = self.prioridade.prazo_dias
            
            self.data_limite = self.data_atribuicao.date() + timedelta(days=dias_prazo)
        
        else:
            self.data_limite = None
            
        # Chama o método save() original para salvar o objeto no banco de dados
        super().save(*args, **kwargs)


@property
def first_initial_attachment_url(self):
    """ Retorna a URL do primeiro anexo do tipo 'INICIAL', ou None se não houver. """
        
        # --- DEBUGGING ---
    print(f"--- Verificando anexos para Doc ID: {self.pk}, Protocolo: {self.protocolo} ---")
    todos_anexos = self.anexos.all()
    print(f"Total de anexos encontrados: {todos_anexos.count()}")
    for a in todos_anexos:
        print(f"  - Anexo ID: {a.pk}, Tipo: '{a.tipo_anexo}', Arquivo: {a.arquivo.name}")
        # --- FIM DEBUGGING ---

        # Filtra os anexos deste documento pelo tipo
    first_anexo = self.anexos.filter(tipo_anexo='INICIAL').first() 
        
        # --- DEBUGGING ---
    if first_anexo:
        print(f"==> Encontrado anexo INICIAL: ID {first_anexo.pk}, URL: {first_anexo.arquivo.url}")
        return first_anexo.arquivo.url
    else:
        print(f"==> Nenhum anexo INICIAL encontrado.")
        return None
        # --- FIM DEBUGGING ---

class Anexo(models.Model):
    TIPO_CHOICES = [
        ('INICIAL', 'Documento Inicial'),
        ('RESPOSTA', 'Documento de Resposta'),
    ]

    documento = models.ForeignKey(Documento, on_delete=models.CASCADE, related_name='anexos', verbose_name="Documento")
    arquivo = models.FileField(
        upload_to='anexos/', 
        verbose_name="Arquivo",
        # ADICIONE ESTE VALIDADOR:
        validators=[
            FileExtensionValidator(allowed_extensions=['pdf', 'png', 'jpg', 'jpeg'])
        ]
    )
    tipo_anexo = models.CharField(max_length=50, choices=TIPO_CHOICES, default='INICIAL', verbose_name="Tipo do Anexo")
    usuario_upload = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name="Enviado por")
    data_upload = models.DateTimeField(auto_now_add=True, verbose_name="Data de Upload")
    ativo = models.BooleanField(default=True, verbose_name="Ativo")
    descricao = models.TextField(blank=True, null=True, verbose_name="Descrição")
    def __str__(self):
        return self.arquivo.name
    
    class Meta:
        verbose_name = "Anexo"
        verbose_name_plural = "Anexos"

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    pin_autorizacao = models.CharField(max_length=128, blank=True, null=True, verbose_name="PIN de Autorização (Criptografado)")

    def __str__(self):
        return self.user.username
    

class HistoricoEdicao(models.Model):
    documento = models.ForeignKey(Documento, on_delete=models.CASCADE, related_name='historico')
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    data_alteracao = models.DateTimeField(auto_now_add=True)
    campo_alterado = models.CharField(max_length=100)
    valor_antigo = models.TextField(null=True, blank=True)
    valor_novo = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['-data_alteracao']

class SolicitacaoDocumento(models.Model):
    STATUS_CHOICES = [
        ('Pendente', 'Pendente de Análise'),
        ('Enviada', 'E-mail enviado ao Remetente'),
        ('Atendida', 'Documento anexado / Concluída'),
        ('Rejeitada', 'Solicitação Negada pela Chefia'),
    ]

    documento = models.ForeignKey(Documento, on_delete=models.CASCADE, related_name='solicitacoes')
    procurador = models.ForeignKey(User, on_delete=models.CASCADE, related_name='minhas_solicitacoes')
    descricao_necessidade = models.TextField(help_text="Explique quais documentos faltam.")
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pendente')
    data_solicitacao = models.DateTimeField(auto_now_add=True)
    
    # Resposta da Chefia
    analisado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    observacao_chefia = models.TextField(blank=True, null=True)
    data_resposta = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Diligência {self.id} - {self.documento.protocolo}"