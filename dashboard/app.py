"""Dashboard - Alfabetizacao na Rede Municipal (versao AWS/Athena)."""
import awswrangler as wr
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Alfabetizacao Municipal", layout="wide")

ATHENA_DATABASE = "tc2_gold"
ATHENA_S3_OUTPUT = "s3://tc2-fiap-athena-results/"

@st.cache_data(ttl=3600)
def q(sql):
    return wr.athena.read_sql_query(
        sql=sql, database=ATHENA_DATABASE,
        s3_output=ATHENA_S3_OUTPUT, ctas_approach=False,
    )

st.title("Alfabetizacao na Rede Municipal")
st.caption("Compromisso Nacional Crianca Alfabetizada - dados INEP/IBGE")

uf_df = q("SELECT * FROM vw_uf_ano")
anos = sorted(uf_df["ano"].unique())
# Default: ultimo ano com taxa realizada (2024), nao o ultimo ano de meta (2030)
anos_com_taxa = sorted(uf_df[uf_df["taxa_media"].notna()]["ano"].unique())
default_ano = anos_com_taxa[-1] if len(anos_com_taxa) else anos[-1]
ano = st.sidebar.selectbox("Ano", anos, index=anos.index(default_ano))
regioes = ["Todas"] + sorted(uf_df["regiao"].unique().tolist())
regiao = st.sidebar.selectbox("Regiao", regioes)

dados = uf_df[uf_df["ano"] == ano]
if regiao != "Todas":
    dados = dados[dados["regiao"] == regiao]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Taxa media", f"{dados['taxa_media'].mean():.1f}%")
c2.metric("Meta media", f"{dados['meta_media'].mean():.1f}%")
c3.metric("Municipios", int(dados["qtd_municipios"].sum()))
c4.metric("UFs analisadas", dados["sigla_uf"].nunique())

st.divider()
fig = px.bar(
    dados.sort_values("taxa_media"),
    x="taxa_media", y="sigla_uf", color="regiao", orientation="h",
    title=f"Taxa media de alfabetizacao por UF - {ano}",
    labels={"taxa_media": "Taxa (%)", "sigla_uf": "UF", "regiao": "Regiao"},
)
fig.update_layout(height=650, yaxis={"categoryorder": "total ascending"})
st.plotly_chart(fig, width="stretch")

regiao_df = q("SELECT * FROM vw_regiao_ano")
regiao_ano = regiao_df[regiao_df["ano"] == ano]
col_a, col_b = st.columns(2)
with col_a:
    fig2 = px.bar(
        regiao_ano.sort_values("taxa_media"),
        x="regiao", y=["taxa_media", "meta_media"], barmode="group",
        title="Realizado vs Meta por regiao",
        labels={"value": "Taxa (%)", "regiao": "Regiao", "variable": ""},
    )
    st.plotly_chart(fig2, width="stretch")
with col_b:
    fig3 = px.bar(
        regiao_ano.sort_values("taxa_media"),
        x="regiao", y="taxa_media", title="Taxa media por regiao",
        labels={"taxa_media": "Taxa (%)", "regiao": "Regiao"},
    )
    st.plotly_chart(fig3, width="stretch")

st.divider()
st.subheader(f"Municipios - {ano}")
mun = q(f"SELECT * FROM vw_municipio WHERE ano = {ano}")
if regiao != "Todas":
    mun = mun[mun["regiao"] == regiao]
ordem = st.radio("Ordenar por gap:", ["Maiores superavits", "Maiores deficits"], horizontal=True)
mun_ord = mun.sort_values("gap_meta", ascending=(ordem == "Maiores deficits"))
st.dataframe(
    mun_ord[["nome_municipio", "sigla_uf", "regiao", "taxa_realizada", "meta", "gap_meta"]],
    width="stretch", height=400, hide_index=True,
    column_config={
        "nome_municipio": "Municipio", "sigla_uf": "UF", "regiao": "Regiao",
        "taxa_realizada": st.column_config.NumberColumn("Realizado (%)", format="%.1f"),
        "meta": st.column_config.NumberColumn("Meta (%)", format="%.1f"),
        "gap_meta": st.column_config.NumberColumn("Gap (p.p.)", format="%.1f"),
    },
)
st.caption("Nota: gaps extremos (acima de ~50 p.p.) geralmente indicam metas mal calibradas em municipios de pequeno porte.")
