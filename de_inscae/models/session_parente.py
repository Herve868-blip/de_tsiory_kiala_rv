import re
from odoo import models, fields, api
from odoo.exceptions import ValidationError

def get_field_mois_selection(arg):
    return [
        ('1', 'Janvier'),
        ('2', 'Février'),
        ('3', 'Mars'),
        ('4', 'Avril'),
        ('5', 'Mai'),
        ('6', 'Juin'),
        ('7', 'Juillet'),
        ('8', 'Août'),
        ('9', 'Septembre'),
        ('10', 'Octobre'),
        ('11', 'Novembre'),
        ('12', 'Décembre')
    ]

class SessionParente(models.Model):
    _name = 'de_inscae.session_parente'
    _description = "Sessions Parentes à l'INSCAE"
    _rec_name = 'libelle'

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Ce code est déjà utilisé.'),
    ]

    code = fields.Char(string="Code de la Session", required=True)
    libelle = fields.Char(string="Libellé de la Session Parente", required=True)
    formation_id = fields.Many2one('de_inscae.formation', string="Formation", required=True)
    mois_debut = fields.Selection(
        selection=get_field_mois_selection,
        string="Mois de Début", required=True
    )
    mois_fin = fields.Selection(
        selection=get_field_mois_selection,
        string="Mois de Fin", required=True
    )

    @api.onchange('code')
    def _onchange_normalize_code(self):
        if self.code:
            self.code = self.code.upper().replace(' ', '')

    @api.onchange('libelle')
    def _onchange_strip_libelle(self):
        if self.libelle:
            self.libelle = ' '.join(self.libelle.split())


class SessionParenteFI(models.Model):
    _name = 'de_inscae.session_parente_fi'
    _description = "Session Parente FI"
    _inherits = {'de_inscae.session_parente': 'session_parente_id'}
    _rec_name = 'libelle'

    session_parente_id = fields.Many2one('de_inscae.session_parente', string="Session Parente", required=True, ondelete='cascade')
    session_niveau_id = fields.Many2one('de_inscae.session_niveau', string="Session Niveau", required=True)
    
    _sql_constraints = [
        ('session_parente_unique_fi', 'UNIQUE(session_parente_id)', 'Cette session parente FI a déjà une session est déjà liée à une session parente.'),
        ('session_niveau_fi_unique', 'UNIQUE(session_niveau_id)', 'Cette session de niveau FI a déjà une session est déjà liée à une session parente.'),
    ]

    @api.constrains('session_parente_id')
    def _check_formation_fi(self):
        for rec in self:
            if rec.session_parente_id.formation_id.sigle != 'FI':
                raise ValidationError("La formation de la session parente doit être FI.")

    @api.constrains('session_niveau_id')
    def _check_formation_fi_session_niveau(self):
        for rec in self:
            if rec.session_niveau_id.niveau_id.formation_id.sigle != 'FI':
                raise ValidationError("La formation de la session de niveau doit être FI.")

class SessionParenteFC(models.Model):
    _name = 'de_inscae.session_parente_fc'
    _description = "Session Parente FC"
    _inherits = {'de_inscae.session_parente': 'session_parente_id'}
    _rec_name = 'libelle'

    session_parente_id = fields.Many2one('de_inscae.session_parente', string="Session Parente", required=True, ondelete='cascade')
    
    _sql_constraints = [
        ('session_parente_unique_fc', 'UNIQUE(session_parente_id)',
         'Cette session parente FC a déjà une session est déjà liée à une session parente.'),
    ]

    @api.constrains('session_parente_id')
    def _check_formation_fc(self):
        for rec in self:
            if rec.session_parente_id.formation_id.sigle != 'FC':
                raise ValidationError("La formation de la session parente doit être FC.")
