# -*- coding: utf-8 -*-
"""
Mostra quem entrou/saiu do painel e quando, lendo o log do Caddy pelo journal
do systemd (journalctl -u caddy) — sem depender de arquivo/permissão nenhuma.

Uso na VPS (linha de comando, saida em texto):
    python3 /srv/painel-eleicoes/_vps/ver_acessos.py
    python3 /srv/painel-eleicoes/_vps/ver_acessos.py --dias 7
    python3 /srv/painel-eleicoes/_vps/ver_acessos.py --usuario jucilei

Uso pelo cron (grava JSON pro painel ler, na tela "Acessos"):
    python3 /srv/painel-eleicoes/_vps/ver_acessos.py --json /srv/painel-eleicoes/site/acessos.json

Depende do bloco de log configurado no Caddyfile (ver _vps/COMO_ATIVAR_LOG.txt) —
so precisa de "log { format json }" no bloco eleicoes.gavix.tech, sem "output file".
"""
import json, sys, datetime, argparse, urllib.parse, subprocess

def coleta(dias=0, usuario=None):
    cmd = ["journalctl", "-u", "caddy", "-o", "cat", "--no-pager"]
    if dias:
        cmd += ["--since", f"{dias} days ago"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except Exception as e:
        print(f"Não consegui ler o journal do caddy: {e}", file=sys.stderr)
        return None

    eventos = []
    for linha in proc.stdout.splitlines():
        linha = linha.strip()
        if not linha or "/_log/" not in linha:
            continue
        try:
            d = json.loads(linha)
        except Exception:
            continue
        req = d.get("request") or {}
        uri = req.get("uri", "")
        if "/_log/login" not in uri and "/_log/logout" not in uri:
            continue
        evento = "login" if "/_log/login" in uri else "logout"
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(uri).query)
        login = (q.get("u") or [""])[0]
        if usuario and login != usuario:
            continue
        ts = d.get("ts")
        if ts is None:
            continue
        ip = req.get("remote_ip", "?")
        eventos.append({"ts": ts, "evento": evento, "login": login, "ip": ip})

    eventos.sort(key=lambda x: x["ts"])
    return eventos

def imprime(eventos):
    if not eventos:
        print("Nenhum acesso registrado.")
        return
    def pad(s, n): s = str(s); return s + " " * max(0, n - len(s))
    print(pad("DATA/HORA", 20) + pad("EVENTO", 10) + pad("LOGIN", 18) + "IP")
    print("-" * 62)
    for e in eventos:
        dt = datetime.datetime.fromtimestamp(e["ts"]).strftime("%d/%m/%Y %H:%M:%S")
        ev = "entrou" if e["evento"] == "login" else "saiu"
        print(pad(dt, 20) + pad(ev, 10) + pad(e["login"], 18) + e["ip"])
    print(f"\nTotal: {len(eventos)} evento(s)")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=0, help="só os últimos N dias (0 = tudo que o journal ainda tiver)")
    ap.add_argument("--usuario", default=None, help="filtra por login")
    ap.add_argument("--json", default=None, help="grava um .json (pra o painel ler) em vez de imprimir")
    args = ap.parse_args()

    eventos = coleta(args.dias, args.usuario)
    if eventos is None:
        sys.exit(1)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(eventos, f, ensure_ascii=False)
        print(f"Gravado {len(eventos)} evento(s) em {args.json}")
    else:
        imprime(eventos)

if __name__ == "__main__":
    main()
