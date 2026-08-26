import re
from odoo import models, fields, api
from odoo.exceptions import ValidationError

class Option(models.Model):
    _name = 'de_inscae.option'
    _description = "Options à l'INSCAE"
    _rec_name = 'intitule'

    _sql_constraints = [
        ('code_et_niveau_unique', 'UNIQUE(code, niveau_id)', 'Ce code est déjà utilisé pour ce niveau.'),
    ]

    code = fields.Char(string="Code de l'Option", required=True)
    intitule = fields.Char(string="Intitulé de l'Option", required=True)
    niveau_id = fields.Many2one('de_inscae.niveau', string="Niveau", required=True)

    @api.onchange('code')
    def _onchange_normalize_code(self):
        if self.code:
            self.code = self.code.upper().replace(' ', '')

    @api.onchange('intitule')
    def _onchange_strip_intitule(self):
        if self.intitule:
            self.intitule = ' '.join(self.intitule.split())