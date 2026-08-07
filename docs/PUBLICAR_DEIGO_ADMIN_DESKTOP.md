# Publicacao do DeTec Admin

O executavel distribuido pelo ERP fica em `artifacts/DeTecAdmin.exe`.

Em outro computador Windows, abra PowerShell na raiz do projeto e execute:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\publicar_admin_desktop.ps1 -Version 0.1.0
```

O script cria ou usa o ambiente de build com Python 3.12, instala as dependencias necessarias, gera `desktop_admin\dist\DeTecAdmin.exe`, copia o resultado para `artifacts\DeTecAdmin.exe` e atualiza o manifesto SHA-256.

Depois reinicie o Django. A pagina `Configuracoes > DeTec Admin` passa a liberar o download. Esta versao de homologacao nao exige certificado de assinatura.