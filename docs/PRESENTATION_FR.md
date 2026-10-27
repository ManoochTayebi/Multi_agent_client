# Atlas CustomerAI — trame de présentation, 6 slides

Durée visée : 8–10 minutes, dont deux courtes démonstrations. Présenter les limites avec les résultats, sans promettre un ROI déjà mesuré.

## 1. Réduire les ruptures dans le parcours client

**Message :** une demande peut réunir suivi, retour et conseil produit ; le client ne devrait pas répéter son contexte.

- Atlas Fashion Group : marque et données fictives pour le cas Saegus.
- Résultat attendu : résolution plus cohérente, supervision des exceptions, recommandations utiles.
- Valeur à mesurer en pilote : résolution au premier contact, temps de traitement, escalades pertinentes, satisfaction et conversion.

**Visuel :** une conversation → trois besoins → une réponse ancrée et une action supervisée.

**À dire :** « Le prototype prouve un parcours logiciel et des appels modèle réels. Les gains économiques restent une hypothèse de pilote. »

## 2. Six responsabilités, des dépendances justifiées

| Agent | Responsabilité propre | Passage de relais |
|---|---|---|
| Orchestrateur | Comprendre les objectifs, extraire les contraintes et agréger | Distribue les tâches indépendantes |
| Investigation retours | Établir les faits, l'éligibilité et les signaux de revue | Fournit les preuves à la résolution |
| Résolution | Choisir proposition standard, exception ou assistance humaine | Attend confirmation et validations |
| Découverte produit | Rechercher et classer des variantes disponibles | Fournit les candidats au styliste |
| Suivi commande | Vérifier statut transporteur et provenance/cache | Partage le statut vérifié |
| Styliste | Choisir une tenue compatible et son budget total | Fournit les variantes exactes sélectionnées |

**Visuel :** diagramme du README : workers LangGraph `Send` en parallèle, jonction des preuves, décisions dépendantes et contrôle qualité.

**À dire :** « Deux recherches indépendantes peuvent avancer ensemble. L'investigation ne décide pas du remboursement ; la découverte ne compose pas la tenue. Le juge est un contrôle séparé, pas un septième rôle métier. »

## 3. Des décisions modèle, ancrées dans des outils métier

- SQL : identité authentifiée, commandes, conditions, prix et stocks ; paramètres contrôlés côté serveur.
- RAG Chroma : politiques citées et recherche sémantique du catalogue ; filtres commerciaux vérifiés en SQL.
- Appels de fonctions natifs, avec schémas et budgets d'exécution ; erreurs d'arguments renvoyées au modèle.
- Résolution et sélection des variantes guidées par le modèle, puis contrôlées par des règles métier.
- Mémoire durable SQL par session et par agent ; traces d'outils, sources et décisions. Pas de checkpoint durable de chaque étape du graphe.

**À dire :** « Le modèle choisit des outils et des recommandations. Il ne choisit ni l'identité client, ni le montant, ni une requête SQL libre. Le transporteur fourni et les paiements sont simulés. »

## 4. Démontrer deux parcours complets

**Parcours A — retour et résolution :** compte C0001, `Refund O1002`. Investigation → proposition de 249 € → contrôle qualité → confirmation client → revue opérateur motivée → exécution simulée → audit. Une approbation avant confirmation est rejetée ; un second traitement ne produit pas de double paiement.

**Parcours B — suivi et stylisme en parallèle :** compte C0001, `Track O1001 and build a smart casual outfit under EUR 150, size M`. Suivi et découverte démarrent en parallèle ; le styliste exploite les produits trouvés ; la réponse rassemble statut sourcé et tenue sous 150 €. Montrer les intervalles d'exécution et les variantes choisies dans la trace.

**Préparation :** démarrer Ollama et l'API, vérifier `/health`, utiliser une base de démonstration dédiée neuve et une nouvelle session pour revoir tous les états de paiement. Les évaluations utilisent automatiquement des bases temporaires. Une nouvelle session seule ne réinitialise pas un remboursement déjà traité : l'unicité par commande est volontaire. Pour une répétition complète, lancer une nouvelle base dédiée, par exemple `DATABASE_URL=sqlite:///runtime/presentation-01.db python -m uvicorn atlas.api:app --host 127.0.0.1 --port 8002`. Conserver les résultats enregistrés si une démonstration CPU est trop longue pour la soutenance ; annoncer clairement qu'il s'agit d'une exécution enregistrée.

## 5. Montrer les preuves et leurs limites

Résultats de développement enregistrés — Qwen3 1.7B local, CPU Intel, all-minilm :

| Preuve | Résultat |
|---|---|
| Tests hors ligne | 35/35 |
| Scénarios déterministes | 13/13 |
| Suite LLM complète | 11/13 stricts ; 2 exécution(s) avec fallback |
| Deux parcours LLM répétés deux fois | 4/4 stricts, 0 fallback |
| Latence des parcours LLM | p50 : 43.3 s ; p95 observé : 64.1 s |
| Politiques, recall@2 | 8/8 sondes de développement |
| Catégories produit, recall@3 | 2/2 sondes de développement |
| Coût fournisseur chat des 4 parcours | 0 USD en local ; 30,011 tokens, hors coûts d'exploitation |

Limite observée dans la suite complète : `tracking`, `missing_order`. Une récupération déterministe permet de répondre mais ne compte pas comme réussite LLM stricte.

Source : [VALIDATION.md](VALIDATION.md) et rapports JSON. Ces sondes ont guidé les corrections ; elles ne sont pas un jeu indépendant.

- Séparer les tests logiciel/démo des exécutions réelles du LLM.
- Afficher réussite stricte sans fallback, répétitions, latences p50/p95, tokens et coût fournisseur estimé.
- Afficher recall@2 des politiques et recall@3 des catégories produit ; les paraphrases exposent la différence lexical/sémantique.
- Mentionner erreurs observées, appels en échec, limites du petit modèle et juge utilisant le même modèle.
- Supervision : confirmations, revue obligatoire, audit et blocage des actions si preuves/juge indisponibles.

**À dire :** « Ces scénarios de développement ont guidé les corrections. Ils ne constituent ni un jeu de test indépendant, ni une mesure de CSAT ou de SLA. »

## 6. Un pilote mesurable, sans infrastructure prématurée

**Aujourd'hui :** FastAPI, LangGraph, SQLAlchemy, Chroma, interface client/opérateur, modèle local léger, dépendances verrouillées et scripts reproductibles.

**Avant un pilote réel :** identité d'entreprise et rôles, vraies intégrations transporteur/entrepôt/paiement, migrations et rétention, évaluation indépendante et charge mesurée. Ajouter verrous distribués, stockage vectoriel partagé et checkpoints seulement selon les exigences de fiabilité et d'échelle.

**Décision proposée :** pilote limité aux politiques et produits bien documentés, avec supervision des exceptions et objectifs de qualité/coût/latence convenus.

**Formule ROI à tester :** contacts éligibles × minutes économisées × coût horaire / 60 − coûts plateforme, modèles et supervision. Mesurer la conversion recommandation séparément pour éviter le double comptage.
