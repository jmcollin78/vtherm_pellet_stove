## Développement avec Visual Studio Code + devcontainer

La façon la plus simple de démarrer est d'utiliser Visual Studio Code avec les devcontainers. Cette approche crée un environnement de développement préconfiguré avec tous les outils nécessaires.

Le container inclut une instance Home Assistant autonome avec votre composant custom. Vous pouvez la configurer en éditant `.devcontainer/configuration.yaml`.

### Prérequis

- [git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git)
- Docker
- [Visual Studio Code](https://code.visualstudio.com/)
- Extension [Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)

### Démarrage

1. Cloner le dépôt.
2. Ouvrir le dossier dans VS Code.
3. Choisir **Reopen in Container** quand VS Code le propose, ou ouvrir la palette de commandes et sélectionner `Dev Containers: Reopen in Container`.

### Lancer Home Assistant

Dans un terminal du container :

```bash
hass -c .devcontainer/ --debug
```

Home Assistant sera accessible sur `http://localhost:8123`.

### Lancer les tests

```bash
pytest tests/
```

Avec coverage :

```bash
pytest tests/ --cov=custom_components/vtherm_pellet_stove --cov-report=term-missing
```

### Débogage pas à pas

1. Lancer Home Assistant (voir ci-dessus).
2. Dans VS Code, lancer la configuration de débogage **Python: Attach Local** (`.vscode/launch.json` fourni).
3. Poser des breakpoints dans le code.

Pour plus d'informations : [Remote Python Debugger](https://www.home-assistant.io/integrations/debugpy/).
