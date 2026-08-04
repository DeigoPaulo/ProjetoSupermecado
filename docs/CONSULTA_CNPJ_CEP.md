# Consulta de CNPJ e CEP

O sistema continua funcional sem internet usando validacao formal, pesquisa nos cadastros locais e preenchimento manual. Para preenchimento externo, configure CADASTRO_CNPJ_PROVIDER_URL e CADASTRO_CEP_PROVIDER_URL com endpoints HTTPS do provedor escolhido.

Valide a configuracao antes da homologacao:

    python manage.py verificar_prontidao_consulta_cadastro --estrito

A opcao --json e apropriada para instaladores e pipelines e nao revela as URLs configuradas. A verificacao local confirma somente configuracao e HTTPS. A conclusao do roadmap exige testar disponibilidade, limites, respostas validas, registros inexistentes, timeout, indisponibilidade e aderencia contratual/LGPD com o provedor real.
