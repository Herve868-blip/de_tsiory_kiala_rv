import re
from odoo import models, fields, api
from odoo.exceptions import ValidationError

class Matiere(models.Model):
    _name = 'de_inscae.matiere'
    _description = "Matière à l'INSCAE"
    _rec_name = 'code'

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Ce code est déjà utilisé.')
    ]

    code = fields.Char(string='Code', required=True)
    intitule = fields.Char(string='Intitulé', required=True)
    est_demi_matiere = fields.Boolean(string='Est une demi-matière', default=False)
    est_amovible = fields.Boolean(string="Est amovible", default=True)
    est_active = fields.Boolean(string='En activité', default=True)
    matiere_prealable_ids = fields.Many2many(
        'de_inscae.matiere',
        'de_inscae_matieres_prealables',
        'matiere_id',
        'matiere_prealable_id',
        string='Matières Préalables'
    )
    moities_compatibles_ids = fields.Many2many(
        'de_inscae.matiere',
        'de_inscae_matieres_moities_compatibles',
        'matiere_id',
        'moitie_id',
        string='Moitiés Compatibles',
        domain=[('est_demi_matiere', '=', True)]
    )
    session_niveau_ids = fields.One2many('de_inscae.session_niveau_matiere', 'matiere_id', string="Sessions de Niveau", required=True)

    @api.onchange('matiere_prealable_ids')
    def _onchange_matiere_prealable_ids(self):
        if self.matiere_prealable_ids:
            tous_les_prealables = set(self.matiere_prealable_ids.ids)
            a_traiter = list(self.matiere_prealable_ids)
            while a_traiter:
                current = a_traiter.pop()
                for prealable in current.matiere_prealable_ids:
                    if prealable.id not in tous_les_prealables:
                        tous_les_prealables.add(prealable.id)
                        a_traiter.append(prealable)
            self.matiere_prealable_ids = [(6, 0, list(tous_les_prealables))]


    @api.onchange('code')
    def _onchange_normalize_code(self):
        if self.code :
            self.code = self.code.upper().replace(' ', '')

    @api.onchange('intitule')
    def _onchange_strip_intitule(self) :
        if self.intitule :
            self.intitule = ' '.join(self.intitule.split())

    @api.onchange('est_demi_matiere')
    def _onchange_est_demi_matiere(self):
        if not self.est_demi_matiere:
            self.moities_compatibles_ids = [(5, 0, 0)]
    
    @api.constrains('matiere_prealable_ids')
    def _check_cycle_prealables(self):
        for rec in self:
            visited = set()
            a_traiter = list(rec.matiere_prealable_ids)
            while a_traiter:
                current = a_traiter.pop()
                if current.id == rec.id:
                    raise ValidationError("Cycle détecté dans les matières préalables.")
                if current.id not in visited:
                    visited.add(current.id)
                    a_traiter.extend(current.matiere_prealable_ids)

    @api.constrains('session_niveau_ids')
    def _check_sessions_niveau(self):
        for rec in self:
            sessions = rec.session_niveau_ids.mapped('session_niveau_id')
            for session in sessions:
                ancetres = set()
                current = session.session_niveau_precedente_id
                while current:
                    ancetres.add(current.id)
                    current = current.session_niveau_precedente_id
                for autre in sessions:
                    if autre.id != session.id and autre.id in ancetres:
                        raise ValidationError(
                            f"La matière '{rec.intitule}' ne peut pas apparaître dans deux sessions de la même chaîne."
                        )

    @api.constrains('moities_compatibles_ids', 'est_demi_matiere')
    def _check_moities_compatibles(self):
        for rec in self:
            if not rec.est_demi_matiere and rec.moities_compatibles_ids:
                raise ValidationError("Seules les demi-matières peuvent avoir des moitiés compatibles.")
            if rec.est_demi_matiere and rec.moities_compatibles_ids:
                niveaux_rec = set(rec.session_niveau_ids.mapped('session_niveau_id.niveau_id.id'))
                for compatible in rec.moities_compatibles_ids:
                    if not compatible.est_demi_matiere:
                        raise ValidationError(f"'{compatible.intitule}' n'est pas une demi-matière.")
                    niveaux_compatible = set(compatible.session_niveau_ids.mapped('session_niveau_id.niveau_id.id'))
                    if not niveaux_rec.intersection(niveaux_compatible):
                        raise ValidationError(
                            f"'{compatible.intitule}' n'appartient pas au même niveau que '{rec.intitule}'."
                        )

    def _sync_moities_compatibles(self):
        for rec in self:
            for compatible in rec.moities_compatibles_ids:
                if rec not in compatible.moities_compatibles_ids:
                    compatible.sudo().write({
                        'moities_compatibles_ids': [(4, rec.id)]
                    })

    @api.model
    def create(self, vals):
        record = super().create(vals)
        if not record.session_niveau_ids:
            raise ValidationError("Une matière doit être associée à au moins une session de niveau.")
        record._sync_moities_compatibles()
        return record

    def write(self, vals):
        result = super().write(vals)
        for rec in self:
            if not rec.session_niveau_ids:
                raise ValidationError("Une matière doit être associée à au moins une session de niveau.")
        if 'moities_compatibles_ids' in vals:
            self._sync_moities_compatibles()
        return result