"""Les entités et les valeurs possibles : classes, causes, paliers, motifs.

Aucune règle de décision ici, seulement le vocabulaire partagé par
identite.py, detection.py et rapport.py. Voir reference/modele.md pour la
définition métier de chaque valeur.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class StatutIdentite(str, Enum):
    OK = "ok"
    MONACO_POSSIBLE = "monaco_possible"
    A_QUALIFIER_FRANCHISE = "a_qualifier_franchise"
    QUARANTAINE_INCOHERENCE = "quarantaine_incoherence"


class Population(str, Enum):
    DOUBLON_ACTIONNABLE = "doublon_actionnable"
    ARBITRAGE_INTER_TENANT = "arbitrage_inter_tenant"
    RESTRUCTURATION = "restructuration"
    CANDIDAT_RATTRAPAGE = "candidat_rattrapage"


class Palier(str, Enum):
    CERTAINE = "certaine"
    A_CONTROLER = "a_controler"
    ARBITRAGE = "arbitrage"  # aucune instruction émise


class Cause(str, Enum):
    RECREATION_SANS_RATTACHEMENT = "recreation_sans_rattachement"
    SAISIE_MULTIPLE_MEME_PERIMETRE = "saisie_multiple_meme_perimetre"
    ZERO_INITIAL_PERDU = "zero_initial_perdu"
    REFERENTIELS_CLIENTS_DISTINCTS = "referentiels_clients_distincts"
    INDETERMINEE = "indeterminee"


class SignalControle(str, Enum):
    RAISON_SOCIALE_DIVERGENTE = "raison_sociale_divergente"
    VILLES_DIFFERENTES = "villes_differentes"
    SIRET_RECONSTITUE = "siret_reconstitue"
    FICHE_RETENUE_SANS_AGENCE = "fiche_retenue_sans_agence"


LIBELLES_SIGNAUX = {
    SignalControle.RAISON_SOCIALE_DIVERGENTE: "Raisons sociales divergentes après normalisation",
    SignalControle.VILLES_DIFFERENTES: "Villes différentes entre les fiches de la famille",
    SignalControle.SIRET_RECONSTITUE: "SIRET reconstitué (zéro initial restauré) : vérifier la saisie",
    SignalControle.FICHE_RETENUE_SANS_AGENCE: (
        "La fiche retenue n'est configurée sur aucune agence alors qu'une autre l'est : "
        "vérifier la reprise des rattachements"
    ),
}

LIBELLES_CAUSES = {
    Cause.RECREATION_SANS_RATTACHEMENT: "Recréation au lieu d'un rattachement à la fiche partagée",
    Cause.SAISIE_MULTIPLE_MEME_PERIMETRE: "Saisie multiple dans le même périmètre",
    Cause.ZERO_INITIAL_PERDU: "Zéro initial perdu sur un SIRET",
    Cause.REFERENTIELS_CLIENTS_DISTINCTS: "Référentiels clients distincts, sans fiche partagée",
    Cause.INDETERMINEE: "Cause non déterminée automatiquement",
}


@dataclass
class Fournisseur:
    id: str
    raison_sociale: str
    siret_brut: str
    tva_brut: str
    adresse: str
    code_postal: str
    ville: str
    id_groupe: Optional[str]  # vide / None => fiche publique (référentiel partagé)
    nom_groupe: Optional[str]  # nom du client propriétaire, None si publique
    date_creation: Optional[str]
    nb_agences: int = 0
    nb_codes_erp: int = 0
    identite: object = None  # mdf.identite.IdentiteFournisseur, typé en amont pour éviter le cycle d'import

    @property
    def est_public(self) -> bool:
        return not self.id_groupe


@dataclass
class Famille:
    """Un groupe de fiches candidates à la fusion, réunies sur un même SIRET."""

    siret: str
    membres: list  # list[Fournisseur]
    population: Population
    palier: Optional[Palier] = None
    cause: Optional[Cause] = None
    signaux: list = field(default_factory=list)
    fiche_a_conserver_id: Optional[str] = None

    @property
    def fiches_a_fusionner_ids(self) -> list:
        """Aucune instruction émise pour un arbitrage inter-tenants : liste vide sans fiche maître."""
        if self.fiche_a_conserver_id is None:
            return []
        return [m.id for m in self.membres if m.id != self.fiche_a_conserver_id]


@dataclass
class GroupeRestructuration:
    """Même SIREN, plusieurs SIRET distincts : des points de vente, pas des doublons."""

    siren: str
    membres: list  # list[Fournisseur], un par SIRET distinct (le premier de chaque groupe)
    nb_etablissements: int


@dataclass
class CandidatRattrapage:
    """Indice de doublon sans SIRET exploitable pour trancher."""

    cle_indice: str
    type_indice: str  # "tva" | "raison_sociale_adresse"
    membres: list  # list[Fournisseur]


@dataclass
class FicheQuarantaine:
    fournisseur: "Fournisseur"
    motif: str
    correction_suggeree: Optional[str]
