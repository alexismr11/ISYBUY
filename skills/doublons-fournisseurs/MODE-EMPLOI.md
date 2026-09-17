# Doublons fournisseurs — mode d'emploi

Skill Claude Code · Delivery, Customer Success, Helpdesk
Référence métier IDT-14552 · Contact : Vincent Di Pasquale

## À quoi ça sert

Vous donnez un nom de client. Vous obtenez un classeur Excel qui dit, fiche
par fiche, laquelle conserver et laquelle fusionner, avec le niveau de
confiance et les contrôles à mener.

**La skill ne fusionne rien.** La fusion est irréversible. Elle est
réalisée par les développeurs iSYBUY à réception de la tâche Jira. La skill
lit des exports, elle n'écrit jamais dans iSYBUY.

## Installation — une fois par poste

1. **Copier la skill.** Copier le dossier `doublons-fournisseurs` dans
   `%USERPROFILE%\.claude\skills\`. Sans le sous-dossier `moteur\.venv`
   s'il est déjà présent (il sera recréé par l'installateur).
2. **Lancer l'installateur** :
   ```
   powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.claude\skills\doublons-fournisseurs\moteur\installer.ps1"
   ```
   Deux minutes environ. Il doit finir par `Installation terminee`. Toute
   autre issue est un échec : ne pas utiliser les résultats tant que
   l'installation n'est pas propre.
3. **Redémarrer Claude Code.**

## Utilisation courante

Dans Claude Code :
```
/doublons-fournisseurs
```
Claude vous accompagne étape par étape et lance les commandes. C'est la
seule chose à connaître pour un usage normal.

Ces phrases déclenchent aussi la skill, sans commande explicite : « analyse
les doublons de CETIH », « combien de doublons chez Salti », « prépare le
ticket de fusion pour NGE ».

### En ligne de commande, au besoin

```
cd "$env:USERPROFILE\.claude\skills\doublons-fournisseurs\moteur"
$env:PYTHONIOENCODING='utf-8'

.venv\Scripts\python.exe -m mdf.cli --liste-clients        # qui a des doublons
.venv\Scripts\python.exe -m mdf.cli --client "CETIH"        # analyser un client
```

Le nom du client accepte une correspondance partielle, insensible à la
casse.

## Ce que vous récupérez

Dans `Documents\Claude\<date>\Fournisseurs - Doublons\` : un classeur Excel
et une synthèse `.json`.

| Onglet | Ce qu'on y fait |
|---|---|
| **Synthèse** | Les volumes. À ouvrir en premier. |
| **Fusions certaines** | Fusionnables en l'état. |
| **Fusions à contrôler** | La colonne *Contrôles requis* dit quoi vérifier, ligne par ligne. Ce contrôle est humain. |
| **Arbitrages inter-tenants** | Décision de gouvernance. Pas un défaut de qualité. |
| **Restructurations** | Établissements réels d'une même entreprise. Ne pas fusionner : rattacher comme points de vente. |
| **Candidats rattrapage** | Indices à qualifier avant toute action. |
| **Quarantaine identité** | Identifiants qui se contredisent, avec la correction suggérée. |

Les colonnes *Statut · Opérateur · Date traitement · Commentaire* sont
vides volontairement : elles servent au suivi une fois le classeur en
main.

## Quatre réflexes

- **Ne pas additionner.** Doublons, arbitrages, restructurations et
  candidats sont quatre sujets distincts. Les additionner gonfle le
  volume et fait passer pour un défaut ce qui n'en est pas un.
- **Restructuration ≠ doublon.** Un SIREN avec plusieurs établissements,
  ce sont des points de vente. Les fusionner détruirait de l'information.
- **Toujours citer le snapshot.** La base évolue chaque jour. « 3
  doublons » n'a de sens qu'avec la date du snapshot analysé.
- **Ça se reproduit.** Les doublons se recréent à chaque import. Une
  passe unique ne règle rien durablement : l'analyse est à reconduire.

## Confidentialité

Un classeur client ne contient que les fiches de ce client et celles du
référentiel partagé, commun à tous. Aucune fiche d'un autre client n'y
figure.

**Exception : l'option `--base-complete`.** Elle produit un résultat qui
nomme tous les clients. Usage interne strict. Ne jamais le transmettre à un
client ni le déposer dans un espace partagé avec un client.

## Si ça coince

| Message | Que faire |
|---|---|
| `Aucun jeu d'exports complet` | Le message liste les emplacements examinés. Passer `--source "<dossier>"`. |
| `Client inconnu` | `--liste-clients`. Un client sans doublon n'y figure pas : c'est un résultat valide. |
| `Plusieurs clients correspondent` | Donner le nom complet ou l'identifiant affiché. |
| Python introuvable à l'installation | Sujet poste de travail : portail logiciel ou Microsoft Store, puis relancer. |
| Accents cassés à l'écran | `$env:PYTHONIOENCODING='utf-8'`. |
| Chiffres différents d'hier | Normal, la base évolue. Comparer deux dates, pas deux exécutions. |

## Pour aller plus loin

- `reference/modele.md` — comment la skill décide : clé de fusion,
  validation des identifiants, les quatre populations, paliers de
  confiance, garde-fous. Miroir du code dans `moteur/mdf/`.
- `reference/jira-idt.md` — gabarit de la tâche Jira IDT de fusion.
- `SKILL.md` — instructions suivies par Claude pendant une session.
