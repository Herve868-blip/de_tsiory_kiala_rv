import re
from odoo import models, fields, api
from odoo.exceptions import ValidationError

class Salle(models.Model):
    _name = 'de_inscae.salle'
    _description = "Salles de l'INSCAE"
    _rec_name = 'numero'

    _sql_constraints = [
        ('numero_unique', 'UNIQUE(numero)', 'Ce numéro de salle est déjà utilisé.'),
    ]

    numero = fields.Char(string="Code de la Salle", required=True)
    capacite = fields.Integer(string="Capacité de la Salle", required=True)

    @api.constrains('capacite')
    def _check_capacite(self):
        for rec in self:
            if rec.capacite <= 0:
                raise ValidationError("La capacité de la salle doit être un nombre positif.")