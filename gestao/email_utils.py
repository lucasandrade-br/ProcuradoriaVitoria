"""
Utilitários para envio de e-mails HTML com templates
"""
import os
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags
from datetime import datetime, timedelta


def enviar_email_html(assunto, template_name, contexto, destinatarios, anexos=None, logo_path=None):
    """
    Envia um e-mail HTML usando um template Django
    
    Args:
        assunto (str): Assunto do e-mail
        template_name (str): Nome do template (ex: 'emails/lembrete_procurador.html')
        contexto (dict): Dicionário com variáveis para o template
        destinatarios (list): Lista de e-mails destinatários
        anexos (list): Lista de caminhos de arquivos para anexar (opcional)
        logo_path (str): Caminho para o arquivo de logo (opcional)
    
    Returns:
        bool: True se enviado com sucesso, False caso contrário
    """
    try:
        # Adiciona o ano atual ao contexto
        contexto['ano_atual'] = datetime.now().year
        
        # Renderiza o template HTML
        html_content = render_to_string(template_name, contexto)
        
        # Cria uma versão texto puro (fallback)
        text_content = strip_tags(html_content)
        
        # Cria o e-mail
        email = EmailMultiAlternatives(
            subject=assunto,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=destinatarios
        )
        
        # Adiciona a versão HTML
        email.attach_alternative(html_content, "text/html")
        
        # Adiciona a logo como imagem inline
        if logo_path is None:
            logo_path = os.path.join(settings.BASE_DIR, 'gestao', 'static', 'gestao', 'imagens', 'logo.png')
        
        if os.path.exists(logo_path):
            with open(logo_path, 'rb') as logo_file:
                email.attach('logo.png', logo_file.read(), 'image/png')
                # Define o Content-ID para referência no HTML
                email.mixed_subtype = 'related'
                for attachment in email.attachments:
                    if attachment[0] == 'logo.png':
                        attachment_data = attachment
                        email.attachments.remove(attachment)
                        from email.mime.image import MIMEImage
                        img = MIMEImage(attachment_data[1])
                        img.add_header('Content-ID', '<logo>')
                        img.add_header('Content-Disposition', 'inline', filename='logo.png')
                        if not hasattr(email, 'attach'):
                            email.attach = lambda x: email.attachments.append(x)
                        # Anexa inline
        
        # Adiciona anexos de documentos
        if anexos:
            for anexo_path in anexos:
                if os.path.exists(anexo_path):
                    email.attach_file(anexo_path)
        
        # Envia o e-mail
        email.send()
        return True
        
    except Exception as e:
        print(f"Erro ao enviar e-mail: {e}")
        return False


def verificar_prazo_proximo(data_limite, dias=3):
    """
    Verifica se uma data limite está próxima (dentro de X dias)
    
    Args:
        data_limite: Data limite a verificar
        dias (int): Número de dias para considerar "próximo"
    
    Returns:
        bool: True se o prazo está próximo
    """
    if not data_limite:
        return False
    
    hoje = datetime.now().date()
    data_alerta = hoje + timedelta(days=dias)
    
    return hoje <= data_limite <= data_alerta
