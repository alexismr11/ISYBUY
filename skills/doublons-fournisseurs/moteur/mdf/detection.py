"""Regroupement, classement, qualification, élection de la fiche à conserver.

Toute la logique de décision du moteur vit ici. Elle s'appuie uniquement sur
mdf.identite (validation des identifiants) et mdf.modele (vocabulaire) ; elle
ne lit ni n'écrit aucun fichier. Voir reference/modele.md pour la définition
métier de chaque règle appliquée ci-dessous.

Une seule clé de fusion : le SIRET à 14 chiffres, clé de Luhn vérifiée. Rien
d'autre — ni le numéro de TVA intracommunautaire, ni la raison sociale, ni
l'adresse — ne regroupe deux fiches entre elles.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import Dict, List, Optional

from mdf.modele import (
    Cause,
    CandidatRattrapage,
    Famille,
    FicheQuarantaine,
    Fournisseur,
    GroupeRestructuration,
    Palier,
    Population,
    SignalControle,
    StatutIdentite,
)


def normaliser_raison_sociale(valeur: Optional[str]) -> str:
    """Normalisation pour comparaison uniquement — jamais utilisée comme clé de fusion."""
    if not valeur:
        return ""
    s = unicodedata.normalize("NFKD", str(valeur)).encode("ascii", "ignore").decode("ascii")
    s = s.upper()
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normaliser_ville(valeur: Optional[str]) -> str:
    return normaliser_raison_sociale(valeur)


def _date_creation(f: Fournisseur) -> date:
    if not f.date_creation:
        return date.max
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(f.date_creation)[:10], fmt).date()
        except ValueError:
            continue
    return date.max


def _score_completude(f: Fournisseur) -> int:
    score = 0
    if f.identite and f.identite.siret:
        score += 1
    if f.identite and f.identite.tva:
        score += 1
    if f.adresse:
        score += 1
    if f.code_postal:
        score += 1
    if f.ville:
        score += 1
    return score


def elire_fiche_maitre(membres: List[Fournisseur]) -> Fournisseur:
    """Détermine la fiche maître d'une famille, dans l'ordre de priorité documenté :

    1. une fiche publique existe -> elle est la cible ;
    2. exposition : nombre d'agences configurées, puis nombre de codes ERP ;
    3. complétude des identifiants ;
    4. ancienneté (fiche la plus ancienne).
    """
    def clef(f: Fournisseur):
        return (
            0 if f.est_public else 1,
            -f.nb_agences,
            -f.nb_codes_erp,
            -_score_completude(f),
            _date_creation(f),
            f.id,
        )

    return sorted(membres, key=clef)[0]


def _signaux_et_palier(famille_membres: List[Fournisseur], maitre: Fournisseur) -> tuple[List[SignalControle], Palier]:
    signaux: List[SignalControle] = []

    raisons = {normaliser_raison_sociale(m.raison_sociale) for m in famille_membres if m.raison_sociale}
    if len(raisons) > 1:
        signaux.append(SignalControle.RAISON_SOCIALE_DIVERGENTE)

    villes = {normaliser_ville(m.ville) for m in famille_membres if m.ville}
    if len(villes) > 1:
        signaux.append(SignalControle.VILLES_DIFFERENTES)

    if any(m.identite and m.identite.siret_reconstruit for m in famille_membres):
        signaux.append(SignalControle.SIRET_RECONSTITUE)

    if maitre.nb_agences == 0 and any(m.nb_agences > 0 for m in famille_membres if m.id != maitre.id):
        signaux.append(SignalControle.FICHE_RETENUE_SANS_AGENCE)

    palier = Palier.A_CONTROLER if signaux else Palier.CERTAINE
    return signaux, palier


def _classer_famille_siret(membres: List[Fournisseur]) -> Famille:
    siret = membres[0].identite.siret
    clients_prives = {m.id_groupe for m in membres if not m.est_public}
    a_une_fiche_publique = any(m.est_public for m in membres)

    if a_une_fiche_publique:
        population = Population.DOUBLON_ACTIONNABLE
        cause = Cause.RECREATION_SANS_RATTACHEMENT if clients_prives else Cause.SAISIE_MULTIPLE_MEME_PERIMETRE
    elif len(clients_prives) > 1:
        population = Population.ARBITRAGE_INTER_TENANT
        cause = Cause.REFERENTIELS_CLIENTS_DISTINCTS
    else:
        population = Population.DOUBLON_ACTIONNABLE
        cause = Cause.SAISIE_MULTIPLE_MEME_PERIMETRE

    if any(m.identite.siret_reconstruit for m in membres) and cause == Cause.SAISIE_MULTIPLE_MEME_PERIMETRE:
        cause = Cause.ZERO_INITIAL_PERDU

    membres_tries = sorted(membres, key=lambda m: m.id)

    if population == Population.ARBITRAGE_INTER_TENANT:
        # Décision de gouvernance : aucune fiche maître désignée, aucune instruction émise.
        return Famille(
            siret=siret,
            membres=membres_tries,
            population=population,
            palier=Palier.ARBITRAGE,
            cause=cause,
            signaux=[],
            fiche_a_conserver_id=None,
        )

    maitre = elire_fiche_maitre(membres_tries)
    signaux, palier = _signaux_et_palier(membres_tries, maitre)
    return Famille(
        siret=siret,
        membres=membres_tries,
        population=population,
        palier=palier,
        cause=cause,
        signaux=signaux,
        fiche_a_conserver_id=maitre.id,
    )


def detecter_familles(fournisseurs: List[Fournisseur]) -> List[Famille]:
    """Regroupe par SIRET valide et hors quarantaine, puis classe chaque famille.

    Fidèle à l'invariant testé : une famille ne porte jamais qu'un seul
    SIRET, jamais un membre en quarantaine d'identité, et jamais un SIRET
    invalide.
    """
    par_siret: Dict[str, List[Fournisseur]] = {}
    for f in fournisseurs:
        if f.identite and f.identite.utilisable_pour_fusion:
            par_siret.setdefault(f.identite.siret, []).append(f)

    familles = [
        _classer_famille_siret(membres)
        for siret, membres in sorted(par_siret.items())
        if len(membres) > 1
    ]
    return familles


def detecter_restructurations(fournisseurs: List[Fournisseur]) -> List[GroupeRestructuration]:
    """Même SIREN, plusieurs SIRET distincts : des points de vente, pas des doublons.

    Ne fusionne jamais rien. N'inclut pas les familles déjà regroupées sur un
    SIRET identique (ce n'est pas une restructuration, c'est le cas normal).
    """
    par_siren: Dict[str, Dict[str, Fournisseur]] = {}
    for f in fournisseurs:
        if f.identite and f.identite.siret and f.identite.statut != StatutIdentite.QUARANTAINE_INCOHERENCE:
            par_siren.setdefault(f.identite.siren, {}).setdefault(f.identite.siret, f)

    groupes = []
    for siren, par_siret in sorted(par_siren.items()):
        if len(par_siret) > 1:
            membres = [par_siret[s] for s in sorted(par_siret)]
            groupes.append(GroupeRestructuration(siren=siren, membres=membres, nb_etablissements=len(membres)))
    return groupes


def detecter_candidats_rattrapage(
    fournisseurs: List[Fournisseur], deja_groupes_ids: set
) -> List[CandidatRattrapage]:
    """Indices de doublon sans SIRET exploitable pour trancher.

    Exposés explicitement pour ne jamais perdre silencieusement un faux
    négatif — mais jamais fusionnés : ce sont des candidats à qualifier.
    """
    isoles = [
        f
        for f in fournisseurs
        if f.id not in deja_groupes_ids
        and (not f.identite or not f.identite.siret or f.identite.statut == StatutIdentite.QUARANTAINE_INCOHERENCE)
    ]

    par_tva: Dict[str, List[Fournisseur]] = {}
    par_nom_adresse: Dict[str, List[Fournisseur]] = {}
    for f in isoles:
        if f.identite and f.identite.tva and f.identite.tva_coherente:
            par_tva.setdefault(f.identite.tva, []).append(f)
        cle_nom = normaliser_raison_sociale(f.raison_sociale)
        if cle_nom and f.code_postal:
            par_nom_adresse.setdefault(f"{cle_nom}|{f.code_postal}", []).append(f)

    candidats: List[CandidatRattrapage] = []
    deja_pris: set = set()
    for tva, membres in sorted(par_tva.items()):
        if len(membres) > 1:
            candidats.append(CandidatRattrapage(cle_indice=tva, type_indice="tva", membres=sorted(membres, key=lambda m: m.id)))
            deja_pris.update(m.id for m in membres)

    for cle, membres in sorted(par_nom_adresse.items()):
        membres_restants = [m for m in membres if m.id not in deja_pris]
        if len(membres_restants) > 1:
            candidats.append(
                CandidatRattrapage(
                    cle_indice=cle, type_indice="raison_sociale_adresse", membres=sorted(membres_restants, key=lambda m: m.id)
                )
            )

    return candidats


def detecter_quarantaine(fournisseurs: List[Fournisseur]) -> List[FicheQuarantaine]:
    lignes = []
    for f in fournisseurs:
        if f.identite and f.identite.statut == StatutIdentite.QUARANTAINE_INCOHERENCE:
            correction = None
            if f.identite.siret_reconstruit and f.identite.siret:
                correction = f"SIRET restauré : {f.identite.siret}"
            lignes.append(FicheQuarantaine(fournisseur=f, motif=f.identite.motif or "", correction_suggeree=correction))
    return sorted(lignes, key=lambda l: l.fournisseur.id)


def analyser(fournisseurs: List[Fournisseur]) -> dict:
    """Point d'entrée du moteur de détection : exécute les quatre passes.

    Pur et déterministe : rejouer sur les mêmes données produit exactement
    le même résultat (aucun horodatage, aucun ordre dépendant d'un
    dictionnaire non trié n'entre dans le calcul).
    """
    familles = detecter_familles(fournisseurs)
    restructurations = detecter_restructurations(fournisseurs)

    ids_deja_groupes = set()
    for fam in familles:
        ids_deja_groupes.update(m.id for m in fam.membres)
    for grp in restructurations:
        ids_deja_groupes.update(m.id for m in grp.membres)

    candidats = detecter_candidats_rattrapage(fournisseurs, ids_deja_groupes)
    quarantaine = detecter_quarantaine(fournisseurs)

    return {
        "familles": familles,
        "restructurations": restructurations,
        "candidats_rattrapage": candidats,
        "quarantaine": quarantaine,
    }
