# Plan : application résidente Windows + installeur

## Objectif

Étendre `pythonbeid-server` avec deux artefacts :

1. **Application résidente Windows** : icône dans la zone de notification (system tray),
   serveur API en arrière-plan, menu contextuel (statut, accès rapide, quitter).
2. **Installeur Windows classique** : exécutable autonome (PyInstaller) empaqueté dans
   un installeur Inno Setup (raccourcis, option de démarrage automatique, désinstallation).

## Phase 1 : application tray (`eid_agent/tray.py`) - TERMINÉ

- [x] `ServerController` : uvicorn lancé dans un thread démon, arrêt propre via `should_exit`.
- [x] Vérification préalable que le port est libre (instance unique de fait) ; boîte de
      dialogue d'erreur et sortie si le port est occupé.
- [x] Icône pystray générée avec Pillow (carte eID stylisée), menu :
      - Titre (version + adresse d'écoute, désactivé)
      - "Vérifier lecteur / carte" -> notification avec l'état (backend direct)
      - "Ouvrir le health check" -> navigateur sur `/v1/health`
      - "Ouvrir le dossier de configuration" -> `%LOCALAPPDATA%\eid-agent`
      - "Quitter" -> arrêt serveur + icône
- [x] Logs fichier rotatif dans `%LOCALAPPDATA%\eid-agent\logs\` (l'exe n'a pas de console).
- [x] Chargement d'un `.env` optionnel depuis `%LOCALAPPDATA%\eid-agent\.env`.
- [x] Entry point GUI `eid-agent-tray` + extras `[tray]` et `[build]` dans `pyproject.toml`.
- [x] Test `tests/test_tray.py` : démarrage/santé/arrêt du `ServerController` sur port éphémère.

## Phase 2 : packaging (`packaging/`) - TERMINÉ

- [x] `packaging/make_icon.py` : génère `packaging/eid-agent.ico` (gitignoré, regénéré au build).
- [x] `packaging/tray_launcher.py` + `packaging/eid_agent_tray.spec` : PyInstaller onedir,
      sans console, collect uvicorn / pythonbeid / smartcard, numpy exclu (47,6 MB au lieu de 75).
- [x] `packaging/eid-agent.iss` : Inno Setup, FR/EN, raccourci menu Démarrer, tâche optionnelle
      "Démarrer avec Windows" (clé Run HKCU), taskkill avant désinstallation.
- [x] `packaging/build.ps1` : pip install extras, icône, PyInstaller, ISCC (`-SkipInstaller` possible).
- [x] Build validé sur cette machine : exe + health check OK,
      installeur `packaging/output/eid-agent-setup-1.1.0.exe` (21,4 MB) compilé.

## Phase 3 : finitions - TERMINÉ

- [x] Bump version `1.1.0` (`pyproject.toml` + `eid_agent/__init__.py`),
      test de version corrigé pour suivre `__version__`.
- [x] README : sections "Application résidente Windows" et "Construire l'exécutable et l'installeur".
- [x] `pytest -q` : 11 tests verts.

## Décisions

- Tray : **pystray + Pillow** (standard, léger, pas de dépendance Qt).
- Build : **PyInstaller onedir** (démarrage plus rapide qu'onefile, antivirus plus tolérant).
- Installeur : **Inno Setup 6** (classique, gratuit, langue FR incluse),
  installé sur cette machine dans `%LOCALAPPDATA%\Programs\Inno Setup 6`.
- UI du tray en français (utilisateurs finaux belges), code et commentaires en anglais.

## Phase 4 : correction détection lecteur/carte - TERMINÉ

Constat : `/v1/status` répondait toujours "pas de lecteur / pas de carte" car
`eid_agent/reader.py` sondait des API (`list_readers`, `has_card`...) inexistantes
dans `pythonbeid`.

- [x] `pythonbeid` 0.3.0 (repo séparé, branche `feat/list-readers`) :
      fonction module `list_readers()` exposée dans `__init__`, 3 tests ajoutés (49 verts).
- [x] `eid_agent/reader.py` : fallback pyscard (`smartcard.System.readers`) dans
      `_list_readers` pour pythonbeid < 0.3.0 ; `_detect_card_presence` retourne `True`
      par défaut (une connexion réussie implique une carte, `CardReader` levant
      `NoCardError` sinon) ; `status()` ne lève plus 500 sur carte muette
      (`0x80100066`) mais dégrade en `has_card: false`.
- [x] `tests/test_reader_backend.py` : 7 tests unitaires (18 verts au total).
- [x] Exe + installeur reconstruits, `/v1/status` vérifié sur matériel réel :
      `{"has_reader": true, "readers": ["ACS ACR38U 0"]}`.

## Reste à faire (hors périmètre de cette phase)

- [ ] Commit sur la branche `feat/tray-installer` puis merge vers `main`.
- [ ] Éventuel job CI GitHub Actions (windows-latest) pour produire l'installeur en release.
- [ ] Signature de code de l'exe/installeur si distribution large (SmartScreen).
