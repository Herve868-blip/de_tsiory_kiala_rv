import re
from odoo import models, fields, api
from odoo.exceptions import ValidationError

class Niveau(models.Model):
    _name = 'de_inscae.niveau'
    _description = "Niveaux à l'INSCAE"

    _sql_constraints = [
        ('code_et_formation_unique', 'UNIQUE(code, formation_id)', 'Ce code de niveau est déjà utilisé dans cette formation.'),
    ]

    code = fields.Char(string="Code du Niveau", required=True)
    intitule = fields.Char(string="Intitulé du Niveau", required=True)
    name = fields.Char(compute="_compute_name")
    formation_id = fields.Many2one('de_inscae.formation', string="Formation", required=True)

    @api.depends('code', 'formation_id')
    def _compute_name(self):
        for record in self:
            record.name = f"{record.code} ({record.formation_id.sigle})"

    @api.onchange('code')
    def _onchange_normalize_code(self):
        if self.code :
            self.code = self.code.upper().replace(' ', '')

    @api.onchange('intitule')
    def _onchange_strip_intitule(self) :
        if self.intitule :
            self.intitule = ' '.join(self.intitule.split())

