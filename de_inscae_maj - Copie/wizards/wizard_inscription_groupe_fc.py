from odoo import models, fields, api
from odoo.exceptions import ValidationError

class WizardInscriptionGroupeFC(models.TransientModel):
    _name = 'de_inscae.wizard_inscription_groupe_fc'
    _description = "Wizard d'inscription à un groupe FC"

    etudiant_session_fc_id = fields.Many2one(
        'de_inscae.etudiant_session_fc',
        string="Inscription",
        required=True,
        readonly=True,
        ondelete='cascade'
    )
    session_calendrier_fc_id = fields.Many2one(
        related='etudiant_session_fc_id.session_calendrier_fc_id',
        string="Session FC",
        readonly=True,
    )

    matiere_id = fields.Many2one(
        'de_inscae.matiere',
        string="Matière",
    )
    groupe_fc_id = fields.Many2one(
        'de_inscae.groupe_fc',
        string="Groupe",
        ondelete='cascade'
    )

    prerequis_issue = fields.Char(
        string="Prérequis manquants",
        compute='_compute_avertissements',
        readonly=True,
    )
    conflit_edt = fields.Char(
        string="Conflits EDT",
        compute='_compute_avertissements',
        readonly=True,
    )
    matiere_dispo_ids = fields.Many2many(
        'de_inscae.matiere',
        compute='_compute_matiere_dispo_ids',
    )

    prof_id = fields.Many2one(
        'de_inscae.prof',
        string="Professeur",
        compute='_compute_info_groupe',
    )

    planning_ids = fields.Many2many(
        'de_inscae.planning',
        compute='_compute_info_groupe',
        string="Planning",
    )

    @api.depends('groupe_fc_id')
    def _compute_info_groupe(self):
        for rec in self:
            if rec.groupe_fc_id:
                rec.prof_id = rec.groupe_fc_id.prof_id
                rec.planning_ids = rec.groupe_fc_id.groupe_id.planning_ids
            else:
                rec.prof_id = False
                rec.planning_ids = self.env['de_inscae.planning'].browse()

    @api.depends('etudiant_session_fc_id')
    def _compute_matiere_dispo_ids(self):
        for rec in self:
            if rec.session_calendrier_fc_id:
                etudiant = rec.etudiant_session_fc_id.etudiant_fc_id.etudiant_id
                tous_etudiant_ids = self.env['de_inscae.etudiant_groupe_fc']._get_tous_etudiant_ids(etudiant)
    
                # Matières déjà réussies (directement ou par équivalence)
                toutes = self.env['de_inscae.matiere_dispo_session_fc'].search([
                    ('session_calendrier_fc_id', '=', rec.session_calendrier_fc_id.id),
                ]).mapped('matiere_id')
    
                matieres_deja_suivies = rec.etudiant_session_fc_id.groupe_fc_ids.mapped(
                    'groupe_fc_id.matiere_dispo_session_fc_id.matiere_id'
                )
    
                matieres_dispo = self.env['de_inscae.matiere'].browse()
                for matiere in toutes:
                    if matiere in matieres_deja_suivies:
                        continue
                    if self.env['de_inscae.equivalence_matiere'].etudiant_a_valide_matiere(
                        matiere, tous_etudiant_ids
                    ):
                        continue
                    matieres_dispo |= matiere
    
                rec.matiere_dispo_ids = matieres_dispo
            else:
                rec.matiere_dispo_ids = self.env['de_inscae.matiere'].browse()

    @api.onchange('matiere_id')
    def _onchange_matiere_id(self):
        self.groupe_fc_id = False
        if self.matiere_id and self.session_calendrier_fc_id:
            matieres_dispo = self.env['de_inscae.matiere_dispo_session_fc'].search([
                ('matiere_id', '=', self.matiere_id.id),
                ('session_calendrier_fc_id', '=', self.session_calendrier_fc_id.id),
            ])
            groupe_ids = self.env['de_inscae.groupe_fc'].search([
                ('matiere_dispo_session_fc_id', 'in', matieres_dispo.ids),
            ]).ids
            return {'domain': {'groupe_fc_id': [('id', 'in', groupe_ids)]}}
        return {'domain': {'groupe_fc_id': [('id', 'in', [])]}}

    @api.depends('matiere_id', 'groupe_fc_id', 'etudiant_session_fc_id')
    def _compute_avertissements(self):
        for rec in self:
            rec.prerequis_issue = False
            rec.conflit_edt = False

            if not rec.matiere_id or not rec.etudiant_session_fc_id:
                continue

            etudiant = rec.etudiant_session_fc_id.etudiant_fc_id.etudiant_id

            # Prérequis
            matieres_prealables = rec.matiere_id.matiere_prealable_ids
            if matieres_prealables:
                ids = self.env['de_inscae.etudiant_groupe_fc']._get_tous_etudiant_ids(etudiant)
                tentatives_reussies = self.env['de_inscae.tentative_matiere_etudiant'].search([
                    ('etudiant_id', 'in', ids),
                    ('matiere_id', 'in', matieres_prealables.ids),
                    ('est_reussie', '=', True),
                ]).mapped('matiere_id')
                manquantes = matieres_prealables - tentatives_reussies
                rec.prerequis_issue = ', '.join(manquantes.mapped('code')) if manquantes else False

            # Conflits EDT
            if rec.groupe_fc_id:
                plannings_groupe = rec.groupe_fc_id.groupe_id.planning_ids
                autres_groupes = rec.etudiant_session_fc_id.groupe_fc_ids.mapped(
                    'groupe_fc_id.groupe_id'
                )
                conflits = []
                for planning in plannings_groupe:
                    for autre_groupe in autres_groupes:
                        for autre_planning in autre_groupe.planning_ids:
                            if (
                                planning.tranche_horaire_id == autre_planning.tranche_horaire_id
                                and planning.jour_semaine == autre_planning.jour_semaine
                            ):
                                conflits.append(
                                    f"{autre_groupe.nom} "
                                    f"({planning.jour_semaine} {planning.tranche_horaire_id.code})"
                                )
                rec.conflit_edt = ', '.join(conflits) if conflits else False

    def action_confirmer(self):
        self.ensure_one()
        if not self.matiere_id:
            raise ValidationError("Veuillez choisir une matière.")
        if not self.groupe_fc_id:
            raise ValidationError("Veuillez choisir un groupe.")

        dispo = self.env['de_inscae.matiere_dispo_session_fc'].search([
            ('matiere_id', '=', self.matiere_id.id),
            ('session_calendrier_fc_id', '=', self.session_calendrier_fc_id.id),
        ], limit=1)
        if not dispo:
            raise ValidationError(
                f"La matière '{self.matiere_id.intitule}' n'est pas disponible dans cette session."
            )

            # Vérification effectif
        groupe = self.groupe_fc_id
        if groupe.effectif >= groupe.capacite:
            raise ValidationError(
                f"Le groupe '{groupe.nom}' est complet ({groupe.effectif}/{groupe.capacite})."
            )

        etudiant = self.etudiant_session_fc_id.etudiant_fc_id.etudiant_id
        tous_etudiant_ids = self.env['de_inscae.etudiant_groupe_fc']._get_tous_etudiant_ids(etudiant)
        deja_reussie = self.env['de_inscae.tentative_matiere_etudiant'].search([
            ('etudiant_id', 'in', tous_etudiant_ids),
            ('matiere_id', '=', self.matiere_id.id),
            ('est_reussie', '=', True),
        ], limit=1)
        if deja_reussie:
            raise ValidationError(
                f"Cet étudiant a déjà réussi la matière '{self.matiere_id.intitule}'."
            )
        self.env['de_inscae.etudiant_groupe_fc'].create({
            'groupe_fc_id': self.groupe_fc_id.id,
            'etudiant_session_fc_id': self.etudiant_session_fc_id.id,
        })
        return {'type': 'ir.actions.act_window_close'}