import re
from odoo import models, fields, api
from odoo.exceptions import ValidationError

class SessionNiveau(models.Model):
    _name = 'de_inscae.session_niveau'
    _description = "Sessions de Niveau à l'INSCAE"
    _rec_name = 'intitule'

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Ce code est déjà utilisé.'),
        ('session_niveau_precedente_id_check', 'CHECK(session_niveau_precedente_id IS NULL OR session_niveau_precedente_id != id)', 'Une session ne peut pas être sa propre session précédente.'),
    ]

    code = fields.Char(string="Code de la Session", required=True)
    intitule = fields.Char(string="Intitulé de la Session", required=True)
    niveau_id = fields.Many2one('de_inscae.niveau', string="Niveau", required=True)
    option_id = fields.Many2one('de_inscae.option', string="Option")
    session_niveau_precedente_id = fields.Many2one('de_inscae.session_niveau', string="Session Précédente")

    niveau_has_options = fields.Boolean(compute='_compute_niveau_has_options')

    matiere_ids = fields.One2many('de_inscae.session_niveau_matiere', 'session_niveau_id', string="Matières")
    
    @api.depends('niveau_id')
    def _compute_niveau_has_options(self):
        for rec in self:
            rec.niveau_has_options = bool(self.env['de_inscae.option'].search_count([('niveau_id', '=', rec.niveau_id.id)]))
    
    @api.onchange('code')
    def _onchange_normalize_code(self):
        if self.code:
            self.code = self.code.upper().replace(' ', '')

    @api.onchange('intitule')
    def _onchange_strip_intitule(self):
        if self.intitule:
            self.intitule = ' '.join(self.intitule.split())

    @api.constrains('session_niveau_precedente_id')
    def _check_session_niveau_precedente_id(self):
        for record in self:
            if record.session_niveau_precedente_id:
                # Vérifier référence à soi-même
                if record.session_niveau_precedente_id == record:
                    raise ValidationError("Une session ne peut pas être sa propre session précédente.")
                elif record.session_niveau_precedente_id.niveau_id.formation_id != record.niveau_id.formation_id:
                    raise ValidationError("La session précédente doit appartenir à la même formation que la session actuelle.")

                # Remonter la chaîne pour détecter un cycle
                visited = set()
                current = record.session_niveau_precedente_id
                while current:
                    if current.id in visited:
                        raise ValidationError("Cycle détecté dans les sessions précédentes.")
                    if current == record:
                        raise ValidationError("Cycle détecté dans les sessions précédentes.")
                    visited.add(current.id)
                    current = current.session_niveau_precedente_id

    @api.constrains('niveau_id', 'session_niveau_precedente_id', 'option_id')
    def _check_option_niveau(self):
        for record in self:
            if record.option_id and record.option_id.niveau_id != record.niveau_id:
                raise ValidationError("L'option sélectionnée n'appartient pas au niveau sélectionné.")
            if record.session_niveau_precedente_id and record.session_niveau_precedente_id.option_id and record.session_niveau_precedente_id.option_id != record.option_id:
                raise ValidationError("La session précédente sélectionnée n'appartient pas au niveau sélectionné.")
            
        
    