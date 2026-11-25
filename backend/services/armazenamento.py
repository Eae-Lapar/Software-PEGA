
import json
import shutil
import uuid
import secrets
import hashlib
import hmac

from pathlib import Path
from datetime import datetime, timezone, timedelta


# CONFIGURAÇÕES

STORAGE_DIR = Path("storage")

TEMPO_EXPIRACAO = timedelta(hours=24)

ARQUIVOS_CALCULO = {
    "emissoes_base.csv": "text/csv",
    "resumo.csv": "text/csv",
    "fatores_utilizados.csv": "text/csv",
    "metadados.json": "application/json",
}


# CRIAR TOKEN PRIVADO

def criar_sessao():

    return secrets.token_urlsafe(32)


# PROTEGER TOKEN

def hash_sessao(token):

    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()


# SALVAR INVENTÁRIO

def salvar_inventario(
    caminho_original,
    resultado,
    token_sessao
):

    inventario_id = str(uuid.uuid4())

    pasta = STORAGE_DIR / inventario_id

    pasta.mkdir(
        parents=True,
        exist_ok=False
    )

    try:

        agora = datetime.now(timezone.utc)

        extensao = Path(
            resultado["nome_arquivo"]
        ).suffix.lower()

        shutil.copy2(
            caminho_original,
            pasta / f"original{extensao}"
        )

        resultado["dados"].to_csv(
            pasta / "dados.csv",
            index=False,
            encoding="utf-8"
        )

        metadados = {

            "inventario_id": inventario_id,

            "sessao_hash": hash_sessao(
                token_sessao
            ),

            "arquivo": resultado["nome_arquivo"],

            "criado_em": agora.isoformat(),

            "expira_em": (
                agora + TEMPO_EXPIRACAO
            ).isoformat(),

            "total_linhas": len(
                resultado["dados"]
            ),

            "colunas": list(
                resultado["dados"].columns
            ),

            "colunas_extras": resultado["colunas_extras"],

            "validacao": resultado["validacao"],

            "status": "validado"
        }

        with (pasta / "metadados.json").open(
            "w",
            encoding="utf-8"
        ) as arquivo:

            json.dump(
                metadados,
                arquivo,
                ensure_ascii=False,
                indent=4
            )

        return inventario_id

    except Exception:

        shutil.rmtree(
            pasta,
            ignore_errors=True
        )

        raise


# LOCALIZAR INVENTÁRIO

def obter_pasta(inventario_id):

    try:

        identificador = str(
            uuid.UUID(inventario_id)
        )

    except (ValueError, TypeError):

        raise FileNotFoundError(
            "Inventário não encontrado."
        )

    pasta = STORAGE_DIR / identificador

    if not pasta.is_dir():

        raise FileNotFoundError(
            "Inventário não encontrado."
        )

    return pasta


# VERIFICAR AUTORIZAÇÃO

def verificar_acesso(
    inventario_id,
    token_sessao
):

    pasta = obter_pasta(inventario_id)

    with (pasta / "metadados.json").open(
        "r",
        encoding="utf-8"
    ) as arquivo:

        metadados = json.load(arquivo)

    autorizado = (
        token_sessao
        and hmac.compare_digest(
            metadados["sessao_hash"],
            hash_sessao(token_sessao)
        )
    )

    if not autorizado:

        raise PermissionError(
            "Acesso não autorizado."
        )

    expiracao = datetime.fromisoformat(
        metadados["expira_em"]
    )

    if datetime.now(timezone.utc) >= expiracao:

        shutil.rmtree(
            pasta,
            ignore_errors=True
        )

        raise FileNotFoundError(
            "Inventário expirado."
        )

    return pasta, metadados


# CONSULTAR INVENTÁRIO

def obter_metadados(inventario_id, token_sessao):
    _, metadados = verificar_acesso(inventario_id, token_sessao)
    metadados.pop("sessao_hash", None)
    return metadados


def ler_metadados_calculo(pasta):
    with (pasta / "metadados.json").open(encoding="utf-8") as arquivo:
        return json.load(arquivo)


def listar_calculos(pasta_inventario):
    raiz = pasta_inventario / "calculos"
    if not raiz.is_dir():
        return []
    calculos = []
    campos = ("calculo_id", "setor", "ano", "combustivel", "total_registros")
    for arquivo in raiz.glob("*/metadados.json"):
        try:
            dados = ler_metadados_calculo(arquivo.parent)
            calculos.append((arquivo.stat().st_mtime_ns, {chave: dados[chave] for chave in campos}))
        except FileNotFoundError:
            continue
    return [dados for _, dados in sorted(calculos, key=lambda item: item[0], reverse=True)]


def obter_pasta_calculo(pasta_inventario, calculo_id):
    try:
        identificador = str(uuid.UUID(calculo_id))
    except ValueError as erro:
        raise FileNotFoundError("Cálculo indisponível.") from erro
    pasta = pasta_inventario / "calculos" / identificador
    if not (pasta / "metadados.json").is_file():
        raise FileNotFoundError("Cálculo indisponível.")
    return pasta


# EXCLUIR INVENTÁRIO

def excluir_inventario(
    inventario_id,
    token_sessao
):

    pasta, _ = verificar_acesso(
        inventario_id,
        token_sessao
    )

    shutil.rmtree(pasta)


# LIMPEZA AUTOMÁTICA

def limpar_expirados():

    if not STORAGE_DIR.is_dir():
        return 0

    agora = datetime.now(timezone.utc)

    removidos = 0

    for pasta in STORAGE_DIR.iterdir():

        if not pasta.is_dir():
            continue

        try:

            with (pasta / "metadados.json").open(
                "r",
                encoding="utf-8"
            ) as arquivo:

                metadados = json.load(arquivo)

            expiracao = datetime.fromisoformat(
                metadados["expira_em"]
            )

            if agora >= expiracao:

                shutil.rmtree(pasta)

                removidos += 1

        except (OSError, ValueError, KeyError):

            continue

    return removidos
