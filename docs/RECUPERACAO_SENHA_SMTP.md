# Recuperacao de senha por SMTP

Antes de liberar o ambiente comercial, configure EMAIL_BACKEND com o backend SMTP do Django e informe host, porta, remetente e, quando exigidos pelo provedor, usuario e senha. TLS e SSL nao devem permanecer ativos simultaneamente.

Comando de verificacao:

    python manage.py verificar_prontidao_recuperacao_senha --estrito

Para automacao, use --json. A saida informa apenas presenca e estado da configuracao; host, usuario e senha nao sao expostos.

A verificacao local nao comprova entrega. Envie uma recuperacao real para uma caixa controlada, confirme validade e uso unico do link, verifique spam e valide SPF, DKIM e DMARC do dominio remetente. O item do roadmap so pode ser concluido depois dessa homologacao.
