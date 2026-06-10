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

Package PyPI: `pythonbeid-server`  
Module Python importable: `eid_agent`  
Commande CLI installée: `eid-agent`

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

## Application résidente Windows (zone de notification)

L'agent peut tourner en tâche de fond avec une icône dans la zone de notification.

Installation des dépendances et lancement depuis les sources:

```bash
pip install -e ".[tray]"
eid-agent-tray
```

Menu de l'icône:

- Vérifier lecteur / carte (notification avec l'état)
- Ouvrir le health check dans le navigateur
- Ouvrir le dossier de configuration
- Quitter

Particularités:

- Une seule instance: si le port est déjà occupé, un message d'erreur s'affiche et
  l'application se ferme.
- Logs fichier rotatifs: `%LOCALAPPDATA%\eid-agent\logs\eid-agent.log`
- Configuration persistante: créer un fichier `.env` dans `%LOCALAPPDATA%\eid-agent\`
  (mêmes variables `EID_AGENT_*` que ci-dessus), par exemple:

```text
EID_AGENT_ALLOWED_ORIGINS=https://school.example
EID_AGENT_PORT=8765
```

## Construire l'exécutable et l'installeur Windows

Prérequis: [Inno Setup 6](https://jrsoftware.org/isinfo.php)
(`winget install JRSoftware.InnoSetup`).

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

Le script:

1. installe les dépendances de build (`.[tray,build]`, PyInstaller),
2. génère l'icône (`packaging\make_icon.py`),
3. construit l'exécutable sans console `dist\eid-agent-tray\eid-agent-tray.exe`,
4. compile l'installeur `packaging\output\eid-agent-setup-<version>.exe`.

Pour construire uniquement l'exécutable: `packaging\build.ps1 -SkipInstaller`.

L'installeur (français/anglais) installe l'application, crée un raccourci dans le menu
Démarrer et propose une option "Lancer eID Agent à l'ouverture de session Windows"
(clé `Run` HKCU, retirée à la désinstallation).

## Tests

```bash
pytest -q
```

Les tests API n’utilisent pas de matériel eID et injectent un backend simulé.

## Publication PyPI (GitHub Actions)

Le workflow CI/CD est fourni ici:

- `.github/workflows/publish-pypi.yml`

Il publie automatiquement sur PyPI avec Trusted Publishing (OIDC) quand un tag `v*` est poussé.

### Configuration initiale (une seule fois)

1. Sur PyPI, créer un Trusted Publisher pour ce projet avec:
   - Owner GitHub
   - Repo GitHub
   - Workflow: `publish-pypi.yml`
   - Environment: `pypi`
2. Sur GitHub, créer l'environnement `pypi` (Settings > Environments).

### Release

1. Mettre à jour la version dans `pyproject.toml` (ex: `1.0.1`).
2. Commit/push.
3. Créer et pousser le tag correspondant:

```bash
git tag v1.0.1
git push origin v1.0.1
```

Le workflow vérifie que le tag correspond à la version (`v<version>`), build le package, puis publie sur PyPI.

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
