# Application de Gestion du Syndic d'Immeuble

Application web Django pour la gestion des copropriétés au Maroc, conforme à la loi 18-00.

## Fonctionnalités

### ✅ Implémentées
- **Gestion des utilisateurs** : Admin et résidents avec rôles
- **Gestion financière** : Cotisations, dépenses, paiements
- **Rapports** : Balance globale et balance âgée (30/60/90+ jours)
- **Documents PDF** : Convocation AG, mise en demeure, reçus
- **Export CSV** : Export des cotisations
- **Import bancaire** : Rapprochement automatique des paiements
- **Notifications** : Email automatique lors des paiements

### 🔄 À développer
- Paiement en ligne (CMI Maroc)
- Module gestion des plaintes
- Support multilingue
- SMS notifications

## Installation

1. **Cloner le projet**
```bash
git clone <repository>
cd syndic
```

2. **Créer l'environnement virtuel**
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate
```

3. **Installer les dépendances**
```bash
pip install -r requirements.txt
```

4. **Configuration de la base de données**
Créer un fichier `.env` basé sur `.env.example` :
```env
DJANGO_SECRET_KEY=your-secret-key
DB_ENGINE=django.db.backends.mysql
DB_NAME=syndic_db
DB_USER=your_user
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=3306
```

5. **Migrations**
```bash
python manage.py migrate
```

6. **Créer un superutilisateur**
```bash
python manage.py createsuperuser
```

7. **Lancer le serveur**
```bash
python manage.py runserver
```

## Utilisation

### Accès
- **Interface web** : http://localhost:8000
- **Admin Django** : http://localhost:8000/admin
- **Compte par défaut** : admin/admin

### Navigation
- **Cotisations** : Gérer les cotisations mensuelles/trimestrielles
- **Dépenses** : Enregistrer les dépenses (eau, électricité, etc.)
- **Paiements** : Enregistrer les paiements des résidents
- **Rapports** : Consulter les balances et retards
- **Documents** : Générer convocations, mises en demeure, reçus
- **Import bancaire** : Rapprocher avec les relevés bancaires

## Structure du projet

```
syndic/
├── accounts/          # Gestion des utilisateurs
├── finance/           # Gestion financière
├── templates/         # Templates HTML
├── static/            # Fichiers statiques
├── syndic/            # Configuration Django
└── manage.py          # Script de gestion Django
```

## Technologies

- **Backend** : Django 5.2
- **Base de données** : MySQL (SQLite en développement)
- **Frontend** : Bootstrap 5
- **PDF** : ReportLab
- **Email** : SMTP Django

## Conformité légale

L'application respecte la loi marocaine 18-00 sur la copropriété et garantit :
- Transparence des comptes
- Traçabilité des paiements
- Génération automatique des documents légaux
- Sécurité des données personnelles

## Support

Pour toute question ou problème, contacter l'équipe de développement.
