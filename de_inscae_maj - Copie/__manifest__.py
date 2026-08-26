{
    'name': 'Direction des Études - INSCAE', # Anaran'ilay projet/module
    'version': '12.0.1.0', # Version : (12.0.1.0) -> 12.0 = Version Odoo et la suite 1.0 = Version du module
    'summary': "Module pour gérer les étudiants au sein de l'INSCAE", # Description
    'author': 'Tsiory', # Auteur
    'depends': ['base', 'web'], # Les modules dont ce module a besoin -> base = coeur d'Odoo (Ny module Odoo rehetra mila ny base daholo)
    'data' : [ # C'est la liste de tous les fichiers XML (et csv) que le module doit charger. L'ordre a de l'importance.
        'security/ir.model.access.csv', # Fichier de sécurité pour les droits d'accès aux modèles
        'data/ir_sequence_data.xml', # Fichier de données pour les séquences
        #'data/factory_data.xml', # Fichier de données pour les modèles
        'views/individu_views.xml', # Fichier de vue pour le modèle Individu
        'views/parcours_academique_views.xml', # Fichier de vue pour le modèle Parcours Academique
        'views/formation_views.xml', # Fichier de vue pour le modèle Formation
        'views/niveau_views.xml', # Fichier de vue pour le modèle Niveau
        'views/option_views.xml', # Fichier de vue pour le modèle Option
        'views/session_niveau_views.xml', # Fichier de vue pour le modèle Session Niveau
        'views/session_parente_views.xml', # Fichier de vue pour le modèle Session Parente
        'views/prof_views.xml', # Fichier de vue pour le modèle Professeur
        'views/tranche_horaire_views.xml', # Fichier de vue pour le modèle Tranche Horaire
        'views/salle_views.xml', # Fichier de vue pour le modèle Salle
        'views/coefficient_views.xml', # Fichier de vue pour le modèle Coefficient
        'views/matiere_views.xml', # Fichier de vue pour le modèle Matière
        'views/session_calendrier_views.xml', # Fichier de vue pour le modèle Session
        'views/concours_views.xml',
        'views/etudiant_views.xml',
        'views/groupe_views.xml',
        'views/wizard_ajout_membre_groupe_fi_views.xml',
        'views/matiere_prof_groupe_fi_views.xml',
        'views/regle_admission_views.xml',
        'views/wizard_inscription_fi.xml',
        'views/wizard_inscription_fc.xml',
        'views/planning_assets.xml',
        'views/planning_views.xml',
        'views/wizard_ajout_matiere_etudiant_fc.xml',
        'views/menus.xml', # Fichier de vue pour le menu
        'report/report_notes_groupe_fi.xml',
    ],
    'qweb' : [
        'static/src/xml/planning_widget.xml',
    ], # Liste des fichiers QWeb (si vous en avez)
    'installable': True, # True = Hita ao amn'ny liste Apps ilay module ka afaka installer-na
    'auto_install': False, # Odoo installe automatiquement le module lorsque toutes ses dépendances sont installées. Tokony False foana io rehefa module personnalisé.
    'application' : True
}