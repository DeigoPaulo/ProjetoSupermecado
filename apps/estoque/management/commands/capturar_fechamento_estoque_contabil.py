from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.empresas.models import Filial
from apps.estoque.fechamento_contabil import capturar_fechamento_estoque_contabil


class Command(BaseCommand):
    help = "Captura o fechamento imutável de quantidade e custo médio do estoque no dia atual."

    def add_arguments(self, parser):
        parser.add_argument("--filial", type=int, help="ID de uma filial; sem ele, fecha todas as filiais ativas.")
        parser.add_argument("--usuario", required=True, help="Usuário ativo responsável pelo fechamento.")
        parser.add_argument("--confirmar-fechamento", action="store_true")

    def handle(self, *args, **options):
        if not options["confirmar_fechamento"]:
            raise CommandError("Use --confirmar-fechamento após conferir as movimentações do dia.")
        usuario = get_user_model().objects.filter(username=options["usuario"], is_active=True).first()
        if not usuario:
            raise CommandError("Usuário ativo responsável não encontrado.")
        filiais = Filial.objects.filter(is_active=True).order_by("pk")
        if not usuario.is_superuser:
            empresas_permitidas = PerfilUsuario.objects.filter(
                usuario=usuario,
                is_active=True,
                tipo__in=[TipoPerfil.ADMINISTRADOR, TipoPerfil.CONTABILIDADE],
                filial__isnull=False,
            ).values_list("filial__empresa_id", flat=True)
            filiais = filiais.filter(empresa_id__in=empresas_permitidas)
        if options.get("filial"):
            filiais = filiais.filter(pk=options["filial"])
            if not filiais.exists():
                raise CommandError("Filial ativa não encontrada.")
        criados = 0
        existentes = 0
        for filial in filiais:
            fechamento, criado = capturar_fechamento_estoque_contabil(
                filial=filial, usuario=usuario, data_referencia=timezone.localdate()
            )
            criados += int(criado)
            existentes += int(not criado)
            self.stdout.write(
                f"Filial {filial.pk}: {fechamento.total_itens} itens, "
                f"valor {fechamento.valor_total_custo:.2f}, SHA-256 {fechamento.conteudo_sha256}."
            )
        self.stdout.write(self.style.SUCCESS(f"Fechamentos criados: {criados}; já existentes: {existentes}."))
