import re
from odoo import models, fields, api
from odoo.exceptions import ValidationError

class TrancheHoraire(models.Model):
    _name = 'de_inscae.tranche_horaire'
    _description = "Tranches Horaires"
    _rec_name = 'code'

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Ce code de tranche horaire est déjà utilisé.'),
    ]

    code = fields.Char(string="Code de la Tranche Horaire", required=True)
    heure_debut = fields.Float(string="Heure de Début", required=True)
    heure_fin = fields.Float(string="Heure de Fin", required=True)
    duree = fields.Float(string="Durée (en heures)", compute="_compute_duree", store=True)

    @api.depends('heure_debut', 'heure_fin')
    def _compute_duree(self):
        for rec in self:
            rec.duree = rec.heure_fin - rec.heure_debut

    @api.constrains('heure_debut', 'heure_fin')
    def _check_heure(self):
        for rec in self:
            if rec.heure_debut >= rec.heure_fin:
                raise ValidationError("L'heure de début doit être inférieure à l'heure de fin.")

    @api.constrains('heure_debut', 'heure_fin')
    def _check_chevauchement(self):
        for rec in self:
            chevauchements = self.env['de_inscae.tranche_horaire'].search([
                ('id', '!=', rec.id),
                ('heure_debut', '<', rec.heure_fin),
                ('heure_fin', '>', rec.heure_debut),
            ])
            if chevauchements:
                raise ValidationError(
                    f"La tranche horaire chevauche avec : {', '.join(chevauchements.mapped('code'))}"
                )