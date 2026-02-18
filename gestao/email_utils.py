"""
Utilitários para envio de e-mails HTML com templates
"""
import os
from urllib.parse import urljoin
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags
from datetime import datetime, timedelta


def enviar_email_html(assunto, template_name, contexto, destinatarios, anexos=None, logo_path=None):
    try:
        contexto['ano_atual'] = datetime.now().year
        html_content = render_to_string(template_name, contexto)
        text_content = strip_tags(html_content)
        
        email = EmailMultiAlternatives(
            subject=assunto,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=destinatarios
        )
        email.attach_alternative(html_content, "text/html")
        email.mixed_subtype = 'related'

        # 2. Tratamento de Anexos (Compatível com Cloud Storage e Local)
        if anexos:
            for anexo in anexos:
                # Se for um objeto de arquivo do Django (FieldFile/File)
                if hasattr(anexo, 'open'):
                    with anexo.open('rb') as f:
                        # Pega o nome do arquivo e o conteúdo binário
                        email.attach(os.path.basename(anexo.name), f.read())
                
                # Se for um caminho string (tentativa de arquivo local)
                elif isinstance(anexo, str) and os.path.exists(anexo):
                    email.attach_file(anexo)
                
                else:
                    print(f"Aviso: Anexo {anexo} não pôde ser processado.")

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


def build_absolute_system_url(path, request=None):
    """Retorna uma URL absoluta para o domínio configurado."""
    base_url = getattr(settings, 'SITE_BASE_URL', '').strip()
    if base_url:
        normalized_base = base_url if base_url.endswith('/') else f"{base_url}/"
        return urljoin(normalized_base, path.lstrip('/'))
    if request is not None:
        return request.build_absolute_uri(path)
    return path
