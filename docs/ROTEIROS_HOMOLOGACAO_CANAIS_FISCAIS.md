# Roteiros de homologação dos canais fiscais

Contrato: `fiscal_channel_homologation_runbook_v1`.

Os roteiros organizam a futura execução externa de autorização, consulta, rejeição,
cancelamento, inutilização, eventos e distribuição DF-e, separadamente para Focus NFe e
SEFAZ direta GO. Eles não executam rede, não carregam segredos e não liberam produção.

Cada roteiro exige identificação da filial, CNPJ, ambiente, canal, responsável e versão;
hash do conteúdo enviado sem segredos; retorno protegido; código de status, motivo e
protocolo; confronto entre esperado e obtido; e evidência de recuperação sem duplicidade
quando aplicável.

## Estado atual

- Treze roteiros possuem estrutura offline e aguardam CNPJ/IE, credenciamento, credencial do
  canal, cenários aprovados e execução real em homologação.
- Eventos Focus permanece bloqueado por lacuna interna: não existe adaptador Focus de CC-e
  ou manifestação no sistema atual.
- Eventos na SEFAZ direta cobre estruturalmente CC-e e manifestação, mas ainda precisa de A1,
  credenciamento e documentos reais de homologação.
- Nenhum resultado offline autoriza marcar homologação concluída ou produção liberada.

## Sequência futura segura

1. Escolher uma filial piloto e um único canal para o primeiro ciclo.
2. Receber CNPJ/IE, credenciamento e credenciais por meio seguro.
3. Revalidar documentação oficial, endpoints e schemas vigentes na data do teste.
4. Aprovar com o responsável fiscal os cenários, inclusive as rejeições controladas.
5. Executar uma operação por vez, armazenar as evidências e confrontar o critério de aceite.
6. Repetir o mesmo roteiro no segundo canal sem reutilizar conclusões do primeiro.
7. Liberar produção somente após aceite técnico/fiscal explícito e verificação das travas.
