import os
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth.models import User
from gestao.models import Documento
from gestao.email_utils import enviar_email_html

class Command(BaseCommand):
    help = 'Envia relatórios de atrasos para Procuradores e Chefia'

    def handle(self, *args, **options):
        hoje = timezone.localdate()
        ano_atual = hoje.year
        
        processos_atrasados = Documento.objects.filter(
            data_limite__lt=hoje,
            data_finalizacao__isnull=True,
            status__in=['Em Análise', 'Em Diligência']
        ).select_related('procurador_atribuido')

        if not processos_atrasados.exists():
            return

        emails_chefes = list(User.objects.filter(groups__name='Procurador-Chefe').values_list('email', flat=True))
        
        # Estrutura principal agrupada
        agrupamento_atrasos = {}

        for doc in processos_atrasados:
            dias_atraso = (hoje - doc.data_limite).days
            proc = doc.procurador_atribuido
            proc_id = proc.id
            nome_proc = proc.get_full_name() or proc.username
            
            if proc_id not in agrupamento_atrasos:
                agrupamento_atrasos[proc_id] = {
                    'nome': nome_proc,
                    'email': proc.email,
                    'processos': [],
                    'total_processos': 0
                }
            
            agrupamento_atrasos[proc_id]['processos'].append({
                'protocolo': doc.protocolo,
                'data_limite': doc.data_limite,
                'dias_atraso': dias_atraso,
            })
            agrupamento_atrasos[proc_id]['total_processos'] += 1

        # 1. Enviar e-mails individuais (Procuradores)
        for p_id, p_data in agrupamento_atrasos.items():
            if p_data['email']:
                enviar_email_html(
                    assunto=f"ALERTA: Seus Processos Fora do Prazo",
                    template_name='emails/atraso_procurador.html',
                    contexto={'nome': p_data['nome'], 'processos': p_data['processos'], 'ano_atual': ano_atual, 'hoje': hoje},
                    destinatarios=[p_data['email']]
                )

        # 2. Enviar e-mail para Chefia (Passando o agrupamento completo)
        if emails_chefes:
            enviar_email_html(
                assunto="RELATÓRIO DE GESTÃO: Processos Fora do Prazo na Procuradoria",
                template_name='emails/atraso_chefia.html',
                contexto={
                    'agrupamento': agrupamento_atrasos.values(), # Enviamos os grupos
                    'total_geral': len(processos_atrasados),
                    'hoje': hoje,
                    'ano_atual': ano_atual
                },
                destinatarios=emails_chefes
            )