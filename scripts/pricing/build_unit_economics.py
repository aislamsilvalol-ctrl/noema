#!/usr/bin/env python
"""Gera a planilha de economia unitária do NOEMA.

    uv run --with openpyxl python scripts/pricing/build_unit_economics.py

Escreve `docs/pricing/noema-unit-economics.xlsx`. Todo número de entrada vem de
`docs/pricing/PRICING_AUDIT.md`, `market-2026-10-19.md` e
`usage-audit-2026-10-19.md`; o que não está lá é marcado como premissa. Toda
célula derivada é uma fórmula do Excel que aponta para as células de entrada
(fonte azul, fundo amarelo), para o dono editar e tudo recalcular.

openpyxl não é dependência da aplicação; por isso o `--with`.
"""

# Rótulos longos em português, com sinais tipográficos de propósito: são texto da planilha.
# ruff: noqa: E501, RUF001

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.worksheet import Worksheet

OUT = (
    Path(__file__).resolve().parents[2] / "docs" / "pricing" / "noema-unit-economics.xlsx"
)

DATA_PRECOS = "2026-10-19"
FONTE_ANTHROPIC = "https://platform.claude.com/docs/en/about-claude/pricing"
FONTE_OPENAI = "https://developers.openai.com/api/docs/pricing"

# --- estilos -------------------------------------------------------------------

INPUT_FONT = Font(color="1F4E9E", bold=False)
INPUT_FILL = PatternFill("solid", fgColor="FFF8D6")
TITLE_FONT = Font(bold=True, size=14)
HEADER_FONT = Font(bold=True)
HEADER_FILL = PatternFill("solid", fgColor="E7E6E6")
NOTE_FONT = Font(italic=True, color="595959", size=9)
REF_FONT = Font(italic=True, color="7F7F7F")
KEY_FILL = PatternFill("solid", fgColor="E2F0D9")
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

FMT_BRL = '"R$" #,##0.00'
FMT_USD = '"US$" #,##0.0000'
FMT_CENTS = "0.000"
FMT_PCT = "0.0%"
FMT_INT = "#,##0"
FMT_MTOK = "0.000"


def title(ws: Worksheet, text: str, note: str | None = None) -> None:
    ws["A1"] = text
    ws["A1"].font = TITLE_FONT
    if note:
        ws["A2"] = note
        ws["A2"].font = NOTE_FONT


def header(ws: Worksheet, row: int, labels: list[str], col: int = 1) -> None:
    for i, label in enumerate(labels):
        c = ws.cell(row=row, column=col + i, value=label)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.border = BOX
        c.alignment = Alignment(wrap_text=True, vertical="center")


def put(
    ws: Worksheet, ref: str, value: object, fmt: str | None = None, *, kind: str = "out"
):
    """Escreve `value` em `ref`. kind: 'in' (editável), 'out' (fórmula), 'ref' (auditoria)."""
    c = ws[ref]
    c.value = value
    if fmt:
        c.number_format = fmt
    c.border = BOX
    if kind == "in":
        c.font = INPUT_FONT
        c.fill = INPUT_FILL
    elif kind == "ref":
        c.font = REF_FONT
    elif kind == "key":
        c.fill = KEY_FILL
        c.font = HEADER_FONT
    return c


def label(ws: Worksheet, ref: str, text: str, *, bold: bool = False) -> None:
    c = ws[ref]
    c.value = text
    c.border = BOX
    if bold:
        c.font = HEADER_FONT


def note(ws: Worksheet, ref: str, text: str) -> None:
    c = ws[ref]
    c.value = text
    c.font = NOTE_FONT


def widths(ws: Worksheet, sizes: dict[str, int]) -> None:
    for col, size in sizes.items():
        ws.column_dimensions[col].width = size


def absref(sheet: str, cell: str) -> str:
    col = "".join(ch for ch in cell if ch.isalpha())
    row = "".join(ch for ch in cell if ch.isdigit())
    return f"'{sheet}'!${col}${row}"


# --- Premissas -----------------------------------------------------------------

PREMISSAS = "Premissas"

# nome -> (linha, rótulo, valor, formato, unidade/nota)
PREMISSAS_ROWS: list[tuple[str, str, object, str, str]] = [
    (
        "fx",
        "Câmbio de planejamento (R$ por US$)",
        5.65,
        "0.00",
        "PRICING_AUDIT: PTAX + ~12% de buffer",
    ),
    ("ptax", "PTAX venda em 19/10/2026", 5.0564, "0.0000", "market-2026-10-19 §3 (BCB)"),
    (
        "imposto",
        "Imposto sobre a receita",
        0.06,
        FMT_PCT,
        "PRICING_AUDIT, risco 6: regime ainda indefinido",
    ),
    (
        "gw_pct",
        "Gateway: cartão (Stripe BR)",
        0.0399,
        "0.00%",
        "market §4: 3,99% + R$ 0,39",
    ),
    ("gw_fixo", "Gateway: fixo por cobrança (R$)", 0.39, FMT_BRL, "market §4"),
    ("gw_billing", "Gateway: Stripe Billing (% do volume)", 0.007, "0.00%", "market §4"),
    (
        "reembolso",
        "Reembolsos (% da receita)",
        0.02,
        FMT_PCT,
        "PRICING_AUDIT, tetos de CAC",
    ),
    ("churn", "Churn mensal", 0.10, FMT_PCT, "PRICING_AUDIT, caso base"),
    (
        "conversao",
        "Conversão cadastro → pagante",
        0.03,
        FMT_PCT,
        "PRICING_AUDIT (instável até dados reais)",
    ),
    ("ltv_cac", "LTV:CAC alvo", 3, "0", "PRICING_AUDIT"),
    ("payback", "Payback do CAC (meses)", 3, "0", "PRICING_AUDIT"),
    (
        "margem_base",
        "Margem bruta do caso base (para o CAC)",
        0.70,
        FMT_PCT,
        "PRICING_AUDIT: 'alvo realista pós-otimização'",
    ),
    ("mix_plus", "Mix de pagantes: Plus", 0.80, FMT_PCT, "PRICING_AUDIT, tetos de CAC"),
    ("mix_pro", "Mix de pagantes: Pro", 0.20, FMT_PCT, "PRICING_AUDIT, tetos de CAC"),
    (
        "trocas_aula",
        "Trocas por aula",
        10,
        "0",
        "PRICING_AUDIT: 'aula de 10 trocas' (até ~12)",
    ),
    (
        "credito_usd",
        "1 crédito interno = US$ de custo de lista",
        0.001,
        "0.000",
        "PRICING_AUDIT, limites internos",
    ),
    (
        "rota_freq",
        "Classificador de rota: % das trocas em que roda",
        0.35,
        FMT_PCT,
        "usage-audit A3: ~35%",
    ),
    (
        "batch_desc",
        "Desconto batch (ingestão de PDF)",
        0.50,
        FMT_PCT,
        "market §1: batch = 50% nos dois provedores",
    ),
]

PREM_FIRST_ROW = 5
PREM: dict[str, str] = {}  # nome -> referência absoluta


def build_premissas(wb: Workbook) -> None:
    ws = wb.active
    ws.title = PREMISSAS
    title(
        ws,
        "Premissas",
        "Células azuis sobre fundo amarelo são entradas. Edite-as; o resto recalcula.",
    )
    header(ws, 4, ["", "Premissa", "Valor", "Fonte / nota"])
    for i, (name, text, value, fmt, src) in enumerate(PREMISSAS_ROWS):
        r = PREM_FIRST_ROW + i
        label(ws, f"B{r}", text)
        put(ws, f"C{r}", value, fmt, kind="in")
        note(ws, f"D{r}", src)
        PREM[name] = absref(PREMISSAS, f"C{r}")
    r = PREM_FIRST_ROW + len(PREMISSAS_ROWS)
    label(
        ws,
        f"B{r}",
        "Deduções sobre a receita (imposto + reembolsos + gateway %)",
        bold=True,
    )
    put(
        ws,
        f"C{r}",
        f"={PREM['imposto']}+{PREM['reembolso']}+{PREM['gw_pct']}+{PREM['gw_billing']}",
        "0.00%",
    )
    note(ws, f"D{r}", "Receita líquida = preço × (1 − deduções) − fixo do gateway")
    PREM["deducoes"] = absref(PREMISSAS, f"C{r}")
    r += 1
    label(ws, f"B{r}", "Verificação: mix Plus + Pro", bold=True)
    put(ws, f"C{r}", f"={PREM['mix_plus']}+{PREM['mix_pro']}", FMT_PCT)
    note(ws, f"D{r}", "Deve dar 100%")
    widths(ws, {"A": 2, "B": 52, "C": 14, "D": 60})


# --- Preços API ----------------------------------------------------------------

PRECOS = "Preços API"

# (provedor, modelo, input, cache leitura, cache escrita 5 min, output, observação)
MODELOS: list[tuple[str, str, float, float, float, float, str]] = [
    (
        "Anthropic",
        "Haiku 5.5",
        0.10,
        0.01,
        0.125,
        0.50,
        "Prompt até 100K; acima: 0,50 / 0,05 / 2,50",
    ),
    (
        "Anthropic",
        "Sonnet 5.5",
        2.00,
        0.10,
        2.50,
        10.00,
        "Leitura de cache 0,05× o input",
    ),
    ("Anthropic", "Opus 5.5", 4.00, 0.20, 5.00, 20.00, "Leitura de cache 0,05× o input"),
    ("OpenAI", "GPT-5.6 Luna", 0.20, 0.02, 0.25, 1.20, "Substituto do gpt-4.1-nano"),
    ("OpenAI", "GPT-5.6 Terra", 2.00, 0.20, 2.50, 12.00, ""),
    (
        "OpenAI",
        "GPT-5.6 Sol",
        4.00,
        0.40,
        5.00,
        20.00,
        "Acima de 272K de input: 2× input, 1,5× output",
    ),
    (
        "OpenAI",
        "gpt-4.1",
        2.00,
        0.50,
        2.00,
        8.00,
        "Sai em 14/01/2027. Sem sobretaxa de escrita de cache",
    ),
    (
        "OpenAI",
        "gpt-4.1-mini",
        0.40,
        0.10,
        0.40,
        1.60,
        "Sai em 14/01/2027. Sem sobretaxa de escrita de cache",
    ),
    ("OpenAI", "text-embedding-3-small", 0.02, 0.0, 0.0, 0.0, "Só input"),
]
PRECOS_FIRST_ROW = 5
MODEL_ROW: dict[str, int] = {}
CHAT_MODELS = [m[1] for m in MODELOS if not m[1].startswith("text-embedding")]


def build_precos(wb: Workbook) -> None:
    ws = wb.create_sheet(PRECOS)
    title(
        ws,
        "Preços oficiais das APIs (US$ por 1M tokens)",
        f"Consultados em {DATA_PRECOS} nas páginas dos provedores (market-2026-10-19.md §1). "
        "Batch = 50% de desconto; residência de dados = +10%.",
    )
    header(
        ws,
        4,
        [
            "Provedor",
            "Modelo",
            "Input",
            "Cache (leitura)",
            "Cache (escrita, 5 min)",
            "Output",
            "Fonte",
            "Data",
            "Observação",
        ],
    )
    for i, (prov, model, p_in, p_cache, p_write, p_out, obs) in enumerate(MODELOS):
        r = PRECOS_FIRST_ROW + i
        MODEL_ROW[model] = r
        label(ws, f"A{r}", prov)
        label(ws, f"B{r}", model, bold=True)
        put(ws, f"C{r}", p_in, FMT_MTOK, kind="in")
        put(ws, f"D{r}", p_cache, FMT_MTOK, kind="in")
        put(ws, f"E{r}", p_write, FMT_MTOK, kind="in")
        put(ws, f"F{r}", p_out, FMT_MTOK, kind="in")
        src = FONTE_ANTHROPIC if prov == "Anthropic" else FONTE_OPENAI
        put(ws, f"G{r}", src)
        put(ws, f"H{r}", DATA_PRECOS)
        put(ws, f"I{r}", obs)
    widths(
        ws,
        {"A": 11, "B": 24, "C": 10, "D": 14, "E": 18, "F": 10, "G": 58, "H": 12, "I": 50},
    )


def price(model: str, col: str) -> str:
    """Referência absoluta ao preço (col C=input, D=cache, E=escrita, F=output)."""
    return absref(PRECOS, f"{col}{MODEL_ROW[model]}")


# --- Custo por operação ------------------------------------------------------------

CUSTO = "Custo por operação"

# (chave, operação, input novo, input em cache, escrita de cache, output, fonte)
OPERACOES: list[tuple[str, str, int, int, int, int, str]] = [
    (
        "troca",
        "Troca com o Mino (chamada de ensino)",
        800,
        4500,
        0,
        500,
        "PRICING_AUDIT: 800 novos, 4.500 em cache. Saída: ver nota abaixo da tabela",
    ),
    ("rota", "Classificador de rota", 765, 0, 0, 15, "usage-audit C1"),
    ("parse", "Parse do objetivo", 350, 0, 0, 120, "usage-audit C2"),
    ("curriculo", "Currículo", 550, 0, 0, 1200, "usage-audit C2"),
    ("quiz", "Quiz de checkpoint (assessment)", 2400, 0, 0, 1100, "usage-audit C2"),
    ("cards", "Lote de flashcards", 1800, 0, 0, 300, "usage-audit C2"),
    ("compact", "Compactação de memória", 5500, 0, 0, 450, "usage-audit C2"),
    (
        "extracao",
        "Extração de conceitos (lote de 5 chunks)",
        3000,
        0,
        0,
        400,
        "usage-audit C5",
    ),
]
OPS_FIRST_ROW = 5
OPS_ROW: dict[str, int] = {}
MODEL_COL: dict[str, str] = {}  # modelo -> letra da coluna de custo (US¢)
CUSTO_REF: dict[str, str] = {}  # saídas usadas por outras abas


def build_custo(wb: Workbook) -> None:
    ws = wb.create_sheet(CUSTO)
    title(
        ws,
        "Custo por operação (US¢ por chamada, preço de lista)",
        "custo = (input novo × p_in + cache × p_cache + escrita × p_escrita + output × p_out) ÷ 1e6 × 100",
    )
    # Os cabeçalhos dos modelos são o nome puro: as listas de seleção abaixo fazem MATCH neles.
    cols = [
        "Operação",
        "Input novo (tok)",
        "Input em cache (tok)",
        "Escrita de cache (tok)",
        "Output (tok)",
    ]
    cols += [*CHAT_MODELS, "Fonte"]
    header(ws, 4, cols, col=2)
    first_model_col = 2 + 5  # coluna G
    for j, model in enumerate(CHAT_MODELS):
        MODEL_COL[model] = get_column_letter(first_model_col + j)
    fonte_col = get_column_letter(first_model_col + len(CHAT_MODELS))

    for i, (key, name, fresh, cached, write, out, src) in enumerate(OPERACOES):
        r = OPS_FIRST_ROW + i
        OPS_ROW[key] = r
        label(ws, f"B{r}", name)
        put(ws, f"C{r}", fresh, FMT_INT, kind="in")
        put(ws, f"D{r}", cached, FMT_INT, kind="in")
        put(ws, f"E{r}", write, FMT_INT, kind="in")
        put(ws, f"F{r}", out, FMT_INT, kind="in")
        for model in CHAT_MODELS:
            col = MODEL_COL[model]
            f = (
                f"=($C{r}*{price(model, 'C')}+$D{r}*{price(model, 'D')}"
                f"+$E{r}*{price(model, 'E')}+$F{r}*{price(model, 'F')})/1000000*100"
            )
            put(ws, f"{col}{r}", f, FMT_CENTS)
        note(ws, f"{fonte_col}{r}", src)

    r = OPS_FIRST_ROW + len(OPERACOES) + 1
    note(
        ws,
        f"B{r}",
        "Saída da troca: a auditoria escreve 'saída média de 300', mas os seus resultados "
        "(0,74¢ / 0,34¢ por troca; R$ 104,56 / R$ 47,99 para 2.500 trocas) só fecham com 500 "
        "tokens de saída (ou 1.800 de input novo). A planilha usa 500 para reproduzir a auditoria; "
        "com 300 a troca conservadora cai para ~0,53¢.",
    )

    # --- Roteamento da troca -------------------------------------------------
    r0 = r + 2
    ws[f"B{r0}"] = "Roteamento da troca com o Mino"
    ws[f"B{r0}"].font = HEADER_FONT
    header(
        ws,
        r0 + 1,
        ["Modelo", "Conservador", "Otimizado", "Custo da troca no modelo (US¢)"],
        col=2,
    )
    mix = {"Haiku 5.5": (0.0, 0.60), "Sonnet 5.5": (0.95, 0.35), "Opus 5.5": (0.05, 0.05)}
    mix_first = r0 + 2
    for i, (model, (cons, opt)) in enumerate(mix.items()):
        rr = mix_first + i
        label(ws, f"B{rr}", model)
        put(ws, f"C{rr}", cons, FMT_PCT, kind="in")
        put(ws, f"D{rr}", opt, FMT_PCT, kind="in")
        put(ws, f"E{rr}", f"={MODEL_COL[model]}{OPS_ROW['troca']}", FMT_CENTS)
    mix_last = mix_first + len(mix) - 1
    rr = mix_last + 1
    label(ws, f"B{rr}", "Soma (deve dar 100%)", bold=True)
    put(ws, f"C{rr}", f"=SUM(C{mix_first}:C{mix_last})", FMT_PCT)
    put(ws, f"D{rr}", f"=SUM(D{mix_first}:D{mix_last})", FMT_PCT)
    note(
        ws,
        f"F{mix_first}",
        "PRICING_AUDIT, premissas das colunas: conservador = Sonnet 95% + Opus 5%;",
    )
    note(
        ws,
        f"F{mix_first + 1}",
        "otimizado = Haiku 60% + Sonnet 35% + Opus 5% (se o Haiku passar no eval).",
    )

    rr += 1
    label(ws, f"B{rr}", "Custo médio por troca (US¢)", bold=True)
    put(
        ws,
        f"C{rr}",
        f"=SUMPRODUCT(C{mix_first}:C{mix_last},$E${mix_first}:$E${mix_last})",
        FMT_CENTS,
        kind="key",
    )
    put(
        ws,
        f"D{rr}",
        f"=SUMPRODUCT(D{mix_first}:D{mix_last},$E${mix_first}:$E${mix_last})",
        FMT_CENTS,
        kind="key",
    )
    put(ws, f"E{rr}", 0.74, FMT_CENTS, kind="ref")
    put(ws, f"F{rr}", 0.34, FMT_CENTS, kind="ref")
    note(ws, f"G{rr}", "← auditoria: 0,74¢ / 0,34¢")
    CUSTO_REF["troca_cons"] = absref(CUSTO, f"C{rr}")
    CUSTO_REF["troca_opt"] = absref(CUSTO, f"D{rr}")
    rr += 1
    label(ws, f"B{rr}", "Custo médio por troca (R$)")
    put(ws, f"C{rr}", f"=C{rr - 1}/100*{PREM['fx']}", "0.0000")
    put(ws, f"D{rr}", f"=D{rr - 1}/100*{PREM['fx']}", "0.0000")
    rr += 1
    label(ws, f"B{rr}", "Troca + classificador de rota (US¢, informativo)")
    put(
        ws,
        f"C{rr}",
        f"=C{rr - 2}+{PREM['rota_freq']}*{MODEL_COL['Haiku 5.5']}{OPS_ROW['rota']}",
        FMT_CENTS,
    )
    put(
        ws,
        f"D{rr}",
        f"=D{rr - 2}+{PREM['rota_freq']}*{MODEL_COL['Haiku 5.5']}{OPS_ROW['rota']}",
        FMT_CENTS,
    )
    note(
        ws,
        f"E{rr}",
        "A auditoria não inclui a rota no custo da troca; ela entra nas chamadas laterais da aula.",
    )

    # --- Chamadas laterais ---------------------------------------------------------
    r1 = rr + 2
    ws[f"B{r1}"] = "Chamadas laterais: modelo por cenário"
    ws[f"B{r1}"].font = HEADER_FONT
    header(
        ws,
        r1 + 1,
        [
            "Operação",
            "Modelo (conservador)",
            "Custo conservador (US¢)",
            "Modelo (otimizado)",
            "Custo otimizado (US¢)",
            "Auditoria cons. (US¢)",
            "Auditoria otim. (US¢)",
        ],
        col=2,
    )
    first_model_letter = MODEL_COL[CHAT_MODELS[0]]
    last_model_letter = MODEL_COL[CHAT_MODELS[-1]]
    hdr = f"${first_model_letter}$4:${last_model_letter}$4"
    dv = DataValidation(type="list", formula1=f"={hdr}", allow_blank=False)
    ws.add_data_validation(dv)

    def cost_lookup(keys: list[str], model_cell: str) -> str:
        parts = [
            f"INDEX(${first_model_letter}${OPS_ROW[k]}:${last_model_letter}${OPS_ROW[k]},1,MATCH({model_cell},{hdr},0))"
            for k in keys
        ]
        return "=" + "+".join(parts)

    laterais: list[tuple[str, str, list[str], float | None, float | None]] = [
        ("rota", "Classificador de rota", ["rota"], None, None),
        (
            "materia",
            "Matéria nova (parse + currículo)",
            ["parse", "curriculo"],
            0.1,
            0.02,
        ),
        ("quiz", "Quiz de checkpoint", ["quiz"], 0.3, 0.1),
        ("cards", "Lote de flashcards", ["cards"], 0.02, 0.02),
        ("compact", "Compactação de memória", ["compact"], 0.03, 0.03),
    ]
    lat_row: dict[str, int] = {}
    for i, (key, name, parts, aud_c, aud_o) in enumerate(laterais):
        rr = r1 + 2 + i
        lat_row[key] = rr
        label(ws, f"B{rr}", name)
        put(ws, f"C{rr}", "Haiku 5.5", kind="in")
        put(ws, f"D{rr}", cost_lookup(parts, f"$C{rr}"), FMT_CENTS)
        put(ws, f"E{rr}", "Haiku 5.5", kind="in")
        put(ws, f"F{rr}", cost_lookup(parts, f"$E{rr}"), FMT_CENTS)
        dv.add(ws[f"C{rr}"])
        dv.add(ws[f"E{rr}"])
        if aud_c is not None:
            put(ws, f"G{rr}", aud_c, FMT_CENTS, kind="ref")
            put(ws, f"H{rr}", aud_o, FMT_CENTS, kind="ref")
    rr = r1 + 2 + len(laterais)
    note(
        ws,
        f"B{rr}",
        "Roteamento proposto (PRICING_AUDIT): rota, parse, compactação e flashcards no Haiku 5.5. "
        "A tabela de roteamento põe o currículo no Sonnet 5.5, mas a 'matéria nova' a 0,1¢ só é "
        "possível no Haiku; a planilha usa Haiku e mostra a referência da auditoria ao lado.",
    )

    # --- PDF de 100 páginas ---------------------------------------------------------
    r2 = rr + 2
    ws[f"B{r2}"] = "PDF (ingestão no worker)"
    ws[f"B{r2}"].font = HEADER_FONT
    pdf_rows: list[tuple[str, str, object, str, str, str]] = [
        ("paginas", "Páginas", 100, FMT_INT, "in", "PRICING_AUDIT"),
        ("chunks_pag", "Chunks por página", 1.15, "0.00", "in", "usage-audit C5"),
        (
            "embed_tok",
            "Tokens de embedding por página",
            630,
            FMT_INT,
            "in",
            "usage-audit C5",
        ),
        ("chunks_lote", "Chunks por chamada de extração", 5, "0", "in", "usage-audit C5"),
        (
            "modelo_extr",
            "Modelo da extração",
            "Haiku 5.5",
            "",
            "in",
            "PRICING_AUDIT: Haiku 5.5 (batch quando der)",
        ),
    ]
    prow: dict[str, int] = {}
    for i, (key, name, value, fmt, kind, src) in enumerate(pdf_rows):
        rr = r2 + 1 + i
        prow[key] = rr
        label(ws, f"B{rr}", name)
        put(ws, f"C{rr}", value, fmt or None, kind=kind)
        note(ws, f"D{rr}", src)
    dv.add(ws[f"C{prow['modelo_extr']}"])
    rr = r2 + 1 + len(pdf_rows)
    label(ws, f"B{rr}", "Chamadas de extração")
    put(
        ws,
        f"C{rr}",
        f"=C{prow['paginas']}*C{prow['chunks_pag']}/C{prow['chunks_lote']}",
        "0.0",
    )
    extr_calls = rr
    rr += 1
    label(ws, f"B{rr}", "Custo da extração com desconto batch (US¢)")
    put(
        ws,
        f"C{rr}",
        f"=C{extr_calls}*INDEX(${first_model_letter}${OPS_ROW['extracao']}:${last_model_letter}${OPS_ROW['extracao']},1,"
        f"MATCH($C${prow['modelo_extr']},{hdr},0))*(1-{PREM['batch_desc']})",
        FMT_CENTS,
    )
    extr_cost = rr
    rr += 1
    label(ws, f"B{rr}", "Custo dos embeddings (US¢)")
    put(
        ws,
        f"C{rr}",
        f"=C{prow['paginas']}*C{prow['embed_tok']}*{price('text-embedding-3-small', 'C')}/1000000*100",
        FMT_CENTS,
    )
    embed_cost = rr
    rr += 1
    label(ws, f"B{rr}", "PDF completo (US¢)", bold=True)
    put(ws, f"C{rr}", f"=C{extr_cost}+C{embed_cost}", FMT_CENTS, kind="key")
    put(ws, f"D{rr}", 0.6, FMT_CENTS, kind="ref")
    note(ws, f"E{rr}", "← auditoria: ~0,6¢ (igual nos dois cenários)")
    CUSTO_REF["pdf"] = absref(CUSTO, f"C{rr}")
    rr += 1
    label(ws, f"B{rr}", "PDF completo (R$)")
    put(ws, f"C{rr}", f"=C{rr - 1}/100*{PREM['fx']}", "0.0000")

    # --- Aula de N trocas -------------------------------------------------------------
    r3 = rr + 2
    ws[f"B{r3}"] = "Aula (trocas + chamadas laterais)"
    ws[f"B{r3}"].font = HEADER_FONT
    header(
        ws,
        r3 + 1,
        ["Item", "Qtd. por aula", "Conservador (US¢)", "Otimizado (US¢)"],
        col=2,
    )
    aula_items: list[tuple[str, str | float, str]] = [
        ("Trocas", f"={PREM['trocas_aula']}", "troca"),
        ("Classificador de rota", f"={PREM['trocas_aula']}*{PREM['rota_freq']}", "rota"),
        ("Matéria nova", 1, "materia"),
        ("Quiz de checkpoint", 1, "quiz"),
        ("Lote de flashcards", 1, "cards"),
        ("Compactação de memória", 0, "compact"),
    ]
    a_first = r3 + 2
    for i, (name, qty, key) in enumerate(aula_items):
        rr = a_first + i
        label(ws, f"B{rr}", name)
        if isinstance(qty, str):
            put(ws, f"C{rr}", qty, "0.00")
        else:
            put(ws, f"C{rr}", qty, "0", kind="in")
        if key == "troca":
            put(ws, f"D{rr}", f"=C{rr}*{CUSTO_REF['troca_cons']}", FMT_CENTS)
            put(ws, f"E{rr}", f"=C{rr}*{CUSTO_REF['troca_opt']}", FMT_CENTS)
        else:
            put(ws, f"D{rr}", f"=C{rr}*$D${lat_row[key]}", FMT_CENTS)
            put(ws, f"E{rr}", f"=C{rr}*$F${lat_row[key]}", FMT_CENTS)
    a_last = a_first + len(aula_items) - 1
    rr = a_last + 1
    label(ws, f"B{rr}", "Aula completa (US¢)", bold=True)
    put(ws, f"D{rr}", f"=SUM(D{a_first}:D{a_last})", FMT_CENTS, kind="key")
    put(ws, f"E{rr}", f"=SUM(E{a_first}:E{a_last})", FMT_CENTS, kind="key")
    put(ws, f"F{rr}", 7.8, FMT_CENTS, kind="ref")
    put(ws, f"G{rr}", 3.8, FMT_CENTS, kind="ref")
    note(ws, f"H{rr}", "← auditoria: 7,8¢ / 3,8¢")
    CUSTO_REF["aula_cons"] = absref(CUSTO, f"D{rr}")
    CUSTO_REF["aula_opt"] = absref(CUSTO, f"E{rr}")
    rr += 1
    label(ws, f"B{rr}", "Aula completa (R$)", bold=True)
    put(ws, f"D{rr}", f"=D{rr - 1}/100*{PREM['fx']}", FMT_BRL, kind="key")
    put(ws, f"E{rr}", f"=E{rr - 1}/100*{PREM['fx']}", FMT_BRL, kind="key")
    put(ws, f"F{rr}", 0.44, FMT_BRL, kind="ref")
    put(ws, f"G{rr}", 0.22, FMT_BRL, kind="ref")
    note(ws, f"H{rr}", "← auditoria: R$ 0,44 / R$ 0,22")
    note(
        ws,
        f"B{rr + 1}",
        "A compactação fica em 0 por aula: usage-audit B3 diz que ela nunca rodou em produção.",
    )

    widths(ws, {"A": 2, "B": 44, "C": 20, "D": 22, "E": 20, "F": 20, "G": 20, "H": 20})
    for model in CHAT_MODELS:
        ws.column_dimensions[MODEL_COL[model]].width = max(
            ws.column_dimensions[MODEL_COL[model]].width or 0, 16
        )
    ws.column_dimensions[fonte_col].width = 40
    ws.freeze_panes = "C5"


# --- Perfis --------------------------------------------------------------------

PERFIS = "Perfis"
PERFIL_ROWS: list[tuple[str, int, float, float]] = [
    ("Free ativado", 40, 1.67, 0.77),
    ("Light", 80, 3.35, 1.54),
    ("Normal", 250, 10.46, 4.80),
    ("Power", 700, 29.28, 13.44),
    ("Extreme, sem teto", 2500, 104.56, 47.99),
]
PERFIS_FIRST_ROW = 5
PERFIL_REF: dict[str, dict[str, str]] = {}


def build_perfis(wb: Workbook) -> None:
    ws = wb.create_sheet(PERFIS)
    title(
        ws,
        "Custo mensal de IA por perfil de uso",
        "custo = trocas × custo médio por troca (sem chamadas laterais)",
    )
    header(
        ws,
        4,
        [
            "Perfil",
            "Trocas por mês",
            "Conservador (US$)",
            "Otimizado (US$)",
            "Conservador (R$)",
            "Otimizado (R$)",
            "Auditoria cons. (R$)",
            "Auditoria otim. (R$)",
        ],
        col=2,
    )
    for i, (name, trocas, aud_c, aud_o) in enumerate(PERFIL_ROWS):
        r = PERFIS_FIRST_ROW + i
        label(ws, f"B{r}", name)
        put(ws, f"C{r}", trocas, FMT_INT, kind="in")
        put(ws, f"D{r}", f"=C{r}*{CUSTO_REF['troca_cons']}/100", FMT_USD)
        put(ws, f"E{r}", f"=C{r}*{CUSTO_REF['troca_opt']}/100", FMT_USD)
        put(ws, f"F{r}", f"=D{r}*{PREM['fx']}", FMT_BRL, kind="key")
        put(ws, f"G{r}", f"=E{r}*{PREM['fx']}", FMT_BRL, kind="key")
        put(ws, f"H{r}", aud_c, FMT_BRL, kind="ref")
        put(ws, f"I{r}", aud_o, FMT_BRL, kind="ref")
        PERFIL_REF[name] = {
            "trocas": absref(PERFIS, f"C{r}"),
            "cons_brl": absref(PERFIS, f"F{r}"),
            "opt_brl": absref(PERFIS, f"G{r}"),
        }
    r = PERFIS_FIRST_ROW + len(PERFIL_ROWS)
    label(ws, f"B{r}", "Extreme, com o uso justo proposto")
    note(ws, f"C{r}", "→ aba Planos, 'Custo de IA no teto de uso justo' (Plus / Pro)")
    widths(
        ws,
        {"A": 2, "B": 34, "C": 16, "D": 18, "E": 18, "F": 18, "G": 18, "H": 20, "I": 20},
    )


# --- Planos --------------------------------------------------------------------

PLANOS = "Planos"
PLANOS_REF: dict[str, str] = {}


def build_planos(wb: Workbook) -> None:
    ws = wb.create_sheet(PLANOS)
    title(
        ws,
        "Planos propostos: receita líquida, custo de IA e margem",
        "Receita líquida = preço × (1 − deduções) − fixo do gateway. Margem = (líquida − custo de IA) ÷ líquida.",
    )
    header(ws, 4, ["", "Free", "Plus", "Pro", "Nota"], col=2)
    cols = {"Free": "C", "Plus": "D", "Pro": "E"}
    r = 5

    def row(
        text: str,
        values: dict[str, object],
        fmt: str | None,
        kind: str = "out",
        nota: str = "",
        *,
        bold=False,
    ):
        nonlocal r
        label(ws, f"B{r}", text, bold=bold)
        for plan, col in cols.items():
            if plan in values:
                put(ws, f"{col}{r}", values[plan], fmt, kind=kind)
        if nota:
            note(ws, f"F{r}", nota)
        r += 1
        return r - 1

    r_preco = row(
        "Preço mensal (R$)",
        {"Free": 0, "Plus": 34.90, "Pro": 69.90},
        FMT_BRL,
        "in",
        "PRICING_AUDIT",
    )
    r_anual = row(
        "Preço anual (R$)",
        {"Plus": 349, "Pro": 699},
        FMT_BRL,
        "in",
        "PRICING_AUDIT: 10× o mensal",
    )
    row(
        "Anual: equivalente mensal (R$)",
        {p: f"={cols[p]}{r_anual}/12" for p in ("Plus", "Pro")},
        FMT_BRL,
        nota="Auditoria: R$ 29,08 / R$ 58,25",
    )
    r_liq = row(
        "Receita líquida mensal (R$)",
        {
            p: f"=IF({cols[p]}{r_preco}=0,0,{cols[p]}{r_preco}*(1-{PREM['deducoes']})-{PREM['gw_fixo']})"
            for p in cols
        },
        FMT_BRL,
        "key",
        "Depois de imposto, gateway (% + fixo + Billing) e reembolsos",
        bold=True,
    )
    row(
        "Anual: receita líquida por mês (R$)",
        {
            p: f"=({cols[p]}{r_anual}*(1-{PREM['deducoes']})-{PREM['gw_fixo']})/12"
            for p in ("Plus", "Pro")
        },
        FMT_BRL,
        nota="Fixo do gateway cobrado uma vez por ano",
    )
    r += 1

    ws[f"B{r}"] = "Limites (o que o usuário vê)"
    ws[f"B{r}"].font = HEADER_FONT
    r += 1
    r_aulas = row(
        "Aulas no modo completo por mês",
        {"Free": "1ª de cada trilha", "Plus": 40, "Pro": 125},
        "0",
        "in",
        "PRICING_AUDIT, limites dos planos",
    )
    r_pdfs = row(
        "PDFs por mês", {"Free": 3, "Plus": 30, "Pro": 100}, "0", "in", "PRICING_AUDIT"
    )
    r += 1

    ws[f"B{r}"] = "Limites internos de uso justo"
    ws[f"B{r}"].font = HEADER_FONT
    r += 1
    r_soft = row(
        "Soft (aviso + modo padrão): créditos",
        {"Free": 180, "Plus": 4000, "Pro": 12500},
        FMT_INT,
        "in",
        "PRICING_AUDIT. 1 crédito = US$ 0,001 de custo de lista",
    )
    r_hard_cred = row(
        "Hard: créditos (Free)", {"Free": 270}, FMT_INT, "in", "PRICING_AUDIT"
    )
    r_hard_trocas = row(
        "Hard: trocas por mês no total (Plus / Pro)",
        {"Plus": 2000, "Pro": 4000},
        FMT_INT,
        "in",
        "PRICING_AUDIT",
    )
    row(
        "Trocas por dia",
        {"Free": 40, "Plus": 150, "Pro": 300},
        FMT_INT,
        "in",
        "PRICING_AUDIT",
    )
    row(
        "Soft em R$ de custo de lista",
        {p: f"={cols[p]}{r_soft}*{PREM['credito_usd']}*{PREM['fx']}" for p in cols},
        FMT_BRL,
        nota="Free: auditoria pede até R$ 1,00 por Free ativado (alvo) e R$ 1,50 (teto duro)",
    )
    row(
        "Hard em R$ de custo de lista (Free)",
        {"Free": f"=C{r_hard_cred}*{PREM['credito_usd']}*{PREM['fx']}"},
        FMT_BRL,
    )
    r += 1

    ws[f"B{r}"] = "Custo de IA e margem no uso esperado"
    ws[f"B{r}"].font = HEADER_FONT
    r += 1
    r_uso = row(
        "Trocas esperadas por mês",
        {
            "Free": f"={PERFIL_REF['Free ativado']['trocas']}",
            "Plus": f"={PERFIL_REF['Normal']['trocas']}",
            "Pro": f"={PERFIL_REF['Power']['trocas']}",
        },
        FMT_INT,
        nota="Premissa: Free = 'Free ativado', Plus = 'Normal', Pro = 'Power' (aba Perfis). "
        "A auditoria não fixa o uso esperado por plano; troque as referências se quiser outro perfil.",
    )
    r_cc = row(
        "Custo de IA, conservador (R$)",
        {
            p: f"={cols[p]}{r_uso}*{CUSTO_REF['troca_cons']}/100*{PREM['fx']}"
            for p in cols
        },
        FMT_BRL,
    )
    r_co = row(
        "Custo de IA, otimizado (R$)",
        {p: f"={cols[p]}{r_uso}*{CUSTO_REF['troca_opt']}/100*{PREM['fx']}" for p in cols},
        FMT_BRL,
    )
    r_mc = row(
        "Margem bruta, conservador",
        {
            p: f"=IF({cols[p]}{r_liq}=0,0,({cols[p]}{r_liq}-{cols[p]}{r_cc})/{cols[p]}{r_liq})"
            for p in ("Plus", "Pro")
        },
        FMT_PCT,
        "key",
        "Auditoria: 61–62% no conservador",
        bold=True,
    )
    r_mo = row(
        "Margem bruta, otimizado",
        {
            p: f"=IF({cols[p]}{r_liq}=0,0,({cols[p]}{r_liq}-{cols[p]}{r_co})/{cols[p]}{r_liq})"
            for p in ("Plus", "Pro")
        },
        FMT_PCT,
        "key",
        "Auditoria: 77–78% no otimizado",
        bold=True,
    )
    net_mix = f"({PREM['mix_plus']}*D{r_liq}+{PREM['mix_pro']}*E{r_liq})"
    r_mix_c = row(
        "Margem bruta no mix de pagantes, conservador",
        {
            "Plus": f"=({net_mix}-({PREM['mix_plus']}*D{r_cc}+{PREM['mix_pro']}*E{r_cc}))/{net_mix}"
        },
        FMT_PCT,
        "key",
        "Ponderada pelo mix Plus/Pro das Premissas (um número só, na coluna Plus)",
    )
    r_mix_o = row(
        "Margem bruta no mix de pagantes, otimizado",
        {
            "Plus": f"=({net_mix}-({PREM['mix_plus']}*D{r_co}+{PREM['mix_pro']}*E{r_co}))/{net_mix}"
        },
        FMT_PCT,
        "key",
    )
    PLANOS_REF["margem_mix_cons"] = absref(PLANOS, f"D{r_mix_c}")
    PLANOS_REF["margem_mix_opt"] = absref(PLANOS, f"D{r_mix_o}")
    r += 1

    ws[f"B{r}"] = "Custo de IA e margem no teto de uso justo"
    ws[f"B{r}"].font = HEADER_FONT
    r += 1
    r_tc = row(
        "Custo de IA no teto, conservador (R$)",
        {
            "Free": f"=C{r_hard_cred}*{PREM['credito_usd']}*{PREM['fx']}",
            "Plus": f"=(D{r_hard_trocas}*{CUSTO_REF['troca_cons']}+D{r_pdfs}*{CUSTO_REF['pdf']})/100*{PREM['fx']}",
            "Pro": f"=(E{r_hard_trocas}*{CUSTO_REF['troca_cons']}+E{r_pdfs}*{CUSTO_REF['pdf']})/100*{PREM['fx']}",
        },
        FMT_BRL,
        nota="Free: teto hard em créditos. Plus/Pro: trocas do teto hard × custo da troca + PDFs do limite",
    )
    r_to = row(
        "Custo de IA no teto, otimizado (R$)",
        {
            "Free": f"=C{r_hard_cred}*{PREM['credito_usd']}*{PREM['fx']}",
            "Plus": f"=(D{r_hard_trocas}*{CUSTO_REF['troca_opt']}+D{r_pdfs}*{CUSTO_REF['pdf']})/100*{PREM['fx']}",
            "Pro": f"=(E{r_hard_trocas}*{CUSTO_REF['troca_opt']}+E{r_pdfs}*{CUSTO_REF['pdf']})/100*{PREM['fx']}",
        },
        FMT_BRL,
    )
    row(
        "Auditoria: 'Extreme com o uso justo' (R$)",
        {"Plus": 28.71, "Pro": 79.82},
        FMT_BRL,
        "ref",
        "A auditoria não mostra como chegou a esses dois valores; não foram reproduzidos a partir dos limites.",
    )
    row(
        "Margem no teto, conservador",
        {
            p: f"=({cols[p]}{r_liq}-{cols[p]}{r_tc})/{cols[p]}{r_liq}"
            for p in ("Plus", "Pro")
        },
        FMT_PCT,
    )
    row(
        "Margem no teto, otimizado",
        {
            p: f"=({cols[p]}{r_liq}-{cols[p]}{r_to})/{cols[p]}{r_liq}"
            for p in ("Plus", "Pro")
        },
        FMT_PCT,
    )
    row(
        "Aulas completas do limite × custo da aula, conservador (R$)",
        {
            p: f"={cols[p]}{r_aulas}*{CUSTO_REF['aula_cons']}/100*{PREM['fx']}"
            for p in ("Plus", "Pro")
        },
        FMT_BRL,
        nota="Informativo: o que custam as aulas no modo completo prometidas pelo plano",
    )

    for p in cols:
        PLANOS_REF[f"liq_{p}"] = absref(PLANOS, f"{cols[p]}{r_liq}")
        PLANOS_REF[f"custo_cons_{p}"] = absref(PLANOS, f"{cols[p]}{r_cc}")
        PLANOS_REF[f"custo_opt_{p}"] = absref(PLANOS, f"{cols[p]}{r_co}")
    for p in ("Plus", "Pro"):
        PLANOS_REF[f"margem_cons_{p}"] = absref(PLANOS, f"{cols[p]}{r_mc}")
        PLANOS_REF[f"margem_opt_{p}"] = absref(PLANOS, f"{cols[p]}{r_mo}")
    widths(ws, {"A": 2, "B": 52, "C": 18, "D": 16, "E": 16, "F": 70})


# --- CAC -----------------------------------------------------------------------

CAC = "CAC"
CAC_REF: dict[str, str] = {}


def build_cac(wb: Workbook) -> None:
    ws = wb.create_sheet(CAC)
    title(
        ws, "Tetos de CAC", "LTV medido em lucro bruto: receita líquida × margem ÷ churn."
    )
    header(ws, 4, ["Métrica", "Valor", "Auditoria", "Nota"], col=2)
    r = 5

    def row(
        text: str,
        value: object,
        fmt: str,
        aud: object = None,
        nota: str = "",
        kind: str = "out",
    ):
        nonlocal r
        label(ws, f"B{r}", text)
        put(ws, f"C{r}", value, fmt, kind=kind)
        if aud is not None:
            put(ws, f"D{r}", aud, fmt, kind="ref")
        if nota:
            note(ws, f"E{r}", nota)
        r += 1
        return r - 1

    r_net = row(
        "Receita líquida média por pagante (R$/mês)",
        f"={PREM['mix_plus']}*{PLANOS_REF['liq_Plus']}+{PREM['mix_pro']}*{PLANOS_REF['liq_Pro']}",
        FMT_BRL,
        36.19,
        "Mix 80% Plus / 20% Pro, já líquida",
        kind="key",
    )
    r_m = row(
        "Margem bruta do caso base", f"={PREM['margem_base']}", FMT_PCT, 0.70, "Premissas"
    )
    r_churn = row("Churn mensal", f"={PREM['churn']}", FMT_PCT, 0.10, "Premissas")
    r_ltv = row(
        "LTV em lucro bruto (R$)",
        f"=C{r_net}*C{r_m}/C{r_churn}",
        FMT_BRL,
        253,
        "Igual ao CAC de break-even por pagante",
        kind="key",
    )
    r_cac = row(
        "CAC-alvo (R$)",
        f"=C{r_ltv}/{PREM['ltv_cac']}",
        FMT_BRL,
        84,
        "LTV ÷ LTV:CAC",
        kind="key",
    )
    r_pb = row(
        "CAC com payback de N meses (R$)",
        f"=C{r_net}*C{r_m}*{PREM['payback']}",
        FMT_BRL,
        76,
        "receita líquida × margem × meses de payback",
    )
    row(
        "Custo máximo por cadastro (R$)",
        f"=C{r_cac}*{PREM['conversao']}",
        FMT_BRL,
        2.50,
        "CAC-alvo × conversão. Instável até haver dados reais de conversão.",
        kind="key",
    )
    row(
        "Custo máximo por cadastro, critério de payback (R$)",
        f"=C{r_pb}*{PREM['conversao']}",
        FMT_BRL,
    )
    CAC_REF["net"] = absref(CAC, f"C{r_net}")
    CAC_REF["ltv"] = absref(CAC, f"C{r_ltv}")
    CAC_REF["cac"] = absref(CAC, f"C{r_cac}")
    r += 1
    label(ws, f"B{r}", "Margem calculada em Planos, conservador (Plus / Pro)")
    put(ws, f"C{r}", f"={PLANOS_REF['margem_cons_Plus']}", FMT_PCT)
    put(ws, f"D{r}", f"={PLANOS_REF['margem_cons_Pro']}", FMT_PCT)
    note(
        ws, f"E{r}", "Referência: a aba usa a margem do caso base das Premissas, não esta"
    )
    r += 1
    label(ws, f"B{r}", "Margem calculada em Planos, otimizado (Plus / Pro)")
    put(ws, f"C{r}", f"={PLANOS_REF['margem_opt_Plus']}", FMT_PCT)
    put(ws, f"D{r}", f"={PLANOS_REF['margem_opt_Pro']}", FMT_PCT)
    r += 1
    label(ws, f"B{r}", "Margem no mix de pagantes (conservador / otimizado)")
    put(ws, f"C{r}", f"={PLANOS_REF['margem_mix_cons']}", FMT_PCT)
    put(ws, f"D{r}", f"={PLANOS_REF['margem_mix_opt']}", FMT_PCT)
    note(ws, f"E{r}", "Auditoria: 61–62% / 77–78%")
    r += 2

    ws[f"B{r}"] = "Sensibilidade do LTV (R$): margem bruta × churn mensal"
    ws[f"B{r}"].font = HEADER_FONT
    r += 1
    churns = [0.07, 0.10, 0.15]
    margens = [0.62, 0.70, 0.76]
    audit = {0.62: (321, 224, 150), 0.70: (362, 253, 169), 0.76: (393, 275, 183)}
    label(ws, f"B{r}", "Margem \\ churn", bold=True)
    for j, ch in enumerate(churns):
        put(ws, f"{get_column_letter(3 + j)}{r}", ch, FMT_PCT, kind="in")
    hdr_row = r
    r += 1
    for m in margens:
        put(ws, f"B{r}", m, FMT_PCT, kind="in")
        for j in range(len(churns)):
            col = get_column_letter(3 + j)
            put(ws, f"{col}{r}", f"=$C${r_net}*$B{r}/{col}${hdr_row}", FMT_BRL)
        r += 1
    note(ws, f"B{r}", "Auditoria, para comparação:")
    r += 1
    for m in margens:
        put(ws, f"B{r}", m, FMT_PCT, kind="ref")
        for j, v in enumerate(audit[m]):
            put(ws, f"{get_column_letter(3 + j)}{r}", v, FMT_BRL, kind="ref")
        r += 1
    widths(ws, {"A": 2, "B": 52, "C": 16, "D": 16, "E": 60})


# --- Free burn -----------------------------------------------------------------

FREE = "Free burn"


def build_free(wb: Workbook) -> None:
    ws = wb.create_sheet(FREE)
    title(
        ws,
        "Queima do Free: os pagantes cobrem o plano grátis?",
        "Cenário da auditoria (riscos, item 1): 10 mil cadastros, 3% de conversão.",
    )
    header(ws, 4, ["Métrica", "Conservador", "Otimizado", "Nota"], col=2)
    r = 5

    def row(
        text: str,
        cons: object,
        opt: object | None,
        fmt: str,
        nota: str = "",
        kind: str = "out",
    ):
        nonlocal r
        label(ws, f"B{r}", text)
        put(ws, f"C{r}", cons, fmt, kind=kind)
        if opt is not None:
            put(ws, f"D{r}", opt, fmt, kind=kind)
        if nota:
            note(ws, f"E{r}", nota)
        r += 1
        return r - 1

    r_cad = row(
        "Cadastros por mês", 10000, None, FMT_INT, "PRICING_AUDIT, risco 1", kind="in"
    )
    r_ativ = row(
        "Ativação (% dos cadastros que usam o Mino)",
        0.40,
        None,
        FMT_PCT,
        "PREMISSA NÃO AUDITADA. Na amostra de QA 21 de 23 contas chamaram IA; sem dado de mercado. "
        "Com 40%, o cenário conservador reproduz a frase da auditoria: o Free consome quase toda a contribuição.",
        kind="in",
    )
    r_conv = row(
        "Conversão cadastro → pagante",
        f"={PREM['conversao']}",
        None,
        FMT_PCT,
        "Premissas",
    )
    r_pag = row("Pagantes", f"=C{r_cad}*C{r_conv}", None, FMT_INT)
    r_free = row("Free ativados", f"=C{r_cad}*C{r_ativ}", None, FMT_INT)
    r_cpf = row(
        "Custo de IA por Free ativado (R$/mês)",
        f"={PERFIL_REF['Free ativado']['cons_brl']}",
        f"={PERFIL_REF['Free ativado']['opt_brl']}",
        FMT_BRL,
        "Aba Perfis. Auditoria: alvo R$ 1,00, teto duro R$ 1,50",
    )
    r_burn = row(
        "Queima do Free (R$/mês)",
        f"=C{r_free}*C{r_cpf}",
        f"=C{r_free}*D{r_cpf}",
        FMT_BRL,
        kind="key",
    )
    r_net = row(
        "Receita líquida por pagante (R$/mês)",
        f"={CAC_REF['net']}",
        f"={CAC_REF['net']}",
        FMT_BRL,
        "Aba CAC",
    )
    r_cpp = row(
        "Custo de IA por pagante no uso esperado (R$/mês)",
        f"={PREM['mix_plus']}*{PLANOS_REF['custo_cons_Plus']}+{PREM['mix_pro']}*{PLANOS_REF['custo_cons_Pro']}",
        f"={PREM['mix_plus']}*{PLANOS_REF['custo_opt_Plus']}+{PREM['mix_pro']}*{PLANOS_REF['custo_opt_Pro']}",
        FMT_BRL,
        "Mix Plus/Pro × custo esperado da aba Planos",
    )
    r_contrib = row(
        "Contribuição dos pagantes (R$/mês)",
        f"=C{r_pag}*(C{r_net}-C{r_cpp})",
        f"=C{r_pag}*(D{r_net}-D{r_cpp})",
        FMT_BRL,
        "pagantes × (receita líquida − custo de IA)",
        kind="key",
    )
    row(
        "Sobra depois do Free (R$/mês)",
        f"=C{r_contrib}-C{r_burn}",
        f"=D{r_contrib}-D{r_burn}",
        FMT_BRL,
        "Negativo = o Free consome mais do que os pagantes deixam",
        kind="key",
    )
    row(
        "Free como % da contribuição",
        f"=C{r_burn}/C{r_contrib}",
        f"=D{r_burn}/D{r_contrib}",
        FMT_PCT,
        kind="key",
    )
    row(
        "Ativação máxima que o Free ainda fecha",
        f"=C{r_contrib}/(C{r_cad}*C{r_cpf})",
        f"=D{r_contrib}/(C{r_cad}*D{r_cpf})",
        FMT_PCT,
        "Acima disso, a conta não fecha neste cenário",
    )
    row(
        "Custo por Free ativado que zera a sobra (R$)",
        f"=C{r_contrib}/C{r_free}",
        f"=D{r_contrib}/C{r_free}",
        FMT_BRL,
        "Compare com o alvo de R$ 1,00 e o teto de R$ 1,50",
    )
    widths(ws, {"A": 2, "B": 48, "C": 18, "D": 18, "E": 80})


# --- Leia-me --------------------------------------------------------------------


def build_leiame(wb: Workbook) -> None:
    ws = wb.create_sheet("Leia-me", 0)
    title(ws, "NOEMA: economia unitária (2026-10-19)")
    lines = [
        "Fontes: docs/pricing/PRICING_AUDIT.md, market-2026-10-19.md, usage-audit-2026-10-19.md.",
        "Regenerar: uv run --with openpyxl python scripts/pricing/build_unit_economics.py",
        "",
        "Legenda:",
    ]
    for i, text in enumerate(lines):
        ws[f"A{3 + i}"] = text
    r = 3 + len(lines)
    c = put(ws, f"A{r}", "entrada editável", kind="in")
    c.alignment = Alignment(horizontal="center")
    ws[f"B{r}"] = "fonte azul, fundo amarelo: edite e tudo recalcula"
    r += 1
    put(ws, f"A{r}", "resultado-chave", kind="key")
    ws[f"B{r}"] = "fundo verde: saída principal da aba"
    r += 1
    put(ws, f"A{r}", "auditoria", kind="ref")
    ws[f"B{r}"] = "cinza itálico: valor da auditoria, só para comparar"
    r += 2
    ws[f"A{r}"] = "Resultados-chave"
    ws[f"A{r}"].font = HEADER_FONT
    r += 1
    header(ws, r, ["Métrica", "Conservador", "Otimizado"])
    r += 1
    rows = [
        (
            "Custo por troca (US¢)",
            CUSTO_REF["troca_cons"],
            CUSTO_REF["troca_opt"],
            FMT_CENTS,
        ),
        (
            "Aula de 10 trocas (US¢)",
            CUSTO_REF["aula_cons"],
            CUSTO_REF["aula_opt"],
            FMT_CENTS,
        ),
        (
            "Margem bruta Plus",
            PLANOS_REF["margem_cons_Plus"],
            PLANOS_REF["margem_opt_Plus"],
            FMT_PCT,
        ),
        (
            "Margem bruta Pro",
            PLANOS_REF["margem_cons_Pro"],
            PLANOS_REF["margem_opt_Pro"],
            FMT_PCT,
        ),
        (
            "Margem bruta no mix 80/20",
            PLANOS_REF["margem_mix_cons"],
            PLANOS_REF["margem_mix_opt"],
            FMT_PCT,
        ),
    ]
    for text, a, b, fmt in rows:
        label(ws, f"A{r}", text)
        put(ws, f"B{r}", f"={a}", fmt)
        put(ws, f"C{r}", f"={b}", fmt)
        r += 1
    for text, ref, fmt in [
        ("LTV em lucro bruto (R$)", CAC_REF["ltv"], FMT_BRL),
        ("CAC-alvo (R$)", CAC_REF["cac"], FMT_BRL),
    ]:
        label(ws, f"A{r}", text)
        put(ws, f"B{r}", f"={ref}", fmt)
        r += 1
    widths(ws, {"A": 34, "B": 18, "C": 18})


def main() -> None:
    wb = Workbook()
    build_premissas(wb)
    build_precos(wb)
    build_custo(wb)
    build_perfis(wb)
    build_planos(wb)
    build_cac(wb)
    build_free(wb)
    build_leiame(wb)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
