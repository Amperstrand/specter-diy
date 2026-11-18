"""Hardware tier: every applet-family story against the real J3R180 (CardMan).

Story functions are imported from the bench suite (repo-root suite.py) — one
implementation, two frontends (CLI bench run + this pytest gate).
"""
import pytest

import suite


def test_teapot_put_get_roundtrip(cardman_conn):
    suite.story_teapot(cardman_conn)


def test_memorycard_channel_pin_secret(cardman_conn):
    suite.story_memorycard(cardman_conn)


def test_singleusekey_select_random(cardman_conn):
    suite.story_singleusekey(cardman_conn)


def test_blindoracle_select_pubkey(cardman_conn):
    suite.story_blindoracle(cardman_conn)


def test_satochip_v014_full_chain(cardman_conn):
    suite.story_satochip(cardman_conn)


def test_seedkeeper_v02_store_list_export(cardman_conn):
    suite.story_seedkeeper(cardman_conn)
