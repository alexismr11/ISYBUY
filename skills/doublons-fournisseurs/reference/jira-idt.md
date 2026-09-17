# Gabarit de la tâche Jira IDT — fusion de doublons fournisseurs

Utilisé par `SKILL.md`, étape 4, uniquement après validation explicite de
la personne qui utilise la skill. Le moteur (`moteur/mdf/`) ne connaît pas
Jira et n'y touche jamais : la création du ticket est une action de
Claude, dans la session, via l'outil Jira disponible (Atlassian), jamais
automatique.

> **À confirmer avec un développeur iSYBUY avant premier usage.** La clé de
> projet (`IDT`), le type de ticket et les champs ci-dessous sont déduits
> de la référence métier du sujet (IDT-14552) et des documents
> fonctionnels fournis, pas d'une lecture du projet Jira réel. Si le nom du
> projet, le type de ticket ou un champ obligatoire diffère, ajuster ce
> gabarit — la skill ne fait que le suivre.

## Champs du ticket

| Champ | Valeur |
|---|---|
| Projet | `IDT` |
| Type | Tâche (à confirmer : peut-être un type dédié « Fusion fournisseur ») |
| Titre | `Fusion à faire — <NOM DU CLIENT>` |
| Priorité | Urgent |
| Labels | `doublons-fournisseurs` |
| Assigné | Non renseigné par défaut — laissé au triage DEV, sauf si l'utilisateur précise un destinataire |

## Corps du ticket

```markdown
## Fusion de doublons fournisseurs — <NOM DU CLIENT>

Snapshot analysé : <date du snapshot, ISO>
Classeur source : Doublons fournisseurs - <NOM DU CLIENT>.xlsx

### Fusions certaines — à exécuter

| SIRET | Fiche à conserver | Fiches à fusionner | Cause |
|---|---|---|---|
| <siret> | <id fiche maître> — <raison sociale> | <id>, <id>, ... | <cause> |

(une ligne par famille au palier "Fusions certaines" uniquement — les
"à contrôler" n'entrent dans le ticket qu'après vérification humaine
confirmée par l'utilisateur)

### Rappel

- Lecture seule côté skill : ces instructions n'ont encore modifié aucune
  fiche.
- La fusion est irréversible.
- En cas de doute sur une ligne, se référer à l'onglet "Fusions certaines"
  du classeur joint, colonne par colonne.
```

## Ce que Claude doit faire, dans l'ordre

1. Ne prendre que les familles du palier **Fusions certaines** (jamais
   « à contrôler » sans confirmation explicite que le contrôle a été fait).
2. Construire le tableau ci-dessus à partir du classeur produit par le
   moteur — jamais de chiffre qui ne vienne pas du classeur.
3. Afficher le brouillon complet (titre, priorité, tableau) à
   l'utilisateur.
4. Attendre une confirmation explicite ("oui, crée le ticket", "vas-y",
   etc.) — une simple lecture du brouillon par l'utilisateur n'est pas une
   confirmation.
5. Créer le ticket avec l'outil Jira disponible dans la session, puis
   renvoyer le lien du ticket créé.
6. Ne jamais créer un second ticket pour le même classeur sans que
   l'utilisateur l'ait redemandé explicitement.
