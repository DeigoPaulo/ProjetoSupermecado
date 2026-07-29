from calendar import monthrange
from datetime import date

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.licenciamento.models import ContratoLicenca, FaturaLicenca, StatusContrato
from apps.licenciamento.services import atualizar_status_contrato, gerar_cobranca_asaas


class Command(BaseCommand):
    help = "Gera uma fatura mensal por contrato e publica a cobrança no Asaas sem duplicidade."

    def handle(self, *args, **options):
        hoje = timezone.localdate()
        competencia = hoje.replace(day=1)
        criadas = publicadas = erros = status_atualizados = 0
        contratos = ContratoLicenca.objects.select_related("empresa", "plano").exclude(status=StatusContrato.CANCELADO)
        for contrato in contratos:
            vencimento = date(hoje.year, hoje.month, min(contrato.dia_vencimento, monthrange(hoje.year, hoje.month)[1]))
            fatura, criada = FaturaLicenca.objects.get_or_create(
                contrato=contrato,
                competencia=competencia,
                defaults={
                    "vencimento": vencimento,
                    "valor": contrato.valor_mensal,
                    "referencia_externa": f"licenca:{contrato.pk}:{competencia:%Y-%m}",
                },
            )
            criadas += int(criada)
            if contrato.cobranca_automatica and not fatura.asaas_payment_id:
                try:
                    gerar_cobranca_asaas(fatura)
                    publicadas += 1
                except RuntimeError as exc:
                    erros += 1
                    self.stderr.write(f"{contrato.empresa}: {exc}")
            status_anterior = contrato.status
            atualizar_status_contrato(contrato)
            status_atualizados += int(contrato.status != status_anterior)
        self.stdout.write(self.style.SUCCESS(
            f"Cobranças: {criadas} criada(s), {publicadas} publicada(s), {erros} erro(s); "
            f"{status_atualizados} contrato(s) atualizado(s)."
        ))
