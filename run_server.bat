@echo off
echo Ativando o ambiente virtual...
call venv\Scripts\activate
echo.
echo Iniciando o servidor de desenvolvimento do Django...
echo.
echo Acesse http://127.0.0.1:8000 no seu navegador.
echo Pressione CTRL+C nesta janela para parar o servidor.
echo.
python manage.py runserver
pause
