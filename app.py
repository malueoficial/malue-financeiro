"""MaLuê Financeiro — dashboard de receita mensal.

Lê a agenda do Google Sheets e mostra:
- Cards de resumo: este mês, próximos 30 dias, ano em curso, total geral
- Gráfico de barras: receita mês a mês
- Tabela detalhada: mês, shows, receita, ticket médio
- Breakdown por tipo de evento
- Top contratantes
"""
from __future__ import annotations

import io
import re
from datetime import date, datetime

import pandas as pd
import streamlit as st

# ============================================================
# Config
# ============================================================
SHEET_ID = "13ibY4_88N7pTK2lrLkNcudGeVyh78Kry6Y60Ijp0JD4"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"
LOGO_URL = "https://raw.githubusercontent.com/malueoficial/malue-contratos/main/malue_icon.png"
ICON_URL = "https://raw.githubusercontent.com/malueoficial/malue-contratos/main/ml_agenda_icon.png"

MESES_PT = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]
MESES_ABREV = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
               "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

st.set_page_config(
    page_title="MaLuê Financeiro",
    page_icon=ICON_URL,
    layout="wide",
)

# ============================================================
# CSS custom
# ============================================================
st.markdown(
    """
    <style>
      :root {
        --lime: #ccff33;
        --bg-dark: #0f0f0f;
        --card-bg: #1a1a1a;
        --text: #f5f5f5;
        --muted: #a3a3a3;
      }
      [data-testid="stAppViewContainer"] { background: var(--bg-dark); }
      [data-testid="stHeader"] { background: transparent; }
      h1, h2, h3 { color: var(--text); }
      .malue-title {
        font-size: 32px; font-weight: 800; letter-spacing: -.5px;
        color: var(--text); margin: 0;
      }
      .malue-title span { color: var(--lime); }
      .malue-sub { color: var(--muted); font-size: 14px; margin: 4px 0 24px; }
      .metric-card {
        background: var(--card-bg);
        border-radius: 14px;
        padding: 18px 20px;
        border-left: 3px solid var(--lime);
        margin-bottom: 8px;
      }
      .metric-card .label {
        font-size: 12px;
        color: var(--muted);
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin: 0;
      }
      .metric-card .value {
        font-size: 26px;
        font-weight: 800;
        color: var(--lime);
        margin: 4px 0 0;
        line-height: 1.2;
      }
      .metric-card .sub {
        font-size: 12px;
        color: var(--muted);
        margin: 4px 0 0;
      }
      [data-testid="stDataFrame"] { background: var(--card-bg); border-radius: 12px; }
      .stAlert { border-radius: 12px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# Utilitários
# ============================================================
def parse_valor(s) -> float:
    """Converte string tipo 'R$ 18.000,00' → 18000.00. Aceita vários formatos BR."""
    if s is None:
        return 0.0
    s = str(s).strip()
    if not s:
        return 0.0
    # Tira tudo que não é dígito, vírgula ou ponto
    s = re.sub(r"[^\d,.\-]", "", s)
    if not s:
        return 0.0
    # Formato ambíguo — decide qual é decimal
    has_comma = "," in s
    has_dot = "." in s
    if has_comma and has_dot:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif has_comma:
        s = s.replace(",", ".")
    elif has_dot:
        parts = s.split(".")
        if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
            s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def fmt_brl(v: float) -> str:
    """18000.0 → 'R$ 18.000,00'"""
    if v is None or v == 0:
        return "R$ 0,00"
    return (
        "R$ "
        + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    )


@st.cache_data(ttl=300)  # cache 5 min
def load_data() -> pd.DataFrame:
    """Puxa CSV da agenda e retorna DataFrame."""
    try:
        r = pd.read_csv(CSV_URL, dtype=str, keep_default_na=False)
    except Exception as e:
        st.error(f"Não consegui carregar a agenda: {e}")
        return pd.DataFrame()
    return r


# ============================================================
# Header
# ============================================================
col_logo, col_title = st.columns([1, 8])
with col_logo:
    try:
        st.image(LOGO_URL, width=80)
    except Exception:
        st.write("🎶")
with col_title:
    st.markdown(
        '<p class="malue-title">MaLuê <span>Financeiro</span></p>'
        '<p class="malue-sub">Fluxo de caixa dos shows — dados direto da agenda</p>',
        unsafe_allow_html=True,
    )

# ============================================================
# Carrega e processa dados
# ============================================================
df_raw = load_data()

if df_raw.empty:
    st.warning("Agenda vazia ou sem acesso. Recarrega em alguns segundos.")
    st.stop()

# Copia pra não afetar cache
df = df_raw.copy()

# Data → datetime
df["_data_dt"] = pd.to_datetime(df.get("Data", ""), format="%d/%m/%Y", errors="coerce")
df = df.dropna(subset=["_data_dt"])

# Valor → float
df["_valor_num"] = df.get("Valor", "").apply(parse_valor)

# Status → limpa
df["_status"] = df.get("Status", "").fillna("").str.strip()

# Ignora shows sem valor (não conta pro cálculo)
df = df[df["_valor_num"] > 0].copy()

if df.empty:
    st.warning("Nenhum show com valor cadastrado ainda.")
    st.stop()

# Ano-mês pra agrupar
df["_ano"] = df["_data_dt"].dt.year
df["_mes"] = df["_data_dt"].dt.month
df["_ano_mes"] = df["_data_dt"].dt.strftime("%Y-%m")
df["_mes_nome"] = df["_mes"].apply(lambda m: MESES_ABREV[m - 1])

# ============================================================
# Cards de resumo no topo
# ============================================================
hoje = pd.Timestamp.today().normalize()

# Este mês (todos os shows do mês atual)
este_mes = df[
    (df["_data_dt"].dt.year == hoje.year) & (df["_data_dt"].dt.month == hoje.month)
]

# Próximos 30 dias (a partir de hoje)
prox_30 = df[
    (df["_data_dt"] >= hoje) & (df["_data_dt"] <= hoje + pd.Timedelta(days=30))
]

# Ano em curso
ano_atual = df[df["_data_dt"].dt.year == hoje.year]

# Total geral
total_geral = df

# Mês passado (pra comparação)
if hoje.month == 1:
    mes_ant_y, mes_ant_m = hoje.year - 1, 12
else:
    mes_ant_y, mes_ant_m = hoje.year, hoje.month - 1
mes_passado = df[
    (df["_data_dt"].dt.year == mes_ant_y) & (df["_data_dt"].dt.month == mes_ant_m)
]

# Renderiza os cards
def _card(label: str, value: str, sub: str = "") -> str:
    return (
        f'<div class="metric-card">'
        f'<p class="label">{label}</p>'
        f'<p class="value">{value}</p>'
        f'<p class="sub">{sub}</p>'
        f'</div>'
    )


c1, c2, c3, c4 = st.columns(4)

with c1:
    total = este_mes["_valor_num"].sum()
    n = len(este_mes)
    st.markdown(
        _card(
            f"Este mês ({MESES_PT[hoje.month - 1]})",
            fmt_brl(total),
            f"{n} show{'s' if n != 1 else ''}",
        ),
        unsafe_allow_html=True,
    )

with c2:
    total = prox_30["_valor_num"].sum()
    n = len(prox_30)
    st.markdown(
        _card(
            "Próximos 30 dias",
            fmt_brl(total),
            f"{n} show{'s' if n != 1 else ''}",
        ),
        unsafe_allow_html=True,
    )

with c3:
    total = ano_atual["_valor_num"].sum()
    n = len(ano_atual)
    st.markdown(
        _card(
            f"Ano {hoje.year}",
            fmt_brl(total),
            f"{n} show{'s' if n != 1 else ''}",
        ),
        unsafe_allow_html=True,
    )

with c4:
    total_ger = total_geral["_valor_num"].sum()
    n = len(total_geral)
    st.markdown(
        _card(
            "Total geral (histórico)",
            fmt_brl(total_ger),
            f"{n} show{'s' if n != 1 else ''} desde o início",
        ),
        unsafe_allow_html=True,
    )

st.divider()

# ============================================================
# Filtro de ano
# ============================================================
anos_disponiveis = sorted(df["_ano"].unique().tolist(), reverse=True)
ano_selecionado = st.selectbox(
    "Ver dados de qual ano?",
    options=anos_disponiveis,
    index=anos_disponiveis.index(hoje.year) if hoje.year in anos_disponiveis else 0,
)

df_ano = df[df["_ano"] == ano_selecionado].copy()

# ============================================================
# Gráfico de barras: receita por mês
# ============================================================
st.subheader(f"📊 Receita mensal — {ano_selecionado}")

# Agrupa por mês do ano selecionado
receita_mes = (
    df_ano.groupby("_mes")["_valor_num"].sum().reindex(range(1, 13), fill_value=0)
)
receita_mes.index = [MESES_ABREV[m - 1] for m in receita_mes.index]
receita_mes = receita_mes.rename("Receita (R$)")

st.bar_chart(receita_mes, height=280, color="#ccff33")

# ============================================================
# Tabela detalhada por mês
# ============================================================
st.subheader(f"📅 Detalhamento — {ano_selecionado}")

grp = df_ano.groupby("_mes").agg(
    Shows=("_valor_num", "count"),
    Receita=("_valor_num", "sum"),
    Ticket_medio=("_valor_num", "mean"),
).reset_index()

grp["Mês"] = grp["_mes"].apply(lambda m: MESES_PT[m - 1])
grp["Receita"] = grp["Receita"].apply(fmt_brl)
grp["Ticket médio"] = grp["Ticket_medio"].apply(fmt_brl)
grp_view = grp[["Mês", "Shows", "Receita", "Ticket médio"]]

# Total do ano na última linha
total_shows = grp["Shows"].sum()
total_receita = df_ano["_valor_num"].sum()
ticket_medio = df_ano["_valor_num"].mean() if len(df_ano) else 0

st.dataframe(
    grp_view,
    use_container_width=True,
    hide_index=True,
)

col_a, col_b, col_c = st.columns(3)
with col_a:
    st.markdown(_card("Total de shows", str(total_shows), ""), unsafe_allow_html=True)
with col_b:
    st.markdown(_card("Receita do ano", fmt_brl(total_receita), ""), unsafe_allow_html=True)
with col_c:
    st.markdown(_card("Ticket médio", fmt_brl(ticket_medio), ""), unsafe_allow_html=True)

st.divider()

# ============================================================
# Breakdown por tipo de evento
# ============================================================
st.subheader(f"🎤 Por tipo de evento — {ano_selecionado}")

tipo_col = df_ano.get("Tipo Evento", pd.Series([""] * len(df_ano)))
if not tipo_col.empty and tipo_col.astype(str).str.strip().any():
    df_ano["_tipo"] = tipo_col.astype(str).str.strip().replace("", "Sem tipo")
    tipo_grp = df_ano.groupby("_tipo").agg(
        Shows=("_valor_num", "count"),
        Receita=("_valor_num", "sum"),
    ).reset_index()
    tipo_grp = tipo_grp.sort_values("Receita", ascending=False)
    tipo_grp["Receita_num"] = tipo_grp["Receita"]
    tipo_grp["Receita"] = tipo_grp["Receita"].apply(fmt_brl)
    tipo_grp["%"] = (
        (tipo_grp["Receita_num"] / total_receita * 100).round(1).astype(str) + "%"
    )
    tipo_view = tipo_grp[["_tipo", "Shows", "Receita", "%"]].rename(
        columns={"_tipo": "Tipo"}
    )
    st.dataframe(tipo_view, use_container_width=True, hide_index=True)
else:
    st.caption("Nenhum tipo de evento cadastrado.")

# ============================================================
# Top contratantes
# ============================================================
st.subheader(f"🏆 Top contratantes — {ano_selecionado}")

cont_col = df_ano.get("Contratante", pd.Series([""] * len(df_ano)))
if not cont_col.empty and cont_col.astype(str).str.strip().any():
    df_ano["_contratante"] = cont_col.astype(str).str.strip()
    df_ano_c = df_ano[df_ano["_contratante"] != ""]
    if not df_ano_c.empty:
        cont_grp = df_ano_c.groupby("_contratante").agg(
            Shows=("_valor_num", "count"),
            Receita=("_valor_num", "sum"),
        ).reset_index()
        cont_grp = cont_grp.sort_values("Receita", ascending=False).head(10)
        cont_grp["Receita"] = cont_grp["Receita"].apply(fmt_brl)
        cont_view = cont_grp[["_contratante", "Shows", "Receita"]].rename(
            columns={"_contratante": "Contratante"}
        )
        st.dataframe(cont_view, use_container_width=True, hide_index=True)
    else:
        st.caption("Nenhum contratante cadastrado.")
else:
    st.caption("Nenhum contratante cadastrado.")

# ============================================================
# Rodapé — Última atualização + link pra admin
# ============================================================
st.divider()
st.caption(
    f"📊 Dados carregados em {datetime.now().strftime('%d/%m/%Y %H:%M')} · "
    f"[Admin agenda](https://malue-admin.streamlit.app) · "
    f"Cache de 5 minutos — puxa 'atualizar' na página se precisar recarregar."
)
