from odoo import models, fields, api
from odoo.exceptions import ValidationError


class Planning(models.Model):
    _name = 'de_inscae.planning'
    _description = "Planning des cours"

    name = fields.Char(string="Intitulé", compute="_compute_name", store=True)

    groupe_id = fields.Many2one('de_inscae.groupe', string="Groupe", required=True, ondelete='cascade')
    matiere_id = fields.Many2one('de_inscae.matiere', string="Matière", required=True, ondelete='cascade')
    prof_id = fields.Many2one('de_inscae.prof', string="Professeur", required=True, ondelete='cascade')
    salle_id = fields.Many2one('de_inscae.salle', string="Salle", required=True, ondelete='cascade')
    tranche_horaire_id = fields.Many2one('de_inscae.tranche_horaire', string="Tranche Horaire", required=True, ondelete='cascade')

    jour_semaine = fields.Selection([
        ('1', 'Lundi'),
        ('2', 'Mardi'),
        ('3', 'Mercredi'),
        ('4', 'Jeudi'),
        ('5', 'Vendredi'),
        ('6', 'Samedi'),
    ], string="Jour", required=True)

    date_debut = fields.Date(string="Date de début", required=True)
    date_fin = fields.Date(string="Date de fin", required=True)

    type_groupe = fields.Selection([
        ('fi', 'Formation Initiale'),
        ('fc', 'Formation Continue'),
    ], string="Type", compute='_compute_type_groupe', store=True)

    _sql_constraints = [
        ('planning_unique',
         'UNIQUE(groupe_id, matiere_id, jour_semaine, tranche_horaire_id, date_debut, date_fin)',
         'Ce cours est déjà planifié pour ce groupe sur ce créneau.'),
    ]

    def _get_formation(self, groupe):
        return groupe.session_calendrier_id.session_parente_id.formation_id

    def _est_fi(self, groupe):
        return self._get_formation(groupe).sigle == 'FI'

    def _est_fc(self, groupe):
        return self._get_formation(groupe).sigle == 'FC'

    def _get_groupe_fi(self, groupe):
        return self.env['de_inscae.groupe_fi'].search(
            [('groupe_id', '=', groupe.id)], limit=1
        )

    def _get_groupe_fc(self, groupe):
        return self.env['de_inscae.groupe_fc'].search(
            [('groupe_id', '=', groupe.id)], limit=1
        )


    @api.depends('groupe_id')
    def _compute_type_groupe(self):
        for rec in self:
            if not rec.groupe_id:
                rec.type_groupe = False
            elif rec._est_fi(rec.groupe_id):
                rec.type_groupe = 'fi'
            elif rec._est_fc(rec.groupe_id):
                rec.type_groupe = 'fc'
            else:
                rec.type_groupe = False

    @api.depends('groupe_id', 'matiere_id', 'jour_semaine', 'tranche_horaire_id')
    def _compute_name(self):
        jours = {'1': 'Lun', '2': 'Mar', '3': 'Mer', '4': 'Jeu', '5': 'Ven', '6': 'Sam'}
        for rec in self:
            if rec.groupe_id and rec.matiere_id and rec.jour_semaine and rec.tranche_horaire_id:
                rec.name = (
                    f"{rec.groupe_id.nom} - {rec.matiere_id.intitule} - "
                    f"{jours[rec.jour_semaine]} {rec.tranche_horaire_id.code}"
                )
            else:
                rec.name = "Planning incomplet"

    @api.onchange('groupe_id')
    def _onchange_groupe_id(self):
        self.matiere_id = False
        self.prof_id = False
        self.date_debut = False
        self.date_fin = False

        if not self.groupe_id:
            return {'domain': {'matiere_id': [('id', 'in', [])]}}

        session_cal = self.groupe_id.session_calendrier_id
        self.date_debut = session_cal.date_debut
        self.date_fin = session_cal.date_fin

        if self._est_fi(self.groupe_id):
            groupe_fi = self._get_groupe_fi(self.groupe_id)
            if groupe_fi:
                matiere_ids = groupe_fi.matiere_prof_ids.mapped('matiere_id').ids
                return {'domain': {'matiere_id': [('id', 'in', matiere_ids)]}}

        elif self._est_fc(self.groupe_id):
            groupe_fc = self._get_groupe_fc(self.groupe_id)
            if groupe_fc:
                self.matiere_id = groupe_fc.matiere_dispo_session_fc_id.matiere_id
                self.prof_id = groupe_fc.prof_id
                return {'domain': {'matiere_id': [('id', '=', self.matiere_id.id)]}}

        return {'domain': {'matiere_id': [('id', 'in', [])]}}

    
    @api.onchange('matiere_id')
    def _onchange_matiere_id(self):
        if not self.matiere_id or not self.groupe_id:
            return

        if self._est_fi(self.groupe_id):
            self.prof_id = False
            groupe_fi = self._get_groupe_fi(self.groupe_id)
            if groupe_fi:
                affectation = self.env['de_inscae.matiere_prof_groupe_fi'].search([
                    ('groupe_fi_id', '=', groupe_fi.id),
                    ('matiere_id', '=', self.matiere_id.id),
                ], limit=1)
                if affectation:
                    self.prof_id = affectation.prof_id

    @api.constrains('date_debut', 'date_fin', 'groupe_id')
    def _check_dates(self):
        for rec in self:
            if rec.date_debut and rec.date_fin:
                if rec.date_debut > rec.date_fin:
                    raise ValidationError("La date de début doit être antérieure à la date de fin.")
    
                if rec.groupe_id:
                    session_cal = rec.groupe_id.session_calendrier_id
                    if session_cal.date_debut and session_cal.date_fin:
                        if rec.date_debut < session_cal.date_debut or rec.date_fin > session_cal.date_fin:
                            raise ValidationError(
                                f"Les dates du planning ({rec.date_debut} → {rec.date_fin}) "
                                f"doivent être comprises dans la période de la session "
                                f"({session_cal.date_debut} → {session_cal.date_fin})."
                            )

    @api.constrains('salle_id', 'jour_semaine', 'tranche_horaire_id', 'date_debut', 'date_fin')
    def _check_conflit_salle(self):
        for rec in self:
            conflits = self.env['de_inscae.planning'].search([
                ('id', '!=', rec.id),
                ('salle_id', '=', rec.salle_id.id),
                ('jour_semaine', '=', rec.jour_semaine),
                ('tranche_horaire_id', '=', rec.tranche_horaire_id.id),
                ('date_debut', '<=', rec.date_fin),
                ('date_fin', '>=', rec.date_debut),
            ])
            for conflit in conflits:
                if conflit.matiere_id != rec.matiere_id or conflit.prof_id != rec.prof_id:
                    raise ValidationError(
                        f"La salle '{rec.salle_id.numero}' est déjà occupée ce créneau "
                        f"par le groupe '{conflit.groupe_id.nom}' "
                        f"(matière : {conflit.matiere_id.intitule}, prof : {conflit.prof_id.nomcomplet})."
                    )

    @api.constrains('prof_id', 'jour_semaine', 'tranche_horaire_id', 'date_debut', 'date_fin')
    def _check_conflit_prof(self):
        for rec in self:
            conflits = self.env['de_inscae.planning'].search([
                ('id', '!=', rec.id),
                ('prof_id', '=', rec.prof_id.id),
                ('jour_semaine', '=', rec.jour_semaine),
                ('tranche_horaire_id', '=', rec.tranche_horaire_id.id),
                ('date_debut', '<=', rec.date_fin),
                ('date_fin', '>=', rec.date_debut),
            ])
            for conflit in conflits:
                if conflit.matiere_id != rec.matiere_id or conflit.salle_id != rec.salle_id:
                    raise ValidationError(
                        f"Le professeur '{rec.prof_id.nomcomplet}' est déjà occupé ce créneau "
                        f"par le groupe '{conflit.groupe_id.nom}' "
                        f"(matière : {conflit.matiere_id.intitule}, salle : {conflit.salle_id.numero})."
                    )

    @api.constrains('groupe_id', 'jour_semaine', 'tranche_horaire_id', 'date_debut', 'date_fin')
    def _check_conflit_groupe(self):
        for rec in self:
            conflits = self.env['de_inscae.planning'].search([
                ('id', '!=', rec.id),
                ('groupe_id', '=', rec.groupe_id.id),
                ('jour_semaine', '=', rec.jour_semaine),
                ('tranche_horaire_id', '=', rec.tranche_horaire_id.id),
                ('date_debut', '<=', rec.date_fin),
                ('date_fin', '>=', rec.date_debut),
            ])
            for conflit in conflits:
                raise ValidationError(
                    f"Le groupe '{rec.groupe_id.nom}' a déjà un cours ce créneau : "
                    f"'{conflit.matiere_id.intitule}'."
                )