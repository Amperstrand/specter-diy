import os
import shutil
import subprocess
import time
import signal


class BitcoinCoreManager:
    RPC_USER = "bitcoin"
    RPC_PASSWORD = "secret"
    RPC_PORT = 18778
    P2P_PORT = 18779

    def __init__(self):
        self.proc = None
        self.datadir = "/tmp/specter-test-bitcoin-%d" % os.getpid()

    @classmethod
    def is_available(cls):
        return shutil.which("bitcoind") is not None

    def start(self):
        print("Starting Bitcoin Core in regtest mode (port %d)..." % self.RPC_PORT)
        try:
            shutil.rmtree(self.datadir)
        except Exception:
            pass
        try:
            os.mkdir(self.datadir)
        except Exception:
            pass

        cmd = (
            "bitcoind"
            " -regtest"
            " -daemon"
            " -datadir=%s"
            " -rpcuser=%s"
            " -rpcpassword=%s"
            " -rpcport=%d"
            " -port=%d"
            " -fallbackfee=0.0002"
            " -listen=0"
        ) % (self.datadir, self.RPC_USER, self.RPC_PASSWORD,
             self.RPC_PORT, self.P2P_PORT)

        subprocess.run(cmd, shell=True, check=True, capture_output=True)

        os.environ["BTC_RPC_USER"] = self.RPC_USER
        os.environ["BTC_RPC_PASSWORD"] = self.RPC_PASSWORD
        os.environ["BTC_RPC_HOST"] = "127.0.0.1"
        os.environ["BTC_RPC_PORT"] = str(self.RPC_PORT)
        os.environ["BTC_RPC_PROTOCOL"] = "http"

        print("Waiting for Bitcoin Core RPC readiness...")
        t0 = time.time()
        while time.time() - t0 < 15:
            try:
                self._rpc_call("getmininginfo")
                print("Bitcoin Core ready")
                return
            except Exception:
                time.sleep(0.5)
        raise RuntimeError("Bitcoin Core did not become ready within 15s")

    def stop(self):
        print("Stopping Bitcoin Core...")
        try:
            self._rpc_call("stop")
            time.sleep(2)
        except Exception as e:
            print("  stop RPC failed: %s" % e)
            try:
                subprocess.run(
                    ["pkill", "-f", "bitcoind.*-datadir=%s" % self.datadir],
                    capture_output=True
                )
                time.sleep(1)
            except Exception:
                pass
        try:
            shutil.rmtree(self.datadir)
        except Exception:
            pass
        print("Bitcoin Core stopped")

    def _rpc_call(self, method, params=None):
        import requests
        url = "http://127.0.0.1:%d" % self.RPC_PORT
        payload = {
            "jsonrpc": "1.0",
            "id": "1",
            "method": method,
            "params": params or [],
        }
        r = requests.post(
            url,
            json=payload,
            auth=(self.RPC_USER, self.RPC_PASSWORD),
            timeout=5,
        )
        r.raise_for_status()
        return r.json()
