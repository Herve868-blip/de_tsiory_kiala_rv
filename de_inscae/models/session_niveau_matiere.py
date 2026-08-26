import re
from odoo import models, fields, api
from odoo.exceptions import ValidationError

class SessionNiveauMatiere(models.Model):
    _name = 'de_inscae.session_niveau_matiere'
    _description = "Matières d'une Session de Niveau"

    session_niveau_id = fields.Many2one('de_inscae.session_niveau', required=True, ondelete='cascade')
    matiere_id = fields.Many2one('de_inscae.matiere', required=True, ondelete='cascade')
    coefficient_id = fields.Many2one('de_inscae.coefficient', string='Coefficient', ondelete='cascade', required=True)

    @api.constrains('coefficient_id')
    def _check_coefficient(self):
        for rec in self:
            if not rec.coefficient_id:
                raise ValidationError("Le coefficient est obligatoire.")