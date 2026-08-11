# Publicacao do PDV Desktop

Em outro computador Windows, abra PowerShell na raiz do projeto e execute:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\publicar_pdv_desktop.ps1 -Version 0.1.11
```

O comando usa Python 3.12, gera `desktop_pdv\dist\DeTecPDV.exe` e publica o arquivo em `artifacts\DeTecPDV.exe` com manifesto SHA-256 para a Central do PDV.

Esta e a versao de homologacao, sem certificado. Para gerar MSI no futuro, use `desktop_pdv\build_msi.ps1` apos o build.