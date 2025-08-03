# Shift Manager - Employee Scheduling System

Ein modernes Mitarbeiterplanungssystem mit Django-Backend und Vue.js-Frontend, das fortschrittliche Planungsalgorithmen, umfassende Analysen und eine responsive Benutzeroberfläche bietet.

## 🚀 Features
- **Multi-Unternehmen Support** - Verwaltung mehrerer Unternehmen mit verschiedenen Größen
- **Fortschrittliche Planungsalgorithmen** - Lineare Programmierung, Genetischer Algorithmus, Simulated Annealing
- **Umfassende Analysen** - KPI-Berechnungen, Abdeckungsraten, Stundenverteilung, Constraint-Verletzungen
- **Mitarbeiter- und Schichtverwaltung** - Flexible Konfiguration von Arbeitszeiten und Abwesenheiten
- **Echtzeit-Algorithmusvergleich** - Performance-Metriken und Benchmarking
- **Mehrere Ansichten** - Dashboard, Monatsansicht, Tagesansicht, Mitarbeiteransicht
- **Mobile-responsive Design** - Optimiert für alle Geräte
- **Docker-Containerisierung** - Einfache Bereitstellung und Skalierung
- **Deutsche Lokalisierung** - Vollständig auf Deutsch verfügbar

## 📝 Voraussetzungen
- Python 3.8+
- Node.js 16+
- npm oder yarn
- Docker 20.10+ (für containerisierte Einrichtung)
- MySQL 8.0 (wird automatisch mit Docker bereitgestellt)

## ⚡ Schnellstart

### Docker (Empfohlen)
```bash
# Repository klonen
git clone <repository-url>
cd shift-manager

# Entwicklungsumgebung starten
./scripts/start.sh          # Linux/macOS
scripts\start.bat           # Windows

# Oder Docker Compose direkt verwenden
docker-compose up -d --build
```

### Lokale Entwicklung
#### Backend
```bash
pip install -r requirements.txt
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py loaddata rostering_app/fixtures/companies.json
python manage.py runserver
```

#### Frontend
```bash
npm install
npm run dev
```

## 🏗️ Projektstruktur
```
shift-manager/
├── src/                    # Vue.js 3 Frontend
│   ├── components/         # UI-Komponenten
│   ├── views/             # Seiten (Dashboard, Analytics, etc.)
│   ├── stores/            # Pinia State Management
│   ├── services/          # API-Services
│   ├── router/            # Vue Router Konfiguration
│   └── assets/            # Statische Assets
├── rostering_app/         # Django App
│   ├── models.py          # Datenmodelle (Company, Employee, Shift, ScheduleEntry)
│   ├── views.py           # API-Endpunkte
│   ├── services/          # KPI-Berechnungen und Analytics
│   ├── fixtures/          # Beispieldaten für verschiedene Unternehmensgrößen
│   └── management/        # Django Management Commands
├── scheduling_core/       # Planungsalgorithmen
│   ├── linear_programming.py
│   ├── genetic_algorithm.py
│   └── simulated_annealing_compact.py
├── rostering_project/     # Django Projekt-Konfiguration
├── Dockerfile*            # Docker-Konfigurationen
├── docker-compose*.yml    # Docker Compose
└── requirements.txt       # Python-Abhängigkeiten
```

## 🎯 Verwendung
- **Frontend**: http://localhost:3000 (Entwicklung) / http://localhost (Docker)
- **Backend API**: http://localhost:8000
- **Django Admin**: http://localhost:8000/admin

### Hauptworkflow:
1. **Unternehmen auswählen** - Wählen Sie aus 4 vorkonfigurierten Unternehmen (klein, mittel, groß, größer)
2. **Dashboard erkunden** - Übersicht über Mitarbeiter, Schichten und Abdeckung
3. **Analysen anzeigen** - Detaillierte KPI-Berechnungen und Statistiken
4. **Algorithmusvergleich** - Performance-Vergleich verschiedener Planungsalgorithmen
5. **Monats-/Tagesansicht** - Detaillierte Zeitplanübersichten
6. **Mitarbeiteransicht** - Individuelle Mitarbeiterstatistiken und Zeitpläne

## 🔑 Wichtige API-Endpunkte
- `GET /api/companies/` - Unternehmen auflisten
- `GET /api/companies/{id}/` - Unternehmensdetails
- `GET /api/companies/{id}/algorithms/` - Verfügbare Algorithmen
- `GET /api/companies/{id}/schedule/` - Zeitplandaten
- `GET /api/companies/{id}/employees/` - Mitarbeiter
- `GET /api/companies/{id}/shifts/` - Schichten
- `GET /api/companies/{id}/analytics/` - Algorithmus-KPIs
- `GET /api/companies/{id}/day/{date}/` - Tagesplan
- `GET /api/companies/{id}/employee/{employeeId}/` - Mitarbeiterdetails

## 📊 Analytics & KPIs
Das System berechnet umfassende Kennzahlen:
- **Abdeckungsraten** - Durchschnittliche und tägliche Schichtabdeckung
- **Stundenverteilung** - Durchschnitt, Standardabweichung, Min/Max Stunden pro Mitarbeiter
- **Constraint-Verletzungen** - Wochenstunden- und Ruhezeitverletzungen
- **Gini-Koeffizient** - Messung der Stundenverteilungsgleichheit
- **Algorithmus-Performance** - Laufzeiten und Qualitätsmetriken

## 🛠️ Fehlerbehebung & Bereitstellung

### Entwicklung
```bash
# Ports ändern (falls belegt)
# docker-compose.yml oder vite.config.js anpassen

# Cache leeren und neu bauen
docker-compose build --no-cache
docker-compose up -d
```

### Produktion
```bash
# Mit SSL-Zertifikaten
./scripts/start.sh prod

# Manuelle Einrichtung
docker-compose -f docker-compose.prod.yml up -d
```

### Docker-Befehle
```bash
# Logs anzeigen
docker-compose logs -f

# Backend-Shell zugreifen
docker-compose exec backend python manage.py shell

# Django-Befehle ausführen
docker-compose exec backend python manage.py migrate
docker-compose exec backend python manage.py createsuperuser

# Services skalieren
docker-compose -f docker-compose.prod.yml up -d --scale backend=3
```

## 🐳 Docker-Bereitstellung

### Entwicklung
```bash
docker-compose up -d
```

### Produktion
```bash
# Mit SSL-Zertifikaten
./scripts/start.sh prod

# Manuelle Einrichtung
docker-compose -f docker-compose.prod.yml up -d
```

### Umgebungsvariablen
Erstellen Sie eine `.env.local` Datei für lokale Konfiguration:
```env
DEBUG=True
SECRET_KEY=your-secret-key
ALLOWED_HOSTS=localhost,127.0.0.1
MYSQL_DATABASE=shift_manager
MYSQL_USER=shift_manager
MYSQL_PASSWORD=shift_manager_password
```

## 📈 Beispieldaten
Das System enthält vorkonfigurierte Beispieldaten für verschiedene Unternehmensgrößen:
- **Kleines Unternehmen**: 10 Mitarbeiter, 2 Schichten
- **Mittleres Unternehmen**: 30 Mitarbeiter, 3 Schichten  
- **Großes Unternehmen**: 100 Mitarbeiter, 4 Schichten
- **Größeres Unternehmen**: 60 Mitarbeiter, 4 Schichten

## 🔧 Technologie-Stack
- **Frontend**: Vue.js 3, Pinia, Vue Router, Chart.js, Bootstrap Icons
- **Backend**: Django 4, Django REST Framework, MySQL
- **Algorithmen**: PuLP (Linear Programming), DEAP (Genetic Algorithm), SciPy
- **Deployment**: Docker, Nginx, Gunicorn
- **Analytics**: Pandas, NumPy, Matplotlib

## 📝 Lizenz
Dieses Projekt ist für Bildungs- und Demonstrationszwecke entwickelt.