@echo off
REM Script de Backup Automático do Banco de Dados MySQL
REM Autor: Sistema SGDP
REM Data: 2025

echo ========================================
echo BACKUP DO BANCO DE DADOS - SGDP
echo ========================================
echo.

REM Configurações (lê do arquivo .env ou define manualmente)
set DB_NAME=Procuradoria
set DB_USER=root
set DB_HOST=127.0.0.1
set DB_PORT=3306

REM Diretório onde os backups serão salvos
set BACKUP_DIR=%~dp0backups
if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

REM Nome do arquivo de backup com data e hora
set TIMESTAMP=%date:~-4%%date:~3,2%%date:~0,2%_%time:~0,2%%time:~3,2%%time:~6,2%
set TIMESTAMP=%TIMESTAMP: =0%
set BACKUP_FILE=%BACKUP_DIR%\sgdp_backup_%TIMESTAMP%.sql

echo Data/Hora: %date% %time%
echo Banco de dados: %DB_NAME%
echo Arquivo de backup: %BACKUP_FILE%
echo.
echo Iniciando backup...

REM Executa o mysqldump (será solicitada a senha)
mysqldump -u %DB_USER% -p -h %DB_HOST% -P %DB_PORT% %DB_NAME% > "%BACKUP_FILE%"

if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo BACKUP CONCLUÍDO COM SUCESSO!
    echo ========================================
    echo Arquivo salvo em: %BACKUP_FILE%
    
    REM Remove backups com mais de 30 dias
    echo.
    echo Limpando backups antigos (mais de 30 dias)...
    forfiles /P "%BACKUP_DIR%" /M *.sql /D -30 /C "cmd /c del @path" 2>nul
    echo Limpeza concluída.
) else (
    echo.
    echo ========================================
    echo ERRO AO REALIZAR BACKUP!
    echo ========================================
    echo Verifique as credenciais do banco de dados.
)

echo.
pause
