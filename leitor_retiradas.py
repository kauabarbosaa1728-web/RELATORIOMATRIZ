"""
ALMOXARIFADO MATRIZ — LEITURA DE RETIRADAS

Organiza retiradas escritas em texto.

Este arquivo:
- Não grava movimentações.
- Não altera o banco de dados.
- Não gera links sozinho.
- Retorna uma prévia e as pendências encontradas.

Qualquer pendência impede a confirmação do texto inteiro.
"""

import re
import unicodedata

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation


# NOMES ALTERNATIVOS CONHECIDOS

APELIDOS_TECNICOS = {
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

    "xc220": [
        "xc 220",
    ],

    "xx530": [
        "xx 530",
    ],

    "xx535": [
        "xx 535",
    ],

    "xx230": [
        "xx 230",
    ],

    "121ac": [
        "121 ac",
    ],

    "1200r": [
        "1200 r",
    ],

    "ex141": [
        "ex 141",
    ],

    "halos12": [
        "halo s12",
        "halo s 12",
        "halos 12",
    ],

    "mr60x": [
        "mr 60x",
    ],

    "onu 1010": [
        "onu1010",
    ],

    "firestick": [
        "fire stick",
    ],
}


# QUANTIDADES POR EXTENSO
# Quantidades maiores também podem ser escritas em algarismos.

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


# PALAVRAS ACEITAS ENTRE OS DADOS

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


# UNIDADES E EMBALAGENS

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

# Conversões para a unidade usada no catálogo.
# Não faz conversões de embalagens desconhecidas.

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


# NORMALIZAÇÃO

def normalizar(texto):
    return "".join(
        caractere
        for caractere in unicodedata.normalize(
            "NFKD",
            texto.lower(),
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

    # Nomes completos são procurados antes dos nomes menores.
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

    # Sem separador de milhar para evitar interpretações ambíguas.
    # Exemplos aceitos: 1000, 12,5 e 0,125.
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


# ORGANIZAÇÃO DO TEXTO

def organizar_retiradas(
    texto,
    tecnicos,
    itens,
    inicio,
    fim,
    data_padrao=None,
    hoje=None,
):
    """
    Recebe:
        texto: retiradas escritas pelo usuário.

        tecnicos:
            [{"id": 1, "name": "Rogério"}, ...]

        itens:
            [{
                "id": 1,
                "name": "APC",
                "unit": "un",
                "category": "material",
                "cost": "6.10",
            }, ...]

        inicio e fim:
            Datas ISO: "2026-10-12".

        data_padrao:
            Data escolhida explicitamente pelo usuário
            para as retiradas que não possuem data no texto.

        hoje:
            Data atual de Brasília fornecida pelo app.py.

    Retorna:
        rows: itens reconhecidos.
        issues: pendências.
        can_confirm: se o texto inteiro pode ser confirmado.

    Não grava dados.
    """

    hoje = hoje or date.today()

    inicio = date.fromisoformat(inicio)
    fim = date.fromisoformat(fim)

    if (
        fim < inicio
        or (fim - inicio).days > 366
        or fim > hoje
    ):
        raise ValueError(
            "Selecione um período válido, sem datas futuras."
        )

    padrao = (
        date.fromisoformat(data_padrao)
        if data_padrao
        else None
    )

    if padrao and not inicio <= padrao <= fim:
        raise ValueError(
            "A data padrão deve estar dentro do período."
        )

    if (
        not isinstance(texto, str)
        or not texto.strip()
        or len(texto) > 20000
    ):
        raise ValueError(
            "Escreva as retiradas em até 20.000 caracteres."
        )

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

        trecho = " ".join(
            partes[max(0, pos - 2):pos + 7]
        )

        pendencias.append({
            "message": mensagem,
            "excerpt": trecho,
        })

    while posicao < len(partes):
        palavra = partes[posicao]

        if palavra in {
            ",",
            ";",
            ":",
            ".",
            "(",
            ")",
        }:
            posicao += 1
            continue

        # Aceita o hífen em "segunda-feira", etc.
        if (
            palavra == "-"
            and posicao
            and partes[posicao - 1] in DIAS
        ):
            posicao += 1
            continue

        # TÉCNICO

        encontrado, tamanho = _encontrar(
            partes,
            posicao,
            mapa_tecnicos,
        )

        if encontrado:
            if nome_sem_item:
                problema(
                    "Há dois técnicos sem itens entre eles. "
                    "Separe as retiradas de cada um."
                )

            tecnico = encontrado
            nome_sem_item = True

            posicao += tamanho
            continue

        # DIA DA SEMANA

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

            if len(candidatas) != 1:
                problema(
                    "Este dia da semana aparece mais de uma "
                    "vez no período. Informe a data completa."
                )

                dia = None

            else:
                dia = candidatas[0]

            posicao += 1
            continue

        # DATA COMPLETA

        if re.fullmatch(
            r"\d{4}-\d{2}-\d{2}"
            r"|\d{1,2}/\d{1,2}(?:/\d{4})?",
            palavra,
        ):
            try:
                if "/" in palavra:
                    pedacos = palavra.split("/")

                    if len(pedacos) != 3:
                        raise ValueError()

                    novo_dia = date(
                        int(pedacos[2]),
                        int(pedacos[1]),
                        int(pedacos[0]),
                    )

                else:
                    novo_dia = date.fromisoformat(
                        palavra
                    )

                if not inicio <= novo_dia <= fim:
                    raise ValueError()

                dia = novo_dia

            except ValueError:
                dia = None

                problema(
                    "Informe uma data completa e válida "
                    "dentro do período."
                )

            posicao += 1
            continue

        # PALAVRAS DE LIGAÇÃO

        if palavra in LIGACOES:
            posicao += 1
            continue

        # DEVOLUÇÕES EXIGEM VÍNCULO COM A RETIRADA ORIGINAL

        if palavra in {
            "devolveu",
            "devolucao",
            "devolucoes",
            "devolver",
        }:
            problema(
                "Registre devoluções pelo formulário próprio, "
                "vinculando a retirada original."
            )

            posicao += 1
            continue

        # QUANTIDADE

        quantidade, tamanho = _quantidade(
            partes,
            posicao,
        )

        if quantidade is None:
            problema(
                "Trecho não reconhecido. Especifique o técnico, "
                "a quantidade e o nome do item."
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

        # ITEM DO CATÁLOGO

        item, tamanho_item = _encontrar(
            partes,
            posicao,
            mapa_itens,
        )

        if not item:
            problema(
                "Qual é o item desta quantidade? Use o nome "
                "completo, como APC ou Cabo Miniflatdrop.",
                comeco,
            )

            continue

        posicao += tamanho_item

        # Também aceita a unidade depois do nome do item.
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

        # VALIDAÇÃO DO TÉCNICO E DA DATA

        if not tecnico or not dia:
            problema(
                "Falta técnico ou data. Informe no texto "
                "ou selecione uma data padrão.",
                comeco,
            )

            continue

        nome_sem_item = False

        # CONVERSÃO DAS EMBALAGENS CONHECIDAS

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
                    "Embalagem incompatível ou fracionada. "
                    "Informe a quantidade na unidade do catálogo.",
                    comeco,
                )

                continue

            quantidade *= fator

        # LIMITES DAS QUANTIDADES

        if (
            quantidade <= 0
            or quantidade > 1000000
            or (
                item["unit"] != "m"
                and quantidade != quantidade.to_integral_value()
            )
        ):
            problema(
                "Quantidade inválida para este item.",
                comeco,
            )

            continue

        # CUSTO DO CATÁLOGO

        try:
            custo = Decimal(
                str(item["cost"])
            )

            if not custo.is_finite() or custo < 0:
                raise InvalidOperation()

        except (
            InvalidOperation,
            ValueError,
        ):
            problema(
                "O custo do item está inválido no catálogo.",
                comeco,
            )

            continue

        linhas.append({
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
        })

        if len(linhas) > 500:
            raise ValueError(
                "Envie no máximo 500 itens por vez."
            )

    if nome_sem_item:
        problema(
            "O último técnico informado está sem itens."
        )

    if not linhas and not pendencias:
        problema(
            "Nenhuma retirada encontrada."
        )

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

        "can_confirm": (
            bool(linhas)
            and not pendencias
        ),

        "used_default_date": (
            padrao.isoformat()
            if padrao
            else None
        ),
    }
