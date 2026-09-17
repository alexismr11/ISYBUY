"""Normalisation et validation des identifiants d'entreprise.

Couche unique : c'est ici, et nulle part ailleurs dans le moteur, que sont
décidées la validité d'un SIRET, d'un SIREN ou d'un numéro de TVA
intracommunautaire français, et la manière de résoudre les incohérences
entre eux. Voir reference/modele.md pour le détail des règles.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from mdf.modele import StatutIdentite


def _luhn_valide(chiffres: str) -> bool:
    """Clé de Luhn (modulo 10) sur une chaîne de chiffres, quelle que soit sa longueur.

    C'est l'algorithme utilisé aussi bien pour la clé du SIREN (9 chiffres)
    que pour celle du SIRET (14 chiffres) : seule la longueur de la chaîne
    change, pas la méthode.
    """
    if not chiffres or not chiffres.isdigit():
        return False
    total = 0
    for i, c in enumerate(reversed(chiffres)):
        n = int(c)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def is_valid_siren(siren: Optional[str]) -> bool:
    return bool(siren) and len(siren) == 9 and siren.isdigit() and _luhn_valide(siren)


def is_valid_siret(siret: Optional[str]) -> bool:
    return bool(siret) and len(siret) == 14 and siret.isdigit() and _luhn_valide(siret)


def _chiffres(valeur) -> str:
    """Extrait les chiffres d'une valeur brute d'export (gère NaN/None/espaces)."""
    if valeur is None:
        return ""
    s = str(valeur).strip()
    if s.lower() in ("", "nan", "none", "nd", "n/d"):
        return ""
    return re.sub(r"\D", "", s)


def _clef_tva_attendue(siren9: str) -> str:
    """Clé de contrôle attendue d'un numéro de TVA intracommunautaire français.

    clé = (12 + 3 * (SIREN mod 97)) mod 97, sur deux chiffres.
    """
    n = int(siren9)
    return f"{(12 + 3 * (n % 97)) % 97:02d}"


@dataclass
class _TvaParsee:
    normalisee: Optional[str]  # "FRxx#########" ou None si non exploitable
    cle: Optional[str]
    siren: Optional[str]
    cle_coherente: bool  # la clé correspond-elle au SIREN apparent ?


def _normaliser_tva(valeur) -> _TvaParsee:
    if valeur is None:
        return _TvaParsee(None, None, None, False)
    s = re.sub(r"[\s.\-]", "", str(valeur).strip().upper())
    if s.lower() in ("", "nan", "none"):
        return _TvaParsee(None, None, None, False)
    m = re.fullmatch(r"FR([0-9A-Z]{2})(\d{9})", s)
    if not m:
        # Certains exports ne portent que la partie numérique, sans préfixe FR.
        m2 = re.fullmatch(r"(\d{2})(\d{9})", s)
        if not m2:
            return _TvaParsee(None, None, None, False)
        cle, siren = m2.group(1), m2.group(2)
    else:
        cle, siren = m.group(1), m.group(2)
    normalisee = f"FR{cle}{siren}"
    if cle.isdigit():
        coherente = cle == _clef_tva_attendue(siren)
    else:
        # Clé alphanumérique (grandes entreprises, schéma dérogatoire) :
        # on ne sait pas la recalculer ici, on ne la déclare donc ni valide ni fautive.
        coherente = False
    return _TvaParsee(normalisee, cle, siren, coherente)


def _normaliser_siret(valeur) -> tuple[Optional[str], bool, Optional[str]]:
    """Retourne (siret_utilisable, a_ete_reconstruit, siret_brut_si_invalide)."""
    digits = _chiffres(valeur)
    if not digits:
        return None, False, None
    if len(digits) == 14 and _luhn_valide(digits):
        return digits, False, None
    if len(digits) == 13:
        candidat = "0" + digits
        if _luhn_valide(candidat):
            return candidat, True, None
    # Rien n'a pu être validé : on conserve la valeur brute pour motiver la quarantaine.
    return None, False, digits


@dataclass
class IdentiteFournisseur:
    siret: Optional[str] = None
    siret_reconstruit: bool = False
    siren: Optional[str] = None
    siren_source: Optional[str] = None  # "siret" | "tva" | None
    tva: Optional[str] = None
    tva_coherente: bool = False
    statut: StatutIdentite = StatutIdentite.OK
    motif: Optional[str] = None

    @property
    def utilisable_pour_fusion(self) -> bool:
        """Seul un SIRET valide et hors quarantaine sert de clé de fusion."""
        return self.siret is not None and self.statut != StatutIdentite.QUARANTAINE_INCOHERENCE


def resoudre_identite(siret_brut, tva_brut) -> IdentiteFournisseur:
    """Construit l'identité normalisée d'une fiche fournisseur.

    Ordre des priorités, fidèle au fonctionnement documenté :
    1. Valider le SIRET (avec restauration d'un zéro initial perdu).
    2. Valider/analyser le numéro de TVA intracommunautaire.
    3. Si les deux désignent des SIREN différents, désigner lequel est fautif
       quand c'est possible ; sinon distinguer le cas « franchise » (deux
       identifiants valides, entreprises différentes) du cas réellement
       incohérent, qui part seul en quarantaine d'identité.
    4. Repérer le profil Monaco (TVA française dont le SIREN apparent ne
       respecte pas sa propre clé de Luhn) pour ne pas le traiter en erreur.
    """
    siret, siret_reconstruit, siret_brut_invalide = _normaliser_siret(siret_brut)
    tva_parsee = _normaliser_tva(tva_brut)

    siren_siret = siret[:9] if siret else None
    siren_siret_valide = is_valid_siren(siren_siret) if siren_siret else None
    siren_tva = tva_parsee.siren

    statut = StatutIdentite.OK
    motif: Optional[str] = None
    siret_utilisable = siret

    if siret and siren_tva and siren_siret != siren_tva:
        tva_coherente = tva_parsee.cle_coherente
        if siren_siret_valide and not tva_coherente:
            # Le SIREN issu du SIRET est valide, la clé de TVA ne l'est pas : le SIRET l'emporte.
            motif = None
        elif tva_coherente and not siren_siret_valide:
            statut = StatutIdentite.QUARANTAINE_INCOHERENCE
            motif = (
                f"SIREN divergents : {siren_siret} (issu du SIRET) vs {siren_tva} "
                f"(issu de la TVA) — la clé du SIREN issu du SIRET est invalide."
            )
            siret_utilisable = None
        elif siren_siret_valide and tva_coherente:
            statut = StatutIdentite.A_QUALIFIER_FRANCHISE
            motif = (
                f"SIREN divergents : {siren_siret} (SIRET) vs {siren_tva} (TVA) — "
                f"deux identifiants valides, probablement deux entreprises "
                f"différentes (schéma franchise). Fiche non fusionnée, à qualifier."
            )
        else:
            statut = StatutIdentite.QUARANTAINE_INCOHERENCE
            motif = (
                f"SIREN divergents : {siren_siret} (SIRET) vs {siren_tva} (TVA) — "
                f"aucun des deux ne peut être désigné fautif automatiquement."
            )
            siret_utilisable = None

    if statut == StatutIdentite.OK and siret_brut_invalide and not siret:
        statut = StatutIdentite.QUARANTAINE_INCOHERENCE
        motif = f"SIRET invalide et non restaurable : {siret_brut_invalide} (clé de Luhn incorrecte)."

    siren: Optional[str] = None
    siren_source: Optional[str] = None
    if siret_utilisable:
        siren = siren_siret
        siren_source = "siret"
    elif siren_tva:
        siren = siren_tva
        siren_source = "tva"
        if statut == StatutIdentite.OK and not is_valid_siren(siren_tva) and tva_parsee.cle_coherente:
            statut = StatutIdentite.MONACO_POSSIBLE
            motif = (
                "Numéro de TVA intracommunautaire française cohérent, mais dont le "
                "SIREN apparent ne respecte pas sa propre clé de Luhn : profil "
                "d'établissement monégasque, pas une erreur de saisie."
            )

    return IdentiteFournisseur(
        siret=siret_utilisable,
        siret_reconstruit=siret_reconstruit,
        siren=siren,
        siren_source=siren_source,
        tva=tva_parsee.normalisee,
        tva_coherente=tva_parsee.cle_coherente,
        statut=statut,
        motif=motif,
    )
