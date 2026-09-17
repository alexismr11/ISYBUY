"""Garde-fous du moteur de détection (chapitre 10 de FONCTIONNEMENT.html).

Ces tests vérifient des invariants, pas des chiffres : ils doivent tenir sur
n'importe quel jeu de données, pas seulement sur les scénarios ci-dessous.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mdf.detection import analyser, elire_fiche_maitre
from mdf.identite import resoudre_identite
from mdf.modele import Cause, Fournisseur, Palier, Population, StatutIdentite

SIRET_A = "55204944700006"
SIRET_B = "40483304800006"
SIRET_C = "38012986600006"
SIRET_D = "77566399000007"
TVA_A = "FR35552049447"


def _f(
    id,
    raison_sociale="ACME",
    siret=SIRET_A,
    tva=None,
    ville="PARIS",
    cp="75001",
    id_groupe=None,
    nom_groupe=None,
    date_creation="2020-01-01",
    nb_agences=0,
    nb_codes_erp=0,
):
    f = Fournisseur(
        id=id,
        raison_sociale=raison_sociale,
        siret_brut=siret,
        tva_brut=tva,
        adresse="1 rue du Test",
        code_postal=cp,
        ville=ville,
        id_groupe=id_groupe,
        nom_groupe=nom_groupe,
        date_creation=date_creation,
        nb_agences=nb_agences,
        nb_codes_erp=nb_codes_erp,
    )
    f.identite = resoudre_identite(siret, tva)
    return f


def test_doublon_actionnable_certaine_meme_client():
    fournisseurs = [
        _f("F1", id_groupe="C1", nom_groupe="CETIH", date_creation="2019-01-01"),
        _f("F2", id_groupe="C1", nom_groupe="CETIH", date_creation="2021-01-01"),
    ]
    resultat = analyser(fournisseurs)
    assert len(resultat["familles"]) == 1
    fam = resultat["familles"][0]
    assert fam.population == Population.DOUBLON_ACTIONNABLE
    assert fam.palier == Palier.CERTAINE
    assert fam.cause == Cause.SAISIE_MULTIPLE_MEME_PERIMETRE
    assert fam.fiche_a_conserver_id == "F1"  # la plus ancienne, à égalité sinon
    assert fam.fiches_a_fusionner_ids == ["F2"]


def test_doublon_actionnable_public_prioritaire_sur_prive():
    fournisseurs = [
        _f("F1", id_groupe="C1", nom_groupe="CETIH", nb_agences=5),
        _f("F2", id_groupe=None, nom_groupe=None, nb_agences=0),  # fiche publique, moins exposée
    ]
    resultat = analyser(fournisseurs)
    fam = resultat["familles"][0]
    assert fam.population == Population.DOUBLON_ACTIONNABLE
    assert fam.cause == Cause.RECREATION_SANS_RATTACHEMENT
    assert fam.fiche_a_conserver_id == "F2"  # publique retenue même moins exposée


def test_signal_raison_sociale_divergente_declasse_le_palier():
    fournisseurs = [
        _f("F1", raison_sociale="ACME FRANCE", id_groupe="C1", nom_groupe="CETIH"),
        _f("F2", raison_sociale="ACME EUROPE", id_groupe="C1", nom_groupe="CETIH"),
    ]
    fam = analyser(fournisseurs)["familles"][0]
    assert fam.palier == Palier.A_CONTROLER
    from mdf.modele import SignalControle

    assert SignalControle.RAISON_SOCIALE_DIVERGENTE in fam.signaux


def test_signal_villes_differentes():
    fournisseurs = [
        _f("F1", ville="PARIS", id_groupe="C1", nom_groupe="CETIH"),
        _f("F2", ville="LYON", id_groupe="C1", nom_groupe="CETIH"),
    ]
    fam = analyser(fournisseurs)["familles"][0]
    assert fam.palier == Palier.A_CONTROLER


def test_signal_siret_reconstitue():
    fournisseurs = [
        _f("F1", siret="4812345900009", id_groupe="C1", nom_groupe="CETIH"),  # zéro perdu
        _f("F2", siret="04812345900009", id_groupe="C1", nom_groupe="CETIH"),
    ]
    fam = analyser(fournisseurs)["familles"][0]
    assert fam.palier == Palier.A_CONTROLER
    assert fam.cause == Cause.ZERO_INITIAL_PERDU


def test_signal_fiche_retenue_sans_agence():
    # La fiche publique l'emporte (règle 1) même si une copie privée est mieux exposée (règle 2) :
    # c'est justement ce décalage que le signal doit faire remonter pour contrôle.
    fournisseurs = [
        _f("F1", id_groupe="C1", nom_groupe="CETIH", nb_agences=3),
        _f("F2", id_groupe=None, nom_groupe=None, nb_agences=0),
    ]
    fam = analyser(fournisseurs)["familles"][0]
    assert fam.fiche_a_conserver_id == "F2"
    assert fam.palier == Palier.A_CONTROLER
    from mdf.modele import SignalControle

    assert SignalControle.FICHE_RETENUE_SANS_AGENCE in fam.signaux


def test_arbitrage_inter_tenant_sans_fiche_publique():
    fournisseurs = [
        _f("F1", id_groupe="C1", nom_groupe="CETIH"),
        _f("F2", id_groupe="C2", nom_groupe="SALTI"),
    ]
    resultat = analyser(fournisseurs)
    fam = resultat["familles"][0]
    assert fam.population == Population.ARBITRAGE_INTER_TENANT
    assert fam.palier == Palier.ARBITRAGE
    assert fam.cause == Cause.REFERENTIELS_CLIENTS_DISTINCTS
    assert fam.fiche_a_conserver_id is None
    assert fam.fiches_a_fusionner_ids == []  # aucune instruction émise


def test_fiche_publique_transforme_un_arbitrage_en_doublon_actionnable():
    fournisseurs = [
        _f("F1", id_groupe="C1", nom_groupe="CETIH"),
        _f("F2", id_groupe="C2", nom_groupe="SALTI"),
        _f("F3", id_groupe=None, nom_groupe=None),  # publique
    ]
    fam = analyser(fournisseurs)["familles"][0]
    assert fam.population == Population.DOUBLON_ACTIONNABLE
    assert fam.fiche_a_conserver_id == "F3"


def test_restructuration_meme_siren_siret_distincts_pas_un_doublon():
    fournisseurs = [
        _f("F1", siret="55204944700006", ville="PARIS"),
        _f("F2", siret="55204944700014", ville="LYON"),  # même SIREN 552049447, SIRET différent
    ]
    resultat = analyser(fournisseurs)
    assert resultat["familles"] == []  # ce n'est pas un doublon
    assert len(resultat["restructurations"]) == 1
    groupe = resultat["restructurations"][0]
    assert groupe.siren == "552049447"
    assert groupe.nb_etablissements == 2


def test_candidat_rattrapage_tva_partagee_sans_siret():
    fournisseurs = [
        _f("F1", siret=None, tva=TVA_A),
        _f("F2", siret=None, tva=TVA_A),
    ]
    resultat = analyser(fournisseurs)
    assert resultat["familles"] == []
    assert len(resultat["candidats_rattrapage"]) == 1
    assert resultat["candidats_rattrapage"][0].type_indice == "tva"


def test_quarantaine_identite_jamais_fusionnee():
    fournisseurs = [
        _f("F1", siret="55204944700005"),  # SIRET invalide, non restaurable
        _f("F2", siret="55204944700005"),
    ]
    resultat = analyser(fournisseurs)
    assert resultat["familles"] == []
    assert len(resultat["quarantaine"]) == 2


def test_elire_fiche_maitre_ordre_de_priorite():
    ancienne_moins_exposee = _f("F1", date_creation="2018-01-01", nb_agences=0, nb_codes_erp=0)
    recente_plus_exposee = _f("F2", date_creation="2022-01-01", nb_agences=2, nb_codes_erp=1)
    assert elire_fiche_maitre([ancienne_moins_exposee, recente_plus_exposee]).id == "F2"


# --- Invariants globaux (chapitre 10) --------------------------------------


def _jeu_de_donnees_mixte():
    return [
        _f("F1", id_groupe="C1", nom_groupe="CETIH", nb_agences=2, date_creation="2019-01-01"),
        _f("F2", id_groupe="C1", nom_groupe="CETIH", nb_agences=0, date_creation="2021-06-01"),
        _f("F3", siret=SIRET_B, id_groupe="C1", nom_groupe="CETIH"),
        _f("F4", siret=SIRET_B, id_groupe="C2", nom_groupe="SALTI"),
        _f("F5", siret="55204944700014", ville="LYON"),  # restructuration : même SIREN que F1/F2, SIRET différent
        _f("F6", siret=None, tva=TVA_A),
        _f("F7", siret=None, tva=TVA_A),
        _f("F8", siret="55204944700005"),  # quarantaine
    ]


def test_famille_ne_porte_jamais_deux_siret_ou_deux_siren():
    resultat = analyser(_jeu_de_donnees_mixte())
    for fam in resultat["familles"]:
        assert len({m.identite.siret for m in fam.membres}) == 1
        assert len({m.identite.siren for m in fam.membres}) == 1


def test_aucun_membre_de_famille_invalide_ou_en_quarantaine():
    resultat = analyser(_jeu_de_donnees_mixte())
    for fam in resultat["familles"]:
        for m in fam.membres:
            assert m.identite.statut != StatutIdentite.QUARANTAINE_INCOHERENCE
            assert m.identite.siret is not None


def test_aucune_instruction_pour_arbitrage_inter_tenants():
    resultat = analyser(_jeu_de_donnees_mixte())
    for fam in resultat["familles"]:
        if fam.population == Population.ARBITRAGE_INTER_TENANT:
            assert fam.fiche_a_conserver_id is None
            assert fam.fiches_a_fusionner_ids == []


def test_fiche_conservee_jamais_parmi_les_fiches_a_fusionner():
    resultat = analyser(_jeu_de_donnees_mixte())
    for fam in resultat["familles"]:
        if fam.fiche_a_conserver_id is not None:
            assert fam.fiche_a_conserver_id not in fam.fiches_a_fusionner_ids


def test_instructions_uniques_relancer_ne_duplique_pas():
    donnees = _jeu_de_donnees_mixte()
    resultat1 = analyser(donnees)
    resultat2 = analyser(donnees)
    assert len(resultat1["familles"]) == len(resultat2["familles"])
    assert len(resultat1["familles"]) == len({fam.siret for fam in resultat1["familles"]})


def test_deux_executions_successives_identiques():
    donnees = _jeu_de_donnees_mixte()
    r1 = analyser(donnees)
    r2 = analyser(list(reversed(donnees)))  # ordre d'entrée différent

    def instantane(resultat):
        return sorted(
            (fam.siret, fam.population.value, fam.palier.value if fam.palier else None, fam.fiche_a_conserver_id)
            for fam in resultat["familles"]
        )

    assert instantane(r1) == instantane(r2)
