# Publicação do DeTec Admin

O executável distribuído pelo ERP fica em `artifacts/DeTecAdmin.exe`.

Em outro computador Windows, abra PowerShell na raiz do projeto e execute:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\publicar_admin_desktop.ps1 -Version 0.1.0
```

O script cria ou usa o ambiente de build com Python 3.12, instala as dependências necessárias, gera `desktop_admin\dist\DeTecAdmin.exe`, copia o resultado para `artifacts\DeTecAdmin.exe` e atualiza o manifesto SHA-256.

Depois reinicie o Django. A página `Configurações > DeTec Admin` passa a liberar o download. Esta versão de homologação não exige certificado de assinatura.