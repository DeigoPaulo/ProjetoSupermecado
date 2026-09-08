import hashlib
import json
import re

from django.utils import timezone

from apps.compras.models import EntradaCompra, StatusEntradaCompra
from apps.vendas.models import StatusVenda, Venda

from .diagnostico_snapshots import diagnostico_prontidao_piloto_real
from .models import (
    FechamentoEstoqueContabil,
    InventarioEstoque,
    PerdaEstoque,
    StatusInventario,
    TipoPerdaEstoque,
)


CONTRATO_FICHA_EXECUCAO_PILOTO = "inventory_pilot_execution_sheet_v2"

ORIENTACOES_OPERACIONAIS = [
    "Conferir filial, produto e os cinco IDs antes de iniciar a verificação final.",
    "Manter emissão fiscal e integrações externas desligadas durante este ensaio de estoque.",
    "Executar o verificador final em modo estrito e não corrigir evidências históricas manualmente.",
    "Arquivar a ficha, o relatório final e seus SHA-256 no dossiê da filial piloto.",
    "Registrar a conferência operacional responsável fora desta ficha antes de declarar aceite.",
]


def _ids_produtos(itens):
    return set(itens.values_list("produto_id", flat=True))


def _texto_operacional(valor, *, campo, obrigatorio=True, limite=100):
    texto = " ".join(str(valor or "").split())
    if not texto and not obrigatorio:
        return ""
    if len(texto) < 3 or len(texto) > limite:
        raise ValueError(f"{campo} deve ter entre 3 e {limite} caracteres.")
    digitos = re.sub(r"\D", "", texto)
    if "@" in texto or len(digitos) in {11, 14}:
        raise ValueError(f"{campo} não deve conter e-mail, CPF ou CNPJ.")
    if any(ord(caractere) < 32 for caractere in texto):
        raise ValueError(f"{campo} contém caracteres inválidos.")
    return texto


def gerar_ficha_execucao_piloto(
    *, entrada_id, venda_id, perda_id, inventario_id, fechamento_id,
    responsavel_execucao="", responsavel_conferencia="",
    observacoes_operacionais="", momento=None,
):
    """Valida uma seleção manual sem alterar dados nem substituir o aceite humano."""
    momento = momento or timezone.now()
    responsavel_execucao = _texto_operacional(
        responsavel_execucao, campo="Responsável pela execução"
    )
    responsavel_conferencia = _texto_operacional(
        responsavel_conferencia, campo="Responsável pela conferência"
    )
    observacoes_operacionais = _texto_operacional(
        observacoes_operacionais,
        campo="Observações operacionais",
        obrigatorio=False,
        limite=500,
    )
    entrada = EntradaCompra.objects.get(pk=entrada_id)
    venda = Venda.objects.get(pk=venda_id)
    perda = PerdaEstoque.objects.get(pk=perda_id)
    inventario = InventarioEstoque.objects.get(pk=inventario_id)
    fechamento = FechamentoEstoqueContabil.objects.get(pk=fechamento_id)

    filial_ids = {
        entrada.filial_id,
        venda.filial_id,
        perda.filial_id,
        inventario.filial_id,
        fechamento.filial_id,
    }
    mesma_filial = len(filial_ids) == 1
    produtos_comuns = (
        _ids_produtos(entrada.itens)
        & _ids_produtos(venda.itens)
        & {perda.produto_id}
        & _ids_produtos(inventario.itens)
        & _ids_produtos(fechamento.itens)
    )
    produto_comum_unico = len(produtos_comuns) == 1

    prontidao = None
    if mesma_filial:
        prontidao = diagnostico_prontidao_piloto_real(
            filial_id=next(iter(filial_ids))
        )
    verificacoes = {
        "mesma_filial": mesma_filial,
        "produto_comum_unico": produto_comum_unico,
        "entrada_finalizada": entrada.status == StatusEntradaCompra.FINALIZADA,
        "venda_finalizada": venda.status == StatusVenda.FINALIZADA,
        "venda_sem_documento_fiscal": not venda.documentos_fiscais.exists(),
        "perda_por_vencimento_com_lote": (
            perda.tipo == TipoPerdaEstoque.VENCIMENTO and perda.lote_id is not None
        ),
        "inventario_aplicado": inventario.status == StatusInventario.APLICADO,
        "fechamento_possui_hash": len(fechamento.conteudo_sha256 or "") == 64,
        "filial_pronta_para_piloto_real": bool(
            prontidao and prontidao["pronta_para_aceite"]
        ),
    }
    mensagens = {
        "mesma_filial": "Os cinco registros devem pertencer à mesma filial.",
        "produto_comum_unico": "Os cinco registros devem compartilhar exatamente um produto.",
        "entrada_finalizada": "A entrada selecionada ainda não está finalizada.",
        "venda_finalizada": "A venda selecionada ainda não está finalizada.",
        "venda_sem_documento_fiscal": "A venda selecionada já possui documento fiscal.",
        "perda_por_vencimento_com_lote": "A perda deve ser por vencimento e estar vinculada ao lote.",
        "inventario_aplicado": "O inventário selecionado ainda não está aplicado.",
        "fechamento_possui_hash": "O fechamento selecionado não possui hash íntegro no formato esperado.",
        "filial_pronta_para_piloto_real": (
            prontidao["motivo"] if prontidao else "A prontidão não pode ser avaliada com filiais diferentes."
        ),
    }
    impedimentos = [
        {"codigo": chave.upper(), "mensagem": mensagens[chave]}
        for chave, passou in verificacoes.items()
        if not passou
    ]
    objetos = {
        "entrada_id": entrada.pk,
        "venda_id": venda.pk,
        "perda_id": perda.pk,
        "inventario_id": inventario.pk,
        "fechamento_id": fechamento.pk,
    }
    comando_verificacao = (
        "manage.py verificar_fluxo_estoque_piloto "
        f"--entrada-id {entrada.pk} --venda-id {venda.pk} --perda-id {perda.pk} "
        f"--inventario-id {inventario.pk} --fechamento-id {fechamento.pk} --estrito"
    )
    payload = {
        "contrato": CONTRATO_FICHA_EXECUCAO_PILOTO,
        "gerado_em": momento.isoformat(),
        "objetos_selecionados_manualmente": objetos,
        "filial_id": next(iter(filial_ids)) if mesma_filial else None,
        "produto_id": next(iter(produtos_comuns)) if produto_comum_unico else None,
        "responsaveis": {
            "execucao": responsavel_execucao,
            "conferencia": responsavel_conferencia,
            "informados_manualmente": True,
            "persistidos_no_banco": False,
            "responsaveis_distintos": (
                responsavel_execucao.casefold() != responsavel_conferencia.casefold()
            ),
            "separacao_de_funcoes_recomendada": True,
        },
        "observacoes_operacionais": observacoes_operacionais,
        "orientacoes_operacionais": ORIENTACOES_OPERACIONAIS,
        "dados_pessoais_sensiveis_solicitados": False,
        "prontidao_piloto_real": prontidao,
        "verificacoes": verificacoes,
        "impedimentos": impedimentos,
        "apta_para_verificacao_final": all(verificacoes.values()),
        "aprovacao_automatica": False,
        "registra_aceite": False,
        "persiste_ficha": False,
        "somente_leitura": True,
        "comunicacao_externa": False,
        "comando_verificacao_final": comando_verificacao,
    }
    payload["conteudo_sha256"] = hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    return payload
