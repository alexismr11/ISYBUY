---
name: doublons-fournisseurs
description: >-
  Détecte les fiches fournisseurs en doublon dans la base iSYBUY pour un
  client donné, à partir des exports quotidiens (FOURNISSEUR.csv,
  GROUPE.csv, CONFIG_FOURNISSEUR_AGENCE.csv), et prépare un classeur Excel
  d'actions ainsi qu'un brouillon de tâche Jira IDT de fusion. Utiliser
  cette skill à chaque fois que quelqu'un mentionne des doublons
  fournisseurs, une fiche fournisseur dupliquée ou créée deux fois, une
  fusion de fiches fournisseurs, un ticket de fusion, ou demande "analyse
  les doublons de <client>", "combien de doublons chez <client>", "prépare
  le ticket de fusion pour <client>" — même sans invoquer explicitement
  /doublons-fournisseurs. Couvre aussi les questions sur les points de
  vente d'un même fournisseur (restructurations, à ne pas confondre avec
  des doublons) et les arbitrages entre deux clients sur le même
  établissement. La skill ne fusionne jamais rien elle-même : lecture
  seule, elle propose, un humain décide.
---

# Doublons fournisseurs

Détecte les fiches fournisseurs iSYBUY qui désignent le même établissement,
classe-les selon le niveau de confiance, et prépare (sans jamais l'envoyer
sans accord) une tâche Jira de fusion pour l'équipe DEV.

**Point le plus important : cette skill est en lecture seule.** Elle ne se
connecte jamais à iSYBUY, ne modifie aucune fiche, et ne crée aucun ticket
Jira sans validation explicite de la personne qui l'utilise. Elle décrit le
travail à faire ; elle ne le fait pas. La fusion elle-même est irréversible
et est réalisée par les développeurs iSYBUY à réception du ticket.

Avant d'aller plus loin dans une session, lire `reference/modele.md` si la
question porte sur *pourquoi* une fiche est classée d'une certaine façon —
il détaille chaque règle (clé de fusion, populations, causes, paliers de
confiance) dont ce fichier ne donne que le résumé opérationnel.

## Ce qui déclenche cette skill

Toute demande d'analyse de doublons fournisseurs pour un client, avec ou
sans la commande `/doublons-fournisseurs` : "analyse les doublons de
CETIH", "combien de doublons chez Salti", "prépare le ticket de fusion pour
NGE", "il y a une fiche fournisseur en double chez X", etc. Le nom du
client accepte une correspondance partielle, insensible à la casse.

## Déroulé standard

### 1. Vérifier que le moteur est installé

Le moteur vit dans `moteur/` à côté de ce fichier, avec son propre
environnement virtuel Python (`moteur/.venv`), créé par
`moteur/installer.ps1` (voir `UTILISATION - installation`). S'il est
absent, l'indiquer clairement à l'utilisateur et proposer de lancer
l'installateur plutôt que d'essayer de contourner : ne jamais exécuter le
moteur avec un interpréteur Python autre que celui du venv, les versions de
pandas/openpyxl comptent.

```
<racine-skill>\moteur\.venv\Scripts\python.exe -m mdf.cli --liste-clients
```

Sur macOS/Linux (postes de développement), l'équivalent est
`moteur/.venv/bin/python -m mdf.cli`.

### 2. Lancer l'analyse pour le client demandé

```
<python-venv> -m mdf.cli --client "<nom du client>"
```

- Si le nom est ambigu ou inconnu, le moteur le dit explicitement et
  propose `--liste-clients` : relayer ce message tel quel, ne pas deviner
  le client à sa place.
- Si les exports ne sont pas localisés automatiquement, le moteur liste les
  emplacements examinés : demander à l'utilisateur le bon dossier et
  relancer avec `--source "<dossier>"`.
- Toujours annoncer la **date du snapshot** affichée par le moteur avant de
  donner le moindre chiffre : "3 doublons" n'a de sens qu'avec la date de
  l'export analysé, la base évolue chaque jour.

### 3. Présenter le résultat, jamais les quatre populations mélangées

Le classeur produit contient sept onglets. Ouvrir et résumer dans cet
ordre :

1. **Synthèse** — les volumes, à toujours citer en premier.
2. **Fusions certaines** — fusionnables en l'état, aucun signal d'alerte.
3. **Fusions à contrôler** — même SIRET valide, mais un point à vérifier
   (raison sociale divergente, villes différentes, SIRET reconstitué, ou
   fiche retenue non configurée sur une agence). La colonne *Contrôles
   requis* dit quoi vérifier, ligne par ligne.
4. **Arbitrages inter-tenants** — décision de gouvernance entre deux
   clients, **pas un défaut de qualité**. Aucune instruction n'est jamais
   émise ici automatiquement.
5. **Restructurations** — établissements réels d'une même entreprise
   (même SIREN, SIRET différents). **Ne jamais proposer de les fusionner** :
   ce sont des points de vente à rattacher, l'inverse détruirait de
   l'information.
6. **Candidats rattrapage** — indices sans SIRET exploitable, à qualifier
   avant toute action.
7. **Quarantaine identité** — identifiants qui se contredisent, jamais
   fusionnés ; la colonne *Correction suggérée* propose un SIRET corrigé
   quand c'est possible.

Ne jamais additionner ces sept chiffres en un seul total de "doublons" : ce
sont des sujets distincts, et les confondre gonfle artificiellement le
volume perçu.

### 4. Préparer le ticket Jira — seulement sur demande, seulement après accord

Quand l'utilisateur demande le ticket de fusion (ou dit explicitement
vouloir avancer sur les "fusions certaines") :

1. Construire le brouillon à partir du modèle `reference/jira-idt.md`
   (projet IDT, priorité Urgent, un tableau par famille de doublons
   certains avec SIRET, fiche à conserver, fiches à fusionner).
2. **Afficher le brouillon complet à l'utilisateur et attendre sa
   confirmation explicite avant toute création.** Ne jamais créer le
   ticket silencieusement, même si l'outil Jira est disponible dans la
   session.
3. Ne mettre dans le ticket que les familles au palier **Fusions
   certaines**. Les "à contrôler" attendent d'abord une vérification
   humaine ; ne pas les inclure sauf si l'utilisateur confirme les avoir
   contrôlées.
4. Une fois confirmé, créer le ticket via l'outil Jira disponible dans la
   session (Atlassian) et renvoyer le lien.

### 5. Rappeler que ça se reproduit

Les doublons se recréent à chaque import (typiquement par recréation d'une
copie privée au lieu d'un rattachement à la fiche partagée). Une passe
unique ne règle rien durablement : le rappeler quand l'utilisateur semble
considérer le sujet comme clos après une fusion.

## Confidentialité entre clients

Un classeur client ne contient **jamais** les fiches d'un autre client,
sauf celles du référentiel partagé (public, commun à tous). L'option
`--base-complete` nomme tous les clients à la fois : **usage interne strict
iSYBUY**, à ne jamais transmettre à un client ni déposer dans un espace
partagé avec un client. Ne jamais la proposer par défaut ; seulement à la
demande explicite d'une personne iSYBUY qui a besoin d'une vue transverse.

## Erreurs courantes et réponses

| Message du moteur | Ce qu'il faut faire |
|---|---|
| `Aucun jeu d'exports complet` | Demander le bon dossier, relancer avec `--source`. |
| `Client inconnu` | Lancer `--liste-clients`. Un client sans doublon n'y figure pas : résultat valide, pas une erreur à corriger. |
| `Plusieurs clients correspondent` | Redemander le nom complet ou l'identifiant affiché. |
| Chiffres différents d'un jour à l'autre | Normal, comparer deux dates de snapshot, pas deux exécutions du même jour. |

## Aller plus loin

- `MODE-EMPLOI.md` — installation détaillée, dépannage complet, usage en
  ligne de commande hors Claude Code.
- `reference/modele.md` — le détail exhaustif des règles de classification,
  miroir du code (`moteur/mdf/`).
- `reference/jira-idt.md` — gabarit exact de la tâche Jira IDT.
