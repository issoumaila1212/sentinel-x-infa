# AetherCorp Industrial Solutions

## Présentation du projet

AetherCorp développe un système autonome de surveillance destiné à détecter des situations inhabituelles dans une zone isolée. Le prototype combine plusieurs sources d'informations : capteurs environnementaux, caméra, analyse IA et interface web.

La chaîne globale est :

Mesurer -> Transmettre -> Stocker -> Analyser -> Détecter -> Alerter

Les trois axes du projet sont :
- IoT : collecte et transmission des données
- IA : détection d'anomalies
- Infrastructure : serveur, base de données et dashboard

---

## Architecture générale

```text
Zone surveillée
  ├── DHT22 : température / humidité
  ├── MQ-2  : gaz / fumée
  └── PIR   : présence
       │
       ▼
   [ ESP8266 ]
       │ Wi-Fi
       ▼
  [ MQTT Broker ]
       │
       ▼
  [ Serveur Python ]
      ├──> SQLite
      ├──> Dashboard (Flask)
      ├──> IA / détection d'anomalies
      └──> Caméra / vision
             │
             ▼
          [ Alertes ]
```

---

## Structure du projet

```text
AETHER/
├── server/
│   ├── main.py
│   ├── mqtt_client.py
│   └── database.py
├── ia/
│   ├── anomaly.py
│   └── model.py
├── camera/
│   └── detection.py
├── dashboard/
│   ├── app.py
│   ├── templates/
│   └── static/
├── data/
├── sensors.db
├── README.md
└── requirements.txt   (à ajouter si nécessaire)
```

---

## Composants principaux

### 1. ESP8266 / Edge Node
Le boîtier de terrain récupère les données des capteurs et les envoie au serveur.

Capteurs :
- DHT22 : température / humidité
- MQ-2 : gaz / fumée
- PIR : présence humaine

Exemple de message envoyé :

```json
{
  "device": "node01",
  "temperature": 26.4,
  "humidity": 52,
  "gas": 180,
  "presence": false
}
```

### 2. MQTT
Le système utilise MQTT pour la transmission des données entre l'ESP8266 et le serveur.

```text
ESP8266 -> MQTT Broker -> Serveur Python
```

Topic exemple :

```text
aether/node01/sensors
```

### 3. Serveur Python
Le serveur central reçoit les données, les valide, les stocke et lance les analyses.

Responsabilités :
- réception MQTT
- stockage SQLite
- gestion des alertes
- mise à jour du dashboard
- appel à la logique IA

### 4. Base de données
Utilisation de SQLite pour garder les historiques et les données de tests.

Exemple :

```text
| Heure | Température | Humidité | Gaz | Présence |
|------|-------------|----------|-----|----------|
| 10:00 | 24.2°C | 51% | 120 | 0 |
| 10:01 | 24.3°C | 51% | 121 | 0 |
| 10:02 | 24.4°C | 50% | 120 | 0 |
| 10:03 | 25.1°C | 50% | 125 | 1 |
```

### 5. Dashboard / App web
La partie application est gérée dans le dossier dashboard.

Fichier principal :
- dashboard/app.py

Le dashboard permet de :
- afficher l'état général du système,
- montrer les capteurs en temps réel,
- afficher les données historiques,
- afficher le score d'anomalie,
- afficher les alertes,
- gérer une interface utilisateur simple et claire.

---

## Partie application : routes

La partie application Flask doit exposer plusieurs routes pour l'interface et l'API.

Routes principales :

```text
GET /                 -> page d'accueil du dashboard
GET /dashboard        -> page principale du tableau de bord
GET /api/status       -> renvoie l'état global du système
GET /api/sensors      -> renvoie les dernières données capteurs
GET /api/alerts       -> renvoie la liste des alertes
POST /api/alert/ack  -> valide / confirme une alerte
```

Exemples de logique attendue :
- / renvoie le template principal
- /dashboard affiche l'état du système en page HTML
- /api/sensors retourne les valeurs JSON du dernier relevé
- /api/alerts retourne l'historique des alertes
- /api/alert/ack confirme une alerte après lecture

---

## Partie app : rôle de dashboard/app.py

Le fichier dashboard/app.py est le point d'entrée de l'application web.

Il doit probablement gérer :
- création de l'application Flask,
- configuration du template folder,
- déclaration des routes,
- récupération de données depuis SQLite ou MQTT,
- rendu des templates HTML,
- sérialisation des données JSON pour l'API.

Exemple de structure logique :

```python
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    return render_template('index.html')

@app.route('/api/sensors')
def get_sensors():
    return jsonify({"temperature": 26.4, "humidity": 52, "gas": 180, "presence": False})

@app.route('/api/alerts')
def get_alerts():
    return jsonify([])

@app.route('/api/alert/ack', methods=['POST'])
def ack_alert():
    return jsonify({"status": "ok"})
```

---

## Caméra / vision

La webcam permet de compléter les capteurs et de confirmer une présence humaine.

```text
Caméra -> Traitement image -> Personne détectée ?
                        ├── Oui -> présence confirmée
                        └── Non -> situation normale
```

Technologies possibles :
- Python
- OpenCV
- détection de personnes

---

## IA et anomalies

Le projet ne doit pas se limiter à des seuils fixes. L'objectif est d'observer l'évolution des données pour détecter une anomalie probable.

Exemple :

```text
24°C -> 24.2°C -> 24.5°C -> 24.6°C
=> comportement stable -> NORMAL

24°C -> 26°C -> 29°C -> 34°C -> 40°C
=> augmentation rapide -> ANOMALIE POSSIBLE
```

Première version possible :
- Isolation Forest (Scikit-learn)

---

## Score global et alertes

Le système peut calculer un score global basé sur les capteurs, la caméra et l'IA.

```text
0%                              100%
|-------------------------------|
NORMAL                     RISQUE
```

Niveaux :
- 0 - 40 % : Normal
- 40 - 70 % : Surveillance
- 70 - 100 % : Alerte

Exemple d'alerte :

```text
+------------------------------+
|          🚨 ALERTE           |
| Anomalie détectée            |
| Température : 38°C          |
| Gaz : ÉLEVÉ                 |
| Score : 87%                 |
+------------------------------+
```

---

## Ordre de développement conseillé

1. ESP8266
2. Capteurs
3. Wi-Fi
4. MQTT
5. Serveur Python
6. Base de données
7. Dashboard / app web
8. Webcam
9. Détection de personnes
10. IA
11. Fusion des données
12. Score de risque
13. Alertes
14. Tests

---

## Conclusion

Le projet vise à créer une chaîne intelligente :

Mesurer -> Transmettre -> Stocker -> Analyser -> Détecter -> Alerter

Cette logique est au cœur du système et explique le rôle de chaque module, en particulier la partie dashboard et les routes de l'application.