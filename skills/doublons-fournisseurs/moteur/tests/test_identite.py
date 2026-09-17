"""Garde-fous de la couche d'identité (chapitre 2 et 10 de FONCTIONNEMENT.html).

Toutes les valeurs de test ci-dessous sont des SIREN/SIRET/TVA construits
pour respecter (ou volontairement violer) la clé de Luhn — aucun n'est un
identifiant réel.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mdf.identite import is_valid_siren, is_valid_siret, resoudre_identite
from mdf.modele import StatutIdentite

SIRET_OK = "55204944700006"  # SIREN 552049447
TVA_OK_MEME_SIREN = "FR35552049447"

SIRET_AUTRE_OK = "40483304800006"  # SIREN 404833048
TVA_AUTRE_OK = "FR83404833048"

SIRET_SIREN_INVALIDE = "10000000000008"  # 14 chiffres valides, 9 premiers invalides en SIREN
TVA_SIREN_INVALIDE_COHERENTE = "FR61100000000"  # clé cohérente pour un SIREN qui échoue en Luhn 9


def test_luhn_siren_siret():
    assert is_valid_siren("552049447")
    assert not is_valid_siren("552049440")
    assert is_valid_siret(SIRET_OK)
    assert not is_valid_siret("55204944700005")


def test_siret_et_tva_coherents_meme_siren():
    identite = resoudre_identite(SIRET_OK, TVA_OK_MEME_SIREN)
    assert identite.statut == StatutIdentite.OK
    assert identite.siret == SIRET_OK
    assert identite.siren == "552049447"
    assert identite.utilisable_pour_fusion


def test_siret_manquant_siren_derive_de_la_tva():
    identite = resoudre_identite(None, TVA_OK_MEME_SIREN)
    assert identite.siret is None
    assert identite.siren == "552049447"
    assert identite.siren_source == "tva"
    assert not identite.utilisable_pour_fusion


def test_zero_initial_restaure():
    identite = resoudre_identite("4812345900009", None)  # 13 chiffres, zéro initial perdu
    assert identite.siret == "04812345900009"
    assert identite.siret_reconstruit is True
    assert identite.statut == StatutIdentite.OK
    assert identite.utilisable_pour_fusion


def test_siret_invalide_non_restaurable_part_en_quarantaine():
    identite = resoudre_identite("55204944700005", None)
    assert identite.siret is None
    assert identite.statut == StatutIdentite.QUARANTAINE_INCOHERENCE
    assert not identite.utilisable_pour_fusion


def test_tva_fautive_le_siret_valide_l_emporte():
    # Même structure que TVA_AUTRE_OK mais avec une clé volontairement fausse.
    identite = resoudre_identite(SIRET_OK, "FR00404833048")
    assert identite.statut == StatutIdentite.OK
    assert identite.siret == SIRET_OK
    assert identite.utilisable_pour_fusion


def test_siret_au_sirent_invalide_avec_tva_coherente_part_en_quarantaine():
    identite = resoudre_identite(SIRET_SIREN_INVALIDE, TVA_AUTRE_OK)
    assert identite.statut == StatutIdentite.QUARANTAINE_INCOHERENCE
    assert identite.siret is None
    assert not identite.utilisable_pour_fusion


def test_deux_identifiants_valides_divergents_cas_franchise():
    identite = resoudre_identite(SIRET_OK, TVA_AUTRE_OK)
    assert identite.statut == StatutIdentite.A_QUALIFIER_FRANCHISE
    # La fiche garde son SIRET (chacun des deux identifiants est valide en soi)
    # mais n'est pas fusionnée automatiquement au vu de la divergence.
    assert identite.siret == SIRET_OK


def test_incoherence_non_resoluble():
    identite = resoudre_identite(SIRET_SIREN_INVALIDE, "FR00404833048")
    assert identite.statut == StatutIdentite.QUARANTAINE_INCOHERENCE
    assert identite.siret is None


def test_profil_monaco_non_traite_comme_une_erreur():
    identite = resoudre_identite(None, TVA_SIREN_INVALIDE_COHERENTE)
    assert identite.statut == StatutIdentite.MONACO_POSSIBLE
    assert identite.siren == "100000000"
    # Jamais fusionné automatiquement : pas de SIRET exploitable.
    assert not identite.utilisable_pour_fusion


def test_aucune_fiche_quarantaine_n_est_utilisable_pour_fusion():
    for siret, tva in [
        ("55204944700005", None),
        (SIRET_SIREN_INVALIDE, TVA_AUTRE_OK),
        (SIRET_SIREN_INVALIDE, "FR00404833048"),
    ]:
        identite = resoudre_identite(siret, tva)
        assert identite.statut == StatutIdentite.QUARANTAINE_INCOHERENCE
        assert not identite.utilisable_pour_fusion
