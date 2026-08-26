import re
from odoo import models, fields, api
from odoo.exceptions import ValidationError

class ParcoursAcademique(models.Model) :
    _name = 'de_inscae.parcours_academique'
    _description = "Parcours Academique à l'INSCAE"
    _rec_name = 'intitule'

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Ce code est déjà utilisé.'),
    ]

    code = fields.Char(string="Code du Parcours", required=True)
    intitule = fields.Char(string="Intitulé du Parcours", required=True)

    @api.onchange('code')
    def _onchange_normalize_code(self):
        if self.code:
            self.code = self.code.upper().replace(' ', '')

    @api.onchange('intitule')
    def _onchange_strip_intitule(self):
        if self.intitule:
            self.intitule = ' '.join(self.intitule.split())