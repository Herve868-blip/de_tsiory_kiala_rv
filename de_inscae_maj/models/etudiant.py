import json

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class Etudiant(models.Model):
    _name = 'de_inscae.etudiant'
    _description = "Etudiant à l'INSCAE"

    individu_id = fields.Many2one('de_inscae.individu', string="Individu", required=True, ondelete='cascade')
    formation_id = fields.Many2one('de_inscae.formation', string="Formation", required=True)
    matricule = fields.Char(string="Matricule", required=True, copy=False)
    ancien_id = fields.Many2one('de_inscae.etudiant', string="Ancien Dossier Étudiant")
    tentative_matiere_ids = fields.One2many('de_inscae.tentative_matiere_etudiant', 'etudiant_id', string="Tentatives Matières")
    state = fields.Selection([
        ('actif', 'Actif'),
        ('sortant', 'Sortant'),
        ('transfere_fc', 'Transféré en FC'),
        ('exclu', 'Exclu'),
    ], string="Statut", default='actif', required=True)

    name = fields.Char(string="Etudiant", compute='_compute_name', readonly=True, store=True)
    @api.depends('individu_id.nom_complet', 'matricule')
    def _compute_name(self):
        for record in self:
            record.name = (f" [{record.matricule}]" if record.matricule else '') + " - " + record.individu_id.nom_complet

    _sql_constraints = [
        ('matricule_unique', 'UNIQUE(matricule)', 'Ce matricule est déjà utilisé.'),
        ('ancien_unique', 'UNIQUE(ancien_id)', 'Cet ancien dossier est déjà lié à un autre étudiant.'),
    ]

    @api.model
    def _verifier_pas_double_inscription(self, individu_id):
        deja_inscrit = self.env['de_inscae.etudiant'].search([
            ('individu_id', '=', individu_id),
            ('formation_id.sigle', 'in', ('FI', 'FC')),
            ('state', '=', 'actif'),
        ], limit=1)
        if deja_inscrit:
            individu = self.env['de_inscae.individu'].browse(individu_id)
            raise ValidationError(
                f"'{individu.nom_complet}' est déjà étudiant actif en {deja_inscrit.formation_id.sigle}."
            )

class TentativeMatiereEtudiant(models.Model):
    _name = 'de_inscae.tentative_matiere_etudiant'
    _description = "Tentative d'un Étudiant à une Matière"

    etudiant_id = fields.Many2one('de_inscae.etudiant', string="Étudiant", required=True, ondelete='cascade')
    matiere_id = fields.Many2one('de_inscae.matiere', string="Matière", required=True, ondelete='cascade')
    session_calendrier_id = fields.Many2one('de_inscae.session_calendrier', string="Session Calendrier", required=True, ondelete='cascade')
    prof_id = fields.Many2one('de_inscae.prof', string="Professeur", ondelete='cascade')
    note_finale = fields.Float(string="Note")
    est_reussie = fields.Boolean(string="Réussie", required=True)

    _sql_constraints = [
        ('etudiant_matiere_session_unique', 'UNIQUE(etudiant_id, matiere_id, session_calendrier_id)',
         'Cet étudiant a déjà une tentative pour cette matière dans cette session.'),
    ]


class EtudiantFI(models.Model):
    _name = 'de_inscae.etudiant_fi'
    _description = "Etudiant FI à l'INSCAE"
    _inherits = {'de_inscae.etudiant': 'etudiant_id'}

    etudiant_id = fields.Many2one('de_inscae.etudiant', required=True, ondelete='cascade')
    session_niveau_actuelle = fields.Many2one('de_inscae.session_niveau', string="Session de Niveau Actuelle", required=True)
    session_fi_ids = fields.One2many('de_inscae.etudiant_session_fi', 'etudiant_fi_id', string="Inscriptions aux Sessions")

    _sql_constraints = [
        ('etudiant_fi_unique', 'UNIQUE(etudiant_id)', 'Cet étudiant est déjà lié à un dossier FI.'),
    ]

    @api.model
    def _generer_matricule(self):
        brut = self.env['ir.sequence'].next_by_code('de_inscae.etudiant.fi')
        if not brut:
            raise ValidationError("La séquence de matricule FI n'est pas configurée.")
        return f"{brut[:3]} {brut[3:]}"

    def unlink(self):
        etudiant_ids = self.mapped('etudiant_id')
        result = super().unlink()
        etudiant_ids.unlink()
        return result

class EtudiantSessionFI(models.Model):
    _name = 'de_inscae.etudiant_session_fi'
    _description = "Inscription d'un Étudiant FI à une Session Calendrier"

    name = fields.Char(string="Étudiant", related='etudiant_fi_id.name', store=True, readonly=True)
    etudiant_fi_id = fields.Many2one('de_inscae.etudiant_fi', string="Étudiant FI", required=True, ondelete='cascade')
    session_calendrier_fi_id = fields.Many2one('de_inscae.session_calendrier_fi', string="Session Calendrier FI", required=True, ondelete='cascade')
    groupe_fi_id = fields.Many2one(
        'de_inscae.groupe_fi',
        string="Groupe",
        domain="[('session_calendrier_fi_id', '=', session_calendrier_fi_id)]"
    )
    moyenne_generale = fields.Float(string="Moyenne Générale")
    resultat_session = fields.Selection([
        ('admis', 'Admis'),
        ('admis_ap_deliberation', 'Admis après délibération'),
        ('en_attente_deliberation', 'En attente de délibération'),
        ('transfere_fc', 'Transféré en FC'),
        ('exclu', 'Exclu'),
    ], string="Résultat de la Session")
    note_ids = fields.One2many('de_inscae.note_fi', 'etudiant_session_fi_id', string="Notes")

    _sql_constraints = [
        ('etudiant_session_unique', 'UNIQUE(etudiant_fi_id, session_calendrier_fi_id)',
         'Cet étudiant est déjà inscrit à cette session.'),
    ]

    @api.constrains('groupe_fi_id', 'session_calendrier_fi_id')
    def _check_groupe_session_coherence(self):
        for rec in self:
            if rec.groupe_fi_id and rec.groupe_fi_id.session_calendrier_fi_id != rec.session_calendrier_fi_id:
                raise ValidationError(
                    "Le groupe sélectionné n'appartient pas à la session calendrier de cette inscription."
                )

    def write(self, vals):
        result = super().write(vals)
        if 'groupe_fi_id' in vals and vals['groupe_fi_id']:
            for rec in self:
                rec._synchroniser_notes()
        return result

    def _synchroniser_notes(self):
        for rec in self:
            if not rec.groupe_fi_id:
                return
            matieres = rec.groupe_fi_id.matiere_prof_ids
            notes_existantes = rec.note_ids.mapped('matiere_prof_groupe_fi_id')
            for matiere_prof in matieres:
                if matiere_prof not in notes_existantes:
                    self.env['de_inscae.note_fi'].create({
                        'etudiant_session_fi_id': rec.id,
                        'matiere_prof_groupe_fi_id': matiere_prof.id,
                    })

    def action_retirer_du_groupe(self):
        self.ensure_one()
        # Supprimer aussi les notes liées au groupe
        self.env['de_inscae.note_fi'].search([
            ('etudiant_session_fi_id', '=', self.id)
        ]).unlink()
        self.groupe_fi_id = False

    def _finaliser_deliberation_si_complete(self):
        """Déclenche le recalcul si toutes les notes sont tranchées."""
        self.ensure_one()
        notes = self.note_ids
        encore_en_deliberation = notes.filtered(lambda n: n.resultat == 'deliberation')
        if not encore_en_deliberation:
            self._recalculer_resultat_session()

    def _recalculer_resultat_session(self):
        self.ensure_one()
        groupe = self.groupe_fi_id
        regle, admission_min, deliberation_min = groupe._get_regle_et_seuils()
        moyenne_generale = groupe._calculer_moyenne_generale(self)
        resultats = self.note_ids.mapped('resultat')

        a_refuse = 'refuse' in resultats
        a_deliberation = 'deliberation' in resultats
        toutes_ok = not a_refuse and not a_deliberation

        if moyenne_generale >= admission_min:
            if a_refuse:
                resultat_session = 'transfere_fc'
            else:
                resultat_session = 'admis_ap_deliberation'

        elif deliberation_min <= moyenne_generale < admission_min:
            if a_refuse:
                resultat_session = 'exclu'
            else:
                resultat_session = 'en_attente_deliberation'

        else :
            if a_refuse:
                resultat_session = 'exclu'
            else:
                resultat_session = 'en_attente_deliberation'

        self.write({
            'moyenne_generale': moyenne_generale,
            'resultat_session': resultat_session,
        })
        self._mettre_a_jour_state_etudiant()

    peut_jury_decider = fields.Boolean(
        string="Jury peut décider",
        compute='_compute_peut_jury_decider'
    )

    @api.depends('resultat_session', 'note_ids.resultat')
    def _compute_peut_jury_decider(self):
        for rec in self:
            rec.peut_jury_decider = (
                rec.resultat_session == 'en_attente_deliberation'
                and not rec.note_ids.filtered(lambda n: n.resultat == 'deliberation')
                and not rec.note_ids.filtered(lambda n: not n.resultat)
            )

    def action_jury_admettre(self):
        self.ensure_one()
        if self.resultat_session != 'en_attente_deliberation':
            raise ValidationError("Cet étudiant n'est pas en attente de délibération manuelle.")
        self.write({'resultat_session': 'admis_ap_deliberation'})
        self._mettre_a_jour_state_etudiant()

    def action_jury_transferer_fc(self):
        self.ensure_one()
        if self.resultat_session != 'en_attente_deliberation':
            raise ValidationError("Cet étudiant n'est pas en attente de délibération manuelle.")
        self.write({'resultat_session': 'transfere_fc'})
        self._mettre_a_jour_state_etudiant()

    def _mettre_a_jour_state_etudiant(self):
        self.ensure_one()
        etudiant = self.etudiant_fi_id.etudiant_id
        resultat = self.resultat_session
        if resultat == 'exclu':
            etudiant.state = 'exclu'
        elif resultat == 'transfere_fc':
            etudiant.state = 'transfere_fc'
        elif resultat in ('admis', 'admis_ap_deliberation', 'en_attente_deliberation'):
            etudiant.state = 'actif'

class EtudiantFC(models.Model):
    _name = 'de_inscae.etudiant_fc'
    _description = "Etudiant FC à l'INSCAE"
    _inherits = {'de_inscae.etudiant': 'etudiant_id'}

    etudiant_id = fields.Many2one('de_inscae.etudiant', required=True, ondelete='cascade')
    session_calendrier_fc_actuelle_id = fields.Many2one(
        'de_inscae.session_calendrier_fc',
        string="Session FC Actuelle",
    )
    session_fc_ids = fields.One2many('de_inscae.etudiant_session_fc', 'etudiant_fc_id', string="Inscriptions aux Sessions")

    est_migre = fields.Boolean(string="Étudiant migré", default=False)

    _sql_constraints = [
        ('etudiant_fc_unique', 'UNIQUE(etudiant_id)', 'Cet étudiant est déjà lié à un dossier FC.'),
    ]

    @api.model
    def _generer_matricule(self):
        brut = self.env['ir.sequence'].next_by_code('de_inscae.etudiant.fc')
        if not brut:
            raise ValidationError("La séquence de matricule FC n'est pas configurée.")
        return f"CA {brut}"

    def unlink(self):
        etudiant_ids = self.mapped('etudiant_id')
        result = super().unlink()
        etudiant_ids.unlink()
        return result

class EtudiantSessionFC(models.Model):
    _name = 'de_inscae.etudiant_session_fc'
    _description = "Inscription d'un Étudiant FC à une Session Calendrier"

    etudiant_fc_id = fields.Many2one('de_inscae.etudiant_fc', string="Étudiant FC", required=True, ondelete='cascade')
    session_calendrier_fc_id = fields.Many2one('de_inscae.session_calendrier_fc', string="Session Calendrier FC", required=True, ondelete='cascade')
    name = fields.Char(related='etudiant_fc_id.name', store=True, readonly=True)
    session_libelle = fields.Char(
        related='session_calendrier_fc_id.session_calendrier_id.libelle',
        store=True, readonly=True
    )
    groupe_fc_ids = fields.One2many('de_inscae.etudiant_groupe_fc', 'etudiant_session_fc_id', string="Groupes Matières")
    resultat_session = fields.Selection([
        ('admis', 'Admis'),
        ('admis_ap_deliberation', 'Admis après délibération'),
        ('en_attente_deliberation', 'En attente de délibération'),
        ('exclu', 'Exclu'),
    ], string="Résultat de la Session")

    tentative_matiere_ids = fields.Many2many(
        'de_inscae.tentative_matiere_etudiant',
        string="Tentatives Matières",
        compute='_compute_tentative_matiere_ids'
    )

    _sql_constraints = [
        ('etudiant_session_fc_unique', 'UNIQUE(etudiant_fc_id, session_calendrier_fc_id)',
         'Cet étudiant est déjà inscrit à cette session.'),
    ]

    @api.depends('etudiant_fc_id.etudiant_id.tentative_matiere_ids',
                 'session_calendrier_fc_id.session_calendrier_id')
    def _compute_tentative_matiere_ids(self):
        for rec in self:
            session_cal = rec.session_calendrier_fc_id.session_calendrier_id
            etudiant = rec.etudiant_fc_id.etudiant_id
            rec.tentative_matiere_ids = etudiant.tentative_matiere_ids.filtered(
                lambda t: t.session_calendrier_id == session_cal
            )

    def _finaliser_deliberation_si_complete(self):
        self.ensure_one()
        encore_en_deliberation = self.groupe_fc_ids.filtered(
            lambda g: g.resultat == 'deliberation'
        )
        if not encore_en_deliberation:
            self._recalculer_resultat_session()

    def _recalculer_resultat_session(self):
        self.ensure_one()

        if self.groupe_fc_ids:
            resultats = self.groupe_fc_ids.mapped('resultat')
            if not resultats or any(not r for r in resultats):
                return
            all_admis_sans_delib = all(r == 'admis' for r in resultats)
            a_refuse = 'refuse' in resultats
            a_deliberation = 'deliberation' in resultats
            if a_deliberation:
                resultat_session = 'en_attente_deliberation'
            elif a_refuse:
                resultat_session = 'exclu'
            elif all_admis_sans_delib:
                resultat_session = 'admis'
            else:
                resultat_session = 'admis_ap_deliberation'

        elif self.etudiant_fc_id.est_migre:
            tentatives = self.tentative_matiere_ids
            if not tentatives:
                return
            toutes_reussies = all(t.est_reussie for t in tentatives)
            resultat_session = 'admis' if toutes_reussies else 'exclu'

        else:
            return

        self.write({'resultat_session': resultat_session})
        self._mettre_a_jour_state_etudiant()

    def _mettre_a_jour_state_etudiant(self):
        self.ensure_one()
        etudiant = self.etudiant_fc_id.etudiant_id
        resultat = self.resultat_session
        if resultat == 'exclu':
            etudiant.state = 'exclu'
        elif resultat in ('admis', 'admis_ap_deliberation', 'en_attente_deliberation'):
            etudiant.state = 'actif'

    peut_jury_decider = fields.Boolean(
        string="Jury peut décider",
        compute='_compute_peut_jury_decider'
    )

    @api.depends('resultat_session', 'groupe_fc_ids.resultat')
    def _compute_peut_jury_decider(self):
        for rec in self:
            rec.peut_jury_decider = (
                rec.resultat_session == 'en_attente_deliberation'
                and not rec.groupe_fc_ids.filtered(lambda g: g.resultat == 'deliberation')
                and not rec.groupe_fc_ids.filtered(lambda g: not g.resultat)
            )

    def action_jury_admettre(self):
        self.ensure_one()
        if self.resultat_session != 'en_attente_deliberation':
            raise ValidationError("Cet étudiant n'est pas en attente de délibération manuelle.")
        self.write({'resultat_session': 'admis_ap_deliberation'})
        self._mettre_a_jour_state_etudiant()

    def action_jury_exclure(self):
        self.ensure_one()
        if self.resultat_session != 'en_attente_deliberation':
            raise ValidationError("Cet étudiant n'est pas en attente de délibération manuelle.")
        self.write({'resultat_session': 'exclu'})
        self._mettre_a_jour_state_etudiant()

    def action_ouvrir_fiche(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'de_inscae.etudiant_session_fc',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
            'views': [(self.env.ref('de_inscae.view_etudiant_session_fc_form').id, 'form')],
        }

    def action_ouvrir_wizard_inscription_groupe(self):
        self.ensure_one()
        wizard = self.env['de_inscae.wizard_inscription_groupe_fc'].create({
            'etudiant_session_fc_id': self.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'de_inscae.wizard_inscription_groupe_fc',
            'view_mode': 'form',
            'res_id': wizard.id,
            'target': 'new',
            'views': [(self.env.ref('de_inscae.view_wizard_inscription_groupe_fc_form').id, 'form')],
        }

class EtudiantGroupeFC(models.Model):
    _name = 'de_inscae.etudiant_groupe_fc'
    _description = "Inscription d'un Étudiant FC à un Groupe Matière"
    _rec_name = 'name'

    groupe_fc_id = fields.Many2one('de_inscae.groupe_fc', string="Groupe Matière", required=True, ondelete='cascade')
    etudiant_session_fc_id = fields.Many2one('de_inscae.etudiant_session_fc', string="Étudiant Inscrit", required=True, ondelete='cascade')
    name = fields.Char(related='etudiant_session_fc_id.name', store=True, readonly=True)
    matiere_id = fields.Many2one(related='groupe_fc_id.matiere_dispo_session_fc_id.matiere_id', string="Matière", store=False, readonly=True)
    prof_id = fields.Many2one(related='groupe_fc_id.prof_id', string="Professeur", store=False, readonly=True)
    prerequis_issue = fields.Char(string="Prérequis manquants", compute='_compute_prerequis_issue', store=False, readonly=True)

    note_quizz = fields.Float(string="Note Quizz")
    note_intra = fields.Float(string="Note Intra")
    note_examen_final = fields.Float(string="Note Examen Final")
    moyenne = fields.Float(string="Moyenne", compute='_compute_moyenne', store=True)
    resultat = fields.Selection([
        ('admis', 'Admis'),
        ('admis_ap_deliberation', 'Délibéré'),
        ('deliberation', 'En attente de délibération'),
        ('refuse', 'Refusé'),
    ], string="Résultat")

    conflit_edt = fields.Char(string="Conflits EDT", compute='_compute_conflit_edt', store=False, readonly=True)

    _sql_constraints = [
        ('etudiant_groupe_fc_unique', 'UNIQUE(groupe_fc_id, etudiant_session_fc_id)',
         'Cet étudiant est déjà inscrit à ce groupe matière.'),
    ]

    @api.model
    def create(self, vals):
        groupe_fc = self.env['de_inscae.groupe_fc'].browse(vals['groupe_fc_id'])
        etudiant_session = self.env['de_inscae.etudiant_session_fc'].browse(vals['etudiant_session_fc_id'])
        etudiant = etudiant_session.etudiant_fc_id.etudiant_id
        matiere = groupe_fc.matiere_dispo_session_fc_id.matiere_id

        if groupe_fc.effectif >= groupe_fc.capacite:
            raise ValidationError(
                f"Le groupe '{groupe_fc.nom}' est complet ({groupe_fc.effectif}/{groupe_fc.capacite})."
            )

        deja_inscrit = self.search([
            ('etudiant_session_fc_id', '=', etudiant_session.id),
            ('groupe_fc_id.matiere_dispo_session_fc_id.matiere_id', '=', matiere.id),
        ], limit=1)
        if deja_inscrit:
            raise ValidationError(
                f"'{etudiant.name}' est déjà inscrit à un groupe pour la matière '{matiere.intitule}'."
            )

        tous_etudiant_ids = self._get_tous_etudiant_ids(etudiant)
        deja_reussie = self.env['de_inscae.tentative_matiere_etudiant'].search([
            ('etudiant_id', 'in', tous_etudiant_ids),
            ('matiere_id', '=', matiere.id),
            ('est_reussie', '=', True),
        ], limit=1)
        if deja_reussie:
            raise ValidationError(
                f"'{etudiant.name}' a déjà réussi la matière '{matiere.intitule}'."
            )
        return super().create(vals)

    @api.model
    def _get_tous_etudiant_ids(self, etudiant):
        ids = [etudiant.id]
        current = etudiant
        while current.ancien_id:
            current = current.ancien_id
            ids.append(current.id)
        return ids

    @api.depends('groupe_fc_id', 'etudiant_session_fc_id')
    def _compute_prerequis_issue(self):
        for rec in self:
            matiere = rec.groupe_fc_id.matiere_dispo_session_fc_id.matiere_id
            matieres_prealables = matiere.matiere_prealable_ids
            if not matieres_prealables:
                rec.prerequis_issue = False
                continue
            
            etudiant = rec.etudiant_session_fc_id.etudiant_fc_id.etudiant_id
            tous_etudiant_ids = rec._get_tous_etudiant_ids(etudiant)
    
            manquantes = []
            for prealable in matieres_prealables:
                if not self.env['de_inscae.equivalence_matiere'].etudiant_a_valide_matiere(
                    prealable, tous_etudiant_ids
                ):
                    manquantes.append(prealable.code)
    
            rec.prerequis_issue = ', '.join(manquantes) if manquantes else False
    
    @api.depends('note_quizz', 'note_intra', 'note_examen_final',
                 'groupe_fc_id.ponderation_quizz',
                 'groupe_fc_id.ponderation_intra',
                 'groupe_fc_id.ponderation_examen_final')
    def _compute_moyenne(self):
        for rec in self:
            g = rec.groupe_fc_id
            rec.moyenne = (
                rec.note_quizz * g.ponderation_quizz
                + rec.note_intra * g.ponderation_intra
                + rec.note_examen_final * g.ponderation_examen_final
            ) / 100.0

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
            if rec.groupe_fc_id.notes_verrouillees:
                raise ValidationError("Les notes sont verrouillées et ne peuvent plus être modifiées.")

    def write(self, vals):
        champs_notes = {'note_quizz', 'note_intra', 'note_examen_final'}
        if champs_notes & vals.keys():
            for rec in self:
                if rec.groupe_fc_id.notes_verrouillees:
                    raise ValidationError("Les notes sont verrouillées. Modification impossible.")
        return super().write(vals)

    @api.constrains('groupe_fc_id', 'etudiant_session_fc_id')
    def _check_coherence_session(self):
        for rec in self:
            if rec.groupe_fc_id.session_calendrier_fc_id != rec.etudiant_session_fc_id.session_calendrier_fc_id:
                raise ValidationError("L'étudiant n'est pas inscrit à la même session FC que ce groupe.")

    def _creer_ou_remplacer_tentative(self, etudiant, matiere, session_cal, prof, note_finale, est_reussie, remplacer=False):
        existante = self.env['de_inscae.tentative_matiere_etudiant'].search([
            ('etudiant_id', '=', etudiant.id),
            ('matiere_id', '=', matiere.id),
            ('session_calendrier_id', '=', session_cal.id),
        ], limit=1)
        if existante:
            if remplacer:
                existante.unlink()
            else:
                raise ValidationError(
                    f"Une tentative existe déjà pour '{matiere.intitule}' "
                    f"et l'étudiant '{etudiant.name}' dans cette session."
                )
        self.env['de_inscae.tentative_matiere_etudiant'].create({
            'etudiant_id': etudiant.id,
            'matiere_id': matiere.id,
            'session_calendrier_id': session_cal.id,
            'prof_id': prof.id if prof else False,
            'note_finale': note_finale,
            'est_reussie': est_reussie,
        })

    def _determiner_resultat(self, moyenne, detail):
        if moyenne >= detail.note_admission:
            return 'admis'
        elif moyenne >= detail.note_deliberation:
            return 'deliberation'
        return 'refuse'

    def _deliberer(self, est_reussie):
        self.ensure_one()
        if self.resultat != 'deliberation':
            raise ValidationError("Cette matière n'est pas en attente de délibération.")

        resultat = 'admis_ap_deliberation' if est_reussie else 'refuse'
        self.write({'resultat': resultat})

        inscription = self.etudiant_session_fc_id
        session_cal = inscription.session_calendrier_fc_id.session_calendrier_id
        etudiant = inscription.etudiant_fc_id.etudiant_id
        matiere = self.groupe_fc_id.matiere_dispo_session_fc_id.matiere_id

        self._creer_ou_remplacer_tentative(
            etudiant, matiere, session_cal,
            self.groupe_fc_id.prof_id, self.moyenne,
            est_reussie, remplacer=True,
        )
        inscription._finaliser_deliberation_si_complete()

    def action_admettre_apres_deliberation(self):
        self._deliberer(est_reussie=True)

    def action_refuser_apres_deliberation(self):
        self._deliberer(est_reussie=False)

    def action_retirer_du_groupe(self):
        self.ensure_one()
        self.unlink()


    @api.depends('groupe_fc_id', 'etudiant_session_fc_id')
    def _compute_conflit_edt(self):
        for rec in self:
            if not rec.groupe_fc_id or not rec.etudiant_session_fc_id:
                rec.conflit_edt = False
                continue

            plannings_groupe = rec.groupe_fc_id.groupe_id.planning_ids

            autres_groupes = rec.etudiant_session_fc_id.groupe_fc_ids.filtered(
                lambda g: g.id != rec.id
            ).mapped('groupe_fc_id.groupe_id')

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
