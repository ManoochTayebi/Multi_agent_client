# Trame de présentation — 6 slides

## 1. Une conversation client, plusieurs processus coordonnés

Atlas veut croître sans augmenter proportionnellement ses effectifs. Les demandes combinent souvent retour, suivi de livraison et conseil produit. CustomerAI partage le contexte et coordonne les spécialistes. Valeur attendue : temps de traitement réduit, cohérence des réponses et conseil plus pertinent. Le ROI reste à mesurer en pilote ; aucun gain chiffré n'est présenté comme acquis.

## 2. Six agents, des dépendances explicites

Orchestrateur central ; investigation des retours ; résolution ; découverte produit ; suivi de commande ; styliste personnel. Les recherches indépendantes se font en parallèle. La résolution utilise l'investigation et le styliste utilise les produits trouvés. Chaque rôle possède une mémoire de session et un plan borné. Les outils métier gardent le contrôle sur les droits, montants et stocks.

## 3. Données et ancrage métier

200 clients, 120 produits, 600 variantes, 600 commandes et expéditions, 60 historiques de retour. Données entièrement fictives, reproductibles et accompagnées d'empreintes SHA-256. RAG Chroma sur quatre politiques versionnées avec sources. SQL pour les faits transactionnels ; API transporteur simulée pour démontrer l'intégration externe. Embeddings lexicaux hors ligne, embeddings sémantiques configurables.

## 4. Démonstration de bout en bout

C0001 demande un remboursement de O1002 et une tenue à moins de 150 €. L'orchestrateur délègue l'investigation et la recherche produit. L'équipe propose une résolution et une tenue respectant le budget. Le client confirme. Le montant de 249 € déclenche une validation humaine ; l'opérateur motive sa décision. La file transactionnelle enregistre ensuite un paiement simulé. Les traces permettent d'expliquer les sources et transitions.

## 5. Qualité et supervision

Contrôles déterministes sur les données et actions ; juge LLM indépendant pour les cas complexes/à risque en mode LLM. Une défaillance du juge bloque l'action. Tests de cloisonnement client, limite de retour, idempotence et suppression de mémoire. Séparer les résultats du mode démo des résultats du vrai modèle : la démo valide le logiciel, pas la qualité conversationnelle d'un LLM.

## 6. Du prototype au pilote

FastAPI, LangGraph, SQLAlchemy, Chroma, interface web et Docker. CI : lint, tests, évaluation, construction et démarrage du conteneur. Suivi agrégé des erreurs, latences et usages modèle ; journal des décisions. Avant production : SSO/RBAC, verrous distribués, base vectorielle partagée, migrations, rétention, vrais connecteurs et évaluation indépendante. Déployer d'abord sur un périmètre limité et mesurer résolution, escalades, CSAT et coût/contact.
