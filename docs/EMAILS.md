# 📧 Sistema de E-mails HTML - SGDP

## Visão Geral

O sistema agora envia e-mails HTML profissionais e estilizados para todas as notificações, incluindo:

- ✅ **Lembrete ao Procurador** - Lembrete de documento pendente
- ✅ **Documento Distribuído** - Notificação de novo documento atribuído
- ✅ **Resposta ao Remetente** - Notificação de análise concluída
- ✅ **Documento Devolvido** - Notificação de revisão solicitada

## Características dos E-mails

### Design
- 🎨 Layout profissional com cores institucionais (#04357b)
- 🖼️ Logo da Procuradoria no cabeçalho
- 📱 Responsivo (funciona em desktop e mobile)
- 🔘 Botões de call-to-action para acessar o sistema
- 📦 Boxes coloridos para destacar informações importantes

### Funcionalidades
- **HTML + Texto**: Versão HTML para clientes modernos e fallback em texto puro
- **Imagens Inline**: Logo embutida no e-mail (não depende de links externos)
- **Anexos**: Suporte completo para anexar documentos
- **Alertas Visuais**: Destaque especial para prazos próximos ou vencidos

## Estrutura de Arquivos

```
templates/
  └── emails/
      ├── base_email.html              # Template base (header/footer)
      ├── lembrete_procurador.html     # E-mail de lembrete
      ├── documento_distribuido.html   # E-mail de distribuição
      ├── resposta_remetente.html      # E-mail de resposta
      └── documento_devolvido.html     # E-mail de devolução

gestao/
  └── email_utils.py                   # Funções auxiliares para envio
```

## Como Usar

### Enviar E-mail HTML

```python
from gestao.email_utils import enviar_email_html

# Prepara o contexto
contexto = {
    'procurador_nome': 'Dr. João Silva',
    'protocolo': '2024-001',
    'remetente': 'Fulano de Tal',
    'data_limite': '20/12/2024',
    'url_documento': 'http://sistema.com/documento/123/',
    # ... outras variáveis
}

# Envia o e-mail
sucesso = enviar_email_html(
    assunto='Lembrete: Documento Pendente',
    template_name='emails/lembrete_procurador.html',
    contexto=contexto,
    destinatarios=['procurador@email.com'],
    anexos=['/path/to/documento.pdf']  # Opcional
)
```

### Criar Novo Template de E-mail

1. Crie um novo arquivo HTML em `templates/emails/`
2. Estenda o template base:

```html
{% extends "emails/base_email.html" %}

{% block title %}Título do E-mail{% endblock %}

{% block content %}
<p class="greeting">Prezado(a) <strong>{{ nome }}</strong>,</p>

<p>Conteúdo do seu e-mail aqui...</p>

<div class="document-box">
    <h2>📄 Informações</h2>
    <div class="info-row">
        <span class="info-label">Campo:</span>
        <span class="info-value">{{ valor }}</span>
    </div>
</div>

<center>
    <a href="{{ url }}" class="button">
        🔍 Botão de Ação
    </a>
</center>
{% endblock %}
```

## Classes CSS Disponíveis

### Boxes de Destaque

```html
<!-- Informação neutra -->
<div class="document-box">Conteúdo</div>

<!-- Alerta (amarelo) -->
<div class="alert-box">⚠️ Atenção!</div>

<!-- Perigo (vermelho) -->
<div class="danger-box">🚨 Urgente!</div>

<!-- Sucesso (verde) -->
<div class="success-box">✅ Concluído!</div>
```

### Elementos

```html
<!-- Botão -->
<a href="..." class="button">Texto do Botão</a>

<!-- Linha de informação -->
<div class="info-row">
    <span class="info-label">Label:</span>
    <span class="info-value">Valor</span>
</div>

<!-- Divisor -->
<div class="divider"></div>
```

## Variáveis de Contexto Comuns

Todas as templates recebem automaticamente:
- `ano_atual` - Ano corrente para o rodapé

Variáveis específicas por template:

### lembrete_procurador.html
- `procurador_nome`
- `protocolo`
- `num_doc_origem`
- `remetente`
- `tipo_documento`
- `prioridade`
- `data_limite`
- `prazo_proximo` (boolean)
- `mensagem_personalizada`
- `url_documento`

### documento_distribuido.html
- `procurador_nome`
- `protocolo`
- `num_doc_origem`
- `remetente`
- `tipo_documento`
- `prioridade`
- `data_limite`
- `observacoes`
- `url_documento`

### resposta_remetente.html
- `remetente_nome`
- `protocolo`
- `num_doc_origem`
- `data_finalizacao`
- `observacoes_finalizacao`

### documento_devolvido.html
- `procurador_nome`
- `protocolo`
- `num_doc_origem`
- `remetente`
- `motivo_devolucao`
- `url_documento`

## Personalização

### Alterar Cores
Edite o arquivo `base_email.html` e modifique as variáveis CSS:

```css
.header {
    background-color: #04357b;  /* Cor principal */
}

.button {
    background-color: #04357b;  /* Cor do botão */
}
```

### Trocar Logo
Substitua o arquivo:
```
gestao/static/gestao/imagens/logo.png
```

### Modificar Rodapé
Edite a seção `footer` no `base_email.html`

## Compatibilidade

Os e-mails foram testados e funcionam em:
- ✅ Gmail (Web e App)
- ✅ Outlook (Desktop e Web)
- ✅ Apple Mail
- ✅ Yahoo Mail
- ✅ Thunderbird
- ✅ Clientes mobile (iOS e Android)

## Solução de Problemas

### E-mail chega sem formatação
- Alguns clientes podem bloquear HTML. A versão texto puro será exibida automaticamente.

### Logo não aparece
- Verifique se o arquivo existe em: `gestao/static/gestao/imagens/logo.png`
- Verifique as permissões do arquivo

### Botões não funcionam
- Certifique-se de que a URL do sistema está configurada corretamente
- Use URLs absolutas (http://...) no contexto

## Logs

Todos os envios são registrados em:
```
logs/sgdp.log
```

Procure por:
```
INFO gestao Lembrete enviado para email@exemplo.com - Documento 2024-001
```

---

**Desenvolvido com ❤️ para a Procuradoria Municipal**
