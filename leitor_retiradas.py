"""
ALMOXARIFADO MATRIZ
Leitura de retiradas digitadas e tabelas copiadas do SGP.

Este módulo organiza os dados para a prévia.
Não grava movimentações nem gera relatórios sozinho.
"""

import csv
import hashlib
import io
import json
import re
import unicodedata

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from html import unescape
from html.parser import HTMLParser


# ==========================================================
# NOMES E APELIDOS
# ==========================================================

APELIDOS_TECNICOS = {
    "magno": [
        "magnovanio",
    ],

    "wildiney": [
        "wild",
        "wildinei",
        "dinei",
    ],
}

APELIDOS_ITENS = {
    "apc": [
        "conector apc",
        "conectores apc",
    ],

    "upc": [
        "conector upc",
        "conectores upc",
    ],

    "abracadeira": [
        "abracadeiras",
    ],

    "cunha": [
        "cunhas",
    ],

    "bucha de acabamento": [
        "buchas de acabamento",
    ],

    "fita isolante": [
        "fitas isolantes",
        "fitaisolante",
    ],

    "pino jack rj45": [
        "pinos jack rj45",
        "pino rj45",
        "pinos rj45",
        "rj45",
    ],

    "miguelao": [
        "migueloes",
    ],

    "cabo de rede": [
        "cabos de rede",
    ],

    "cabo miniflatdrop": [
        "cabo miniflat drop",
        "miniflatdrop",
        "miniflat drop",
    ],

    "xc220": ["xc 220"],
    "xx530": ["xx 530"],
    "xx535": ["xx 535"],
    "xx230": ["xx 230"],
    "121ac": ["121 ac"],
    "1200r": ["1200 r"],
    "ex141": ["ex 141"],

    "halos12": [
        "halo s12",
        "halo s 12",
        "halos 12",
    ],

    "mr60x": ["mr 60x"],
    "onu 1010": ["onu1010"],
    "firestick": ["fire stick"],
}


# ==========================================================
# QUANTIDADES E UNIDADES
# ==========================================================

NUMEROS = {
    "um": 1,
    "uma": 1,
    "dois": 2,
    "duas": 2,
    "tres": 3,
    "quatro": 4,
    "cinco": 5,
    "seis": 6,
    "sete": 7,
    "oito": 8,
    "nove": 9,
    "dez": 10,
    "onze": 11,
    "doze": 12,
    "treze": 13,
    "quatorze": 14,
    "catorze": 14,
    "quinze": 15,
    "dezesseis": 16,
    "dezessete": 17,
    "dezoito": 18,
    "dezenove": 19,
    "vinte": 20,
    "trinta": 30,
    "quarenta": 40,
    "cinquenta": 50,
    "sessenta": 60,
    "setenta": 70,
    "oitenta": 80,
    "noventa": 90,
    "cem": 100,
}

LIGACOES = {
    "pegou",
    "retirou",
    "retirada",
    "retiradas",
    "levou",
    "recebeu",
    "tecnico",
    "tecnicos",
    "de",
    "do",
    "da",
    "no",
    "na",
    "o",
    "a",
    "os",
    "as",
    "e",
    "mais",
    "dia",
    "feira",
    "em",
}

UNIDADES = {
    "un": "un",
    "unidade": "un",
    "unidades": "un",

    "m": "m",
    "metro": "m",
    "metros": "m",

    "rolo": "rolo",
    "rolos": "rolo",
    "bobina": "rolo",
    "bobinas": "rolo",

    "pacote": "pacote",
    "pacotes": "pacote",
    "pacotinho": "pacote",
    "pacotinhos": "pacote",

    "caixa": "caixa",
    "caixas": "caixa",
}

EMBALAGENS = {
    ("abracadeira", "pacote"): Decimal("100"),
    ("miguelao", "pacote"): Decimal("100"),
    ("cabo de rede", "caixa"): Decimal("305"),
    ("cabo miniflatdrop", "rolo"): Decimal("1000"),
}

DIAS = {
    "segunda": 0,
    "terca": 1,
    "quarta": 2,
    "quinta": 3,
    "sexta": 4,
    "sabado": 5,
    "domingo": 6,
}


# ==========================================================
# NORMALIZAÇÃO
# ==========================================================

def normalizar(texto):
    return "".join(
        caractere
        for caractere in unicodedata.normalize(
            "NFKD",
            str(texto).lower(),
        )
        if not unicodedata.combining(caractere)
    )


def tokens(texto):
    return re.findall(
        r"\d{4}-\d{2}-\d{2}"
        r"|\d{1,2}/\d{1,2}(?:/\d{4})?"
        r"|[a-z0-9]+(?:[.,][0-9]+)*"
        r"|[^\w\s]",
        normalizar(texto),
    )


def _chave(texto):
    return re.sub(
        r"[^a-z0-9]+",
        " ",
        normalizar(texto),
    ).strip()


def _mapa(registros, apelidos):
    resultado = {}

    for registro in registros:
        nome = normalizar(registro["name"])

        formas = [nome] + apelidos.get(
            nome,
            [],
        )

        for forma in formas:
            chave = tuple(tokens(forma))

            if (
                chave in resultado
                and resultado[chave]["id"] != registro["id"]
            ):
                raise ValueError(
                    "Apelido duplicado no catálogo: " + forma
                )

            resultado[chave] = registro

    return sorted(
        resultado.items(),
        key=lambda par: len(par[0]),
        reverse=True,
    )


def _encontrar(partes, posicao, mapa):
    for chave, registro in mapa:
        trecho = tuple(
            partes[posicao:posicao + len(chave)]
        )

        if trecho == chave:
            return registro, len(chave)

    return None, 0


def _quantidade(partes, posicao):
    palavra = partes[posicao]

    if re.fullmatch(
        r"\d+(?:,\d{1,3})?",
        palavra,
    ):
        return Decimal(
            palavra.replace(",", ".")
        ), 1

    if palavra in NUMEROS:
        valor = NUMEROS[palavra]
        tamanho = 1

        if (
            20 <= valor < 100
            and posicao + 2 < len(partes)
            and partes[posicao + 1] == "e"
            and 0 < NUMEROS.get(
                partes[posicao + 2],
                0,
            ) < 10
        ):
            valor += NUMEROS[
                partes[posicao + 2]
            ]

            tamanho = 3

        return Decimal(valor), tamanho

    return None, 0


# ==========================================================
# VALIDAÇÃO E RESULTADO
# ==========================================================

def _linha(item, tecnico, dia, quantidade):
    custo = Decimal(
        str(item["cost"])
    )

    if not custo.is_finite() or custo < 0:
        raise ValueError(
            "Custo inválido no catálogo: "
            + item["name"]
        )

    if (
        not quantidade.is_finite()
        or quantidade <= 0
        or quantidade > 1000000
        or quantidade.as_tuple().exponent < -3
        or (
            item["unit"] != "m"
            and quantidade != quantidade.to_integral_value()
        )
    ):
        raise ValueError(
            "Quantidade inválida para "
            + item["name"]
        )

    return {
        "date": dia.isoformat(),

        "technician_id": tecnico["id"],
        "technician": tecnico["name"],

        "item_id": item["id"],
        "item": item["name"],

        "unit": item["unit"],
        "category": item["category"],

        "quantity": str(quantidade),
        "cost": str(custo),

        "kind": "retirada",
    }


def _resultado(
    linhas,
    pendencias,
    padrao=None,
    avisos=None,
    eventos=None,
    formato="texto",
):
    linhas.sort(
        key=lambda linha: (
            linha["date"],
            linha["technician"],
            linha["item"],
        )
    )

    return {
        "rows": linhas,
        "issues": pendencias,
        "warnings": avisos or [],

        "can_confirm": (
            bool(linhas)
            and not pendencias
        ),

        "used_default_date": (
            padrao.isoformat()
            if padrao
            else None
        ),

        "format": formato,
        "sgp_events": eventos or [],
    }


# ==========================================================
# TEXTO DIGITADO
# Mantém a compatibilidade com a primeira versão.
# ==========================================================

def _organizar_texto(
    texto,
    tecnicos,
    itens,
    inicio,
    fim,
    padrao,
):
    mapa_tecnicos = _mapa(
        tecnicos,
        APELIDOS_TECNICOS,
    )

    mapa_itens = _mapa(
        itens,
        APELIDOS_ITENS,
    )

    partes = tokens(texto)

    linhas = []
    pendencias = []

    tecnico = None
    dia = padrao
    nome_sem_item = False
    posicao = 0

    def problema(mensagem, pos=None):
        pos = posicao if pos is None else pos

        pendencias.append({
            "message": mensagem,

            "excerpt": " ".join(
                partes[max(0, pos - 2):pos + 7]
            ),
        })

    while posicao < len(partes):
        palavra = partes[posicao]

        if (
            palavra in {
                ",",
                ";",
                ":",
                ".",
                "(",
                ")",
            }
            or (
                palavra == "-"
                and posicao
                and partes[posicao - 1] in DIAS
            )
        ):
            posicao += 1
            continue

        encontrado, tamanho = _encontrar(
            partes,
            posicao,
            mapa_tecnicos,
        )

        if encontrado:
            if nome_sem_item:
                problema(
                    "Separe as retiradas de cada técnico; "
                    "há dois nomes sem itens entre eles."
                )

            tecnico = encontrado
            nome_sem_item = True

            posicao += tamanho
            continue

        if palavra in DIAS:
            candidatas = [
                inicio + timedelta(days=numero)

                for numero in range(
                    (fim - inicio).days + 1
                )

                if (
                    inicio + timedelta(days=numero)
                ).weekday() == DIAS[palavra]
            ]

            dia = (
                candidatas[0]
                if len(candidatas) == 1
                else None
            )

            if dia is None:
                problema(
                    "O dia da semana não identifica uma data "
                    "única no período. Informe a data completa."
                )

            posicao += 1
            continue

        if re.fullmatch(
            r"\d{4}-\d{2}-\d{2}"
            r"|\d{1,2}/\d{1,2}(?:/\d{4})?",
            palavra,
        ):
            try:
                if "/" in palavra:
                    dia = datetime.strptime(
                        palavra,
                        "%d/%m/%Y",
                    ).date()

                else:
                    dia = date.fromisoformat(
                        palavra
                    )

                if not inicio <= dia <= fim:
                    raise ValueError()

            except ValueError:
                dia = None

                problema(
                    "Informe uma data completa e válida "
                    "dentro do período."
                )

            posicao += 1
            continue

        if palavra in LIGACOES:
            posicao += 1
            continue

        if palavra in {
            "devolveu",
            "devolucao",
            "devolucoes",
            "devolver",
        }:
            problema(
                "Use o formulário de devolução, "
                "vinculando a retirada original."
            )

            posicao += 1
            continue

        quantidade, tamanho = _quantidade(
            partes,
            posicao,
        )

        if quantidade is None:
            problema(
                "Trecho não reconhecido. Informe técnico, "
                "quantidade e nome completo do item."
            )

            posicao += 1
            continue

        comeco = posicao
        posicao += tamanho

        unidade = None

        if (
            posicao < len(partes)
            and partes[posicao] in UNIDADES
        ):
            unidade = UNIDADES[
                partes[posicao]
            ]

            posicao += 1

        if (
            posicao < len(partes)
            and partes[posicao] == "de"
        ):
            posicao += 1

        item, tamanho_item = _encontrar(
            partes,
            posicao,
            mapa_itens,
        )

        if not item:
            problema(
                "Qual é o item desta quantidade? "
                "Use o nome completo do catálogo.",
                comeco,
            )

            continue

        posicao += tamanho_item

        if (
            posicao < len(partes)
            and partes[posicao] in UNIDADES
        ):
            if unidade is not None:
                problema(
                    "Informe a unidade apenas uma vez.",
                    comeco,
                )

                posicao += 1
                continue

            unidade = UNIDADES[
                partes[posicao]
            ]

            posicao += 1

        if not tecnico or not dia:
            problema(
                "Falta técnico ou data. Informe no texto "
                "ou escolha uma data padrão.",
                comeco,
            )

            continue

        nome_sem_item = False

        if unidade and unidade != item["unit"]:
            fator = EMBALAGENS.get((
                normalizar(item["name"]),
                unidade,
            ))

            if (
                fator is None
                or quantidade != quantidade.to_integral_value()
            ):
                problema(
                    "Embalagem incompatível. "
                    "Use a unidade do catálogo.",
                    comeco,
                )

                continue

            quantidade *= fator

        try:
            linhas.append(
                _linha(
                    item,
                    tecnico,
                    dia,
                    quantidade,
                )
            )

        except (
            ValueError,
            InvalidOperation,
        ) as erro:
            problema(
                str(erro),
                comeco,
            )

        if len(linhas) > 1000:
            raise ValueError(
                "Envie até 1.000 itens por vez."
            )

    if nome_sem_item:
        problema(
            "O último técnico está sem itens."
        )

    if not linhas and not pendencias:
        problema(
            "Nenhuma retirada encontrada."
        )

    return _resultado(
        linhas,
        pendencias,
        padrao,
    )


# ==========================================================
# LIMPEZA DAS CÉLULAS DO SGP
# Lê texto de HTML sem executar código.
# ==========================================================

class _TextoCelula(HTMLParser):
    def __init__(self):
        super().__init__(
            convert_charrefs=True
        )

        self.partes = []

    def handle_starttag(self, tag, attrs):
        if tag in {
            "br",
            "p",
            "div",
            "li",
        }:
            self.partes.append("\n")

    def handle_endtag(self, tag):
        if tag in {
            "p",
            "div",
            "li",
        }:
            self.partes.append("\n")

    def handle_data(self, data):
        self.partes.append(data)


def _celula(valor):
    leitor = _TextoCelula()

    leitor.feed(
        unescape(valor).replace(
            "\xa0",
            " ",
        )
    )

    return "".join(
        leitor.partes
    ).strip()


# ==========================================================
# IDENTIFICAÇÃO DOS TÉCNICOS DO SGP
# ==========================================================

def _tecnico_sgp(destino, tecnicos):
    nome = re.sub(
        r"\btecnic[oa]\b",
        "",
        _chave(destino),
    )

    nome = " ".join(
        nome.split()
    )

    encontrados = []

    for tecnico in tecnicos:
        chave = _chave(
            tecnico["name"]
        )

        formas = [chave] + [
            _chave(apelido)

            for apelido in APELIDOS_TECNICOS.get(
                normalizar(tecnico["name"]),
                [],
            )
        ]

        # Associações adicionais fornecidas pelo app.py.
        formas += [
            " ".join(
                re.sub(
                    r"\btecnic[oa]\b",
                    "",
                    _chave(apelido),
                ).split()
            )

            for apelido in tecnico.get(
                "sgp_aliases",
                [],
            )
        ]

        if nome in formas:
            encontrados.append(tecnico)

    return (
        encontrados[0]
        if len(encontrados) == 1
        else None
    )


# ==========================================================
# IDENTIFICAÇÃO DOS PRODUTOS DO SGP
# ==========================================================

def _item_sgp(descricao, itens):
    nome = _chave(descricao)

    candidatos = []

    for item in itens:
        chave = _chave(
            item["name"]
        )

        achou = False

        if chave in {
            "apc",
            "upc",
        }:
            achou = bool(
                re.search(
                    r"\b" + chave + r"\b",
                    nome,
                )
                and "conector" in nome
            )

        elif chave == "miguelao":
            achou = bool(
                re.search(
                    r"\bmiguelao\b",
                    nome,
                )
            )

        elif chave == "cunha":
            achou = bool(
                re.search(
                    r"\bcunha\b",
                    nome,
                )
            )

        elif chave in {
            "xc220",
            "xx530",
            "xx535",
            "xx230",
        }:
            modelos = {
                "xc220": r"xc\s*220(?:\s*g3v)?",
                "xx530": r"xx\s*530",
                "xx535": r"xx\s*535",
                "xx230": r"xx\s*230v?",
            }

            achou = bool(
                re.search(
                    r"\b"
                    + modelos[chave]
                    + r"\b",
                    nome,
                )
            )

        else:
            formas = [chave] + [
                _chave(apelido)

                for apelido in APELIDOS_ITENS.get(
                    normalizar(item["name"]),
                    [],
                )
            ]

            achou = any(
                re.search(
                    r"\b"
                    + re.escape(forma)
                    + r"\b",
                    nome,
                )

                for forma in formas
            )

        if achou:
            candidatos.append(item)

    # Mais de um produto possível também gera pendência.
    return (
        candidatos[0]
        if len(candidatos) == 1
        else None
    )


# ==========================================================
# LEITURA DA TABELA
# Aceita Markdown com "|" ou texto separado por tabulações.
# ==========================================================

def _linhas_tabela(texto):
    if "|" in texto:
        return [
            linha.strip().strip("|").split("|")

            for linha in texto.splitlines()

            if "|" in linha
        ]

    return list(
        csv.reader(
            io.StringIO(texto),
            delimiter="\t",
        )
    )


# ==========================================================
# ORGANIZAÇÃO DAS MOVIMENTAÇÕES DO SGP
# ==========================================================

def _organizar_sgp(
    texto,
    tecnicos,
    itens,
    inicio,
    fim,
):
    linhas = []
    pendencias = []
    avisos = []
    eventos = []

    cabecalho = None

    ids_vistos = {}

    encontrou_registro = False

    destinos_desconhecidos = set()

    def problema(mensagem, trecho):
        pendencias.append({
            "message": mensagem,
            "excerpt": trecho[:400],
        })

    for numero, celulas in enumerate(
        _linhas_tabela(texto),
        1,
    ):
        celulas = [
            _celula(celula)
            for celula in celulas
        ]

        chaves = [
            _chave(celula)
            for celula in celulas
        ]

        # Ignora linhas vazias e separadores do Markdown.
        if not any(chaves):
            continue

        # Localiza as colunas pelo cabeçalho.
        if "id" in chaves and "itens" in chaves:
            exigidas = [
                "id",
                "data",
                "local de origem",
                "local de destino",
                "status",
                "itens",
            ]

            if not all(
                coluna in chaves
                for coluna in exigidas
            ):
                problema(
                    "Faltam colunas obrigatórias "
                    "no cabeçalho do SGP.",
                    " | ".join(celulas),
                )

                continue

            cabecalho = {
                coluna: chaves.index(coluna)
                for coluna in exigidas
            }

            continue

        if cabecalho is None:
            if any(
                re.fullmatch(
                    r"\d+",
                    celula.strip(),
                )

                for celula in celulas
            ):
                problema(
                    "Cole também o cabeçalho "
                    "da tabela do SGP.",
                    " | ".join(celulas),
                )

            continue

        if max(cabecalho.values()) >= len(celulas):
            problema(
                "Linha incompleta na tabela.",
                " | ".join(celulas),
            )

            continue

        registro = {
            coluna: celulas[posicao]
            for coluna, posicao in cabecalho.items()
        }

        sgp_id = registro["id"].strip()

        if not sgp_id.isdigit():
            problema(
                "ID de movimentação inválido.",
                " | ".join(celulas),
            )

            continue

        encontrou_registro = True

        # DATA E HORÁRIO DO SGP

        try:
            momento = None

            for formato in [
                "%d/%m/%Y %H:%M:%S",
                "%d/%m/%Y %H:%M",
                "%d/%m/%Y",
            ]:
                try:
                    momento = datetime.strptime(
                        registro["data"],
                        formato,
                    )

                    break

                except ValueError:
                    pass

            if momento is None:
                raise ValueError()

        except ValueError:
            problema(
                "Data inválida na movimentação SGP "
                + sgp_id
                + ".",
                registro["data"],
            )

            continue

        dia = momento.date()

        # FILTRO DO PERÍODO

        if not inicio <= dia <= fim:
            avisos.append(
                "SGP "
                + sgp_id
                + " — "
                + dia.strftime("%d/%m/%Y")
                + ": fora do período; não será importada."
            )

            continue

        # APENAS MOVIMENTAÇÕES APROVADAS

        if _chave(registro["status"]) != "aprovada":
            avisos.append(
                "SGP "
                + sgp_id
                + ": status "
                + registro["status"]
                + "; não será importada."
            )

            continue

        # APENAS SAÍDAS DO ALMOXARIFADO MATRIZ

        if (
            _chave(registro["local de origem"])
            != "almoxarifado matriz"
        ):
            avisos.append(
                "SGP "
                + sgp_id
                + ": a origem não é Almoxarifado Matriz; "
                "não será importada."
            )

            continue

        # IDENTIFICA O TÉCNICO

        tecnico = _tecnico_sgp(
            registro["local de destino"],
            tecnicos,
        )

        if not tecnico:
            destinos_desconhecidos.add(
                registro["local de destino"]
            )

            problema(
                "Destino ainda não associado a um técnico: "
                + registro["local de destino"]
                + ".",
                "SGP " + sgp_id,
            )

            continue

        retiradas = []
        erros_antes = len(pendencias)

        # CADA LINHA DA CÉLULA "ITENS"

        for indice, parte in enumerate(
            registro["itens"].splitlines(),
            1,
        ):
            parte = " ".join(
                parte.split()
            )

            if not parte:
                continue

            # São legendas de unidade, não produtos.
            if re.fullmatch(
                r"\((?:uni|un|pc|pcs|pç|m|mt|metros?|unidades?)\)",
                normalizar(parte),
            ):
                continue

            quantidade_final = re.fullmatch(
                r"(.+?)\s+-\s+(-?\d+(?:[.,]\d{1,3})?)",
                parte,
            )

            if not quantidade_final:
                problema(
                    "Não identifiquei a quantidade no final "
                    "do item do SGP "
                    + sgp_id
                    + ".",
                    parte,
                )

                continue

            corpo, quantidade = (
                quantidade_final.groups()
            )

            # O SGP utiliza valores como 1.0 e 100.0.
            quantidade = Decimal(
                quantidade.replace(",", ".")
            )

            segmentos = re.split(
                r"\s+-\s+",
                corpo,
            )

            serial = ""

            if (
                len(segmentos) > 1
                and re.fullmatch(
                    r"[A-Za-z0-9:_-]{6,120}",
                    segmentos[-1],
                )
            ):
                serial = segmentos.pop()

            descricao = " - ".join(
                segmentos
            )

            item = _item_sgp(
                descricao,
                itens,
            )

            if not item:
                problema(
                    "Item desconhecido ou ambíguo no SGP "
                    + sgp_id
                    + ". Não foi atribuído um preço.",
                    descricao,
                )

                continue

            try:
                linha = _linha(
                    item,
                    tecnico,
                    dia,
                    quantidade,
                )

            except (
                ValueError,
                InvalidOperation,
            ) as erro:
                problema(
                    str(erro)
                    + " no SGP "
                    + sgp_id
                    + ".",
                    parte,
                )

                continue

            linha.update(
                sgp_id=sgp_id,
                sgp_line=indice,
                sgp_serial=serial,
                sgp_description=descricao,

                sgp_datetime=momento.isoformat(
                    timespec="seconds"
                ),
            )

            retiradas.append(linha)

        if (
            not retiradas
            and len(pendencias) == erros_antes
        ):
            problema(
                "A movimentação SGP "
                + sgp_id
                + " está sem itens.",
                registro["itens"],
            )

        # Não aproveita parcialmente uma movimentação com erros.
        # A confirmação geral também será bloqueada.
        if len(pendencias) != erros_antes:
            continue

        # ASSINATURA DO CONTEÚDO DE CADA ID

        canonico = sorted(
            (
                linha["item_id"],

                format(
                    Decimal(
                        linha["quantity"]
                    ).normalize(),
                    "f",
                ),

                linha["sgp_serial"],

                _chave(
                    linha["sgp_description"]
                ),
            )

            for linha in retiradas
        )

        assinatura = hashlib.sha256(
            json.dumps(
                [
                    momento.isoformat(),
                    tecnico["id"],
                    canonico,
                ],

                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

        # REPETIÇÃO DENTRO DA MESMA TABELA COLADA

        if sgp_id in ids_vistos:
            if ids_vistos[sgp_id] != assinatura:
                problema(
                    "O ID SGP "
                    + sgp_id
                    + " aparece com conteúdos diferentes. "
                    "Confira a tabela.",
                    sgp_id,
                )

            else:
                avisos.append(
                    "SGP "
                    + sgp_id
                    + ": repetida na tabela colada; "
                    "considerada apenas uma vez."
                )

            continue

        ids_vistos[sgp_id] = assinatura

        linhas.extend(retiradas)

        eventos.append({
            "id": sgp_id,
            "fingerprint": assinatura,
            "date": dia.isoformat(),
            "technician_id": tecnico["id"],

            "datetime": momento.isoformat(
                timespec="seconds"
            ),
        })

        if len(linhas) > 1000:
            raise ValueError(
                "Cole até 1.000 itens por vez."
            )

    if not encontrou_registro:
        problema(
            "Nenhuma movimentação encontrada. "
            "Cole o cabeçalho e as linhas da tabela do SGP.",
            "",
        )

    resultado = _resultado(
        linhas,
        pendencias,
        avisos=avisos,
        eventos=eventos,
        formato="sgp",
    )

    resultado["unknown_technicians"] = sorted(
        destinos_desconhecidos
    )

    return resultado


# ==========================================================
# ENTRADA PRINCIPAL UTILIZADA PELO APP.PY
# ==========================================================

def organizar_retiradas(
    texto,
    tecnicos,
    itens,
    inicio,
    fim,
    data_padrao=None,
    hoje=None,
):
    hoje = hoje or date.today()

    inicio = date.fromisoformat(inicio)
    fim = date.fromisoformat(fim)

    if (
        fim < inicio
        or (fim - inicio).days > 366
        or fim > hoje
    ):
        raise ValueError(
            "Escolha um período válido de até 367 dias, "
            "sem datas futuras."
        )

    if (
        not isinstance(texto, str)
        or not texto.strip()
        or len(texto) > 200000
    ):
        raise ValueError(
            "Cole ou escreva as retiradas "
            "em até 200.000 caracteres."
        )

    # TABELA COPIADA DO SGP
    if "|" in texto or "\t" in texto:
        return _organizar_sgp(
            texto,
            tecnicos,
            itens,
            inicio,
            fim,
        )

    # TEXTO DIGITADO MANUALMENTE
    padrao = (
        date.fromisoformat(data_padrao)
        if data_padrao
        else None
    )

    if padrao and not inicio <= padrao <= fim:
        raise ValueError(
            "A data padrão deve estar dentro do período."
        )

    return _organizar_texto(
        texto,
        tecnicos,
        itens,
        inicio,
        fim,
        padrao,
    )
