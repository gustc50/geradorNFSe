"""Guarda da senha do certificado."""

import pytest

from nfse.cofre import Cofre, ErroDeCofre


def test_senha_nao_fica_em_texto_puro(tmp_path):
    cofre = Cofre(tmp_path)
    cifrada = cofre.cifrar("minha-senha-secreta")
    assert "minha-senha-secreta" not in cifrada
    assert cofre.decifrar(cifrada) == "minha-senha-secreta"


def test_outra_instancia_le_a_mesma_senha(tmp_path):
    cifrada = Cofre(tmp_path).cifrar("abc123")
    assert Cofre(tmp_path).decifrar(cifrada) == "abc123"


def test_cada_cifragem_gera_texto_diferente(tmp_path):
    cofre = Cofre(tmp_path)
    assert cofre.cifrar("igual") != cofre.cifrar("igual")


def test_senha_mestre_protege_o_cofre(tmp_path):
    cifrada = Cofre(tmp_path, senha_mestre="mestra").cifrar("segredo")
    assert Cofre(tmp_path, senha_mestre="mestra").decifrar(cifrada) == "segredo"
    with pytest.raises(ErroDeCofre):
        Cofre(tmp_path, senha_mestre="errada").decifrar(cifrada)


def test_cadastro_antigo_em_texto_puro_continua_sendo_lido(tmp_path):
    assert Cofre(tmp_path).decifrar("senha-antiga") == "senha-antiga"


def test_arquivo_da_chave_so_e_legivel_pelo_dono(tmp_path):
    cofre = Cofre(tmp_path)
    cofre.cifrar("x")
    assert oct(cofre.arquivo_chave.stat().st_mode)[-3:] == "600"
