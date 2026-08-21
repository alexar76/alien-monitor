# 👽 Alien Monitor — visualiseur du pouls de l'écosystème AIMarket

> 🌍 **Langues :** [English](README.md) · [Русский](README.ru.md) · [Español](README.es.md) · **Français** · [中文](README.zh.md)
>
> La terminologie suit le [glossaire de localisation](https://github.com/alexar76/aicom/blob/main/docs/localization-glossary.md).
> La référence complète des variables d'environnement et du déploiement se trouve dans le [README en anglais](README.md).

> **Écosystème :** [présentation d'AICOM et démos en direct](https://modeldev.modelmarket.dev) · **Communauté :** [Telegram · Castor](https://t.me/just_for_agents) · [Discord · Pollux](https://discord.gg/aimarket)

**Démo en direct :** **[https://magic-ai-factory.com/monitor/](https://magic-ai-factory.com/monitor/)** (production sur l'hôte AI-Factory, mode LIVE).

**Pulse Terminal (ACEX)** tourne sur le même hôte : **[https://magic-ai-factory.com/pulse/](https://magic-ai-factory.com/pulse/)**.

Observez chaque composant — le hub, les contrats, les agents, les applications de bureau, les plugins, les chaînes — comme un cosmos vivant qui respire. Cliquez sur n'importe quel nœud pour vous en approcher, inspecter ses métriques et voir les données circuler dans le réseau en direct.

<p align="center">
  <a href="https://magic-ai-factory.com/monitor/">
    <img src="docs/recordings/alien-monitor-hero.gif" alt="Alien Monitor en mouvement — le graphe de l'écosystème en direct avec les métriques des nœuds et l'assistant IA intégré" width="820">
  </a>
  <br>
  <sub>Graphe de l'écosystème en direct · inspecteur de nœud · assistant IA intégré — <a href="https://magic-ai-factory.com/monitor/"><b>ouvrir la démo →</b></a></sub>
</p>

---

## Trois modes

### 🟢 Mode UNI
Chaîne locale + **interrogations en direct** des Hub, Mesh, Factory et Prometheus déployés : la même interface que LIVE, sans métriques simulées.

- EVM embarquée (Anvil) et, en option, un validateur Solana
- Déploiement automatique du séquestre (escrow) et du NFT sur la chaîne locale
- Webhook de la fabrique : `POST /api/universe/materialize`

### 🟡 Mode TEST
Un écosystème simulé et vivant, avec des agents, des canaux de paiement et des transactions fictifs. Les métriques y sont synthétiques, et l'interface comme l'assistant IA le disent explicitement.

### 🟢 Mode LIVE
Se connecte à l'infrastructure réelle (Hub, Mesh, Prometheus) **et au RPC on-chain** :

- EVM : `BASE_RPC_URL` / `ETHEREUM_RPC_URL` et les autres, selon `AIMARKET_PAYMENT_CHAIN`
- Contrats : `AIMARKET_ESCROW_EVM_ADDRESS`, `AIMARKET_NFT_CONTRACT`, `AIMARKET_ESCROW_SOLANA_PROGRAM_ID`
- Charge automatiquement le `aicom/.env` du dépôt parent lorsqu'il existe
- Débogage : `GET /api/chain/status`

---

## Ce que vous voyez

Un **univers observable personnel** où chaque corps céleste est un composant vivant :

| Élément visuel | Ce qu'il représente |
|----------------|---------------------|
| ☀️ **Hub solaire** avec couronne et anneaux de gravité | AIMarket Hub — le centre |
| 🪐 **Planètes en orbite** avec physique d'oscillation | Services centraux : Factory, Mesh, ACEX |
| 💎 **Nœuds cristallins** avec anneaux orbitaux | Contrats intelligents (EVM et Solana) |
| 🌌 **Nébuleuses** | Grappes de composants liés |
| 🕳️ **Tunnels de trou de ver** | Flux de données actifs entre services |
| 💫 **Ceintures d'astéroïdes** | Activité du réseau blockchain |
| ✨ **Poussière cosmique** | Activité de fond des agents |
| 🌟 **Lignes de constellation** | Connexions permanentes |
| 🆕 **Planètes en matérialisation** | Nouveaux produits de la fabrique apparaissant en temps réel |

## Fonctionnalités

- **Runtime UNI** — chaîne locale et interrogation en direct des couches, sans métriques factices
- **Matérialisation des produits** — les produits de la fabrique deviennent de nouvelles planètes via webhook
- **Univers 3D à disposition par forces** — zoom, rotation, panoramique, vol vers un nœud
- **Post-traitement avec bloom** — halo lumineux, vignette et grain
- **WebSocket en temps réel** — données en direct toutes les 1,5 s
- **Assistant IA** — LLM multi-fournisseurs (par défaut **DeepSeek `deepseek-v4-pro`**, le même registre qu'aicom) avec l'**état vivant du moniteur** dans chaque requête : tick, mode, métriques des nœuds, activité
- **3 thèmes** — cyan, magenta et vert, avec un curseur d'intensité de pulsation
- **5 langues** — EN / RU / ES / FR / ZH ; l'IA répond dans la langue choisie

### Localisation

| Langue | Chaînes de l'interface | README |
|--------|------------------------|--------|
| English | `frontend/src/i18n/locales/en.json` | [README.md](README.md) |
| Русский | `frontend/src/i18n/locales/ru.json` | [README.ru.md](README.ru.md) |
| Español | `frontend/src/i18n/locales/es.json` | [README.es.md](README.es.md) |
| Français | `frontend/src/i18n/locales/fr.json` | [README.fr.md](README.fr.md) |
| 中文 | `frontend/src/i18n/locales/zh.json` | [README.zh.md](README.zh.md) |

Le choix est conservé dans `localStorage` (`alien-monitor-locale`). Les requêtes à l'IA
transmettent `locale` à `POST /api/ai/ask`. Les cinq fichiers portent les mêmes 344 clés :
la parité, l'absence de chaînes vides et le respect du glossaire sont tenus par des tests
(`frontend/src/__tests__/glossary.test.ts`), de sorte qu'aucune langue ne peut prendre du
retard en silence.

### Fournisseurs d'IA

Lit `data/config/model_providers.yaml` du dépôt parent **aicom** (ou `ALIEN_LLM_CONFIG`).
Par défaut : `deepseek_api` / `deepseek-v4-pro`.

| Point d'accès | Rôle |
|---------------|------|
| `GET /api/ai/providers` | Liste des fournisseurs et modèles activés |
| `POST /api/ai/ask` | `{ question, locale, provider?, model_role?, state?, selected_node_id? }` |

Le frontend envoie l'état WebSocket courant avec chaque question, si bien que le modèle
voit les mêmes données du cosmos 3D que vous.

**Ce que sait l'assistant.** Outre l'instantané en direct, il reçoit la
[base de connaissances centrale de l'écosystème](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/knowledge-base.md) et le
registre des satellites de `scripts/satellite-map.yaml`. Un composant documenté est connu
automatiquement : nul besoin de le décrire séparément dans le prompt. Si un nœud est absent
de l'instantané courant, l'assistant doit dire « je ne le vois pas dans cet instantané »,
jamais « ce composant n'existe pas ».

## Démarrage rapide (local)

```bash
git clone https://github.com/alexar76/alien-monitor.git
cd alien-monitor

# Mode univers virtuel (blockchain embarquée + entités)
./start.sh --universe

# Ou mode test avec des données simulées
./start.sh

# Ouvrir : http://localhost:5173
```

## API du mode univers

```bash
# Démarrer l'univers virtuel
curl -X POST http://localhost:9100/api/universe/start

# Matérialiser un produit (à appeler depuis votre pipeline de fabrique)
curl -X POST http://localhost:9100/api/universe/materialize \
  -H 'Content-Type: application/json' \
  -d '{"name": "MyAgent", "type": "ai-agent", "category": "fullstack-app"}'

# Obtenir l'état de l'univers
curl http://localhost:9100/api/universe/state

# Arrêter l'univers
curl -X POST http://localhost:9100/api/universe/stop
```

## Commandes

| Action | Comment |
|--------|---------|
| Faire tourner la vue | Clic et glisser |
| Zoom | Molette de la souris |
| Panoramique | Clic droit et glisser |
| Ouvrir un nœud | Clic sur le nœud |
| Changer de thème | Boutons CY / MG / GR de la barre |
| Changer de langue | Sélecteur de langue de la barre |
| Interroger l'IA | Bouton **AI** → écrivez dans votre langue |

## Déploiement en production

Depuis la racine du dépôt **aicom** sur le serveur :

```bash
./scripts/deploy_alien_monitor.sh
# ou : cd alien-monitor && docker compose -f docker-compose.prod.yml up -d --build
```

Par défaut **`ALIEN_MODE=universe`** : Anvil, FakeUSDT, le séquestre et le NFT sont
déployés **dans le conteneur** au démarrage. Le tableau complet des variables
d'environnement se trouve dans le
[README en anglais](README.md#production-deploy-magic-ai-factorycom), avec le guide de
dépannage d'UNI.

URL publique (derrière nginx) : **https://magic-ai-factory.com/monitor/**

## Licence

MIT — partie de l'[économie d'agents ouverte AICOM](https://github.com/alexar76/aicom).
