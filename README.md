# eID Agent (localhost API)

Agent local Python pour lire une carte eID belge via `pythonbeid` et exposer une API HTTP sur `127.0.0.1` pour un front web distant (HTTPS).

## Fonctionnalités

- Bind local strict: `127.0.0.1` uniquement
- API FastAPI JSON UTF-8
- Session token en mémoire (TTL, Bearer token)
- CORS strict configurable par liste d’origines
- Rate limit simple sur `/v1/read`
- Mapping des données eID vers un contrat stable pour préremplissage formulaire

## Installation

```bash
pip install -e .
```

Avec dépendances de test:

```bash
pip install -e ".[dev]"
```

## Exécution

Mode recommandé:

```bash
eid-agent
```

Alternative:

```bash
python -m eid_agent
```

## Configuration (variables d’environnement)

- `EID_AGENT_PORT` (défaut: `8765`)
- `EID_AGENT_ALLOWED_ORIGINS` (ex: `https://school.example,https://dev.school.example`)
- `EID_AGENT_SESSION_TTL_SECONDS` (défaut: `120`)
- `EID_AGENT_RATE_LIMIT_PER_MINUTE` (défaut: `10`)
- `EID_AGENT_LOG_LEVEL` (défaut: `INFO`)

HTTPS local optionnel:

- `EID_AGENT_HTTPS=1`
- `EID_AGENT_TLS_CERT_PATH`
- `EID_AGENT_TLS_KEY_PATH`

Si HTTPS est activé sans cert/key valides, l’agent échoue au démarrage.

## API v1

Toutes les réponses JSON incluent:

- `ok` (bool)
- `timestamp` (ISO8601 UTC)
- `error` en cas d’échec

### Health

`GET /v1/health`

### Session

`POST /v1/session`

Retourne:

```json
{
  "ok": true,
  "timestamp": "2026-03-03T09:00:00Z",
  "token": "<opaque_token>",
  "expires_in": 120
}
```

### Status (auth requise)

`GET /v1/status`

Header:

`Authorization: Bearer <token>`

### Read eID (auth requise)

`POST /v1/read`

Body:

```json
{
  "include_photo": true,
  "fields": [
    "first_names",
    "first_name",
    "last_name",
    "national_number",
    "birth_date",
    "birth_place",
    "nationality",
    "sex",
    "card_number",
    "issuing_municipality",
    "validity_start",
    "validity_end",
    "address_street",
    "address_zip",
    "address_city"
  ]
}
```

Si `fields` est omis, l’agent renvoie l’ensemble par défaut (incluant les champs eID usuels + adresse).

### Logout (auth requise)

`POST /v1/logout`

## Exemple côté front web

```javascript
const sessionResp = await fetch("http://127.0.0.1:8765/v1/session", {
  method: "POST"
});
const sessionJson = await sessionResp.json();
const token = sessionJson.token;

const readResp = await fetch("http://127.0.0.1:8765/v1/read", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": `Bearer ${token}`
  },
  body: JSON.stringify({
    include_photo: true
  })
});
const readJson = await readResp.json();
console.log(readJson.data);
```

Important:

- Le domaine front doit être explicitement autorisé via `EID_AGENT_ALLOWED_ORIGINS`.
- Sans origine autorisée, aucun header `Access-Control-Allow-Origin` n’est envoyé.

## Exemple curl

Créer une session:

```bash
curl -X POST http://127.0.0.1:8765/v1/session
```

Lire la carte:

```bash
curl -X POST http://127.0.0.1:8765/v1/read ^
  -H "Authorization: Bearer <token>" ^
  -H "Content-Type: application/json" ^
  -d "{\"include_photo\":true}"
```

## Confidentialité et logs

- Aucun token n’est loggé.
- Aucune donnée personnelle eID (nom, adresse, NISS, photo) n’est loggée.
- Logs techniques: démarrage/arrêt, config réseau, erreurs techniques.

## Tests

```bash
pytest -q
```

Les tests API n’utilisent pas de matériel eID et injectent un backend simulé.

## Page web d'exemple

Un exemple de formulaire auto-rempli est disponible ici:

- `examples/web/index.html`

### Servir la page (PowerShell)

1. Démarrer l'agent avec une origine CORS qui correspond au serveur statique:

```powershell
$env:EID_AGENT_ALLOWED_ORIGINS="http://127.0.0.1:8080"
python -m eid_agent
```

2. Dans un second terminal, servir la page:

```powershell
python -m http.server 8080 --bind 127.0.0.1 --directory examples/web
```

3. Ouvrir:

- `http://127.0.0.1:8080`

Puis cliquer sur le bouton `Lire eID et remplir`.
