# -*- coding: utf-8 -*-
"""
Pre-carrega as paginas de 2026 com os NOMES dos candidatos e partidos (votos = 0).

Le a lista de candidatos registrados direto do portal de resultados do TSE
(Nova Lima, Zona 194) e as secoes de site/secoes.js, e grava
planilhas/Resultados 2026.xlsx — uma aba por cargo, no mesmo formato das abas de 2022.
Depois e so rodar gerar_dados.py: as paginas de 2026 aparecem com todos os candidatos.

Na apuracao, os numeros entram com importar_votos_2026.py (ou colando na planilha).

Uso:   python candidatos_2026.py
"""
import os, sys, json, base64, urllib.request
import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
SAIDA = os.path.join(RAIZ, "planilhas", "Resultados 2026.xlsx")
BASE = "https://resultados.tse.jus.br/oficial/ele2026/{e}/dados/mg/mg48950-z0194-c{c}-e00{e}-u.jws"

# aba na planilha, eleicao no TSE, codigo do cargo, nome do cargo, tem legenda de partido
CARGOS = [
    ("5 - Presidente 1 turno 2026", "6257", "0001", "Presidente",        False, 1),
    ("Governador 2026",             "6259", "0003", "Governador",        False, 1),
    ("3 Senador 2026",              "6259", "0005", "Senador",           False, 1),
    ("2 Deputado Federal 2026",     "6259", "0006", "Deputado Federal",  True,  1),
    ("1 Deputado Estadual 2026",    "6259", "0007", "Deputado Estadual", True,  1),
]
MINUSC = {"de", "da", "do", "dos", "das", "e", "di", "du", "van", "von"}


def bonito(s):
    ps = str(s).strip().lower().split()
    return " ".join(p if (i and p in MINUSC) else p.capitalize() for i, p in enumerate(ps))


def baixa(e, c):
    req = urllib.request.Request(BASE.format(e=e, c=c), headers={"User-Agent": "Mozilla/5.0"})
    t = urllib.request.urlopen(req, timeout=60).read().decode().strip()
    p = t.split(".")[1]
    p += "=" * (-len(p) % 4)
    return json.loads(base64.urlsafe_b64decode(p))


def le_secoes():
    txt = open(os.path.join(RAIZ, "site", "secoes.js"), encoding="utf-8").read()
    return json.loads(txt[txt.index("window.SECOES =") + 15:].strip().rstrip(";"))


def main():
    secoes = le_secoes()
    print(f"{len(secoes)} secoes em site/secoes.js")
    with pd.ExcelWriter(SAIDA, engine="openpyxl") as w:
        for aba, e, c, cargo, legenda, turno in CARGOS:
            d = baixa(e, c)
            cg = d["carg"][0]
            linhas = []   # (numero, nome, sigla)
            for a in cg.get("agr", []):
                for p in a.get("par", []):
                    if legenda:
                        linhas.append((p["n"], bonito(p["nm"]), p["sg"]))
                    for cd in p.get("cand", []):
                        linhas.append((cd["n"], bonito(cd.get("nmu") or cd["nm"]), p["sg"]))
            # nomes repetidos (homonimos) ganham o numero, para nao somarem juntos
            cont = {}
            for _, nome, _ in linhas:
                cont[nome] = cont.get(nome, 0) + 1
            linhas = [(n, nm if cont[nm] == 1 else f"{nm} ({n})", sg) for n, nm, sg in linhas]
            nome_col = "Candidato" if cargo in ("Deputado Federal", "Deputado Estadual") else "Nome"
            reg = []
            for s in secoes:
                for n, nm, sg in linhas:
                    reg.append({
                        "nm_local_votacao": s["loc"], "ds_local_votacao_endereco": s["end"],
                        "nr_secao": int(s["s"]), "nr_turno": turno, "ds_cargo": cargo,
                        "nr_votavel": int(n), nome_col: nm, "Partido": sg,
                        "qt_aptos": 0, "qt_comparecimento": 0, "qt_abstencoes": 0,
                        "qt_votos_nominais": 0, "Votos": 0,
                    })
            pd.DataFrame(reg).to_excel(w, sheet_name=aba, index=False)
            print(f"  {aba}: {len(linhas)} candidatos/legendas x {len(secoes)} secoes = {len(reg)} linhas")
    print("OK ->", SAIDA)


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        print("ERRO:", ex)
        sys.exit(1)
