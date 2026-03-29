"""Tests for wallet management — create, save, load, exists, info."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from xrpl.wallet import Wallet

from xrpl_lab.actions.wallet import (
    create_wallet,
    load_wallet,
    save_wallet,
    wallet_exists,
    wallet_info,
)


class TestCreateWallet:
    def test_returns_wallet_instance(self):
        wallet = create_wallet()
        assert isinstance(wallet, Wallet)

    def test_has_address(self):
        wallet = create_wallet()
        assert wallet.address
        assert wallet.address.startswith("r")

    def test_has_seed(self):
        wallet = create_wallet()
        assert wallet.seed
        assert len(wallet.seed) > 0

    def test_unique_wallets(self):
        w1 = create_wallet()
        w2 = create_wallet()
        assert w1.address != w2.address
        assert w1.seed != w2.seed


class TestSaveWallet:
    def test_creates_file(self, tmp_path):
        wallet = create_wallet()
        path = tmp_path / "wallet.json"
        save_wallet(wallet, path=path)
        assert path.exists()

    def test_file_has_required_keys(self, tmp_path):
        wallet = create_wallet()
        path = tmp_path / "wallet.json"
        save_wallet(wallet, path=path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "address" in data
        assert "seed" in data
        assert "public_key" in data

    def test_address_matches(self, tmp_path):
        wallet = create_wallet()
        path = tmp_path / "wallet.json"
        save_wallet(wallet, path=path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["address"] == wallet.address

    def test_returns_path(self, tmp_path):
        wallet = create_wallet()
        path = tmp_path / "wallet.json"
        result = save_wallet(wallet, path=path)
        assert result == path

    def test_creates_parent_dirs(self, tmp_path):
        wallet = create_wallet()
        nested = tmp_path / "deep" / "nested" / "wallet.json"
        save_wallet(wallet, path=nested)
        assert nested.exists()


class TestLoadWallet:
    def test_roundtrip(self, tmp_path):
        wallet = create_wallet()
        path = tmp_path / "wallet.json"
        save_wallet(wallet, path=path)
        loaded = load_wallet(path=path)
        assert loaded is not None
        assert loaded.address == wallet.address

    def test_missing_file_returns_none(self, tmp_path):
        path = tmp_path / "nonexistent.json"
        result = load_wallet(path=path)
        assert result is None

    def test_corrupted_json_returns_none(self, tmp_path):
        path = tmp_path / "wallet.json"
        path.write_text("{this is not valid json{{", encoding="utf-8")
        result = load_wallet(path=path)
        assert result is None

    def test_missing_seed_key_returns_none(self, tmp_path):
        path = tmp_path / "wallet.json"
        path.write_text(json.dumps({"address": "rFAKE", "public_key": "PUBKEY"}), encoding="utf-8")
        result = load_wallet(path=path)
        assert result is None


class TestWalletExists:
    def test_true_when_file_present(self, tmp_path):
        wallet = create_wallet()
        path = tmp_path / "wallet.json"
        save_wallet(wallet, path=path)
        assert wallet_exists(path=path) is True

    def test_false_when_missing(self, tmp_path):
        path = tmp_path / "wallet.json"
        assert wallet_exists(path=path) is False

    def test_reflects_deletion(self, tmp_path):
        wallet = create_wallet()
        path = tmp_path / "wallet.json"
        save_wallet(wallet, path=path)
        assert wallet_exists(path=path) is True
        path.unlink()
        assert wallet_exists(path=path) is False


class TestWalletInfo:
    def test_has_address_and_public_key(self):
        wallet = create_wallet()
        info = wallet_info(wallet)
        assert "address" in info
        assert "public_key" in info

    def test_does_not_include_seed(self):
        wallet = create_wallet()
        info = wallet_info(wallet)
        assert "seed" not in info

    def test_address_matches(self):
        wallet = create_wallet()
        info = wallet_info(wallet)
        assert info["address"] == wallet.address
