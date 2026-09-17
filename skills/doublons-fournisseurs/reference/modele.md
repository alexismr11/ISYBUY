# Doublons fournisseurs — fonctionnement détaillé

Miroir métier du code dans `moteur/mdf/`. Si ce document et le code
divergent un jour, le code fait foi ; corriger ce fichier en conséquence.

> **Statut de cette version.** Ce moteur a été écrit à partir de la
> spécification fonctionnelle du sujet (référence IDT-14552), pas recopié
> d'un moteur de production existant. Les noms de colonnes des trois
> exports (`moteur/mdf/cli.py::ALIAS_COLONNES`) et les emplacements de
> recherche automatique (`moteur/mdf/cli.py::localiser_exports`) sont des
> hypothèses raisonnables, pas une confirmation du schéma réel. Avant
> premier usage en production, un développeur iSYBUY doit rejouer le moteur
> sur un export réel et ajuster ces deux points si nécessaire — le reste du
> moteur (identite.py, modele.py, detection.py, rapport.py) n'a pas à
> changer pour ça.

## 1. La chaîne complète

Six maillons, du fichier d'export jusqu'à la fusion. La skill couvre les
maillons 1 à 4. Les deux derniers sont humains.

1. **Exports quotidiens** — `FOURNISSEUR.csv`, `GROUPE.csv`,
   `CONFIG_FOURNISSEUR_AGENCE.csv`. Le moteur les localise seul
   (`localiser_exports`) et affiche la date du snapshot retenu (date de
   modification la plus récente des trois fichiers).
2. **Identification des fiches** — chaque identifiant est normalisé puis
   validé (`mdf/identite.py`). Les fiches dont les identifiants se
   contredisent sont mises de côté, jamais fusionnées.
3. **Regroupement et classement** — les fiches portant le même
   établissement sont regroupées, réparties entre quatre populations
   distinctes (`mdf/detection.py`), une cause est qualifiée et un palier de
   confiance attribué.
4. **Classeur d'actions** — sept onglets (`mdf/rapport.py`), une ligne par
   fiche, restreint au périmètre du client demandé.
5. **Contrôle et tâche Jira** — l'onglet *Fusions à contrôler* est vérifié
   par une personne. La tâche IDT est pré-remplie (`reference/jira-idt.md`),
   validée explicitement avant création.
6. **Fusion** — exécutée par les développeurs iSYBUY à réception du ticket.
   Irréversible.

**Le point le plus important : le moteur est en lecture seule.** Il ne se
connecte jamais à iSYBUY, ne modifie aucune fiche, ne crée aucun ticket
sans validation.

## 2. Comment une fiche est identifiée (`mdf/identite.py`)

Toute la normalisation et toute la validation passent par
`resoudre_identite()`, la seule fonction qui décide de l'identité d'une
fiche. Aucun autre composant ne valide un identifiant.

### Contrôles appliqués

- **SIREN (9 chiffres) et SIRET (14 chiffres)** : clé de Luhn (`_luhn_valide`
  — même algorithme, seule la longueur change).
- **Numéro de TVA intracommunautaire français** : la clé attendue se
  calcule à partir du SIREN — `clé = (12 + 3 × (SIREN mod 97)) mod 97`. Si
  la clé fournie ne correspond pas, le numéro n'est pas dit cohérent
  (`tva_coherente`). Les clés alphanumériques (schéma dérogatoire des
  grandes entreprises) ne sont ni validées ni invalidées : on ne sait pas
  les recalculer, elles ne servent alors qu'à comparer les SIREN.
- **Croisement** : quand le SIREN déduit du SIRET diverge de celui déduit
  de la TVA, le moteur regarde laquelle des deux clés est en tort :
  - SIREN du SIRET valide, TVA incohérente → la TVA est ignorée, le SIRET
    l'emporte, **pas de quarantaine**.
  - TVA cohérente, SIREN du SIRET invalide (en tant que SIREN à 9
    chiffres) → **quarantaine d'identité**, motif explicite.
  - Les deux valides et cohérents mais désignant des SIREN différents →
    **cas franchise** (§ ci-dessous), pas une quarantaine.
  - Aucun des deux concluant → **quarantaine d'identité**, motif
    « incohérence non résolue ».
- **SIRET sur 13 chiffres** : un zéro initial a été perdu au stockage. Il
  est restauré (`siret_reconstruit = True`) si le SIRET à 14 chiffres
  obtenu passe la clé de Luhn ; sinon la valeur brute est conservée pour
  motiver une éventuelle quarantaine.

### Deux cas qui ne sont pas des erreurs

- **Entités monégasques** : numéro de TVA française cohérent dont le
  SIREN apparent ne respecte pas sa propre clé de Luhn. Statut
  `MONACO_POSSIBLE`, jamais traité comme une erreur — de toute façon, sans
  SIRET valide, une telle fiche ne peut jamais servir de clé de fusion.
- **Franchise** : deux identifiants valides désignant des entreprises
  différentes (l'établissement porte le numéro de TVA du franchiseur).
  Statut `A_QUALIFIER_FRANCHISE`. La fiche garde son SIRET (donc reste
  éligible au regroupement par SIRET comme n'importe quelle autre fiche) ;
  seule la comparaison SIRET/TVA n'est pas traitée comme une alarme.

### Quarantaine d'identité

Statut `QUARANTAINE_INCOHERENCE`. La fiche sort de toute détection de
doublon et atterrit dans l'onglet *Quarantaine identité*, avec le motif et,
quand c'est possible, une correction suggérée (SIRET restauré). Elle n'est
jamais fusionnée : mieux vaut une fiche en attente qu'une fusion fausse.

## 3. Sur quoi les fiches sont regroupées (`detecter_familles`)

**Une seule clé de fusion : le SIRET à 14 chiffres, clé de Luhn vérifiée,
hors quarantaine.** Rien d'autre ne regroupe deux fiches — ni le numéro de
TVA intracommunautaire (commun à toute une entreprise, porté par le
franchiseur dans le cas d'une franchise), ni la raison sociale (nombreux
homonymes, valeurs non discriminantes), ni l'adresse (signal de contrôle
seulement).

Le numéro de TVA sert à deux choses seulement : dériver le SIREN quand le
SIRET manque, et contredire un SIRET incohérent (§2).

## 4. Les quatre populations

Disjointes, elles ne s'additionnent pas. Les confondre gonfle
artificiellement le volume et fait passer pour un défaut ce qui n'en est
pas un.

| Population | Définition | Action |
|---|---|---|
| **Doublons actionnables** | Même établissement, plusieurs fiches. Seules ces familles reçoivent une instruction de fusion. | Fusionner |
| **Arbitrages inter-tenants** | Fiches privées de clients différents sur le même établissement, sans fiche partagée. Décision de gouvernance, pas technique. | Arbitrer — aucune instruction émise |
| **Restructurations** | Même SIREN, plusieurs SIRET distincts : ce sont les points de vente d'une même entreprise, pas des doublons. | Rattacher, ne jamais fusionner |
| **Candidats de rattrapage** | Indice de doublon sans SIRET exploitable pour trancher. | Qualifier d'abord |

### Règle de décision (`_classer_famille_siret`)

Pour une famille regroupée sur un même SIRET :

1. **Une fiche publique est présente** (peu importe combien de clients
   privés différents sont aussi présents) → `DOUBLON_ACTIONNABLE`. La cible
   de fusion est toujours la fiche publique (§7), donc la présence de
   plusieurs clients privés ne crée pas de conflit d'arbitrage : chacun
   consolide vers le référentiel partagé.
2. **Aucune fiche publique, un seul client privé** → `DOUBLON_ACTIONNABLE`
   (doublon interne à ce client).
3. **Aucune fiche publique, plusieurs clients privés différents** →
   `ARBITRAGE_INTER_TENANT`.

## 5. Classement par visibilité

iSYBUY est multi-tenant. Une fiche est **publique** quand son groupe
propriétaire est vide : elle appartient au référentiel partagé, commun à
tous les clients. Sinon elle est **privée** à un client
(`Fournisseur.est_public`).

| Composition de la famille | Lecture |
|---|---|
| Toutes publiques | Référentiel commun pollué. Impact maximal, visible de tous les clients. |
| Une publique + une ou plusieurs copies privées | Motif principal du référentiel : une copie privée créée alors qu'une fiche partagée existait déjà. Consolidation vers la fiche partagée. |
| Toutes du même client | Doublon interne à ce client. |
| Clients différents, sans fiche publique | Arbitrage obligatoire, jamais d'automatisme. |

## 6. Causes qualifiées

| Cause | Critère (`_classer_famille_siret`) |
|---|---|
| Recréation au lieu d'un rattachement | Une fiche publique est présente dans la famille aux côtés d'au moins une copie privée. |
| Saisie multiple dans le même périmètre | Toutes les fiches privées relèvent du même client (ou toutes publiques, le périmètre étant alors le référentiel partagé lui-même). |
| Zéro initial perdu | Un des membres a un SIRET restauré (13→14 chiffres) et la cause par défaut aurait été « saisie multiple » — priorité donnée à cette cause plus précise. |
| Référentiels clients distincts | Population `ARBITRAGE_INTER_TENANT` par définition. |

## 7. Quelle fiche est conservée (`elire_fiche_maitre`)

Priorité, dans cet ordre strict (chaque critère ne départage qu'à égalité
du précédent) :

1. **Une fiche publique existe** → elle est la cible, quelle que soit son
   exposition.
2. **Exposition** : nombre d'agences configurées (`nb_agences`), puis
   nombre de codes ERP (`nb_codes_erp`).
3. **Complétude des identifiants** : SIRET valide, TVA renseignée,
   adresse, code postal, ville.
4. **Ancienneté** : la fiche la plus ancienne (`date_creation`).

Aucune famille d'arbitrage inter-tenants n'a de fiche maître élue : la
décision est humaine, pas technique.

## 8. Paliers de confiance

| Palier | Condition | Ce que vous faites |
|---|---|---|
| **Certaine** | Même SIRET valide, aucun des quatre signaux ci-dessous. | Fusionnable en l'état. |
| **À contrôler** | Même SIRET valide, mais au moins un signal. | Vérifier le motif indiqué, puis fusionner. |
| **Arbitrage** | La fusion croiserait les référentiels de deux clients différents. | Aucune instruction émise. Décision de gouvernance. |

### Les quatre signaux qui déclassent en « à contrôler »

1. **Raisons sociales divergentes** après normalisation (accents, casse,
   ponctuation retirés).
2. **Villes différentes** entre les fiches de la famille.
3. **SIRET reconstitué** par restauration du zéro initial.
4. **La fiche retenue n'est configurée sur aucune agence** alors qu'une
   autre l'est (le cas le plus fréquent : une fiche publique moins exposée
   l'emporte sur une copie privée par la règle 1 du §7).

Le motif exact est écrit ligne par ligne dans la colonne *Contrôles
requis* du classeur.

## 9. Restructurations (`detecter_restructurations`)

Regroupement par SIREN, indépendant du regroupement par SIRET du §4.
N'inclut que les groupes où au moins deux SIRET distincts et valides
partagent le même SIREN — une famille déjà regroupée sur un SIRET commun
n'est pas une restructuration, c'est le cas normal du §4. Les fiches en
quarantaine d'identité n'y participent jamais.

## 10. Candidats de rattrapage (`detecter_candidats_rattrapage`)

Ne concerne que les fiches sans SIRET exploitable (absent, invalide, ou en
quarantaine). Deux indices, jamais utilisés comme clé de fusion, seulement
comme signal à qualifier :

- **Numéro de TVA intracommunautaire partagé**, cohérent, entre au moins
  deux fiches isolées.
- **Raison sociale normalisée + code postal identiques**, à défaut de TVA
  partagée (pour ne pas manquer un indice supplémentaire sur les fiches
  restantes).

## 11. Étanchéité entre clients (`restreindre_perimetre`)

Un classeur client ne contient que les fiches de ce client et celles du
référentiel partagé. Règle appliquée groupe par groupe (famille,
restructuration, candidat) : **si un groupe contient la fiche privée d'un
autre client, le groupe entier est retiré du périmètre — jamais tronqué.**
Une famille d'arbitrage entre le client demandé et un autre client
n'apparaît donc dans aucun des deux classeurs individuels : seule
`--base-complete` la montre.

**Exception : `--base-complete`.** Produit un résultat nommant tous les
clients. Usage interne strict. Ne jamais le transmettre à un client ni le
déposer dans un espace partagé avec un client.

## 12. Ce que les tests garantissent (`moteur/tests/`)

`test_identite.py` et `test_detection.py` vérifient des invariants, pas
seulement des chiffres, rejouables sur n'importe quel snapshot :

- une famille ne porte jamais qu'un seul SIRET, donc qu'un seul SIREN ;
- aucun membre de famille n'a un SIRET invalide, ni n'est en quarantaine
  d'identité ;
- aucune instruction n'est émise pour un arbitrage inter-tenants ;
- la fiche conservée n'apparaît jamais parmi les fiches à fusionner ;
- les instructions sont uniques (relancer l'analyse ne produit pas de
  doublon de demande) ;
- deux exécutions successives, même avec les fiches en entrée dans un
  ordre différent, donnent un résultat identique.

## 13. Ce que le moteur ne fait jamais

- Fusionner une fiche.
- Créer un ticket Jira sans validation explicite (ça, c'est la
  responsabilité de `SKILL.md`, pas du moteur : le moteur ne parle à
  aucune API externe).
- Modifier quoi que ce soit dans iSYBUY.
- Fusionner deux SIREN valides différents.
- Fusionner sur la seule base d'un numéro de TVA ou d'une raison sociale.
- Fusionner une fiche dont les identifiants se contredisent.
- Trancher un arbitrage entre deux clients.
- Mélanger deux clients dans un livrable (hors `--base-complete`).
- Produire un chiffre qui ne vient pas du moteur.

## 14. Une limite structurelle à connaître

Les doublons se recréent à chaque import de référentiel fournisseur,
notamment par recréation d'une copie privée au lieu d'un rattachement à la
fiche partagée. Un nettoyage isolé ne règle rien durablement : il faut
reconduire l'analyse, et si possible traiter la cause à la source (§6).

## 15. Composition technique

| Composant | Rôle |
|---|---|
| `moteur/mdf/identite.py` | Normalisation et validation des identifiants. Couche unique. |
| `moteur/mdf/modele.py` | Entités et valeurs possibles : classes, causes, paliers, motifs. |
| `moteur/mdf/detection.py` | Regroupement, classement, qualification, élection de la fiche à conserver. |
| `moteur/mdf/rapport.py` | Restriction au périmètre client, classeur Excel, synthèse JSON. |
| `moteur/mdf/cli.py` | Point d'entrée unique. Localise la source, charge les exports, enchaîne les étapes. |
| `moteur/tests/test_identite.py`, `test_detection.py` | Les garde-fous du §12. |

Deux bibliothèques seulement : pandas et openpyxl. Aucune correspondance
approximative de noms n'est utilisée pour regrouper deux fiches — le modèle
décide sur des identifiants, jamais sur une ressemblance.
