# -*- coding: utf-8 -*-
"""
Le o log de acesso do Caddy e mostra quem entrou/saiu do painel e quando.

Uso na VPS:
    python3 /srv/painel-eleicoes/_vps/ver_acessos.py
    python3 /srv/painel-eleicoes/_vps/ver_acessos.py --dias 7
    python3 /srv/painel-eleicoes/_vps/ver_acessos.py --usuario jucilei

Depende do bloco de log configurado no Caddyfile (ver _vps/COMO_ATIVAR_LOG.txt).
"""
import json, sys, datetime, argparse, urllib.parse

LOG = "/var/log/caddy/eleicoes-access.log"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=0, help="só mostra os últimos N dias (0 = tudo)")
    ap.add_argument("--usuario", default=None, help="filtra por login")
    ap.add_argument("--arquivo", default=LOG)
    args = ap.parse_args()

    corte = None
    if args.dias:
        corte = datetime.datetime.now() - datetime.timedelta(days=args.dias)

    linhas = []
    try:
        f = open(args.arquivo, encoding="utf-8", errors="ignore")
    except FileNotFoundError:
        print("Não achei o arquivo de log:", args.arquivo)
        print("Veja _vps/COMO_ATIVAR_LOG.txt para configurar o Caddy.")
        sys.exit(1)

    with f:
        for linha in f:
            linha = linha.strip()
            if not linha or "/_log/" not in linha:
                continue
            try:
                d = json.loads(linha)
            except Exception:
                continue
            uri = (d.get("request") or {}).get("uri", "")
            if "/_log/login" not in uri and "/_log/logout" not in uri:
                continue
            evento = "entrou " if "/_log/login" in uri else "saiu   "
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(uri).query)
            login = (q.get("u") or [""])[0]
            if args.usuario and login != args.usuario:
                continue
            ip = (d.get("request") or {}).get("remote_ip", "?")
            ts = d.get("ts")
            if ts is None:
                continue
            dt = datetime.datetime.fromtimestamp(ts)
            if corte and dt < corte:
                continue
            linhas.append((dt, evento, login, ip))

    linhas.sort(key=lambda x: x[0])
    if not linhas:
        print("Nenhum acesso registrado" + (f" para '{args.usuario}'" if args.usuario else "") + ".")
        return

    print(f"{'DATA/HORA':<20}{'EVENTO':<10}{'LOGIN':<18}IP")
    print("-" * 62)
    for dt, evento, login, ip in linhas:
        print(f"{dt.strftime('%d/%m/%Y %H:%M:%S'):<20}{evento:<10}{login:<18}{ip}")
    print(f"\nTotal: {len(linhas)} evento(s)")

if __name__ == "__main__":
    main()
