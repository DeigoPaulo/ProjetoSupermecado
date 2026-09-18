"""Gera e embute a qualificação fiscal no pacote comercial, sem rede."""

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    raiz = Path(args.root).resolve()
    sys.path.insert(0, str(raiz))
    from apps.fiscal.manifesto_qualificacao_fiscal import (
        NOME_IDENTIDADE, NOME_MANIFESTO, gerar_identidade_instalacao, gerar_manifesto_qualificacao,
    )
    arquivo = Path(args.archive)
    hash_base = hashlib.sha256(arquivo.read_bytes()).hexdigest()
    manifesto = gerar_manifesto_qualificacao(raiz_projeto=raiz, versao=args.version, commit=args.commit, hash_base_pacote=hash_base)
    identidade = gerar_identidade_instalacao(versao=args.version, commit=args.commit)
    with zipfile.ZipFile(arquivo, "a", zipfile.ZIP_DEFLATED) as pacote:
        pacote.writestr(NOME_MANIFESTO, json.dumps(manifesto, ensure_ascii=False, indent=2))
        pacote.writestr(NOME_IDENTIDADE, json.dumps(identidade, ensure_ascii=False, indent=2))
    print(json.dumps({"manifesto": NOME_MANIFESTO, "sha256": manifesto["hash_integridade"]}))


if __name__ == "__main__":
    main()
