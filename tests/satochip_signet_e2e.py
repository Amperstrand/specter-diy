#!/usr/bin/env python3
import argparse
import base64
import json
import time
from urllib import request, error, parse

import serial


class SpecterSerial:
    EOL = b"\r\n"
    ACK = b"ACK"

    def __init__(self, port: str, baudrate: int = 115200):
        self.port = port
        self.baudrate = baudrate

    def _read_until(self, ser, eol, timeout):
        t0 = time.time()
        buf = b""
        while eol not in buf:
            chunk = ser.read(1)
            if chunk:
                buf += chunk
            if timeout is not None and time.time() > t0 + timeout:
                raise TimeoutError("serial timeout")
        return buf

    def query(self, cmd: str, timeout: float = 60.0) -> str:
        payload = self.EOL * 2 + cmd.encode() + self.EOL
        with serial.Serial(self.port, self.baudrate, timeout=0) as ser:
            ser.write(payload)
            ack = self._read_until(ser, self.EOL, 3)[:-len(self.EOL)]
            if ack != self.ACK:
                raise RuntimeError("device did not return ACK")
            out = self._read_until(ser, self.EOL, timeout)[:-len(self.EOL)]
            return out.decode()


class Rpc:
    def __init__(self, base_url: str, user: str, password: str, wallet: str = None):
        self.base_url = base_url.rstrip("/")
        self.user = user
        self.password = password
        self.wallet = wallet

    def _url(self):
        if self.wallet:
            return self.base_url + "/wallet/" + parse.quote(self.wallet, safe="")
        return self.base_url

    def call(self, method: str, params=None):
        if params is None:
            params = []
        payload = json.dumps({"jsonrpc": "1.0", "id": "satochip-e2e", "method": method, "params": params}).encode()
        req = request.Request(self._url(), data=payload, method="POST")
        auth = base64.b64encode(f"{self.user}:{self.password}".encode()).decode()
        req.add_header("Authorization", f"Basic {auth}")
        req.add_header("Content-Type", "application/json")
        try:
            with request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode())
        except error.HTTPError as e:
            raise RuntimeError(f"rpc http error: {e.read().decode()}")
        if body.get("error") is not None:
            raise RuntimeError(f"rpc {method} failed: {body['error']}")
        return body["result"]


def ensure_wallet(rpc_root: Rpc, wallet: str):
    dirs = rpc_root.call("listwalletdir")
    names = {w["name"] for w in dirs.get("wallets", [])}
    loaded = set(rpc_root.call("listwallets"))
    if wallet not in names:
        rpc_root.call("createwallet", [wallet, True, True, "", False, True, True, False])
    elif wallet not in loaded:
        rpc_root.call("loadwallet", [wallet])


def descriptor_with_checksum(rpc_root: Rpc, desc: str) -> str:
    return rpc_root.call("getdescriptorinfo", [desc])["descriptor"]


def import_watch_descriptors(wallet_rpc: Rpc, rpc_root: Rpc, fp: str, xpub: str, coin: int, account: int):
    base = f"[{fp}/84h/{coin}h/{account}h]{xpub}"
    recv = descriptor_with_checksum(rpc_root, f"wpkh({base}/0/*)")
    chg = descriptor_with_checksum(rpc_root, f"wpkh({base}/1/*)")
    req = [
        {"desc": recv, "active": True, "internal": False, "range": [0, 1000], "timestamp": "now"},
        {"desc": chg, "active": True, "internal": True, "range": [0, 1000], "timestamp": "now"},
    ]
    res = wallet_rpc.call("importdescriptors", [req])
    if not all(r.get("success") for r in res):
        raise RuntimeError(f"descriptor import failed: {res}")


def first_partial_sig_hex(wallet_rpc: Rpc, psbt_b64: str):
    dec = wallet_rpc.call("decodepsbt", [psbt_b64])
    for inp in dec.get("inputs", []):
        ps = inp.get("partial_signatures")
        if ps:
            return next(iter(ps.values()))
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial-port", required=True)
    ap.add_argument("--rpc-url", default="http://127.0.0.1:38332")
    ap.add_argument("--rpc-user", required=True)
    ap.add_argument("--rpc-password", required=True)
    ap.add_argument("--wallet", default="satochip-signet-e2e")
    ap.add_argument("--network", default="signet", choices=["signet", "test", "regtest", "main"])
    ap.add_argument("--account", type=int, default=0)
    ap.add_argument("--amount", type=float, default=0.0001)
    ap.add_argument("--fee-rate", type=float, default=1.0)
    ap.add_argument("--dest-address", default="")
    ap.add_argument("--wait-funds", action="store_true")
    ap.add_argument("--wait-timeout", type=int, default=900)
    ap.add_argument("--broadcast", action="store_true")
    ap.add_argument("--repeat", type=int, default=3)
    args = ap.parse_args()

    coin = 0 if args.network == "main" else 1
    account_path = f"m/84h/{coin}h/{args.account}h"

    dev = SpecterSerial(args.serial_port)
    root_rpc = Rpc(args.rpc_url, args.rpc_user, args.rpc_password)
    ensure_wallet(root_rpc, args.wallet)
    wallet_rpc = Rpc(args.rpc_url, args.rpc_user, args.rpc_password, args.wallet)

    net_resp = dev.query(f"TEST_SET_NETWORK:{args.network}")
    pin_resp = dev.query("TEST_PIN:1234")
    ready_resp = dev.query("TEST_WAIT_READY")
    if not net_resp.startswith("OK:"):
        raise RuntimeError(net_resp)
    if not pin_resp.startswith("OK:"):
        raise RuntimeError(pin_resp)
    if not ready_resp.startswith("OK:"):
        raise RuntimeError(ready_resp)

    fp = dev.query("fingerprint")
    xpub = dev.query(f"xpub {account_path}")
    if not fp or not xpub:
        raise RuntimeError("failed to get fingerprint/xpub")

    import_watch_descriptors(wallet_rpc, root_rpc, fp, xpub, coin, args.account)
    recv_addr = wallet_rpc.call("deriveaddresses", [descriptor_with_checksum(root_rpc, f"wpkh([{fp}/84h/{coin}h/{args.account}h]{xpub}/0/0)")])[0]

    unspents = wallet_rpc.call("listunspent", [0, 9999999, [recv_addr]])
    if not unspents and args.wait_funds:
        t0 = time.time()
        while time.time() - t0 < args.wait_timeout and not unspents:
            time.sleep(5)
            unspents = wallet_rpc.call("listunspent", [0, 9999999, [recv_addr]])

    if not unspents:
        print(json.dumps({
            "status": "awaiting_funds",
            "funding_address": recv_addr,
            "account_path": account_path,
            "fingerprint": fp,
            "xpub": xpub,
        }, indent=2))
        return

    utxo = unspents[0]
    dest = args.dest_address or wallet_rpc.call("getnewaddress", ["satochip-e2e-dest", "bech32"])
    change = wallet_rpc.call("getrawchangeaddress", ["bech32"])

    unsigned = wallet_rpc.call("createpsbt", [[{"txid": utxo["txid"], "vout": utxo["vout"]}], [{dest: args.amount}], 0, True])
    enriched = wallet_rpc.call("walletprocesspsbt", [unsigned, False, "ALL", True])["psbt"]

    sig_hexes = []
    signed_psbts = []
    for _ in range(max(1, args.repeat)):
        signed = dev.query("sign " + enriched, timeout=120)
        signed_psbts.append(signed)
        sig_hexes.append(first_partial_sig_hex(wallet_rpc, signed))

    unique = sorted({s for s in sig_hexes if s})
    deterministic = len(unique) == 1 and len(sig_hexes) > 1

    final = wallet_rpc.call("finalizepsbt", [signed_psbts[0], True])
    txid = None
    if args.broadcast:
        if not final.get("complete"):
            raise RuntimeError("finalizepsbt incomplete")
        txid = root_rpc.call("sendrawtransaction", [final["hex"]])

    print(json.dumps({
        "status": "ok",
        "network": args.network,
        "account_path": account_path,
        "funding_address": recv_addr,
        "spend_destination": dest,
        "unsigned_psbt": enriched,
        "signed_psbt": signed_psbts[0],
        "sig_samples": sig_hexes,
        "unique_sig_count": len(unique),
        "deterministic": deterministic,
        "broadcast": bool(args.broadcast),
        "txid": txid,
    }, indent=2))


if __name__ == "__main__":
    main()
