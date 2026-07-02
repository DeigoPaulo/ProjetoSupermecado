import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone


def _fernet():
    digest = hashlib.sha256(settings.FISCAL_CERTIFICATE_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def criptografar(valor):
    if isinstance(valor, str):
        valor = valor.encode("utf-8")
    return _fernet().encrypt(valor)


def descriptografar(valor):
    try:
        return _fernet().decrypt(bytes(valor))
    except InvalidToken as exc:
        raise ValidationError("Nao foi possivel abrir o certificado protegido. Verifique a chave fiscal do ambiente.") from exc


def _validade_certificado(conteudo, senha):
    senha_bytes = senha.encode("utf-8") if senha else None
    try:
        _, certificado, _ = load_key_and_certificates(conteudo, senha_bytes)
    except Exception as exc:
        raise ValidationError("Certificado A1 invalido ou senha incorreta.") from exc
    if not certificado:
        raise ValidationError("O arquivo informado nao contem um certificado valido.")
    validade = certificado.not_valid_after_utc
    return timezone.localtime(validade).date()


def salvar_certificado_a1(configuracao, arquivo, senha):
    conteudo = arquivo.read()
    validade = _validade_certificado(conteudo, senha)
    configuracao.certificado_nome = arquivo.name
    configuracao.certificado_validade = validade
    configuracao.certificado_a1_criptografado = criptografar(conteudo)
    configuracao.certificado_senha_criptografada = criptografar(senha)
    configuracao.certificado_atualizado_em = timezone.now()
    configuracao.save(
        update_fields=[
            "certificado_nome",
            "certificado_validade",
            "certificado_a1_criptografado",
            "certificado_senha_criptografada",
            "certificado_atualizado_em",
            "atualizado_em",
        ]
    )


def abrir_certificado_a1(configuracao):
    if not configuracao.certificado_configurado:
        raise ValidationError("Certificado A1 nao configurado.")
    return (
        descriptografar(configuracao.certificado_a1_criptografado),
        descriptografar(configuracao.certificado_senha_criptografada).decode("utf-8"),
    )
