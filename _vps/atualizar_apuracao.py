#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Atualiza a apuracao de 2026 (Nova Lima, Zona 194) a partir dos Boletins de Urna do TSE
e grava site/apuracao.json — o painel abre ja com esse resultado, para todo mundo.

Roda sozinho na VPS (cron, a cada 5 min) — veja _vps/COMO_ATIVAR_APURACAO.txt.
Cada urna recebida nao muda mais, entao so as secoes novas sao baixadas a cada rodada.

Uso manual:   python3 atualizar_apuracao.py
"""
import os, sys, json, base64, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
SITE = os.path.join(RAIZ, "site")
SAIDA = os.path.join(SITE, "apuracao.json")
BASE = "https://resultados.tse.jus.br/oficial/ele2026/arquivo-urna/3220/dados/mg/48950/0194/"
UA = {"User-Agent": "Mozilla/5.0 (painel-eleicoes)"}


def get(url, tentativas=2):
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers=UA)
            return urllib.request.urlopen(req, timeout=40).read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return None          # ainda nao publicado
        except Exception:
            time.sleep(1)
    return None


def jws(b):
    p = b.decode().strip().split(".")[1]
    p += "=" * (-len(p) % 4)
    return json.loads(base64.urlsafe_b64decode(p))


# ---- leitor minimo de ASN.1 BER (formato do BU) ----
def ber(b, s, e):
    out, i = [], s
    while i < e:
        t = b[i]; i += 1
        cls, tag = t >> 6, t & 31
        cons = (t >> 5) & 1
        if tag == 31:
            tag = 0
            while True:
                x = b[i]; i += 1
                tag = (tag << 7) | (x & 127)
                if not x & 128:
                    break
        l = b[i]; i += 1
        if l & 128:
            n = l & 127; l = 0
            for _ in range(n):
                l = l * 256 + b[i]; i += 1
        nd = {"cls": cls, "tag": tag, "vs": i, "ve": i + l, "ch": None}
        if cons:
            nd["ch"] = ber(b, i, i + l)
        out.append(nd); i += l
    return out


def num(n, b):
    return int.from_bytes(b[n["vs"]:n["ve"]], "big")


def le_bu(b):
    env = ber(b, 0, len(b))[0]["ch"]
    oct_ = env[4]
    pl = b[oct_["vs"]:oct_["ve"]]
    r = ber(pl, 0, len(pl))[0]["ch"]
    comp = None
    for n in r:
        if comp is None and n["cls"] == 0 and n["tag"] == 2:
            comp = num(n, pl)
    aptos, cargos = 0, {}
    for ele in r[-2]["ch"]:
        if not aptos:
            aptos = num(ele["ch"][1], pl)
        for rv in ele["ch"][4]["ch"]:
            for tvc in rv["ch"][2]["ch"]:
                cod = num(tvc["ch"][0], pl)
                lista = []
                for v in tvc["ch"][2]["ch"]:
                    t = q = p = n_ = 0
                    for c in v["ch"]:
                        if c["cls"] != 2:
                            continue
                        if c["tag"] == 1: t = num(c, pl)
                        elif c["tag"] == 2: q = num(c, pl)
                        elif c["tag"] == 3 and c["ch"]:
                            p = num(c["ch"][0], pl); n_ = num(c["ch"][1], pl)
                    lista.append([t, q, p, n_])
                cargos[str(cod)] = lista
    return {"aptos": aptos, "comp": comp or 0, "cargos": cargos}


def baixa_secao(sec):
    t = get(BASE + sec + "/p003220-mg-m48950-z0194-s" + sec + "-aux.jws?nocache=" + str(int(time.time())))
    if not t:
        return sec, None
    try:
        hs = [h for h in jws(t).get("hashes", []) if any(a["tp"] == "bu" for a in h.get("arq", []))]
        if not hs:
            return sec, None
        h = hs[-1]
        nm = [a["nm"] for a in h["arq"] if a["tp"] == "bu"][0]
        bu = get(BASE + sec + "/" + h["hash"] + "/" + nm)
        return sec, (le_bu(bu) if bu else None)
    except Exception as ex:
        print("  erro na secao", sec, ex)
        return sec, None


ZONA_ELE = {1: "6257", 3: "6259", 5: "6259", 6: "6259", 7: "6259"}


def zona_cargo(cod):
    """Totais da zona (apuracao oficial do TSE, costuma estar a frente dos boletins por urna)."""
    ele = ZONA_ELE[cod]
    url = ("https://resultados.tse.jus.br/oficial/ele2026/%s/dados/mg/mg48950-z0194-c000%d-e00%s-u.jws?nocache=%d"
           % (ele, cod, ele, int(time.time())))
    b = get(url)
    if not b:
        return None
    z = jws(b)
    cand, leg = {}, {}
    for a in (z.get("carg") or [{}])[0].get("agr", []):
        for pt in a.get("par", []):
            leg[pt["n"]] = int(pt.get("tvtl") or 0)
            for cd in pt.get("cand", []):
                cand[cd["n"]] = int(cd.get("vap") or 0)
    e, v, s = z.get("e", {}), z.get("v", {}), z.get("s", {})
    return {"hora": "%s %s" % (z.get("dg", ""), z.get("hg", "")), "secTot": int(s.get("ts") or 0),
            "secApur": int(s.get("st") or 0), "pApur": s.get("pst") or "0,00",
            "aptos": int(e.get("est") or 0) or int(e.get("te") or 0), "comp": int(e.get("c") or 0),
            "abst": int(e.get("a") or 0), "nom": int(v.get("vnom") or 0), "br": int(v.get("vb") or 0),
            "nu": int(v.get("vn") or 0), "cand": cand, "leg": leg}


def main():
    txt = open(os.path.join(SITE, "secoes.js"), encoding="utf-8").read()
    secoes = [s["s"] for s in json.loads(txt[txt.index("window.SECOES =") + 15:].strip().rstrip(";"))]
    atual = {}
    if os.path.exists(SAIDA):
        try:
            atual = json.load(open(SAIDA, encoding="utf-8")).get("secoes", {})
        except Exception:
            atual = {}
    pend = [s for s in secoes if s not in atual]
    novas = 0
    with ThreadPoolExecutor(max_workers=12) as ex:
        for sec, d in ex.map(baixa_secao, pend):
            if d:
                atual[sec] = d; novas += 1
    zona = {}
    for cod in ZONA_ELE:
        try:
            z = zona_cargo(cod)
            if z:
                zona[str(cod)] = z
        except Exception as ex:
            print("  erro na zona do cargo", cod, ex)
    out = {"zona": zona, "gerado_ts": int(time.time()), "gerado_em": time.strftime("%Y-%m-%d %H:%M:%S"), "total": len(secoes),
           "recebidas": len(atual), "secoes": atual}
    tmp = SAIDA + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    os.replace(tmp, SAIDA)
    zc = zona.get("1", {})
    print(f"{time.strftime('%d/%m %H:%M:%S')}  +{novas} novas · {len(atual)} de {len(secoes)} boletins · zona: {zc.get('secApur', '?')} secoes apuradas · {os.path.getsize(SAIDA)//1024} KB")


if __name__ == "__main__":
    main()
