"""Point d'entrée unique. Localise la source, enchaîne les étapes, écrit le livrable.

    python -m mdf.cli --liste-clients
    python -m mdf.cli --client "CETIH"

Le nom du client accepte une correspondance partielle, insensible à la casse.

IMPORTANT — schéma des exports : les noms de colonnes ci-dessous
(ALIAS_COLONNES) sont ceux attendus des trois exports quotidiens
FOURNISSEUR.csv, GROUPE.csv et CONFIG_FOURNISSEUR_AGENCE.csv. Cette
version de la skill a été écrite à partir de la spécification fonctionnelle
et n'a pas encore été rejouée sur un export réel : si les en-têtes de
production diffèrent, ajuster uniquement ALIAS_COLONNES ci-dessous — le
reste du moteur n'a pas à changer.
"""
from __future__ import annotations

import argparse
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from mdf.detection import analyser
from mdf.identite import resoudre_identite
from mdf.modele import Fournisseur
from mdf.rapport import (
    ClientAmbigu,
    ClientInconnu,
    construire_classeur,
    ecrire_synthese_json,
    resoudre_client,
    restreindre_perimetre,
)

FICHIER_FOURNISSEUR = "FOURNISSEUR.csv"
FICHIER_GROUPE = "GROUPE.csv"
FICHIER_CONFIG_AGENCE = "CONFIG_FOURNISSEUR_AGENCE.csv"
FICHIERS_REQUIS = (FICHIER_FOURNISSEUR, FICHIER_GROUPE, FICHIER_CONFIG_AGENCE)

# Variantes d'en-têtes acceptées par colonne canonique (comparaison insensible
# à la casse et aux accents, mais PAS aux séparateurs : "CODE_POSTAL" et
# "CODEPOSTAL" sont deux variantes distinctes à lister toutes les deux).
#
# Les noms en tête de chaque liste (fourn_id, fourn_nom, siret,
# codetva_intracom, adresse1/2/3, codepostal, ville, fourn_ownergrp,
# groupe_id, groupe_nom) sont les en-têtes RÉELS observés le 2026-09-17 sur
# Data_SFTP/FOURNISSEUR.csv et Data_SFTP/GROUPE.csv (SharePoint, site
# TEAM-iBAT77-F.CUSTOMERSUCCESS, 80. ANALYTICS/Dashboard_CARE/Data_SFTP/).
# Les noms restants sont des hypothèses conservées au cas où un autre export
# (client, environnement) utilise un schéma différent.
#
# Point non confirmé : CONFIG_FOURNISSEUR_AGENCE.csv fait ~191 Mo en
# production, trop volumineux pour être ouvert depuis cette session — son
# en-tête réel n'a pas pu être vérifié. Les alias ci-dessous restent des
# hypothèses pour ce fichier.
#
# Point à trancher avec un développeur : FOURNISSEUR.csv porte à la fois
# fourn_owner (probablement l'utilisateur créateur de la fiche) et
# fourn_ownergrp (probablement le groupe/tenant propriétaire, celui qui
# correspond à groupe_id dans GROUPE.csv). C'est fourn_ownergrp qui est
# mappé sur id_groupe ci-dessous ; à confirmer avant usage en production,
# car une confusion entre les deux casserait la distinction public/privé
# (§5 de reference/modele.md) et donc l'étanchéité entre clients.
ALIAS_COLONNES = {
    "fournisseur": {
        "id": ["FOURN_ID", "ID_FOURNISSEUR", "ID", "FOURNISSEUR_ID"],
        "raison_sociale": ["FOURN_NOM", "RAISON_SOCIALE", "NOM", "LIBELLE"],
        "siret": ["SIRET", "N_SIRET", "NUM_SIRET"],
        "tva": ["CODETVA_INTRACOM", "TVA_INTRACOM", "TVA_INTRACOMMUNAUTAIRE", "N_TVA", "NUM_TVA"],
        "adresse": ["ADRESSE1", "ADRESSE", "ADRESSE_1"],
        "adresse2": ["ADRESSE2", "ADRESSE_2"],
        "adresse3": ["ADRESSE3", "ADRESSE_3"],
        "code_postal": ["CODEPOSTAL", "CODE_POSTAL", "CP"],
        "ville": ["VILLE"],
        "id_groupe": ["FOURN_OWNERGRP", "ID_GROUPE", "GROUPE_ID", "ID_TENANT"],
        "date_creation": ["DATE_CREATION", "DATE_CREATE", "CREATED_AT"],
    },
    "groupe": {
        "id": ["GROUPE_ID", "ID_GROUPE", "ID"],
        "nom": ["GROUPE_NOM", "NOM_GROUPE", "NOM", "RAISON_SOCIALE"],
    },
    "config_agence": {
        "id_fournisseur": ["FOURN_ID", "ID_FOURNISSEUR", "FOURNISSEUR_ID"],
        "id_agence": ["ID_AGENCE", "AGENCE_ID"],
        "code_erp": ["CODE_ERP", "CODE_ERP_AGENCE"],
    },
}


class SourceIntrouvable(Exception):
    pass


def _cle(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return s.strip().upper()


def _lire_csv(chemin: Path) -> pd.DataFrame:
    for sep in (";", ",", "\t"):
        df = pd.read_csv(chemin, sep=sep, dtype=str, encoding="utf-8-sig", keep_default_na=True)
        if df.shape[1] > 1:
            return df
    return pd.read_csv(chemin, dtype=str, encoding="utf-8-sig")


def _mapper_colonnes(df: pd.DataFrame, alias: Dict[str, List[str]], fichier: str) -> Dict[str, str]:
    colonnes_normalisees = {_cle(c): c for c in df.columns}
    correspondance = {}
    for canonique, variantes in alias.items():
        trouve = next((colonnes_normalisees[_cle(v)] for v in variantes if _cle(v) in colonnes_normalisees), None)
        if trouve:
            correspondance[canonique] = trouve
    return correspondance


def localiser_exports(source_forcee: Optional[str] = None) -> Path:
    """Cherche un dossier contenant les trois exports requis.

    Ordre de recherche : --source explicite, variable d'environnement
    MDF_EXPORTS_DIR, puis quelques emplacements usuels du poste de travail.
    Ajuster CANDIDATS ci-dessous une fois l'emplacement réel de synchronisation
    SharePoint connu.
    """
    import os

    candidats: List[Path] = []
    if source_forcee:
        candidats.append(Path(source_forcee))
    env = os.environ.get("MDF_EXPORTS_DIR")
    if env:
        candidats.append(Path(env))
    home = Path.home()
    candidats += [
        home / "iSYBUY" / "Exports fournisseurs",
        home / "OneDrive - iSYBUY" / "Exports fournisseurs",
        home / "Documents" / "iSYBUY" / "Exports fournisseurs",
    ]

    for dossier in candidats:
        if dossier.is_dir() and all((dossier / f).is_file() for f in FICHIERS_REQUIS):
            return dossier

    examines = "\n".join(f"  - {c}" for c in candidats)
    raise SourceIntrouvable(
        "Aucun jeu d'exports complet (FOURNISSEUR.csv, GROUPE.csv, "
        "CONFIG_FOURNISSEUR_AGENCE.csv) n'a été trouvé.\n"
        f"Emplacements examinés :\n{examines}\n"
        "Relancer avec --source \"<dossier>\" pour indiquer l'emplacement exact."
    )


def _date_snapshot(dossier: Path) -> str:
    horodatages = [(dossier / f).stat().st_mtime for f in FICHIERS_REQUIS]
    return datetime.fromtimestamp(max(horodatages)).date().isoformat()


def charger_fournisseurs(dossier: Path) -> Tuple[List[Fournisseur], Dict[str, str]]:
    df_fourn = _lire_csv(dossier / FICHIER_FOURNISSEUR)
    df_groupe = _lire_csv(dossier / FICHIER_GROUPE)
    df_agence = _lire_csv(dossier / FICHIER_CONFIG_AGENCE)

    col_f = _mapper_colonnes(df_fourn, ALIAS_COLONNES["fournisseur"], FICHIER_FOURNISSEUR)
    col_g = _mapper_colonnes(df_groupe, ALIAS_COLONNES["groupe"], FICHIER_GROUPE)
    col_a = _mapper_colonnes(df_agence, ALIAS_COLONNES["config_agence"], FICHIER_CONFIG_AGENCE)

    for requis, fichier, cols in (
        ("id", FICHIER_FOURNISSEUR, col_f),
        ("siret", FICHIER_FOURNISSEUR, col_f),
        ("id", FICHIER_GROUPE, col_g),
        ("nom", FICHIER_GROUPE, col_g),
    ):
        if requis not in cols:
            raise SourceIntrouvable(
                f"Colonne « {requis} » introuvable dans {fichier}. "
                f"Colonnes disponibles : {list(df_fourn.columns if fichier == FICHIER_FOURNISSEUR else df_groupe.columns)}. "
                "Ajuster ALIAS_COLONNES dans mdf/cli.py."
            )

    groupes = {
        str(row[col_g["id"]]).strip(): str(row[col_g["nom"]]).strip()
        for _, row in df_groupe.iterrows()
        if pd.notna(row[col_g["id"]])
    }

    nb_agences: Dict[str, int] = {}
    nb_codes_erp: Dict[str, int] = {}
    if "id_fournisseur" in col_a and "id_agence" in col_a:
        for fid, grp in df_agence.groupby(col_a["id_fournisseur"]):
            nb_agences[str(fid).strip()] = grp[col_a["id_agence"]].nunique(dropna=True)
            if "code_erp" in col_a:
                nb_codes_erp[str(fid).strip()] = int(grp[col_a["code_erp"]].notna().sum())

    fournisseurs: List[Fournisseur] = []
    for _, row in df_fourn.iterrows():
        fid = str(row[col_f["id"]]).strip()
        id_groupe = str(row[col_f["id_groupe"]]).strip() if col_f.get("id_groupe") and pd.notna(row.get(col_f["id_groupe"])) else None
        if id_groupe in ("", "0", None):
            # "0" est le sentinel observé en production pour « aucun groupe propriétaire »
            # (fiche du référentiel partagé) — au même titre qu'une valeur vide.
            id_groupe = None

        adresse = " ".join(
            str(row.get(col_f[c], "") or "").strip()
            for c in ("adresse", "adresse2", "adresse3")
            if col_f.get(c) and pd.notna(row.get(col_f[c]))
        ).strip()

        f = Fournisseur(
            id=fid,
            raison_sociale=str(row.get(col_f.get("raison_sociale"), "") or "").strip(),
            siret_brut=row.get(col_f.get("siret")),
            tva_brut=row.get(col_f.get("tva")),
            adresse=adresse,
            code_postal=str(row.get(col_f.get("code_postal"), "") or "").strip(),
            ville=str(row.get(col_f.get("ville"), "") or "").strip(),
            id_groupe=id_groupe,
            nom_groupe=groupes.get(id_groupe) if id_groupe else None,
            date_creation=row.get(col_f.get("date_creation")),
            nb_agences=nb_agences.get(fid, 0),
            nb_codes_erp=nb_codes_erp.get(fid, 0),
        )
        f.identite = resoudre_identite(f.siret_brut, f.tva_brut)
        fournisseurs.append(f)

    return fournisseurs, groupes


def _lister_clients(fournisseurs: List[Fournisseur], groupes: Dict[str, str]) -> List[str]:
    """Clients ayant au moins un doublon actionnable ou un arbitrage. Un client sans
    doublon n'y figure pas : c'est un résultat valide, pas une erreur."""
    resultat = analyser(fournisseurs)
    ids_concernes = set()
    for fam in resultat["familles"]:
        ids_concernes.update(m.id_groupe for m in fam.membres if not m.est_public)
    return sorted(groupes[i] for i in ids_concernes if i in groupes)


def executer(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="mdf.cli", description="Détection des doublons fournisseurs iSYBUY (lecture seule).")
    parser.add_argument("--client", help="Nom du client à analyser (correspondance partielle, insensible à la casse).")
    parser.add_argument("--liste-clients", action="store_true", help="Liste les clients ayant au moins un doublon.")
    parser.add_argument("--source", help="Dossier contenant les trois exports, si la localisation automatique échoue.")
    parser.add_argument("--sortie", help="Dossier de sortie, à défaut Documents/Claude/<date>/Fournisseurs - Doublons.")
    parser.add_argument(
        "--base-complete",
        action="store_true",
        help="Produit un résultat nommant tous les clients. Usage interne strict — ne jamais transmettre à un client.",
    )
    args = parser.parse_args(argv)

    try:
        dossier_source = localiser_exports(args.source)
    except SourceIntrouvable as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Exports localisés : {dossier_source}")
    date_snapshot = _date_snapshot(dossier_source)
    print(f"Date du snapshot retenu : {date_snapshot}")

    fournisseurs, groupes = charger_fournisseurs(dossier_source)

    if args.liste_clients:
        clients = _lister_clients(fournisseurs, groupes)
        if not clients:
            print("Aucun client avec doublon détecté sur ce snapshot.")
        else:
            for nom in clients:
                print(nom)
        return 0

    resultat = analyser(fournisseurs)

    id_client = None
    libelle_perimetre = "Base complète — usage interne strict, ne jamais transmettre à un client"
    if args.base_complete:
        print("⚠ --base-complete : résultat nommant tous les clients. Usage interne strict.")
    elif args.client:
        try:
            id_client = resoudre_client(groupes, args.client)
        except ClientInconnu as exc:
            print(str(exc), file=sys.stderr)
            return 1
        except ClientAmbigu as exc:
            print(str(exc), file=sys.stderr)
            return 1
        libelle_perimetre = f"{groupes[id_client]} + référentiel partagé"
    else:
        parser.print_help()
        return 1

    resultat = restreindre_perimetre(resultat, id_client, args.base_complete)

    contexte = {"date_snapshot": date_snapshot, "libelle_perimetre": libelle_perimetre}
    dossier_sortie = Path(args.sortie) if args.sortie else Path.home() / "Documents" / "Claude" / date.today().isoformat() / "Fournisseurs - Doublons"
    nom_fichier = args.client or ("base-complete" if args.base_complete else "resultat")
    chemin_xlsx = dossier_sortie / f"Doublons fournisseurs - {nom_fichier}.xlsx"
    chemin_json = dossier_sortie / f"Doublons fournisseurs - {nom_fichier}.json"

    construire_classeur(resultat, chemin_xlsx, contexte)
    ecrire_synthese_json(resultat, chemin_json, contexte)

    print(f"Classeur écrit : {chemin_xlsx}")
    print(f"Synthèse JSON  : {chemin_json}")
    return 0


def main() -> None:
    sys.exit(executer())


if __name__ == "__main__":
    main()
