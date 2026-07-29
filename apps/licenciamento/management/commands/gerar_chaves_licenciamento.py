from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Gera o par Ed25519 usado nas liberações emergenciais offline."

    def add_arguments(self, parser):
        parser.add_argument("--diretorio", required=True, help="Diretório seguro fora do repositório.")
        parser.add_argument("--substituir", action="store_true")

    def handle(self, *args, **options):
        diretorio = Path(options["diretorio"]).expanduser().resolve()
        diretorio.mkdir(parents=True, exist_ok=True)
        privada_path = diretorio / "licenciamento_ed25519_private.pem"
        publica_path = diretorio / "licenciamento_ed25519_public.pem"
        if not options["substituir"] and (privada_path.exists() or publica_path.exists()):
            raise CommandError("As chaves já existem. Não substitua chaves em uso sem um plano de rotação.")
        privada = Ed25519PrivateKey.generate()
        privada_path.write_bytes(
            privada.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        publica_path.write_bytes(
            privada.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
        self.stdout.write(self.style.SUCCESS(f"Chave privada central: {privada_path}"))
        self.stdout.write(self.style.SUCCESS(f"Chave pública para servidores locais: {publica_path}"))
        self.stdout.write("Proteja a chave privada com permissões do sistema operacional e nunca a distribua aos clientes.")