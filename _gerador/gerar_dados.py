# -*- coding: utf-8 -*-
"""
Gera o arquivo ../dados.js a partir de ../planilhas/Arquivo das eleicoes.xlsx

Como usar:
    1. Substitua a planilha em  ELEICOES/planilhas/  (mesmo nome de arquivo)
    2. Rode:   python gerar_dados.py
    3. Abra o  "Painel Eleicoes Nova Lima.html"

Requisitos:  python -m pip install pandas openpyxl
"""
import json, os, sys, datetime, unicodedata

try:
    import pandas as pd
except ImportError:
    print("Falta a biblioteca pandas. Rode:  python -m pip install pandas openpyxl")
    sys.exit(1)

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
PL   = os.path.join(RAIZ, "planilhas")

def achar_planilha():
    cand = []
    for f in os.listdir(PL):
        if f.lower().endswith((".xlsx", ".xlsm")) and not f.startswith("~$"):
            cand.append(os.path.join(PL, f))
    if not cand:
        print("Nenhuma planilha .xlsx encontrada em", PL); sys.exit(1)
    # prefere uma que contenha "eleic"
    for c in cand:
        if "eleic" in unicodedata.normalize("NFKD", c.lower()).encode("ascii","ignore").decode():
            return c
    return cand[0]

XLSX = achar_planilha()
print("Lendo:", XLSX)
xl = pd.ExcelFile(XLSX)
SHEETS = xl.sheet_names
print("Abas:", SHEETS)

def sheet(nome_parcial):
    for s in SHEETS:
        if nome_parcial.lower() in s.lower():
            return xl.parse(s)
    return None

# ---------- mapa de regioes ----------
reg = sheet("regi")
reg.columns = [str(c).strip() for c in reg.columns]
col_macro = [c for c in reg.columns if "macro" in c.lower()][0]
col_micro = [c for c in reg.columns if "micro" in c.lower()][0]
col_sec   = [c for c in reg.columns if "sec"  in c.lower() and "1" not in c][0]
col_loc   = [c for c in reg.columns if "local" in c.lower()][0]
col_end   = [c for c in reg.columns if "endereco" in c.lower() or "endereço" in c.lower()][0]

reg[col_sec] = pd.to_numeric(reg[col_sec], errors="coerce")
sec2micro = dict(zip(reg[col_sec], reg[col_micro]))
sec2macro = dict(zip(reg[col_sec], reg[col_macro]))
micro2macro = {}
for _, r in reg.iterrows():
    micro2macro[str(r[col_micro])] = str(r[col_macro])

MACROS_ORDEM = ["Centro alto","Centro","Nordeste","Noroeste","Centro baixo",
                "Centro Leste","Vila da Serra","Cond. MG 030","Cond. BR 356"]
MACROS_ORDEM = [m for m in MACROS_ORDEM if m in set(micro2macro.values())] + \
               [m for m in sorted(set(micro2macro.values())) if m not in MACROS_ORDEM]

# referencia de regioes (para a pagina "Definicao das Regioes")
regioes_ref = []
for macro in MACROS_ORDEM:
    micros = []
    sub = reg[reg[col_macro] == macro]
    for micro in sorted(sub[col_micro].unique()):
        locais = sub[sub[col_micro] == micro][[col_loc, col_end, col_sec]].drop_duplicates()
        micros.append({
            "micro": str(micro),
            "secoes": int(locais[col_sec].nunique()),
            "locais": sorted({str(x) for x in locais[col_loc].dropna().unique()}),
        })
    regioes_ref.append({"macro": macro, "micros": micros})

# ---------- helpers ----------
def pick(df, *opcoes):
    for o in opcoes:
        for c in df.columns:
            if c.lower() == o.lower():
                return c
    for o in opcoes:
        for c in df.columns:
            if o.lower() in c.lower():
                return c
    return None

def build_pagina(pid, grupo, titulo, df, ccand, cvot, csec=None,
                 cstatus=None, cpartido=None, kpi_mode="secao",
                 kpi_cols=("apto","comparec","absten","nomin")):
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    df[cvot] = pd.to_numeric(df[cvot], errors="coerce").fillna(0)
    df[ccand] = df[ccand].astype(str).str.strip()

    cap  = pick(df, kpi_cols[0]) or None
    ccmp = pick(df, kpi_cols[1]) or None
    cabs = pick(df, kpi_cols[2]) or None
    cnom = pick(df, kpi_cols[3]) or None
    KPI = [("aptos", cap), ("comparecimento", ccmp), ("abstencoes", cabs), ("nominais", cnom)]
    for _, c in KPI:
        if c: df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    # regiao por secao
    tem_regiao = False
    if csec and csec in df.columns:
        df["_sec"] = pd.to_numeric(df[csec], errors="coerce")
        df["_micro"] = df["_sec"].map(sec2micro)
        tem_regiao = df["_micro"].notna().any()
    # ou colunas de regiao ja existentes
    if not tem_regiao:
        cmi = [c for c in df.columns if "micro" in c.lower()]
        if cmi:
            df["_micro"] = df[cmi[0]].astype(str)
            df["_sec"] = None
            tem_regiao = True

    # ---- KPIs por micro-regiao (para tudo ser dinamico) ----
    # valor de cada KPI por secao:
    #   kpi_mode="soma"  -> os valores estao espalhados em poucas linhas (0 nas demais): soma por secao
    #   kpi_mode="secao" -> o valor se repete em toda linha da secao: pega o 1o (max) por secao
    kpis_micro = {}
    kpis = {}
    if csec and csec in df.columns and any(c for _, c in KPI):
        cols_kpi = [c for _, c in KPI if c]
        if kpi_mode == "soma":
            per_sec = df.groupby("_sec")[cols_kpi].sum()
        else:
            per_sec = df.groupby("_sec")[cols_kpi].max()
        per_sec["_micro"] = per_sec.index.map(sec2micro)
        for nome, c in KPI:
            kpis[nome] = int(per_sec[c].sum()) if c else 0
        grp = per_sec.dropna(subset=["_micro"]).groupby("_micro")[cols_kpi].sum()
        for micro, row in grp.iterrows():
            kpis_micro[str(micro)] = {
                "a": int(row[cap]) if cap else 0,
                "c": int(row[ccmp]) if ccmp else 0,
                "ab": int(row[cabs]) if cabs else 0,
                "n": int(row[cnom]) if cnom else 0,
            }
    else:
        for nome, c in KPI:
            kpis[nome] = int(df[c].sum()) if c else 0

    if not kpis.get("comparecimento"):
        kpis["comparecimento"] = int(df[cvot].sum())

    # totais por candidato
    g = df.groupby(ccand)[cvot].sum().sort_values(ascending=False)
    cand_status = {}
    cand_part = {}
    if cstatus and cstatus in df.columns:
        for nome, sub in df.groupby(ccand):
            cand_status[nome] = str(sub[cstatus].mode().iloc[0]) if not sub[cstatus].mode().empty else ""
    if cpartido and cpartido in df.columns:
        for nome, sub in df.groupby(ccand):
            m = sub[cpartido].mode()
            cand_part[nome] = str(m.iloc[0]) if not m.empty else ""

    candidatos = []
    for nome, v in g.items():
        if not nome or nome.lower() == "nan":
            continue
        item = {"nome": nome, "votos": int(v)}
        if nome in cand_status and cand_status[nome] and cand_status[nome].lower() != "nan":
            item["status"] = cand_status[nome]
        if nome in cand_part and cand_part[nome] and cand_part[nome].lower() != "nan":
            item["partido"] = cand_part[nome]
        candidatos.append(item)

    # cruzamento candidato x micro-regiao (esparso)
    cruz = []
    if tem_regiao:
        gg = (df[df["_micro"].notna()]
              .groupby([ccand, "_micro"])[cvot].sum())
        for (nome, micro), v in gg.items():
            if v > 0 and nome and nome.lower() != "nan":
                cruz.append({"c": nome, "m": str(micro), "v": int(v)})

    pag = {
        "id": pid, "grupo": grupo, "titulo": titulo,
        "kpis": kpis, "kpis_micro": kpis_micro, "tem_regiao": bool(tem_regiao),
        "candidatos": candidatos, "cruzamento": cruz,
    }
    if cpartido:
        pag["tem_partido"] = True
    print(f"  [{pid}] cand={len(candidatos)} cruz={len(cruz)} kpis_micro={len(kpis_micro)} kpis={kpis}")
    return pag

paginas = []

# 1. Prefeito 2024
d = sheet("P_2024")
paginas.append(build_pagina("prefeito_2024", "Prefeito", "Prefeito — 2024", d,
    ccand=pick(d,"Votável","Votavel"), cvot=pick(d,"Votos"), csec=pick(d,"Seçao","Secao","nr_secao"),
    cstatus=pick(d,"Status"), kpi_mode="soma"))

# 2. Prefeito 2020
d = sheet("P_2020")
paginas.append(build_pagina("prefeito_2020", "Prefeito", "Prefeito — 2020", d,
    ccand=pick(d,"Votável","Votavel"), cvot=pick(d,"Votos"), csec=pick(d,"Seçao","Secao","nr_secao"),
    cstatus=pick(d,"Status"), kpi_mode="soma"))

# 3. Vereador 2024
d = sheet("9 - Vereador") if sheet("9 - Vereador") is not None else sheet("Vereador")
paginas.append(build_pagina("vereador_2024", "Vereador", "Vereador — 2024", d,
    ccand=pick(d,"Candidato.","Candidato"), cvot=pick(d,"Votos"), csec=pick(d,"Seçao","Secao","nr_secao"),
    cstatus=pick(d,"Status"), cpartido=pick(d,"Partido"), kpi_mode="secao"))

# 4. Vereador - votacao por partido  (mesma base, visao por partido)
d = sheet("9 - Vereador") if sheet("9 - Vereador") is not None else sheet("Vereador")
pg = build_pagina("vereador_partido", "Vereador", "Vereador — Votação por partido", d,
    ccand=pick(d,"Candidato.","Candidato"), cvot=pick(d,"Votos"), csec=pick(d,"Seçao","Secao","nr_secao"),
    cstatus=pick(d,"Status"), cpartido=pick(d,"Partido"), kpi_mode="secao")
pg["titulo"] = "Vereador — Votação por partido e região"
pg["vista"] = "partido"
paginas.append(pg)

# 5-10. Eleicoes 2022
cfg2022 = [
    ("presidente_1t_2022", "Eleições 2022", "Presidente — 1º turno (2022)", "5 - Presidente 1 turno", ("Nome","Candidato")),
    ("presidente_2t_2022", "Eleições 2022", "Presidente — 2º turno (2022)", "6 - Presidente 2 turno", ("Candidato","Nome")),
    ("governador_2022",    "Eleições 2022", "Governador (2022)",             "Governador",              ("Candidato","Nome")),
    ("senador_2022",       "Eleições 2022", "Senador (2022)",                "3 Senador",               ("Nome","Candidato")),
    ("dep_federal_2022",   "Eleições 2022", "Deputado Federal (2022)",       "2 Deputado Federal",      ("Candidato","Nome")),
    ("dep_estadual_2022",  "Eleições 2022", "Deputado Estadual (2022)",      "1 Deputado Estadual",     ("Candidato","Nome")),
]
for pid, grupo, titulo, aba, cols in cfg2022:
    d = sheet(aba)
    if d is None:
        print("  !! aba nao encontrada:", aba); continue
    d.columns = [str(c).strip() for c in d.columns]
    paginas.append(build_pagina(pid, grupo, titulo, d,
        ccand=pick(d, *cols), cvot=pick(d,"Votos","Voto"),
        csec=pick(d,"nr_secao","Seçao","Secao"),
        kpi_mode="secao",
        kpi_cols=("apto","comparec","absten","nomin")))

# ---------- monta dados.js ----------
DADOS = {
    "gerado_em": datetime.date.today().isoformat(),
    "fonte": "TRE-MG — compilado por Jucilei Nunes Ferreira (31-99615-0881)",
    "municipio": "Nova Lima / MG",
    "macros_ordem": MACROS_ORDEM,
    "micro_para_macro": {k: v for k, v in micro2macro.items() if k and k.lower() != "nan"},
    "regioes_ref": regioes_ref,
    "paginas": paginas,
}

saida = os.path.join(RAIZ, "site", "dados.js")
os.makedirs(os.path.dirname(saida), exist_ok=True)
with open(saida, "w", encoding="utf-8") as f:
    f.write("// Gerado automaticamente por _gerador/gerar_dados.py em "
            + DADOS["gerado_em"] + "\n")
    f.write("// NAO edite a mao — rode o gerador de novo se a planilha mudar.\n")
    f.write("window.DADOS = ")
    json.dump(DADOS, f, ensure_ascii=False, separators=(",", ":"))
    f.write(";\n")

print("\nOK ->", saida, "(", os.path.getsize(saida)//1024, "KB )")
