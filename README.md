# SGDP - Sistema de Gestão de Documentos da Procuradoria

Sistema web desenvolvido em Django para gerenciar o fluxo de trabalho de documentos jurídicos em uma procuradoria municipal.

## 📋 Descrição do Sistema

O SGDP (Sistema de Gestão de Documentos da Procuradoria) é uma aplicação web que automatiza e organiza o processo de tramitação de documentos jurídicos, desde o protocolo inicial até a finalização, incluindo:

- Cadastro e protocolo de documentos
- Distribuição automática ou manual para procuradores
- Análise e emissão de pareceres
- Controle de prazos e prioridades
- Gestão de anexos (documentos recebidos e pareceres)
- Sistema de notificações e lembretes por e-mail
- Controle de acesso por perfis de usuário
- Auditoria de ações realizadas

## 🚀 Funcionalidades Principais

### Para Protocoladores
- Cadastro de novos documentos
- Upload de anexos
- Distribuição de processos para procuradores
- Monitoramento do andamento das análises
- Envio de lembretes

### Para Procuradores
- Visualização de processos atribuídos
- Anexação de pareceres e respostas
- Devolução de processos para redistribuição
- Finalização de análises
- Dashboard com destaque para prazos

### Para Analistas/Chefes
- Confirmação ou rejeição de finalizações
- Monitoramento geral do sistema
- Gestão de usuários (admin)

## 🛠️ Tecnologias Utilizadas

- **Backend:** Python 3.11 + Django 5.2.7
- **Banco de Dados:** MySQL
- **Frontend:** HTML5, CSS3, Bootstrap 5, JavaScript
- **Autenticação:** Sistema de usuários e grupos do Django
- **E-mail:** SMTP (Gmail)

## 📦 Requisitos do Sistema

### Softwares Necessários
- Python 3.11 ou superior
- MySQL 5.7 ou superior
- MySQL Workbench (opcional, para gerenciamento visual)
- Git (para controle de versão)

### Bibliotecas Python (instaladas via pip)
- Django 5.2.7
- django-environ (gerenciamento de variáveis de ambiente)
- mysqlclient (driver MySQL para Python)
- Outras dependências listadas em `requirements.txt`

## 🔧 Instalação e Configuração

### 1. Clone o Repositório
```bash
git clone <url-do-repositorio>
cd sgdp
```

### 2. Crie o Ambiente Virtual
```bash
python -m venv venv
```

### 3. Ative o Ambiente Virtual
**Windows:**
```bash
venv\Scripts\activate
```

**Linux/Mac:**
```bash
source venv/bin/activate
```

### 4. Instale as Dependências
```bash
pip install -r requirements.txt
```

### 5. Configure as Variáveis de Ambiente

Copie o arquivo de exemplo e edite com suas credenciais:
```bash
copy .env.example .env
```

Edite o arquivo `.env` e preencha:
```env
SECRET_KEY=sua-chave-secreta-aqui
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

DB_ENGINE=django.db.backends.mysql
DB_NAME=Procuradoria
DB_USER=root
DB_PASSWORD=sua-senha-mysql
DB_HOST=127.0.0.1
DB_PORT=3306

EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=seu-email@gmail.com
EMAIL_HOST_PASSWORD=sua-senha-de-app
```

**Dica:** Para gerar uma nova SECRET_KEY:
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 6. Crie o Banco de Dados

No MySQL (via MySQL Workbench ou terminal):
```sql
CREATE DATABASE Procuradoria CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 7. Execute as Migrações
```bash
python manage.py migrate
```

### 8. Crie um Superusuário
```bash
python manage.py createsuperuser
```

### 9. Crie os Grupos de Usuários

Acesse o painel admin (`http://127.0.0.1:8000/admin/`) e crie os seguintes grupos:
- Protocolo
- Protocolador-Chefe
- Procuradores
- Procurador-Chefe
- Procurador-Analista
- Cadastrante

### 10. Inicie o Servidor

**Modo Simples:**
Dê um duplo clique no arquivo `run_server.bat`

**Ou via terminal:**
```bash
python manage.py runserver
```

Acesse: `http://127.0.0.1:8000`

## 📂 Estrutura do Projeto

```
sgdp/
│
├── config/                 # Configurações do Django
│   ├── settings.py         # Configurações principais
│   ├── urls.py            # URLs do projeto
│   └── wsgi.py            # WSGI para deploy
│
├── gestao/                # Aplicação principal
│   ├── models.py          # Modelos (Documento, Anexo, etc.)
│   ├── views.py           # Views e lógica de negócio
│   ├── forms.py           # Formulários Django
│   ├── urls.py            # URLs da aplicação
│   ├── admin.py           # Configuração do Django Admin
│   └── migrations/        # Migrações do banco de dados
│
├── templates/             # Templates HTML
│   └── gestao/            # Templates da aplicação
│       ├── base.html      # Template base
│       ├── dashboard.html
│       └── ...
│
├── media/                 # Arquivos enviados pelos usuários
│   └── anexos/            # Anexos dos documentos
│
├── logs/                  # Logs da aplicação
├── backups/               # Backups do banco de dados
├── venv/                  # Ambiente virtual (não versionado)
│
├── .env                   # Variáveis de ambiente (não versionado)
├── .env.example           # Exemplo de configuração
├── .gitignore             # Arquivos ignorados pelo Git
├── manage.py              # Script de gerenciamento Django
├── requirements.txt       # Dependências Python
├── run_server.bat         # Script para iniciar o servidor
├── backup_database.bat    # Script para backup do BD
└── README.md              # Este arquivo
```

## 🔒 Segurança

### Variáveis de Ambiente
Todas as informações sensíveis (SECRET_KEY, senhas, etc.) são gerenciadas via arquivo `.env`, que **nunca deve ser commitado** no Git.

### Grupos e Permissões
O sistema utiliza o sistema de grupos do Django para controlar o acesso às funcionalidades. Certifique-se de atribuir os usuários aos grupos corretos.

### Backup
Execute regularmente o script `backup_database.bat` para fazer backup do banco de dados. Os backups são salvos na pasta `backups/` e mantidos por 30 dias.

**Para fazer backup manual:**
```bash
backup_database.bat
```

## 📊 Logs e Auditoria

O sistema registra automaticamente:
- Ações importantes realizadas pelos usuários
- Erros e exceções
- Avisos do sistema

Os logs são salvos em `logs/sgdp.log` e são automaticamente rotacionados quando atingem 10MB.

## 🧪 Qualidade de Código

O projeto utiliza ferramentas de qualidade de código:
- **Black:** Formatação automática de código
- **isort:** Organização de imports
- **Flake8:** Linting e verificação de estilo
- **pre-commit:** Hooks para executar verificações antes do commit

### Instalando os hooks de pre-commit:
```bash
pre-commit install
```

### Formatando o código manualmente:
```bash
black .
isort .
flake8
```

## 📝 Fluxo de Trabalho do Sistema

1. **Protocolo:** Cadastrante/Protocolador registra o documento no sistema
2. **Distribuição:** Protocolador-Chefe distribui para um procurador
3. **Análise:** Procurador recebe, analisa e anexa o parecer
4. **Finalização:** Procurador finaliza a análise (com PIN)
5. **Confirmação:** Analista/Chefe confirma ou rejeita a finalização
6. **Arquivo:** Documento finalizado fica disponível para consulta

## 🆘 Solução de Problemas

### Erro: "No module named 'MySQLdb'"
Instale o driver MySQL:
```bash
pip install mysqlclient
```

### Erro: "Can't connect to MySQL server"
Verifique se:
- O MySQL está rodando
- As credenciais no `.env` estão corretas
- O banco de dados `Procuradoria` foi criado

### Erro: "ImproperlyConfigured: SECRET_KEY"
Certifique-se de que o arquivo `.env` existe e contém a SECRET_KEY.

## 👥 Perfis de Usuário

| Grupo | Permissões |
|-------|-----------|
| **Protocolo** | Cadastrar documentos, distribuir processos |
| **Protocolador-Chefe** | Todas do Protocolo + monitoramento completo |
| **Procuradores** | Visualizar processos atribuídos, anexar pareceres |
| **Procurador-Chefe** | Todas dos Procuradores + confirmar finalizações |
| **Procurador-Analista** | Todas dos Procuradores + confirmar finalizações |
| **Cadastrante** | Apenas cadastrar documentos |

## 📞 Suporte e Contato

Para dúvidas, problemas ou sugestões, entre em contato com a equipe de desenvolvimento.

## 📄 Licença

Este sistema foi desenvolvido para uso interno da Procuradoria Municipal da Vitória de Santo Antão.

---

**Desenvolvido usando Django**
