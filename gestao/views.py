import logging
import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, Group
from django.contrib.auth.hashers import make_password, check_password
from .models import Documento, Anexo, HistoricoEdicao, Remetente, SolicitacaoDocumento
from django.http import JsonResponse
from .forms import DocumentoForm, AnexoFormSet, AnexoForm, FinalizacaoForm, DocumentoFilterForm, RemetenteForm, PinForm, DocumentoUpdateForm, AnexoUpdateFormSet
from django.utils import timezone
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Max, Q
from django.core.mail import EmailMessage, send_mail, EmailMultiAlternatives
from django.conf import settings
from django.core.paginator import Paginator
from django.urls import reverse
from datetime import datetime
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.db import transaction
from .email_utils import enviar_email_html

logger = logging.getLogger('gestao')

@login_required
def dashboard_view(request):
    
    # 1. Lógica de Contagem ATUALIZADA
    
    # Total de docs na fila de distribuição
    total_para_distribuir = Documento.objects.filter(
        status__in=['Aguardando Distribuição', 'Devolvido pela Análise']
    ).count()
    
    # Total de docs que estão com procuradores (para monitorar)
    total_para_monitorar = Documento.objects.filter(
        status__in=['Em Análise', 'Análise Concluída', 'Rejeitado', 'Em Diligência']
    ).count()
    
    # Total de docs que aguardam a confirmação final do Analista/Chefe
    total_para_confirmar = Documento.objects.filter(
        status='Aguardando Confirmação'
    ).count()
    
    # Total de docs pendentes para o PROCURADOR logado (para o card dele)
    total_pendente_procurador = Documento.objects.filter(
        status__in=['Em Análise', 'Rejeitado', 'Em Diligência'],
        procurador_atribuido=request.user
    ).count()

    total_diligencias_pendentes = SolicitacaoDocumento.objects.filter(
        status='Pendente' # Ou o status que representa "aguardando gestão"
    ).count()

    # 2. Preparar os dados para enviar ao HTML
    context = {
        'total_para_distribuir': total_para_distribuir,
        'total_para_monitorar': total_para_monitorar,
        'total_para_confirmar': total_para_confirmar,
        'total_pendente_procurador': total_pendente_procurador,
        'total_diligencias_pendentes': total_diligencias_pendentes,
    }

    # 3. Renderizar a página
    return render(request, 'gestao/dashboard.html', context)


@login_required
def documento_create_view(request):
    is_protocolo_chefe = request.user.groups.filter(name='Protocolador-Chefe').exists()
    is_protocolo = request.user.groups.filter(name='Protocolo').exists()
    is_cadastrante = request.user.groups.filter(name='Cadastrante').exists()
    if not request.user.is_superuser and not is_protocolo_chefe and not is_protocolo and not is_cadastrante:
        raise PermissionDenied("Você não tem permissão para cadastrar documentos.")
    
    
    # Lógica POST: Processa o formulário principal E o formset
    if request.method == 'POST':
        documento_form = DocumentoForm(request.POST) 
        # Instancia com o prefixo aqui
        anexo_formset = AnexoFormSet(request.POST, request.FILES, prefix='anexos') 

        if documento_form.is_valid() and anexo_formset.is_valid():
            tem_anexo = any(form.cleaned_data.get('arquivo') for form in anexo_formset.forms 
                            if form.cleaned_data and not form.cleaned_data.get('DELETE', False))

            if not tem_anexo:
                messages.error(request, "É obrigatório anexar pelo menos um documento.")
            else:
                try:
                    with transaction.atomic():
                        documento = documento_form.save(commit=False)
                        documento.protocolado_por = request.user
                        documento.save() 
                        documento_form.save_m2m() 

                        anexo_formset.instance = documento
                        anexos_salvos = anexo_formset.save(commit=False) 
                        for anexo in anexos_salvos:
                            anexo.usuario_upload = request.user
                            anexo.tipo_anexo = 'INICIAL'
                            anexo.save() 

                        anexo_formset.save_m2m()
                        
                        # IMPORTANTE: Você precisa retornar o redirect aqui dentro do sucesso!
                        return redirect('gestao:documento_confirmacao', pk=documento.pk)

                except Exception as e:
                    messages.error(request, f"Erro crítico ao salvar: {str(e)}")
        else:
            messages.error(request, "Erro ao cadastrar o documento. Verifique os campos.")

    else:
        # Lógica GET: Instancia o formset vazio com o prefixo
        documento_form = DocumentoForm()
        anexo_formset = AnexoFormSet(prefix='anexos') # Defina o prefixo aqui

    # Contexto limpo: Apenas passa as variáveis já instanciadas
    context = {
        'documento_form': documento_form,
        'anexo_formset': anexo_formset 
    }
    

    return render(request, 'gestao/documento_form.html', context)


@login_required
def distribuicao_view(request):
    is_protocolo_chefe = request.user.groups.filter(name='Protocolador-Chefe').exists()
    is_protocolo = request.user.groups.filter(name='Protocolo').exists()
    if not request.user.is_superuser and not is_protocolo_chefe and not is_protocolo:
        raise PermissionDenied("Você não tem permissão para distribuir documentos.")
    
    # --- LÓGICA DE ATRIBUIÇÃO (POST) ---
    if request.method == 'POST':
        documentos_ids = request.POST.getlist('documento_selecionado')
        procurador_id = request.POST.get('procurador_id')

        if not documentos_ids:
            messages.error(request, 'Nenhum documento foi selecionado.')
            return redirect('gestao:distribuicao')

        if not procurador_id:
            messages.error(request, 'Nenhum procurador foi selecionado.')
            return redirect('gestao:distribuicao')

        try:
            procurador = User.objects.get(id=procurador_id)
            documentos_para_atribuir = Documento.objects.filter(id__in=documentos_ids, status__in=['Aguardando Distribuição', 'Devolvido pela Análise'])

            if not documentos_para_atribuir.exists():
                messages.warning(request, 'Os documentos selecionados já foram distribuídos por outro usuário.')
                return redirect('gestao:distribuicao')

            emails_enviados_count = 0

            for doc in documentos_para_atribuir:
                doc.procurador_atribuido = procurador
                doc.status = 'Em Análise'
                doc.data_atribuicao = timezone.now()
                doc.motivo_ultima_devolucao = None
                
                doc.save() # Dispara o cálculo da data limite

                # --- INÍCIO DO BLOCO DE ENVIO DE E-MAIL ---
                try:
                    from .email_utils import enviar_email_html
                    
                    url_documento = request.build_absolute_uri(f'/documento/{doc.pk}/')
                    
                    contexto = {
                        'procurador_nome': procurador.get_full_name() or procurador.username,
                        'protocolo': doc.protocolo,
                        'num_doc_origem': doc.num_doc_origem,
                        'remetente': doc.remetente.nome_razao_social,
                        'tipo_documento': doc.tipo_documento.descricao,
                        'prioridade': doc.prioridade.descricao,
                        'data_limite': doc.data_limite.strftime('%d/%m/%Y') if doc.data_limite else None,
                        'observacoes': doc.observacoes_protocolo,
                        'url_documento': url_documento,
                    }
                    
                    anexos_iniciais = doc.anexos.filter(tipo_anexo='INICIAL', ativo=True)
                    anexos_paths = [anexo.arquivo.path for anexo in anexos_iniciais if os.path.exists(anexo.arquivo.path)]
                    
                    assunto = f"Novo Documento para Análise - Protocolo {doc.protocolo}"
                    sucesso = enviar_email_html(
                        assunto=assunto,
                        template_name='emails/documento_distribuido.html',
                        contexto=contexto,
                        destinatarios=[procurador.email],
                        anexos=anexos_paths
                    )
                    
                    if sucesso:
                        emails_enviados_count += 1
                        logger.info(f"E-mail de distribuição enviado para {procurador.email} - Documento {doc.protocolo}")

                except Exception as e_mail:
                    # Captura erros no envio (configuração errada, email inválido, etc.)
                    messages.error(request, f"Erro ao enviar e-mail para o documento {doc.protocolo}: {e_mail}")



            nome_procurador = procurador.get_full_name() or procurador.username
            messages.success(request, f'{len(documentos_para_atribuir)} documento(s) atribuído(s) com sucesso para {nome_procurador}.')
        
        except User.DoesNotExist:
             messages.error(request, 'Procurador selecionado inválido.')
        
        return redirect('gestao:distribuicao')

    # --- LÓGICA DE EXIBIÇÃO (GET) ---
    
    # 1. Busca a lista de documentos para distribuir
    lista_de_documentos = Documento.objects.filter(
        status__in=['Aguardando Distribuição', 'Devolvido pela Análise']
    ).select_related( # Otimização para ForeignKey
        'remetente', 'procurador_atribuido', 'prioridade', 'tipo_documento' 
    ).prefetch_related( # OTIMIZAÇÃO: Busca os anexos eficientemente
        'anexos', 'interessados'
    ).order_by('data_recebimento')

    # 2. Busca a lista de usuários que pertencem ao grupo "Procuradores" (ativos)
    procurador_recomendado = None
    lista_de_procuradores = []
    try:
        grupo_procuradores = Group.objects.get(name='Procuradores')
        # Filtra apenas usuários ativos
        lista_de_procuradores = list(grupo_procuradores.user_set.filter(is_active=True).order_by('id')) 
    except Group.DoesNotExist:
        messages.warning(request, 'Grupo "Procuradores" não encontrado. Crie o grupo no Painel de Admin.')

    # --- LÓGICA DE RECOMENDAÇÃO (ROUND-ROBIN) ---
    if lista_de_procuradores: # Só executa se houver procuradores na lista
        # Encontra o ID do último procurador que recebeu um documento
        # Usamos aggregate(Max(...)) para encontrar a data de atribuição mais recente
        ultima_atribuicao = Documento.objects.filter(
            procurador_atribuido__in=lista_de_procuradores # Apenas entre os procuradores ativos
        ).aggregate(ultima_data=Max('data_atribuicao'))
        
        ultimo_procurador_id = None
        if ultima_atribuicao and ultima_atribuicao['ultima_data']:
            # Pega o documento com a data mais recente para saber quem foi o último
            ultimo_documento = Documento.objects.filter(
                data_atribuicao=ultima_atribuicao['ultima_data']
            ).first()
            if ultimo_documento:
                ultimo_procurador_id = ultimo_documento.procurador_atribuido_id

        if ultimo_procurador_id:
            # Encontra o índice do último procurador na lista ordenada por ID
            indice_ultimo = -1
            for i, p in enumerate(lista_de_procuradores):
                if p.id == ultimo_procurador_id:
                    indice_ultimo = i
                    break
            
            # Calcula o índice do próximo usando módulo (%) para dar a volta na lista
            if indice_ultimo != -1:
                indice_proximo = (indice_ultimo + 1) % len(lista_de_procuradores)
                procurador_recomendado = lista_de_procuradores[indice_proximo]
            else:
                 # Se o último não foi encontrado (talvez inativado?), recomenda o primeiro
                 procurador_recomendado = lista_de_procuradores[0]
        else:
            # Se ninguém recebeu ainda, recomenda o primeiro da lista
            procurador_recomendado = lista_de_procuradores[0]
    # --- FIM DA LÓGICA DE RECOMENDAÇÃO ---


    # 3. O Contexto: Preparamos os dados para o HTML
    context = {
        'documentos': lista_de_documentos,
        'procuradores': lista_de_procuradores,
        'procurador_recomendado': procurador_recomendado, # <-- ENVIA A RECOMENDAÇÃO
    }

    # 4. Renderizar a página
    return render(request, 'gestao/distribuicao.html', context)


@login_required
def procurador_dashboard_view(request):
    
    # --- OTIMIZAÇÃO PARA PERFORMANCE MÁXIMA ---
    # 1. Buscamos os documentos otimizando o acesso ao banco
    lista_de_documentos = Documento.objects.filter(
        status__in=['Em Análise', 'Rejeitado', 'Em Diligência'],
        procurador_atribuido=request.user
    ).select_related(
        'tipo_documento', 
        'prioridade'
    ).prefetch_related(
        'interessados' # <--- OBRIGATÓRIO para a nova tabela com badges
    ).order_by('data_limite')
    
    # 2. O Contexto
    context = {
        'documentos': lista_de_documentos
    }

    # 3. Renderizar a página
    return render(request, 'gestao/procurador_dashboard.html', context)



@login_required
def documento_detail_view(request, pk):
    # 1. Busca o documento
    documento = get_object_or_404(Documento, pk=pk)

    # 2. VERIFICAÇÃO DE PERMISSÃO (GET - Ver a Página)
    # (Baseada na sua lógica anterior)
    is_procurador_chefe = request.user.groups.filter(name='Procurador-Chefe').exists()
    is_procurador = request.user.groups.filter(name='Procuradores').exists()
    is_procurador_analista = request.user.groups.filter(name='Procurador-Analista').exists()
    is_procurador_atribuido = (request.user == documento.procurador_atribuido)
    
    pode_ver = False
    if request.user.is_superuser or is_procurador_chefe:
        pode_ver = True
    elif (is_procurador or is_procurador_analista) and is_procurador_atribuido:
        pode_ver = True
        
    if not pode_ver:
         raise PermissionDenied("Você não tem permissão para visualizar este documento.")
    # --- FIM DA VERIFICAÇÃO GET ---

    # 3. VERIFICAÇÃO DE PERMISSÃO (POST - Realizar Ações)
    # (A mesma lógica, mas determina se o usuário pode enviar formulários)
    pode_agir = False
    if request.user.is_superuser or is_procurador_chefe:
         pode_agir = True
    elif (is_procurador or is_procurador_analista) and is_procurador_atribuido:
         pode_agir = True
         
    # --- LÓGICA DE PROCESSAMENTO (POST) ---
    if request.method == 'POST':
        
        # Garante que apenas usuários permitidos possam fazer POST
        if not pode_agir:
             messages.error(request, "Você não tem permissão para realizar esta ação.")
             return redirect('gestao:documento_detail', pk=documento.pk)

        # 1. Lógica para SOLICITAR DILIGÊNCIA (Aba 5)
        if 'submit_diligencia' in request.POST:
            descricao = request.POST.get('descricao_necessidade')
            
            if descricao:
                # Cria o registro da solicitação
                SolicitacaoDocumento.objects.create(
                    documento=documento,
                    procurador=request.user,
                    descricao_necessidade=descricao,
                    status='Pendente'
                )
                
                # MUDANÇA DE STATUS: O processo sai da fila "ativa" do procurador
                documento.status = 'Em Diligência'
                documento.save()
                
                messages.success(request, "Solicitação de documentos enviada com sucesso à Chefia.")
                return redirect('gestao:documento_detail', pk=pk)
            else:
                messages.error(request, "Você precisa descrever o que está faltando.")


        # --- AÇÃO 1: APENAS ANEXAR ---
        # (Verifica se o botão 'submit_anexar' foi pressionado - nome do template)
        elif 'submit_anexar' in request.POST:
            anexo_form = AnexoForm(request.POST, request.FILES)
            if anexo_form.is_valid():
                anexo = anexo_form.save(commit=False)
                anexo.documento = documento
                anexo.usuario_upload = request.user
                anexo.tipo_anexo = 'RESPOSTA'
                anexo.save()
                messages.success(request, "Arquivo anexado com sucesso. Revise-o antes de concluir.")
                # Redireciona para a MESMA página para permitir revisão
                return redirect('gestao:documento_detail', pk=documento.pk)
            else:
                messages.error(request, "Erro ao anexar arquivo. Verifique se selecionou um arquivo válido.")
                
        # --- AÇÃO 2: CONCLUIR ANÁLISE ---
        # (Verifica se o botão 'submit_concluir' foi pressionado - nome do template)
        elif 'submit_concluir' in request.POST:
            # 1. TRAVA DE DILIGÊNCIAS: Verifica se há solicitações que não foram finalizadas
            # Filtra por 'Pendente' ou 'Enviada'
            diligencias_ativas = documento.solicitacoes.filter(status__in=['Pendente', 'Enviada']).exists()
            
            if diligencias_ativas:
                messages.error(
                    request, 
                    "Não é possível concluir: este processo possui diligências pendentes ou enviadas que ainda não foram resolvidas."
                )
                return redirect('gestao:documento_detail', pk=documento.pk)
            # Verifica se há pelo menos uma resposta ativa antes de concluir
            if not documento.anexos.filter(tipo_anexo='RESPOSTA', ativo=True).exists():
                 messages.error(request, "Você deve anexar pelo menos um parecer antes de concluir.")
                 return redirect('gestao:documento_detail', pk=documento.pk)

            # Tudo certo, vamos concluir!
            documento.status = 'Análise Concluída'
            documento.data_resposta_procurador = timezone.now()
            documento.save(update_fields=['status', 'data_resposta_procurador']) # Salva só os campos mudados
            
            messages.success(request, f'Análise do protocolo {documento.protocolo} concluída com sucesso!')
            # Redireciona para a mesa de trabalho
            return redirect('gestao:procurador_dashboard')
    
    # --- LÓGICA DE EXIBIÇÃO (GET ou se POST falhar) ---
    
    # Busca os anexos (ativos) para exibir nas listas
    anexos_iniciais = documento.anexos.filter(tipo_anexo='INICIAL', ativo=True)
    anexos_resposta = documento.anexos.filter(tipo_anexo='RESPOSTA', ativo=True)
    
    # Prepara um formulário de anexo vazio para o upload
    # (Se o POST falhou no 'submit_anexar', o 'anexo_form' com erros será usado)
    if 'anexo_form' not in locals():
        anexo_form = AnexoForm()

    context = {
        'documento': documento,
        'anexos_iniciais': anexos_iniciais,
        'anexos_resposta': anexos_resposta, # Envia a lista de respostas
        'anexo_form': anexo_form,
        'solicitacoes': documento.solicitacoes.all().order_by('-data_solicitacao'),
    }
    
    return render(request, 'gestao/documento_detail.html', context)

@login_required
def monitoramento_analises_view(request):
    # Verificação de permissões (Mantida como está, está correta)
    is_protocolo_chefe = request.user.groups.filter(name='Protocolador-Chefe').exists()
    is_protocolo = request.user.groups.filter(name='Protocolo').exists()
    if not request.user.is_superuser and not is_protocolo_chefe and not is_protocolo:
        raise PermissionDenied("Você não tem permissão para acessar esta página.")

    # 1. A Lógica Otimizada:
    lista_de_documentos = Documento.objects.filter(
        status__in=['Em Análise', 'Análise Concluída', 'Rejeitado', 'Em Diligência']
    ).select_related(
        'tipo_documento', 
        'prioridade', 
        'procurador_atribuido'
    ).prefetch_related(
        'interessados'  # <--- CRUCIAL para a tabela que você alterou!
    ).order_by('data_limite')

    # 2. O Contexto
    context = {
        'documentos': lista_de_documentos
    }

    # 3. Renderizar
    return render(request, 'gestao/monitoramento_analises.html', context)



@login_required
def finalizacao_detail_view(request, pk):
    # Verificação de permissão de acesso (GET)
    is_protocolo_chefe = request.user.groups.filter(name='Protocolador-Chefe').exists()
    is_protocolo = request.user.groups.filter(name='Protocolo').exists()
    if not request.user.is_superuser and not is_protocolo_chefe and not is_protocolo:
        raise PermissionDenied("Você não tem permissão para acessar esta página.")
    
    documento = get_object_or_404(Documento, pk=pk)
    pode_arquivar_direto = is_protocolo_chefe or request.user.is_superuser

    # Instanciamos os formulários FORA do if/else para reuso
    finalizacao_form = FinalizacaoForm(request.POST or None, instance=documento)
    anexo_form = AnexoForm(request.POST or None, request.FILES or None)

    if request.method == 'POST':
        
        # --- AÇÃO 1: Anexar Parecer (igual a antes) ---
        if 'submit_anexo' in request.POST: 
            if anexo_form.is_valid():
                anexo = anexo_form.save(commit=False)
                anexo.documento = documento
                anexo.usuario_upload = request.user
                anexo.tipo_anexo = 'RESPOSTA'
                anexo.save()
                messages.success(request, f"Parecer anexado com sucesso ao documento {documento.protocolo}.")
                return redirect('gestao:finalizacao_detail', pk=documento.pk)
            else:
                messages.error(request, "Erro ao anexar o parecer. Verifique o arquivo.")

        # --- AÇÃO 2: Enviar para Conclusão ---
        elif 'submit_enviar_conclusao' in request.POST:
            if documento.solicitacoes.filter(status__in=['Pendente', 'Enviada']).exists():
                messages.error(request, "Impossível prosseguir: Existem diligências pendentes ou enviadas que ainda não foram resolvidas.")
                return redirect('gestao:finalizacao_detail', pk=documento.pk)
            
            if not documento.anexos.filter(tipo_anexo='RESPOSTA', ativo=True).exists():
                messages.error(request, "Impossível prosseguir: Nenhum parecer/resposta foi anexado a este processo.")
                return redirect('gestao:finalizacao_detail', pk=documento.pk)


            if finalizacao_form.is_valid():
                documento_salvo = finalizacao_form.save(commit=False)
                documento_salvo.status = 'Aguardando Confirmação' # <-- NOVO STATUS
                documento_salvo.data_finalizacao = None
                documento_salvo.finalizado_por = None
                documento_salvo.save()
                
                messages.success(request, f"Processo {documento.protocolo} enviado para Confirmação.")
                return redirect('gestao:monitoramento_analises')
            else:
                 messages.error(request, "Erro ao enviar para conclusão. Verifique o campo de registro.")

        # --- AÇÃO 3: Arquivar Diretamente ---
        elif 'submit_arquivar_direto' in request.POST:
            # Verificação de segurança dupla
            if not pode_arquivar_direto:
                raise PermissionDenied
            
            if documento.solicitacoes.filter(status__in=['Pendente', 'Enviada']).exists():
                messages.error(request, "Impossível arquivar: Existem diligências em aberto (pendentes ou enviadas).")
                return redirect('gestao:finalizacao_detail', pk=documento.pk)
            
            if not documento.anexos.filter(tipo_anexo='RESPOSTA', ativo=True).exists():
                messages.error(request, "Impossível arquivar: Nenhum parecer/resposta foi anexado a este processo.")
                return redirect('gestao:finalizacao_detail', pk=documento.pk)

            if finalizacao_form.is_valid():
                # O form salva a 'obs_finalizacao'
                documento_salvo = finalizacao_form.save(commit=False) 
                documento_salvo.status = 'Finalizado' # <-- STATUS FINAL
                documento_salvo.data_finalizacao = timezone.now()
                documento_salvo.finalizado_por = request.user
                documento_salvo.save()
                
                # --- LÓGICA DE ENVIO DE E-MAIL (REFATORADA PARA MÚLTIPLOS DESTINATÁRIOS) ---
                email_enviado_sucesso = False
                try:
                    from .email_utils import enviar_email_html
                    
                    # 1. Monta a lista de destinatários (Interessados + Opcional Remetente)
                    destinatarios = [i.email for i in documento.interessados.all() if i.email] #
                    
                    if documento.notificar_remetente and documento.remetente.email: #
                        destinatarios.append(documento.remetente.email) #

                    # Só prossegue se houver pelo menos um e-mail na lista
                    if destinatarios:
                        contexto = {
                            # Dica: No template, você pode mudar 'remetente_nome' para algo mais genérico
                            'remetente_nome': "Interessados", 
                            'protocolo': documento.protocolo,
                            'num_doc_origem': documento.num_doc_origem,
                            'data_finalizacao': documento.data_finalizacao.strftime('%d/%m/%Y %H:%M') if documento.data_finalizacao else timezone.now().strftime('%d/%m/%Y %H:%M'),
                            'observacoes_finalizacao': documento.obs_finalizacao,
                        }
                        
                        # Lógica de anexos permanece a mesma (Muito boa por sinal!)
                        anexos_paths = []
                        for anexo in documento.anexos.filter(tipo_anexo__in=['INICIAL', 'RESPOSTA'], ativo=True):
                            if os.path.exists(anexo.arquivo.path):
                                anexos_paths.append(anexo.arquivo.path)
                        
                        assunto = f"Resposta ao Documento Protocolo {documento.protocolo} - Procuradoria"
                        
                        # Enviamos para a LISTA completa
                        email_enviado_sucesso = enviar_email_html(
                            assunto=assunto,
                            template_name='emails/resposta_remetente.html',
                            contexto=contexto,
                            destinatarios=destinatarios, # Passa a lista aqui
                            anexos=anexos_paths
                        )
                        
                        if email_enviado_sucesso:
                            logger.info(f"E-mail enviado para {destinatarios} - Doc {documento.protocolo}")
                    else:
                        logger.info(f"Doc {documento.protocolo} finalizado sem e-mails válidos na lista de interessados.")
                        
                except Exception as e:
                    logger.error(f"Erro ao enviar e-mail de resposta do documento {documento.protocolo}: {e}")
                    messages.error(request, f"Documento arquivado, mas falha ao enviar e-mail: {e}")

                if email_enviado_sucesso:
                    messages.success(request, f"Documento {documento.protocolo} arquivado e e-mails enviados aos interessados!")
                else:
                    messages.success(request, f"Documento {documento.protocolo} arquivado com sucesso! (Nenhum e-mail enviado).")
                return redirect('gestao:monitoramento_analises')
            else:
                messages.error(request, "Erro ao arquivar. Verifique se TODOS os registros estão corretos - Descrição Final também é obrigatória.")

    # --- LÓGICA GET (Continua buscando os dados) ---
    anexos_iniciais = documento.anexos.filter(tipo_anexo='INICIAL', ativo=True)
    anexos_resposta = documento.anexos.filter(tipo_anexo='RESPOSTA', ativo=True)
    
    context = {
        'documento': documento,
        'anexos_iniciais': anexos_iniciais,
        'anexos_resposta': anexos_resposta,
        'finalizacao_form': finalizacao_form,
        'anexo_form': anexo_form,
        'pode_arquivar_direto': pode_arquivar_direto, # <-- Passa a permissão para o template
    }

    return render(request, 'gestao/finalizacao_detail.html', context)



@login_required
def busca_view(request):
    # 1. Inicia o formulário com os dados da URL
    form = DocumentoFilterForm(request.GET or None)
    
    # --- OTIMIZAÇÃO DE PERFORMANCE (SELECT E PREFETCH) ---
    # Já iniciamos o queryset trazendo tudo o que a tabela precisa
    queryset = Documento.objects.select_related(
        'tipo_documento', 
        'prioridade', 
    ).prefetch_related(
        'interessados' # <--- Essencial para as badges na tabela
    )

    # 2. Lógica de Permissão (Filtro de visibilidade)
    is_protocolo_chefe = request.user.groups.filter(name='Protocolador-Chefe').exists()
    is_protocolo = request.user.groups.filter(name='Protocolo').exists()
    is_procurador_chefe = request.user.groups.filter(name='Procurador-Chefe').exists()

    # Se não for um dos perfis "mestre", vê apenas os seus processos
    if not (request.user.is_superuser or is_protocolo or is_protocolo_chefe or is_procurador_chefe):
        queryset = queryset.filter(procurador_atribuido=request.user)

    # 3. Aplicação dos Filtros Dinâmicos
    if form.is_valid():
        protocolo = form.cleaned_data.get('protocolo')
        tipo_documento = form.cleaned_data.get('tipo_documento')
        interessados = form.cleaned_data.get('interessados')
        status = form.cleaned_data.get('status')
        data_inicio = form.cleaned_data.get('data_inicio')
        data_fim = form.cleaned_data.get('data_fim')
        
        if protocolo:
            queryset = queryset.filter(protocolo__icontains=protocolo)
        
        # ALTERADO: Agora filtra pela relação ManyToMany de Interessados
        if interessados:
            queryset = queryset.filter(interessados=interessados).distinct()
            
        if status:
            queryset = queryset.filter(status=status)
            
        if data_inicio:
            queryset = queryset.filter(data_recebimento__date__gte=data_inicio)
            
        if data_fim:
            queryset = queryset.filter(data_recebimento__date__lte=data_fim)
        if tipo_documento:
            queryset =queryset.filter(tipo_documento=tipo_documento)

    # 4. Lógica de Ordenação
    ordenar_por = request.GET.get('ordenar_por', 'data_recebimento')
    ordem = request.GET.get('ordem', 'desc')
    prefixo = '-' if ordem == 'desc' else ''
    
    # Adicionamos 'id' como desempate para evitar instabilidade na paginação
    queryset = queryset.order_by(f'{prefixo}{ordenar_por}', f'{prefixo}id')

    # 5. Contexto para o template
    context = {
        'filter_form': form,
        'documentos': queryset,
        'ordenar_por_atual': ordenar_por,
        'ordem_atual': ordem,
    }
    
    # --- INÍCIO DA LÓGICA DE PAGINAÇÃO ---
    itens_por_pagina = 25 # Defina quantos processos quer ver por vez
    paginator = Paginator(queryset, itens_por_pagina)
    
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    # ---------------------------------------

    # Truque de Mestre: Mantendo os filtros na URL da paginação
    # Isso evita que ao clicar na pág 2, o sistema esqueça o filtro de "Interessados"
    query_params = request.GET.copy()
    if 'page' in query_params:
        del query_params['page']
    url_params = query_params.urlencode()

    context = {
        'filter_form': form,
        'documentos': page_obj, # IMPORTANTE: Passamos o objeto da página, não o queryset todo
        'ordenar_por_atual': ordenar_por,
        'ordem_atual': ordem,
        'url_params': url_params, # Para usar nos links de página
    }


    return render(request, 'gestao/busca.html', context)


@login_required
def documento_consulta_view(request, pk):
    documento = get_object_or_404(Documento, pk=pk)
    origem = request.GET.get('origem', 'busca')
    procuradores = User.objects.filter(groups__name='Procuradores').order_by('first_name')

    is_protocolo_chefe = request.user.groups.filter(name='Protocolador-Chefe').exists()
    is_protocolo = request.user.groups.filter(name='Protocolo').exists()
    is_procurador_chefe = request.user.groups.filter(name='Procurador-Chefe').exists()
    is_procurador = request.user.groups.filter(name='Procuradores').exists()
    is_procurador_analista = request.user.groups.filter(name='Procurador-Analista').exists()
    is_procurador_atribuido = (request.user == documento.procurador_atribuido)

    pode_ver = False
    # Quem pode ver TODOS?
    if request.user.is_superuser or is_protocolo or is_protocolo_chefe or is_procurador_chefe:
        pode_ver = True
    # Quem pode ver SÓ OS SEUS?
    elif (is_procurador or is_procurador_analista) and is_procurador_atribuido:
        pode_ver = True

    if not pode_ver:
        raise PermissionDenied("Você não tem permissão para consultar este documento.")


    pode_reativar = is_procurador_chefe or request.user.is_superuser
     # --- FIM DA LÓGICA DE PERMISSÃO ---

    # Busca os anexos
    anexos_iniciais = documento.anexos.filter(tipo_anexo='INICIAL', ativo=True)
    anexos_resposta = documento.anexos.filter(tipo_anexo='RESPOSTA', ativo=True)
    
    # --- ADICIONE A LÓGICA DE CÁLCULO AQUI ---
    tempo_resposta = None # Começa como Nulo
    if documento.data_resposta_procurador and documento.data_atribuicao:
        # Calcula a diferença (resulta em um objeto 'timedelta')
        delta = documento.data_resposta_procurador - documento.data_atribuicao
        tempo_resposta = delta.days # Pega apenas a parte de 'dias'
    # --- FIM DA LÓGICA DE CÁLCULO ---
    
    # Contexto (adiciona a nova variável)
    context = {
        'documento': documento,
        'anexos_iniciais': anexos_iniciais,
        'anexos_resposta': anexos_resposta,
        'tempo_resposta': tempo_resposta, 
        'pode_reativar': pode_reativar,
        'origem': origem,
        'procuradores': procuradores,
    }

    return render(request, 'gestao/documento_consulta.html', context)

@login_required
def devolver_documento_view(request, pk):
    documento = get_object_or_404(Documento, pk=pk)

    is_procurador_analista = request.user.groups.filter(name='Procurador-Analista').exists()
    is_procurador = request.user.groups.filter(name='Procuradores').exists()
    is_procurador_atribuido = (request.user == documento.procurador_atribuido)

    # Só pode devolver se for Procurador OU Analista E for o atribuído
    if not ( (is_procurador or is_procurador_analista) and is_procurador_atribuido ):
         raise PermissionDenied("Apenas o procurador/analista atribuído pode devolver este documento.")

    # Ação só ocorre via POST (quando o formulário for enviado)
    if request.method == 'POST':
        motivo_devolucao = request.POST.get('motivo_devolucao', '').strip() # Pega o motivo do formulário

        if not motivo_devolucao:
            messages.error(request, "O motivo da devolução é obrigatório.")
            # Redireciona de volta para a tela de detalhes se o motivo estiver vazio
            return redirect('gestao:documento_detail', pk=documento.pk)

        # Atualiza os campos do documento
        documento.status = 'Devolvido pela Análise'
        documento.procurador_atribuido = None # Remove a atribuição
        documento.data_atribuicao = None
        documento.data_limite = None
        
        documento.motivo_ultima_devolucao = motivo_devolucao
        
        
        # Poderíamos guardar o motivo em um campo de histórico ou observação, se tivéssemos um
        documento.save(update_fields=['status', 'procurador_atribuido', 'data_atribuicao', 'data_limite', 'motivo_ultima_devolucao']) # Otimização: salva apenas os campos alterados

        messages.success(request, f"Documento {documento.protocolo} devolvido à distribuição com sucesso.")
        # Redireciona para a mesa de trabalho do procurador
        return redirect('gestao:procurador_dashboard')

    # Se a requisição for GET (acesso direto à URL), redireciona para a tela de detalhes
    # pois a devolução só deve ocorrer via formulário POST.
    messages.warning(request, "Ação de devolução inválida.")
    return redirect('gestao:documento_detail', pk=documento.pk)


@login_required
def reativar_documento_view(request, pk):
    documento = get_object_or_404(Documento, pk=pk)

    is_protocolo_chefe = request.user.groups.filter(name='Protocolador-Chefe').exists()
    is_protocolo = request.user.groups.filter(name='Protocolo').exists()
    if not request.user.is_superuser and not is_protocolo_chefe and not is_protocolo:
        raise PermissionDenied("Você não tem permissão para reativar este documento.")

    # Ação só ocorre via POST
    if request.method == 'POST':
        # (Opcional: Poderíamos pegar um 'motivo_reativacao' do POST aqui se quiséssemos)
        motivo_reativacao = request.POST.get('motivo_reativacao', '').strip()
        # Guarda o protocolo para a mensagem antes de limpar
        protocolo_doc = documento.protocolo 

        # Reverte o status e limpa os campos relevantes
        documento.status = 'Aguardando Distribuição'
        documento.procurador_atribuido = None
        documento.data_atribuicao = None
        documento.data_limite = None
        documento.data_resposta_procurador = None
        documento.data_finalizacao = None
        documento.obs_finalizacao = None
        documento.finalizado_por = None
        documento.motivo_ultima_reativacao = motivo_reativacao

        # Salva as alterações
        documento.save() 
        # (Não precisamos especificar update_fields aqui, pois estamos alterando vários campos)

        messages.success(request, f"Documento {protocolo_doc} reativado com sucesso e retornado para 'Aguardando Distribuição'.")
        # Redireciona para a lista de distribuição
        return redirect('gestao:distribuicao')

    # Se a requisição for GET, apenas redireciona de volta para a consulta
    messages.warning(request, "Ação de reativação inválida.")
    return redirect('gestao:documento_consulta', pk=documento.pk)


@login_required
def documento_confirmacao_view(request, pk):
    # Busca o documento que acabou de ser criado
    documento = get_object_or_404(Documento, pk=pk)
    
    # Prepara o contexto para exibir os dados
    context = {
        'documento': documento
    }
    
    # Renderiza a nova página de confirmação
    return render(request, 'gestao/documento_confirmacao.html', context)



@login_required
def cadastrar_remetente_ajax_view(request):
    
    is_protocolo_chefe = request.user.groups.filter(name='Protocolador-Chefe').exists()
    is_protocolo = request.user.groups.filter(name='Protocolo').exists()
    is_cadastrante = request.user.groups.filter(name='Cadastrante').exists()
    if not request.user.is_superuser and not is_protocolo_chefe and not is_protocolo and not is_cadastrante:
         return JsonResponse({'success': False, 'error': 'Permissão negada'}, status=403)
    
    if request.method == 'POST':
        form = RemetenteForm(request.POST)
        if form.is_valid():
            try:
                novo_remetente = form.save()
                # Retorna sucesso e os dados do novo remetente
                return JsonResponse({
                    'success': True,
                    'id': novo_remetente.id,
                    'nome': novo_remetente.nome_razao_social
                })
            except Exception as e:
                # Captura erros gerais (ex: CPF/CNPJ duplicado)
                return JsonResponse({'success': False, 'error': str(e)}, status=400)
        else:
            # Retorna os erros de validação do formulário
            return JsonResponse({'success': False, 'errors': form.errors}, status=400)
    
    # Se não for POST, retorna erro
    return JsonResponse({'success': False, 'error': 'Método inválido'}, status=405)


def remetente_autocomplete_view(request):
    # Pega o termo de busca enviado pelo Select2 via GET (?term=...)
    term = request.GET.get('term', '').strip()
    
    # Define um limite mínimo de caracteres para iniciar a busca (opcional)
    if len(term) < 2: 
        return JsonResponse({'results': []}) # Retorna vazio se termo for muito curto

    # Faz a busca no banco de dados
    # Busca por nome OU por CPF/CNPJ que CONTENHAM o termo
    remetentes = Remetente.objects.filter(
        Q(nome_razao_social__icontains=term) | 
        Q(cpf_cnpj__icontains=term)
    ).order_by('nome_razao_social')[:10] # Limita a 10 resultados para performance

    # Formata os resultados no formato que o Select2 espera: {'results': [{id: ..., text: ...}]}
    results = []
    for remetente in remetentes:
        results.append({
            'id': remetente.id,
            'text': f"{remetente.nome_razao_social} ({remetente.cpf_cnpj})" # Exibe nome e CPF/CNPJ
        })

    return JsonResponse({'results': results})

@login_required
def enviar_lembrete_view(request, pk):
    from .email_utils import enviar_email_html, verificar_prazo_proximo
    
    documento = get_object_or_404(Documento, pk=pk)

    is_protocolo_chefe = request.user.groups.filter(name='Protocolador-Chefe').exists()
    is_protocolo = request.user.groups.filter(name='Protocolo').exists()
    if not request.user.is_superuser and not is_protocolo_chefe and not is_protocolo:
        raise PermissionDenied("Você não tem permissão para enviar lembretes.")

    # Verifica se o documento está realmente 'Em Análise' e tem um procurador com e-mail
    if documento.status != 'Em Análise' or not documento.procurador_atribuido:
        messages.error(request, "Lembrete só pode ser enviado para documentos 'Em Análise' com procurador atribuído.")
        return redirect('gestao:monitoramento_analises')
    email_procurador = documento.procurador_atribuido.email
    if not email_procurador:
         messages.error(request, f"Não é possível enviar lembrete. O procurador {documento.procurador_atribuido.username} não possui e-mail cadastrado.")
         return redirect('gestao:monitoramento_analises')

    # --- LÓGICA POST (ENVIO DO E-MAIL) ---
    if request.method == 'POST':
        mensagem_personalizada = request.POST.get('custom_message', '').strip()

        try:
            # Prepara o contexto para o template
            url_documento = request.build_absolute_uri(f'/documento/{documento.pk}/')
            
            contexto = {
                'procurador_nome': documento.procurador_atribuido.get_full_name() or documento.procurador_atribuido.username,
                'protocolo': documento.protocolo,
                'num_doc_origem': documento.num_doc_origem,
                'remetente': documento.remetente.nome_razao_social,
                'tipo_documento': documento.tipo_documento,
                'prioridade': documento.prioridade,
                'data_limite': documento.data_limite.strftime('%d/%m/%Y') if documento.data_limite else None,
                'prazo_proximo': verificar_prazo_proximo(documento.data_limite, dias=3),
                'mensagem_personalizada': mensagem_personalizada,
                'url_documento': url_documento,
            }
            
            # Prepara anexos
            anexos_iniciais = documento.anexos.filter(tipo_anexo='INICIAL', ativo=True)
            anexos_paths = [anexo.arquivo.path for anexo in anexos_iniciais if os.path.exists(anexo.arquivo.path)]
            
            # Envia o e-mail HTML
            assunto = f"Lembrete: Documento Pendente - Protocolo {documento.protocolo}"
            sucesso = enviar_email_html(
                assunto=assunto,
                template_name='emails/lembrete_procurador.html',
                contexto=contexto,
                destinatarios=[email_procurador],
                anexos=anexos_paths
            )
            
            if sucesso:
                logger.info(f"Lembrete enviado para {email_procurador} - Documento {documento.protocolo}")
                messages.success(request, f"Lembrete enviado com sucesso para {email_procurador} ({len(anexos_paths)} anexo(s) incluído(s)).")
            else:
                messages.error(request, f"Erro ao enviar e-mail de lembrete para o documento {documento.protocolo}.")

        except Exception as e_mail:
            logger.error(f"Erro ao enviar lembrete do documento {documento.protocolo}: {e_mail}")
            messages.error(request, f"Erro ao enviar e-mail de lembrete: {e_mail}")
        
        # Redireciona de volta para a LISTA após enviar
        return redirect('gestao:monitoramento_analises')

    # --- LÓGICA GET (MOSTRAR PÁGINA DE CONFIRMAÇÃO) ---
    else: # request.method == 'GET'
        context = {
            'documento': documento
        }
        # Renderiza o NOVO template de confirmação
        return render(request, 'gestao/lembrete_confirmacao.html', context)
    

@login_required
def confirmacao_lista_view(request):
    # --- LÓGICA DE PERMISSÃO (Mantida - está correta) ---
    is_procurador_analista = request.user.groups.filter(name='Procurador-Analista').exists()
    is_procurador_chefe = request.user.groups.filter(name='Procurador-Chefe').exists()
    
    if not is_procurador_analista and not is_procurador_chefe and not request.user.is_superuser:
        raise PermissionDenied("Você não tem permissão para acessar esta página.")

    # 1. A Lógica Otimizada:
    # Usamos select_related para as chaves estrangeiras e prefetch_related para os interessados
    lista_de_documentos = Documento.objects.filter(
        status='Aguardando Confirmação'
    ).select_related(
        'remetente', 
        'tipo_documento', 
        'prioridade',
        'procurador_atribuido' # Importante para saber quem respondeu
    ).prefetch_related(
        'interessados' # <--- O segredo para a tabela não travar
    ).order_by('data_resposta_procurador')

    # 2. O Contexto
    context = {
        'documentos': lista_de_documentos
    }

    # 3. Renderizar a página
    return render(request, 'gestao/confirmacao_lista.html', context)

@login_required
def confirmacao_detail_view(request, pk):
    documento = get_object_or_404(Documento, pk=pk)
    
    # --- LÓGICA DE PERMISSÃO ---
    # Apenas Procurador-Analista, Procurador-Chefe ou Superusuários podem confirmar
    is_procurador_analista = request.user.groups.filter(name='Procurador-Analista').exists()
    is_procurador_chefe = request.user.groups.filter(name='Procurador-Chefe').exists()
    if not is_procurador_analista and not is_procurador_chefe and not request.user.is_superuser:
        raise PermissionDenied("Você não tem permissão para acessar esta página.")
    # --- FIM DA LÓGICA DE PERMISSÃO ---

    # --- LÓGICA POST (ARQUIVAMENTO FINAL) ---
    if request.method == 'POST':
        # Pega o registro de finalização (que o protocolador já preencheu)
        # O Analista poderia adicionar ao registro, mas por enquanto vamos apenas salvar
        
        # (Opcional: Se quisermos que o analista *também* escreva algo, usaríamos um form)
        # form = FinalizacaoForm(request.POST, instance=documento)
        # if form.is_valid(): 
        #    documento_salvo = form.save(commit=False) ... etc

        # Ação simples: Apenas arquiva
        documento.status = 'Finalizado'
        documento.data_finalizacao = timezone.now()
        documento.finalizado_por = request.user # Agora o 'finalizado_por' é o Analista
        documento.save()

        # --- LÓGICA DE ENVIO DE E-MAIL PARA O REMETENTE ---
        email_enviado_sucesso = False
        try:
            from .email_utils import enviar_email_html
            
            email_remetente = documento.remetente.email
            if email_remetente:
                contexto = {
                    'remetente_nome': documento.remetente.nome_razao_social,
                    'protocolo': documento.protocolo,
                    'num_doc_origem': documento.num_doc_origem,
                    'data_finalizacao': documento.data_finalizacao.strftime('%d/%m/%Y %H:%M') if documento.data_finalizacao else timezone.now().strftime('%d/%m/%Y %H:%M'),
                    'observacoes_finalizacao': documento.obs_finalizacao,
                }
                
                anexos_paths = []
                for anexo in documento.anexos.filter(tipo_anexo__in=['INICIAL', 'RESPOSTA'], ativo=True):
                    if os.path.exists(anexo.arquivo.path):
                        anexos_paths.append(anexo.arquivo.path)
                
                assunto = f"Resposta ao Documento Protocolo {documento.protocolo} - Procuradoria"
                email_enviado_sucesso = enviar_email_html(
                    assunto=assunto,
                    template_name='emails/resposta_remetente.html',
                    contexto=contexto,
                    destinatarios=[email_remetente],
                    anexos=anexos_paths
                )
                
                if email_enviado_sucesso:
                    logger.info(f"E-mail de resposta (confirmação) enviado para {email_remetente} - Documento {documento.protocolo}")
            else:
                logger.info(f"Doc {documento.protocolo} finalizado sem e-mail (remetente sem e-mail).")
        except Exception as e:
            logger.error(f"Erro ao enviar e-mail de resposta (confirmação) do documento {documento.protocolo}: {e}")
            messages.error(request, f"Documento arquivado, mas falha ao enviar e-mail: {e}")
        
        if email_enviado_sucesso:
            messages.success(request, f"Documento {documento.protocolo} confirmado, arquivado e e-mail enviado ao remetente!")
        else:
            messages.success(request, f"Documento {documento.protocolo} confirmado e arquivado com sucesso! (E-mail não enviado).")

        return redirect('gestao:confirmacao_lista') # Volta para a lista de confirmação

    # --- LÓGICA GET (MOSTRAR TELA DE REVISÃO PJe) ---
    else:
        # Busca os anexos para os painéis
        anexos_iniciais = documento.anexos.filter(tipo_anexo='INICIAL', ativo=True)
        anexos_resposta = documento.anexos.filter(tipo_anexo='RESPOSTA', ativo=True)
        
        # Pega as observações que o protocolador deixou
        obs_protocolador = documento.obs_finalizacao

    # Contexto
    context = {
        'documento': documento,
        'anexos_iniciais': anexos_iniciais,
        'anexos_resposta': anexos_resposta,
        'obs_protocolador': obs_protocolador, # Envia as observações para o template
    }
    
    return render(request, 'gestao/confirmacao_detail.html', context)


@login_required
def definir_pin_view(request):
    # Pega o perfil do usuário logado (criado pelos signals)
    profile = request.user.profile
    
    # Lógica POST: Processa o formulário enviado
    if request.method == 'POST':
        form = PinForm(request.POST)
        if form.is_valid():
            # Pega o PIN validado
            novo_pin = form.cleaned_data.get('novo_pin')
            
            # Criptografa (hash) o PIN antes de salvar
            pin_hash = make_password(novo_pin)
            
            # Salva o PIN criptografado no perfil do usuário
            profile.pin_autorizacao = pin_hash
            profile.save()
            
            messages.success(request, "Seu PIN de autorização foi definido/atualizado com sucesso!")
            return redirect('gestao:dashboard') # Redireciona para o Dashboard
    
    # Lógica GET: Mostra o formulário vazio
    else:
        form = PinForm()

    context = {
        'form': form
    }
    return render(request, 'gestao/definir_pin.html', context)

@login_required
def verificar_pin_ajax_view(request):
    if request.method != 'POST':
        # Só permite o método POST
        return JsonResponse({'success': False, 'error': 'Método inválido'}, status=405)

    pin_digitado = request.POST.get('pin_digitado', '').strip()
    
    # 1. Verifica se o usuário tem um PIN definido
    pin_salvo_hash = request.user.profile.pin_autorizacao
    if not pin_salvo_hash:
        return JsonResponse({'success': False, 'error': 'PIN não definido. Por favor, defina seu PIN na página "Definir/Alterar PIN".'}, status=400)

    # 2. Verifica se o PIN digitado tem 4 dígitos (validação rápida)
    if not pin_digitado.isdigit() or len(pin_digitado) != 4:
         return JsonResponse({'success': False, 'error': 'PIN inválido. Deve conter 4 números.'}, status=400)

    # 3. Compara o PIN digitado com o PIN criptografado salvo
    # Usamos check_password, que é a função correta para comparar um texto puro com um hash
    pin_valido = check_password(pin_digitado, pin_salvo_hash)

    if pin_valido:
        return JsonResponse({'success': True})
    else:
        return JsonResponse({'success': False, 'error': 'PIN incorreto.'}, status=400)
    
@login_required
def rejeitar_confirmacao_view(request, pk):
    documento = get_object_or_404(Documento, pk=pk)

    # --- LÓGICA DE PERMISSÃO ---
    # Verifica se o usuário tem permissão para esta ação
    is_procurador_analista = request.user.groups.filter(name='Procurador-Analista').exists()
    is_procurador_chefe = request.user.groups.filter(name='Procurador-Chefe').exists()
    if not is_procurador_analista and not is_procurador_chefe and not request.user.is_superuser:
        raise PermissionDenied("Você não tem permissão para rejeitar este processo.")
    # --- FIM DA LÓGICA DE PERMISSÃO ---

    # Esta ação só pode ser executada via POST (envio de formulário)
    if request.method == 'POST':
        # Pega o motivo da rejeição do formulário
        motivo_rejeicao = request.POST.get('motivo_rejeicao', '').strip()

        # Validação: O motivo é obrigatório
        if not motivo_rejeicao:
            messages.error(request, "O motivo da rejeição é obrigatório para devolver o processo.")
            # Redireciona de volta para a tela de detalhes onde o formulário está
            return redirect('gestao:confirmacao_detail', pk=documento.pk) 

        # 1. Atualiza o documento no banco de dados
        documento.status = 'Rejeitado' # Devolve o status para "Em Análise"
        documento.motivo_rejeicao_analista = motivo_rejeicao # Salva o motivo da rejeição
        documento.obs_finalizacao = None # Limpa a observação do protocolador (pois foi rejeitada)
        documento.save(update_fields=['status', 'motivo_rejeicao_analista', 'obs_finalizacao'])

        # 2. Notifica o PROCURADOR ORIGINAL por e-mail (Bônus)
        try:
            from .email_utils import enviar_email_html
            
            procurador_original = documento.procurador_atribuido
            if procurador_original and procurador_original.email:
                url_documento = request.build_absolute_uri(f'/documento/{documento.pk}/')
                
                contexto = {
                    'procurador_nome': procurador_original.get_full_name() or procurador_original.username,
                    'protocolo': documento.protocolo,
                    'num_doc_origem': documento.num_doc_origem,
                    'remetente': documento.remetente.nome_razao_social,
                    'motivo_devolucao': motivo_rejeicao,
                    'url_documento': url_documento,
                }
                
                assunto = f"Revisão Solicitada: Processo {documento.protocolo} Devolvido"
                sucesso = enviar_email_html(
                    assunto=assunto,
                    template_name='emails/documento_devolvido.html',
                    contexto=contexto,
                    destinatarios=[procurador_original.email]
                )
                
                if sucesso:
                    logger.info(f"E-mail de devolução enviado para {procurador_original.email} - Documento {documento.protocolo}")
            else:
                 messages.warning(request, "Documento devolvido, mas não foi possível notificar o procurador original (e-mail ausente).")

        except Exception as e:
            logger.error(f"Erro ao enviar e-mail de rejeição do documento {documento.protocolo}: {e}")
            messages.warning(request, "Documento devolvido, mas falha ao notificar o procurador por e-mail.")
        
        messages.success(request, f"Documento {documento.protocolo} rejeitado e devolvido para 'Em Análise'.")
        # Redireciona de volta para a lista de confirmação (de onde o documento sumirá)
        return redirect('gestao:confirmacao_lista')

    # Se alguém tentar acessar esta URL via GET, apenas redireciona
    messages.error(request, "Ação inválida.")
    return redirect('gestao:confirmacao_lista')

@login_required
def excluir_anexo_view(request, pk, anexo_id):
    # Busca o anexo ou retorna erro 404
    anexo = get_object_or_404(Anexo, pk=anexo_id)
    documento = anexo.documento
    
    # Verifica se o anexo realmente pertence ao documento
    if documento.pk != pk:
        messages.error(request, "Anexo não pertence a este documento.")
        return redirect('gestao:documento_detail', pk=documento.pk)

    # --- VERIFICAÇÃO DE PERMISSÕES (AS REGRAS QUE DEFINIMOS) ---
    
    # 1. Quem pode? (Dono do anexo OU Protocolador-Chefe)
    is_dono = (request.user == anexo.usuario_upload)
    is_protocolo_chefe = request.user.groups.filter(name='Protocolador-Chefe').exists()
    
    if not is_dono and not is_protocolo_chefe and not request.user.is_superuser:
        messages.error(request, "Você não tem permissão para excluir este anexo.")
        return redirect('gestao:documento_detail', pk=documento.pk)

    # 2. O que pode? (Apenas tipo RESPOSTA)
    if anexo.tipo_anexo != 'RESPOSTA':
        messages.error(request, "Não é permitido excluir documentos originais.")
        return redirect('gestao:documento_detail', pk=documento.pk)

    # 3. Quando pode? (Apenas se o status do documento permitir edição)
    # Adicione aqui os status que você criou, como 'Rejeitado' ou 'Devolvido pela Análise'
    status_permitidos = ['Em Análise', 'Devolvido pela Análise', 'Rejeitado', 'Análise Concluída'] 
    if documento.status not in status_permitidos:
        messages.error(request, f"Não é possível excluir anexos de um documento com status '{documento.status}'.")
        return redirect('gestao:documento_detail', pk=documento.pk)

    # --- FIM DAS VERIFICAÇÕES ---

    # Executa a "Exclusão Lógica"
    if request.method == 'POST':
        anexo.ativo = False
        anexo.save()
        messages.success(request, "Anexo removido com sucesso.")
    else:
        # Se tentar acessar via GET, avisa que precisa ser POST (segurança)
        messages.warning(request, "Ação inválida. Use o botão de excluir.")

    # Redireciona de volta para a tela de onde o usuário veio (provavelmente a de análise)
    # Usamos request.META.get('HTTP_REFERER') para tentar voltar para a página anterior inteligente,
    # ou fixamos uma página padrão se não conseguir.
    return redirect(request.META.get('HTTP_REFERER') or 'gestao:dashboard')

@login_required
def documento_update_view(request, pk):
    documento = get_object_or_404(Documento, pk=pk)
    origem = request.GET.get('origem') or request.POST.get('origem') or 'busca'
    voltar_para = request.GET.get('voltar_para') or request.POST.get('voltar_para') or 'consulta'

    # REGRA 1: Imutabilidade de processos finalizados
    if documento.status == 'Finalizado':
        messages.error(request, "Processos finalizados não podem ser alterados.")
        url_destino = reverse('gestao:documento_consulta', kwargs={'pk': pk})
        return redirect(f"{url_destino}?origem={origem}")

    # REGRA 2: Apenas Chefias e Admins
    is_chefia = request.user.groups.filter(name__in=['Protocolador-Chefe', 'Procurador-Chefe']).exists()
    if not (request.user.is_superuser or is_chefia):
        raise PermissionDenied("Acesso restrito à chefia.")

    if request.method == 'POST':
        form = DocumentoUpdateForm(request.POST, instance=documento)
        formset = AnexoUpdateFormSet(request.POST, request.FILES, instance=documento)

        if form.is_valid() and formset.is_valid():
            
            # --- 1. LOG DE ALTERAÇÕES (CAMPOS DO DOCUMENTO) ---
            # Fazemos antes de salvar para comparar o valor antigo com o novo
            for campo in form.changed_data:
                valor_antigo = getattr(documento, campo)
                valor_novo = form.cleaned_data[campo]
                
                HistoricoEdicao.objects.create(
                    documento=documento,
                    usuario=request.user,
                    campo_alterado=campo.replace('_', ' ').capitalize(),
                    valor_antigo=str(valor_antigo),
                    valor_novo=str(valor_novo)
                )

            # --- 2. SALVAR DOCUMENTO PRINCIPAL ---
            # Isso já salva os campos e os Interessados (M2M) automaticamente
            form.save()

            # --- 3. SALVAR NOVOS ANEXOS (OU EDITADOS) ---
            # Usamos commit=False para injetar o usuário logado e evitar o IntegrityError
            anexos = formset.save(commit=False)
            for anexo in anexos:
                anexo.usuario_upload = request.user  # <--- Resolve o erro de Column cannot be null
                anexo.save()

            # --- 4. LOG E INATIVAÇÃO DE ANEXOS ---
            # Tratamos os anexos que o usuário marcou para remover
            for anexo_para_inativar in formset.deleted_objects:
                # Registra no log antes de mudar
                HistoricoEdicao.objects.create(
                    documento=documento,
                    usuario=request.user,
                    campo_alterado="Anexo",
                    valor_antigo=f"Arquivo: {anexo_para_inativar.arquivo.name}",
                    valor_novo="Inativado pelo usuário"
                )
                # Em vez de deletar do banco, apenas inativamos
                anexo_para_inativar.ativo = False
                anexo_para_inativar.save()

            messages.success(request, f"Processo {documento.protocolo} atualizado com sucesso.")
            # DECISÃO DE REDIRECIONAMENTO
            if voltar_para == 'finalizacao':
                url_nome = 'gestao:finalizacao_detail' # Ajuste para o nome real da sua rota
            else:
                url_nome = 'gestao:documento_consulta'

            url_destino = reverse(url_nome, kwargs={'pk': pk})
            return redirect(f"{url_destino}?origem={origem}")
    else:
        form = DocumentoUpdateForm(instance=documento)
        formset = AnexoUpdateFormSet(instance=documento)

    return render(request, 'gestao/documento_update.html', {
        'form': form,
        'formset': formset,
        'documento': documento,
        'anexos_iniciais': documento.anexos.filter(ativo=True),
        'origem': origem,
        'voltar_para': voltar_para,
    })

@login_required
def diligencias_pendentes_view(request):
    # Apenas Chefias e Admins acessam esta central de controle
    is_chefia = request.user.groups.filter(name__in=['Protocolador-Chefe', 'Procurador-Chefe']).exists()
    if not (request.user.is_superuser or is_chefia):
        raise PermissionDenied("Acesso restrito à gestão de diligências.")

    # Filtra conforme solicitado: Pendentes (novas) e Enviadas (aguardando remetente)
    solicitacoes = SolicitacaoDocumento.objects.filter(
        status__in=['Pendente', 'Enviada']
    ).select_related('documento', 'procurador').order_by('-data_solicitacao')

    return render(request, 'gestao/diligencias_pendentes.html', {
        'solicitacoes': solicitacoes,
        'total_pendentes': solicitacoes.filter(status='Pendente').count()
    })

@login_required
def decidir_diligencia_view(request, diligencia_id):
    diligencia = get_object_or_404(SolicitacaoDocumento, id=diligencia_id)
    documento = diligencia.documento
    
    if request.method == 'POST':
        acao = request.POST.get('acao_gestao')
        
        # Atribuímos o usuário e a data antes de entrar nos IFs
        diligencia.analisado_por = request.user
        diligencia.data_resposta = timezone.now()

        if acao == 'enviar_email':
            texto_email = request.POST.get('texto_decisao')
            email_destino = request.POST.get('email_destino')
            
            # 1. Prepara o contexto para o template
            contexto = {
                'remetente_nome': documento.remetente.nome_razao_social,
                'protocolo': documento.protocolo,
                'texto_solicitacao': texto_email,
                'ano_atual': timezone.now().year,
            }

            # 2. Renderiza o HTML
            html_content = render_to_string('emails/solicitacao_diligencia_email.html', contexto)
            text_content = strip_tags(html_content) # Versão em texto puro (segurança)

            # 3. Configura o e-mail
            assunto = f"PGM - Solicitação de Documentação: {documento.protocolo}"
            email = EmailMultiAlternatives(
                assunto,
                text_content,
                settings.DEFAULT_FROM_EMAIL,
                [email_destino]
            )
            email.attach_alternative(html_content, "text/html")

            try:
                email.send()
                diligencia.status = 'Enviada'
                messages.success(request, f"E-mail enviado com sucesso!")
            except Exception as e:
                messages.error(request, f"Erro ao disparar e-mail: {str(e)}")

        elif acao == 'negar':
            # CORREÇÃO: Pega do campo 'texto_decisao_negar' definido no HTML
            justificativa = request.POST.get('texto_decisao_negar')
            diligencia.status = 'Rejeitada'
            diligencia.observacao_chefia = justificativa
            documento.status = 'Em Análise'
            documento.save()
            messages.warning(request, "Solicitação negada e processo devolvido.")

        elif acao == 'concluir_manual':
            diligencia.status = 'Atendida'
            # CORREÇÃO: Pega do campo 'texto_decisao_sanear'
            diligencia.observacao_chefia = request.POST.get('texto_decisao_sanear')
            
            # PROCESSAMENTO DE ARQUIVOS (Agora com enctype funcionará)
            arquivos = request.FILES.getlist('arquivos_saneamento')
            for f in arquivos:
                Anexo.objects.create(
                    documento=documento,
                    arquivo=f,
                    tipo_anexo='INICIAL',
                    usuario_upload=request.user,
                    descricao=f"Anexo via Saneamento - Diligência #{diligencia.id}"
                )

            documento.status = 'Em Análise'
            documento.save()
            messages.success(request, "Diligência concluída com sucesso!")

        diligencia.save()

        proxima = request.POST.get('proxima_url')
        return redirect(proxima if proxima else 'gestao:diligencias')
            
    return redirect('gestao:diligencias')

@login_required
def atribuir_procurador_direto_view(request, pk):
    documento = get_object_or_404(Documento, pk=pk)
    
    if request.method == 'POST':
        procurador_id = request.POST.get('procurador_id')
        
        try:
            procurador = User.objects.get(id=procurador_id)
            
            # 1. ATUALIZAÇÃO DO BANCO DE DADOS
            documento.procurador_atribuido = procurador
            documento.status = 'Em Análise'
            documento.data_atribuicao = timezone.now()
            documento.motivo_ultima_devolucao = None
            documento.save() # Dispara o cálculo da data limite no Model

            # 2. PREPARAÇÃO DO E-MAIL (Lógica replicada)
            try:
                url_documento = request.build_absolute_uri(f'/documento/{documento.pk}/')
                
                contexto = {
                    'procurador_nome': procurador.get_full_name() or procurador.username,
                    'protocolo': documento.protocolo,
                    'num_doc_origem': documento.num_doc_origem,
                    'remetente': documento.remetente.nome_razao_social,
                    'tipo_documento': documento.tipo_documento.descricao,
                    'prioridade': documento.prioridade.descricao,
                    'data_limite': documento.data_limite.strftime('%d/%m/%Y') if documento.data_limite else None,
                    'observacoes': documento.observacoes_protocolo,
                    'url_documento': url_documento,
                    'ano_atual': timezone.now().year,
                }
                
                # Coleta caminhos físicos dos anexos iniciais para anexar ao e-mail
                anexos_iniciais = documento.anexos.filter(tipo_anexo='INICIAL', ativo=True)
                anexos_paths = [
                    anexo.arquivo.path for anexo in anexos_iniciais 
                    if os.path.exists(anexo.arquivo.path)
                ]
                
                assunto = f"Novo Documento para Análise - Protocolo {documento.protocolo}"
                
                # Disparo do e-mail usando sua utilitária
                sucesso_email = enviar_email_html(
                    assunto=assunto,
                    template_name='emails/documento_distribuido.html',
                    contexto=contexto,
                    destinatarios=[procurador.email],
                    anexos=anexos_paths
                )
                
                if sucesso_email:
                    messages.success(request, f"Processo atribuído e e-mail enviado para {procurador.email}.")
                else:
                    messages.warning(request, "Processo atribuído, mas houve uma falha ao enviar o e-mail de notificação.")

            except Exception as e_mail:
                messages.error(request, f"Erro técnico ao processar e-mail: {e_mail}")

        except User.DoesNotExist:
            messages.error(request, 'Procurador selecionado inválido.')
            
    return redirect('gestao:documento_consulta', pk=pk)