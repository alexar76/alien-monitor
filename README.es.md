# 👽 Alien Monitor — visualizador del pulso del ecosistema AIMarket

> 🌍 **Idiomas:** [English](README.md) · [Русский](README.ru.md) · **Español** · [Français](README.fr.md) · [中文](README.zh.md)
>
> La terminología sigue el [glosario de localización](https://github.com/alexar76/aicom/blob/main/docs/localization-glossary.md).
> La referencia completa de variables de entorno y despliegue está en el [README en inglés](README.md).

> **Ecosistema:** [resumen de AICOM y demos en vivo](https://modeldev.modelmarket.dev) · **Comunidad:** [Telegram · Castor](https://t.me/just_for_agents) · [Discord · Pollux](https://discord.gg/aimarket)

**Mapas:** **UNI** [https://monitor-uni.modelmarket.dev/](https://monitor-uni.modelmarket.dev/) (`ALIEN_MODE=universe`) · **LIVE** [https://monitor.modelmarket.dev/](https://monitor.modelmarket.dev/) (`ALIEN_MODE=real`). División: [uni-and-live.es.md](https://github.com/alexar76/aicom/blob/main/docs/uni-and-live.es.md).

**Pulse Terminal (ACEX)** corre en el mismo host: **[https://magic-ai-factory.com/pulse/](https://magic-ai-factory.com/pulse/)**.

Observa cada componente —el hub, los contratos, los agentes, las aplicaciones de escritorio, los plugins, las cadenas— como un cosmos vivo que respira. Haz clic en cualquier nodo para acercarte, inspeccionar sus métricas y ver los datos fluyendo por la red en vivo.

<p align="center">
  <a href="https://monitor.modelmarket.dev/">
    <img src="docs/recordings/alien-monitor-hero.gif" alt="Alien Monitor en movimiento — el grafo del ecosistema en vivo con métricas de nodos y el asistente IA integrado" width="820">
  </a>
  <br>
  <sub>Grafo del ecosistema en vivo · inspector de nodos · asistente IA integrado — <a href="https://monitor.modelmarket.dev/"><b>abrir la demo →</b></a></sub>
</p>

---

## Tres modos

### 🟢 Modo UNI
Cadena local + **sondeos en vivo** de Hub, Mesh, Factory y Prometheus desplegados: la misma interfaz que LIVE, sin métricas simuladas.

- EVM embebida (Anvil) y, opcionalmente, un validador de Solana
- Despliegue automático del depósito en garantía (escrow) y del NFT en la cadena local
- Webhook de la fábrica: `POST /api/universe/materialize`

### 🟡 Modo TEST
Un ecosistema simulado y vibrante con agentes, canales de pago y transacciones ficticios. Aquí las métricas son sintéticas, y tanto la interfaz como el asistente IA lo dicen de forma explícita.

### 🟢 Modo LIVE
Se conecta a la infraestructura real (Hub, Mesh, Prometheus) **y al RPC on-chain**:

- EVM: `BASE_RPC_URL` / `ETHEREUM_RPC_URL` y demás, según `AIMARKET_PAYMENT_CHAIN`
- Contratos: `AIMARKET_ESCROW_EVM_ADDRESS`, `AIMARKET_NFT_CONTRACT`, `AIMARKET_ESCROW_SOLANA_PROGRAM_ID`
- Carga el `aicom/.env` del repositorio padre cuando está presente
- Depuración: `GET /api/chain/status`

---

## Qué se ve

Un **universo observable propio** donde cada cuerpo celeste es un componente vivo:

| Elemento visual | Qué representa |
|-----------------|----------------|
| ☀️ **Hub solar** con corona y anillos de gravedad | AIMarket Hub — el centro |
| 🪐 **Planetas en órbita** con física de oscilación | Servicios centrales: Factory, Mesh, ACEX |
| 💎 **Nodos cristalinos** con anillos orbitales | Contratos inteligentes (EVM y Solana) |
| 🌌 **Nebulosas** | Grupos de componentes relacionados |
| 🕳️ **Túneles de agujero de gusano** | Flujos de datos activos entre servicios |
| 💫 **Cinturones de asteroides** | Actividad de la red blockchain |
| ✨ **Polvo cósmico** | Actividad de fondo de los agentes |
| 🌟 **Líneas de constelación** | Conexiones permanentes |
| 🆕 **Planetas materializándose** | Productos nuevos de la fábrica apareciendo en tiempo real |

## Características

- **Runtime UNI** — cadena local más sondeo en vivo de las capas, sin métricas ficticias
- **Materialización de productos** — los productos de la fábrica se vuelven planetas nuevos vía webhook
- **Universo 3D con disposición por fuerzas** — zoom, rotación, paneo, vuelo hacia un nodo
- **Posprocesado con bloom** — resplandor, viñeta y ruido
- **WebSocket en tiempo real** — datos en vivo cada 1,5 s
- **Asistente IA** — LLM multiproveedor (por defecto **DeepSeek `deepseek-v4-pro`**, el mismo registro que aicom) con el **estado vivo del monitor** en cada consulta: tick, modo, métricas de nodos, actividad
- **3 temas** — cian, magenta y verde, con control de intensidad del pulso
- **5 idiomas** — EN / RU / ES / FR / ZH; la IA responde en el idioma elegido

### Localización

| Idioma | Cadenas de la interfaz | README |
|--------|------------------------|--------|
| English | `frontend/src/i18n/locales/en.json` | [README.md](README.md) |
| Русский | `frontend/src/i18n/locales/ru.json` | [README.ru.md](README.ru.md) |
| Español | `frontend/src/i18n/locales/es.json` | [README.es.md](README.es.md) |
| Français | `frontend/src/i18n/locales/fr.json` | [README.fr.md](README.fr.md) |
| 中文 | `frontend/src/i18n/locales/zh.json` | [README.zh.md](README.zh.md) |

La elección se guarda en `localStorage` (`alien-monitor-locale`). Las consultas a la IA
envían `locale` a `POST /api/ai/ask`. Los cinco archivos tienen las mismas 344 claves:
la paridad, la ausencia de cadenas vacías y el cumplimiento del glosario están cubiertos
por pruebas (`frontend/src/__tests__/glossary.test.ts`), así que ningún idioma puede
quedarse atrás en silencio.

### Proveedores de IA

Lee `data/config/model_providers.yaml` del repositorio padre **aicom** (o
`ALIEN_LLM_CONFIG`). Por defecto: `deepseek_api` / `deepseek-v4-pro`.

| Endpoint | Propósito |
|----------|-----------|
| `GET /api/ai/providers` | Lista de proveedores y modelos habilitados |
| `POST /api/ai/ask` | `{ question, locale, provider?, model_role?, state?, selected_node_id? }` |

El frontend envía el `state` actual del WebSocket con cada pregunta, de modo que el
modelo ve los mismos datos del cosmos 3D que ves tú.

**Qué sabe el asistente.** Además del snapshot en vivo recibe la
[base de conocimiento central del ecosistema](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/knowledge-base.md) y el
registro de satélites de `scripts/satellite-map.yaml`. Un componente documentado es
conocido automáticamente: no hace falta describirlo aparte en el prompt. Si un nodo no
está en el snapshot actual, el asistente debe decir «no lo veo en este snapshot», nunca
«ese componente no existe».

## Inicio rápido (local)

```bash
git clone https://github.com/alexar76/alien-monitor.git
cd alien-monitor

# Modo universo virtual (blockchain embebida + entidades)
./start.sh --universe

# O modo de prueba con datos simulados
./start.sh

# Abrir: http://localhost:5173
```

## API del modo universo

```bash
# Arrancar el universo virtual
curl -X POST http://localhost:9100/api/universe/start

# Materializar un producto (llámalo desde tu pipeline de fábrica)
curl -X POST http://localhost:9100/api/universe/materialize \
  -H 'Content-Type: application/json' \
  -d '{"name": "MyAgent", "type": "ai-agent", "category": "fullstack-app"}'

# Obtener el estado del universo
curl http://localhost:9100/api/universe/state

# Detener el universo
curl -X POST http://localhost:9100/api/universe/stop
```

## Controles

| Acción | Cómo |
|--------|------|
| Rotar la vista | Clic y arrastrar |
| Zoom | Rueda del ratón |
| Paneo | Clic derecho y arrastrar |
| Abrir un nodo | Clic en el nodo |
| Cambiar de tema | Botones CY / MG / GR de la barra |
| Cambiar de idioma | Selector de idioma de la barra |
| Preguntar a la IA | Botón **AI** → escribe en tu idioma |

## Despliegue en producción

Desde la raíz del repositorio **aicom** en el servidor:

```bash
./scripts/deploy_alien_monitor.sh
# o: cd alien-monitor && docker compose -f docker-compose.prod.yml up -d --build
```

Por defecto **`ALIEN_MODE=universe`**: Anvil, FakeUSDT, el escrow y el NFT se despliegan
**dentro del contenedor** al arrancar. La tabla completa de variables de entorno está en
el [README en inglés](README.md#production-deploy-magic-ai-factorycom), junto con la guía
de resolución de problemas de UNI.

URLs públicas (detrás de nginx): **UNI** https://monitor-uni.modelmarket.dev/ · **LIVE** https://monitor.modelmarket.dev/

## Licencia

MIT — parte de la [economía de agentes abierta AICOM](https://github.com/alexar76/aicom).
