odoo.define('de_inscae.PlanningWidget', function (require) {
    'use strict';

    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');
    var rpc = require('web.rpc');
    var Dialog = require('web.Dialog');
    var QWeb = core.qweb;
    var _t = core._t;

    var JOURS = {
        '1': 'Lundi',
        '2': 'Mardi',
        '3': 'Mercredi',
        '4': 'Jeudi',
        '5': 'Vendredi',
        '6': 'Samedi',
    };

    var PlanningWidget = AbstractAction.extend({

        template: 'de_inscae.PlanningWidget',

        events: {
            'change .o_planning_groupe_select':  '_onGroupeChange',
            'change .o_planning_date_filter':    '_onDateChange',
            'click .o_planning_btn_layout':      '_onLayoutSwitch',
            'click .o_planning_btn_add':         '_onBtnAdd',
        },

        // ----------------------------------------------------------------
        // Init
        // ----------------------------------------------------------------
        init: function (parent, action) {
            this._super.apply(this, arguments);
            this.layout       = 'jours_colonnes'; // ou 'jours_lignes'
            this.groupeFilter = false;
            this.dateFilter   = false;
            this.tranches     = [];
            this.groupes      = [];
            this.cours        = [];
            this._draggedId   = null;
        },

        start: function () {
            var self = this;
            return this._super().then(function () {
                return self._loadReferentiels().then(function () {
                    self._populateGroupeSelect();
                    return self._loadCours().then(function () {
                        self._renderGrille();
                    });
                });
            });
        },

        _loadReferentiels: function () {
            var self = this;
            return Promise.all([
                rpc.query({
                    model: 'de_inscae.tranche_horaire',
                    method: 'search_read',
                    args: [[]],
                    kwargs: { fields: ['id', 'code', 'heure_debut', 'heure_fin'] }
                }),
                rpc.query({
                    model: 'de_inscae.groupe',
                    method: 'search_read',
                    args: [[]],
                    kwargs: { fields: ['id', 'nom'] }
                }),
            ]).then(function (results) {
                self.tranches = _.sortBy(results[0], 'heure_debut');
                self.groupes  = results[1];
            });
        },

        // ----------------------------------------------------------------
        // Chargement des cours (planning)
        // ----------------------------------------------------------------
        _loadCours: function () {
            var self = this;
            var domain = [];

            if (self.groupeFilter) {
                domain.push(['groupe_id', '=', self.groupeFilter]);
            }
            if (self.dateFilter) {
                domain.push(['date_debut', '<=', self.dateFilter]);
                domain.push(['date_fin',   '>=', self.dateFilter]);
            }

            self.$('.o_planning_loader').show();

            return rpc.query({
                model: 'de_inscae.planning',
                method: 'search_read',
                args: [domain],
                kwargs: {
                    fields: [
                        'id', 'jour_semaine', 'tranche_horaire_id',
                        'groupe_id', 'matiere_id', 'prof_id', 'salle_id',
                        'type_groupe', 'date_debut', 'date_fin',
                    ]
                }
            }).then(function (records) {
                self.cours = records;
                self.$('.o_planning_loader').hide();
            });
        },

        // ----------------------------------------------------------------
        // Populate select groupes
        // ----------------------------------------------------------------
        _populateGroupeSelect: function () {
            var $select = this.$('.o_planning_groupe_select');
            _.each(this.groupes, function (g) {
                $select.append('<option value="' + g.id + '">' + g.nom + '</option>');
            });
        },

        // ----------------------------------------------------------------
        // Rendu de la grille
        // ----------------------------------------------------------------
        _renderGrille: function () {
            if (this.layout === 'jours_colonnes') {
                this._renderJoursColonnes();
            } else {
                this._renderJoursLignes();
            }
            this._bindDragDrop();
        },

        // Layout : tranches en lignes, jours en colonnes
        _renderJoursColonnes: function () {
            var self   = this;
            var jours  = Object.keys(JOURS);
            var $thead = this.$('.o_planning_thead').empty();
            var $tbody = this.$('.o_planning_tbody').empty();

            // Header
            var $headRow = $('<tr>');
            $headRow.append('<th class="o_planning_th_header">Horaire</th>');
            _.each(jours, function (j) {
                $headRow.append('<th>' + JOURS[j] + '</th>');
            });
            $thead.append($headRow);

            // Lignes par tranche
            _.each(self.tranches, function (tranche) {
                var $row = $('<tr>');
                $row.append(
                    '<td class="o_planning_td_header">' +
                    tranche.code + '</td>'
                );
                _.each(jours, function (jour) {
                    var $td   = $('<td>');
                    var $cell = $('<div class="o_planning_cell">')
                        .attr('data-jour', jour)
                        .attr('data-tranche', tranche.id);
                    var coursCell = self._getCoursFor(jour, tranche.id);
                    _.each(coursCell, function (c) {
                        $cell.append(self._renderCours(c));
                    });
                    $td.append($cell);
                    $row.append($td);
                });
                $tbody.append($row);
            });
        },

        // Layout : jours en lignes, tranches en colonnes
        _renderJoursLignes: function () {
            var self   = this;
            var jours  = Object.keys(JOURS);
            var $thead = this.$('.o_planning_thead').empty();
            var $tbody = this.$('.o_planning_tbody').empty();

            // Header
            var $headRow = $('<tr>');
            $headRow.append('<th class="o_planning_th_header">Jour</th>');
            _.each(self.tranches, function (t) {
                $headRow.append('<th>' + t.code + '</th>');
            });
            $thead.append($headRow);

            // Lignes par jour
            _.each(jours, function (jour) {
                var $row = $('<tr>');
                $row.append(
                    '<td class="o_planning_td_header">' +
                    JOURS[jour] + '</td>'
                );
                _.each(self.tranches, function (tranche) {
                    var $td   = $('<td>');
                    var $cell = $('<div class="o_planning_cell">')
                        .attr('data-jour', jour)
                        .attr('data-tranche', tranche.id);
                    var coursCell = self._getCoursFor(jour, tranche.id);
                    _.each(coursCell, function (c) {
                        $cell.append(self._renderCours(c));
                    });
                    $td.append($cell);
                    $row.append($td);
                });
                $tbody.append($row);
            });
        },

        // Retourne les cours pour un jour + tranche donnés
        _getCoursFor: function (jour, trancheId) {
            return _.filter(this.cours, function (c) {
                return c.jour_semaine === jour &&
                       c.tranche_horaire_id[0] === trancheId;
            });
        },

        // Rendu d'un bloc cours
        _renderCours: function (cours) {
            var $div = $(QWeb.render('de_inscae.PlanningCours', { cours: cours }));
            var self = this;

            // Clic → ouvrir formulaire
            $div.on('click', function (e) {
                e.stopPropagation();
                self._openRecord(cours.id);
            });

            return $div;
        },

        // ----------------------------------------------------------------
        // Drag & Drop
        // ----------------------------------------------------------------
        _bindDragDrop: function () {
            var self = this;

            // Draggable : cours
            this.$('.o_planning_cours').on('dragstart', function (e) {
                self._draggedId = parseInt($(this).data('id'));
                $(this).addClass('dragging');
                e.originalEvent.dataTransfer.effectAllowed = 'move';
            });

            this.$('.o_planning_cours').on('dragend', function () {
                $(this).removeClass('dragging');
            });

            // Drop targets : cellules
            this.$('.o_planning_cell').on('dragover', function (e) {
                e.preventDefault();
                e.originalEvent.dataTransfer.dropEffect = 'move';
                $(this).addClass('o_planning_drag_over');
            });

            this.$('.o_planning_cell').on('dragleave', function () {
                $(this).removeClass('o_planning_drag_over');
            });

            this.$('.o_planning_cell').on('drop', function (e) {
                e.preventDefault();
                $(this).removeClass('o_planning_drag_over');

                var nouveauJour    = $(this).data('jour').toString();
                var nouveauTranche = $(this).data('tranche');

                if (self._draggedId) {
                    self._deplacerCours(self._draggedId, nouveauJour, nouveauTranche);
                }
                self._draggedId = null;
            });

            // Clic sur cellule vide → créer
            this.$('.o_planning_cell').on('click', function () {
                var jour    = $(this).data('jour').toString();
                var tranche = $(this).data('tranche');
                self._createRecord(jour, tranche);
            });
        },

        // ----------------------------------------------------------------
        // Actions CRUD
        // ----------------------------------------------------------------
        _openRecord: function (id) {
            this.do_action({
                type: 'ir.actions.act_window',
                res_model: 'de_inscae.planning',
                res_id: id,
                views: [[false, 'form']],
                target: 'new',
            });
        },

        _createRecord: function (jour, trancheId) {
            this.do_action({
                type: 'ir.actions.act_window',
                res_model: 'de_inscae.planning',
                views: [[false, 'form']],
                target: 'new',
                context: {
                    default_jour_semaine: jour,
                    default_tranche_horaire_id: trancheId,
                    default_groupe_id: this.groupeFilter || false,
                },
            });
        },

        _deplacerCours: function (id, nouveauJour, nouveauTrancheId) {
            var self = this;
            Dialog.confirm(this, _t("Déplacer ce cours vers ce créneau ?"), {
                confirm_callback: function () {
                    var promise = rpc.query({
                        model: 'de_inscae.planning',
                        method: 'write',
                        args: [[id], {
                            jour_semaine: nouveauJour,
                            tranche_horaire_id: nouveauTrancheId,
                        }],
                    });
                    
                    promise.then(function () {
                        return self._loadCours();
                    }).then(function () {
                        self._renderGrille();
                    });

                    promise.fail(function (err) {
                        var message = err.message && err.message.data && err.message.data.message
                            ? err.message.data.message
                            : "Une erreur est survenue lors du déplacement.";
                        self.do_warn('Conflit détecté', message);
                        self._renderGrille();
                    });
                }
            });
        },

        // ----------------------------------------------------------------
        // Event handlers
        // ----------------------------------------------------------------
        _onGroupeChange: function (e) {
            this.groupeFilter = parseInt($(e.target).val()) || false;
            this._loadCours().then(this._renderGrille.bind(this));
        },

        _onDateChange: function (e) {
            this.dateFilter = $(e.target).val() || false;
            this._loadCours().then(this._renderGrille.bind(this));
        },

        _onLayoutSwitch: function (e) {
            var $btn = $(e.currentTarget);
            this.$('.o_planning_btn_layout').removeClass('active');
            $btn.addClass('active');
            this.layout = $btn.data('layout');
            this._renderGrille();
        },

        _onBtnAdd: function () {
            this._createRecord(false, false);
        },

        // Rafraîchir après fermeture d'un dialog
        on_reverse_breadcrumb: function () {
            this._loadCours().then(this._renderGrille.bind(this));
        },
    });

    core.action_registry.add('de_inscae_planning', PlanningWidget);

    return PlanningWidget;
});
