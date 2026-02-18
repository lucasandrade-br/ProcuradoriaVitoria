# 1. Imagem base otimizada
FROM python:3.11-slim

# 2. Variáveis de ambiente
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# 3. Unificação de comandos para reduzir camadas e limpar cache
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-libmysqlclient-dev \
    build-essential \
    pkg-config \
    && pip install --upgrade pip \
    && rm -rf /var/lib/apt/lists/*

# 4. Criação de usuário não-root para segurança
RUN useradd -m appuser
WORKDIR /app

# 5. Instalação de dependências (Cacheando a camada de requisitos)
COPY requirements.txt .
# Certifique-se de que o 'gunicorn' esteja dentro do seu requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copiar o projeto e dar permissão ao usuário
COPY . .
RUN chown -R appuser:appuser /app

# 7. Trocar para o usuário seguro
USER appuser

# 8. Expor a porta (documentação)
EXPOSE 8080

# 9. Comando de inicialização flexível
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT} config.wsgi:application"]