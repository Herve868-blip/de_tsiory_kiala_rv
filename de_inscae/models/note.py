from odoo import models, fields, api
from odoo.exceptions import ValidationError


class NoteFI(models.Model):
    _name = 'de_inscae.note_fi'
    _description = "Notes des Étudiants à l'INSCAE"

    etudiant_session_fi_id = fields.Many2one('de_inscae.etudiant_session_fi', string="Étudiant Inscrit", required=True, ondelete='cascade')
    matiere_prof_groupe_fi_id = fields.Many2one('de_inscae.matiere_prof_groupe_fi', string="Matière/Prof", required=True, ondelete='cascade')

    matiere_id = fields.Many2one(
        related='matiere_prof_groupe_fi_id.matiere_id',
        string="Matière", store=False, readonly=True
    )
    prof_id = fields.Many2one(
        related='matiere_prof_groupe_fi_id.prof_id',
        string="Professeur", store=False, readonly=True
    )
    ponderation_quizz = fields.Float(
        related='matiere_prof_groupe_fi_id.ponderation_quizz',
        string="% Quizz", store=False, readonly=True
    )
    ponderation_intra = fields.Float(
        related='matiere_prof_groupe_fi_id.ponderation_intra',
        string="% Intra", store=False, readonly=True
    )
    ponderation_examen_final = fields.Float(
        related='matiere_prof_groupe_fi_id.ponderation_examen_final',
        string="% Exam", store=False, readonly=True
    )
    note_quizz = fields.Float(string="Note Quizz")
    note_intra = fields.Float(string="Note Examen Intra")
    note_examen_final = fields.Float(string="Note Examen Final")
    est_delibere = fields.Boolean(string="Délibéré", default=False)

    moyenne = fields.Float(string="Moyenne", compute='_compute_moyenne', store=True)
    resultat = fields.Selection([
        ('admis', 'Admis'),
        ('admis_ap_deliberation', 'Délibéré'),
        ('deliberation', 'En attente de délibération'),
        ('refuse', 'Refusé'),
    ], string="Résultat", store=True)

    groupe_fi_id = fields.Many2one(
        related='matiere_prof_groupe_fi_id.groupe_fi_id',
        string="Groupe",
        store=False,
        readonly=True
    )

    _sql_constraints = [
        ('etudiant_matiere_unique', 'UNIQUE(etudiant_session_fi_id, matiere_prof_groupe_fi_id)',
         'Cet étudiant a déjà une note pour cette matière.'),
    ]

    @api.depends('note_quizz', 'note_intra', 'note_examen_final',
                 'matiere_prof_groupe_fi_id.ponderation_quizz',
                 'matiere_prof_groupe_fi_id.ponderation_intra',
                 'matiere_prof_groupe_fi_id.ponderation_examen_final')
    def _compute_moyenne(self):
        for rec in self:
            mpg = rec.matiere_prof_groupe_fi_id
            moy = (
                rec.note_quizz * mpg.ponderation_quizz
                + rec.note_intra * mpg.ponderation_intra
                + rec.note_examen_final * mpg.ponderation_examen_final
            ) / 100.0
            rec.moyenne = moy if moy >= 0 and moy <= 20 else 20 if moy > 20 else 0

    @api.constrains('etudiant_session_fi_id', 'matiere_prof_groupe_fi_id')
    def _check_meme_groupe(self):
        for rec in self:
            if rec.etudiant_session_fi_id.groupe_fi_id != rec.matiere_prof_groupe_fi_id.groupe_fi_id:
                raise ValidationError(
                    "Cet étudiant n'appartient pas au même groupe que cette matière."
                )

    @api.constrains('note_quizz', 'note_intra', 'note_examen_final')
    def _check_plage_notes(self):
        for rec in self:
            for champ, valeur in [
                ('Quizz', rec.note_quizz),
                ('Intra', rec.note_intra),
                ('Examen Final', rec.note_examen_final),
            ]:
                if valeur < 0 or valeur > 20:
                    raise ValidationError(f"La note '{champ}' doit être comprise entre 0 et 20.")

    @api.constrains('note_quizz', 'note_intra', 'note_examen_final')
    def _check_notes_non_verrouillees(self):
        for rec in self:
            if rec.matiere_prof_groupe_fi_id.notes_verrouillees:
                raise ValidationError(
                    "Les notes sont verrouillées et ne peuvent plus être modifiées."
                )

    def action_admettre_apres_deliberation(self):
        self.ensure_one()
        if self.resultat != 'deliberation':
            raise ValidationError("Cette note n'est pas en attente de délibération.")
    
        self.write({'resultat': 'admis_ap_deliberation', 'est_delibere': True})
    
        inscription = self.etudiant_session_fi_id
        groupe = self.matiere_prof_groupe_fi_id.groupe_fi_id
        groupe._creer_tentative(inscription, self, est_reussie=True)
    
        # Synchroniser la demi-matière
        note_moitie = self._get_note_moitie()
        if note_moitie and note_moitie.resultat == 'deliberation':
            note_moitie.write({'resultat': 'admis_ap_deliberation', 'est_delibere': True})
            inscription_moitie = note_moitie.etudiant_session_fi_id
            groupe._creer_tentative(inscription_moitie, note_moitie, est_reussie=True)
    
        inscription._finaliser_deliberation_si_complete()
    
    def action_refuser_apres_deliberation(self):
        self.ensure_one()
        if self.resultat != 'deliberation':
            raise ValidationError("Cette note n'est pas en attente de délibération.")
    
        self.write({'resultat': 'refuse', 'est_delibere': True})
    
        inscription = self.etudiant_session_fi_id
        groupe = self.matiere_prof_groupe_fi_id.groupe_fi_id
        groupe._creer_tentative(inscription, self, est_reussie=False)
    
        # Synchroniser la demi-matière
        note_moitie = self._get_note_moitie()
        if note_moitie and note_moitie.resultat == 'deliberation':
            note_moitie.write({'resultat': 'refuse', 'est_delibere': True})
            inscription_moitie = note_moitie.etudiant_session_fi_id
            groupe._creer_tentative(inscription_moitie, note_moitie, est_reussie=False)
    
        inscription._finaliser_deliberation_si_complete()
    
    def _get_note_moitie(self):
        """Retourne la note de l'autre demi-matière compatible, pour le même étudiant."""
        self.ensure_one()
        matiere = self.matiere_prof_groupe_fi_id.matiere_id
        if not matiere.est_demi_matiere:
            return None
    
        matieres_moitie = matiere.moities_compatibles_ids
        if not matieres_moitie:
            return None
    
        moitie_mpgfi = self.env['de_inscae.matiere_prof_groupe_fi'].search([
            ('groupe_fi_id', '=', self.matiere_prof_groupe_fi_id.groupe_fi_id.id),
            ('matiere_id', 'in', matieres_moitie.ids),
        ], limit=1)
    
        if not moitie_mpgfi:
            return None
    
        return self.env['de_inscae.note_fi'].search([
            ('etudiant_session_fi_id', '=', self.etudiant_session_fi_id.id),
            ('matiere_prof_groupe_fi_id', '=', moitie_mpgfi.id),
        ], limit=1)

    