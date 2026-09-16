# Consulta de CNPJ e CEP

O sistema continua funcional sem internet usando validacao formal, pesquisa nos cadastros locais e preenchimento manual. Para preenchimento externo, configure CADASTRO_CNPJ_PROVIDER_URL e CADASTRO_CEP_PROVIDER_URL com endpoints HTTPS do provedor escolhido.

A busca local de CNPJ usa a representação canônica de 14 caracteres e aceita tanto CNPJ
numérico quanto alfanumérico, puro ou com a máscara oficial. Letras são preservadas e
convertidas para maiúsculas; o backend continua responsável por formato e dígitos
verificadores.

Por segurança, o provider externo é considerado numérico até que seu contrato seja
homologado. Somente defina CADASTRO_CNPJ_PROVIDER_SUPORTA_ALFANUMERICO=true quando houver
evidência de que o endpoint aceita a representação canônica de 12 caracteres alfanuméricos
mais dois dígitos. Sem essa declaração, um CNPJ alfanumérico não é enviado ao provider: a
tela informa a limitação e permite continuar o cadastro manualmente.

Valide a configuracao antes da homologacao:

    python manage.py verificar_prontidao_consulta_cadastro --estrito

A opcao --json e apropriada para instaladores e pipelines e nao revela as URLs configuradas. A verificacao local confirma somente configuracao e HTTPS. A conclusao do roadmap exige testar disponibilidade, limites, respostas validas, registros inexistentes, timeout, indisponibilidade e aderencia contratual/LGPD com o provedor real.
