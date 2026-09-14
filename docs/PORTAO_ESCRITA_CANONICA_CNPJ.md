# Portão de escrita canônica do CNPJ

14/09/2026 · ciclo 114 · contrato `alphanumeric_cnpj_canonical_write_gate_v1`.

## Objetivo

O portão prepara uma representação canônica de CNPJ para uma futura integração, sem consultar banco, alterar objeto, gravar valor ou autorizar persistência. As fronteiras estruturais iniciais são Empresa, Filial, Cliente pessoa jurídica e Fornecedor pessoa jurídica.

Ele aceita criação e atualização. Filial, Cliente e Fornecedor exigem escopo explícito da empresa; Empresa permanece como raiz. A proposta só é estruturalmente aceita quando usa o formato oficial e possui DV válido.

## Atualizações protegidas

Uma atualização exige o valor atual:

- representações diferentes da mesma identidade resultam em `SEM_ALTERACAO_CANONICA`;
- valor legado inválido resulta em `LEGADO_INVALIDO_REQUER_REVISAO` e nunca é corrigido automaticamente;
- mudança para outra identidade resulta em `TROCA_IDENTIDADE_REQUER_CONTROLES_EXTERNOS`;
- colisão, titularidade, autorização e auditoria permanecem controles externos obrigatórios.

Mesmo `CANONICO_PREPARADO` mantém `pode_persistir=false`. O valor canônico é uma proposta para o próximo adaptador sombra, não uma autorização de cadastro.

## Limites

Não houve integração com formulários, modelos, services, banco, licença, credencial ou certificado. O portão não libera homologação, produção, Focus, SEFAZ direta ou emissão.

Foram aprovados oito testes próprios, 14 testes do ciclo com a estratégia, 70 testes focados acumulados e 531 testes da suíte fiscal completa. O inventário permaneceu em 332 candidatos e nenhuma migração foi gerada.

## Próximo passo

Especificar um adaptador sombra de escrita que compare a proposta com o comportamento atual sem salvar dados, antes de escolher qualquer fronteira operacional.
